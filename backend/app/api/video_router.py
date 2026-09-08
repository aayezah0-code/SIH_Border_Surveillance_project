"""
Video Ingestion API Router
--------------------------
Endpoints:
  POST   /api/v1/video/upload               — Upload a local video file
  GET    /api/v1/video/sources              — List all registered sources
  GET    /api/v1/video/sources/{id}         — Get status of a specific source
  PATCH  /api/v1/video/sources/{id}/status  — Update source status (PLAYING/STOPPED/etc.)
  DELETE /api/v1/video/sources/{id}         — Remove a source (leaves file on disk)
  GET    /api/v1/video/stream/{filename}    — Serve the video file (Range-request aware)
"""

import os
import re
import uuid
import mimetypes
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException, Request, status
from fastapi.responses import StreamingResponse, JSONResponse

from app.services.video_service import (
    register_file_source,
    register_rtsp_source,
    get_all_sources,
    get_source,
    remove_source,
    UPLOADS_DIR,
    SourceStatus,
    set_source_status,
)
from app.services.stream_manager import stream_manager
from pydantic import BaseModel
import time
import asyncio
from app.services.db_service import db_service

# Phase 6: clean up per-source tracker state on delete
import sys, os as _os
_AI_ENGINE_ROOT = _os.path.join(_os.path.dirname(__file__), '..', '..', '..', '..')
if str(_AI_ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, _AI_ENGINE_ROOT)
try:
    from ai_engine.modules.tracking.tracker_registry import tracker_registry as _tracker_registry
    _HAS_TRACKER = True
except Exception:
    _HAS_TRACKER = False

from app.api.detection_router import stop_rtsp_detection

router = APIRouter(prefix="/api/v1/video", tags=["Video Ingestion"])

# Allowed video MIME types and extensions
ALLOWED_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"}
ALLOWED_MIME_TYPES = {
    "video/mp4", "video/x-msvideo", "video/quicktime",
    "video/x-matroska", "video/webm", "video/x-m4v",
    "application/octet-stream",   # some browsers report this for .mkv/.avi
}
MAX_FILE_SIZE_MB = 500   # 500 MB limit
CHUNK_SIZE = 1024 * 1024  # 1 MB streaming chunks


def _ensure_uploads_dir():
    os.makedirs(UPLOADS_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# POST /upload
# ---------------------------------------------------------------------------

@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_video(file: UploadFile = File(...)):
    """
    Upload a local video file to use as a surveillance source.
    Returns the source_id to use when referencing this feed.
    """
    _ensure_uploads_dir()

    # --- Validation ---
    original_name = file.filename or "unknown"
    ext = Path(original_name).suffix.lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported file type '{ext}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            ),
        )

    # Secondary MIME-type check (browsers may report generic types for some formats)
    if file.content_type and file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported content type '{file.content_type}'.",
        )

    # --- Save file with unique name to prevent collisions ---
    source_id = str(uuid.uuid4())
    safe_filename = f"{source_id}{ext}"
    dest_path = os.path.join(UPLOADS_DIR, safe_filename)

    try:
        contents = await file.read()
        size_mb = len(contents) / (1024 * 1024)
        if size_mb > MAX_FILE_SIZE_MB:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large ({size_mb:.1f} MB). Max allowed: {MAX_FILE_SIZE_MB} MB.",
            )
        with open(dest_path, "wb") as f:
            f.write(contents)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {str(e)}",
        )

    # --- Register as a source ---
    source = register_file_source(
        source_id=source_id,
        filename=safe_filename,
        original_name=original_name,
    )

    # Persist camera source & start session
    try:
        db_service.record_camera_source(
            source_id=source.source_id,
            name=original_name,
            source_type="FILE",
            uri=source.uri,
            stream_url=source.stream_url,
            status="PLAYING",
        )
        db_service.start_session(
            source_id=source.source_id,
            camera_name=original_name,
            source_type="FILE",
        )
    except Exception as _dbe:
        pass

    return {
        "message": "Video uploaded and source registered successfully.",
        "source_id": source.source_id,
        "source_type": source.source_type,
        "filename": safe_filename,
        "original_name": original_name,
        "size_mb": round(size_mb, 2),
        "status": source.status,
        "stream_url": source.stream_url,
    }

# ---------------------------------------------------------------------------
# POST /sources/rtsp
# ---------------------------------------------------------------------------

class RTSPRequest(BaseModel):
    name: str
    location: str
    url: str
    source_id: str = ""  # Optional stable sector ID supplied by frontend

@router.post("/sources/rtsp", status_code=status.HTTP_201_CREATED)
async def add_rtsp_source(request: RTSPRequest):
    """
    Register an RTSP camera stream.
    If a source_id is provided by the client (e.g. a stable sector ID like 'sector_4_alpha'),
    it will be reused so reconnects cleanly replace the previous stream without leaking resources.
    """
    # basic validation
    if not request.url.startswith("rtsp://") and not request.url.startswith("http"):
        raise HTTPException(status_code=400, detail="Invalid RTSP URL")

    # Use client-supplied stable ID or generate a fresh UUID
    source_id = request.source_id.strip() if request.source_id else str(uuid.uuid4())

    # If this source_id is already registered, remove the old stream first for clean reconnect
    existing = get_source(source_id)
    if existing:
        await stop_rtsp_detection(source_id)
        remove_source(source_id)

    source = register_rtsp_source(
        source_id=source_id,
        rtsp_url=request.url,
        name=request.name,
        location=request.location,
    )
    
    # Wait until OpenCV successfully opens the stream and obtains an actual frame
    stream = stream_manager.get_stream(source_id)
    if stream:
        start_wait = time.time()
        while time.time() - start_wait < 15.0:
            if stream.error:
                remove_source(source_id)
                raise HTTPException(status_code=400, detail=stream.error)
            
            if stream.is_connected and stream.latest_jpeg is not None:
                # Stream is fully active and frames are ready for MJPEG endpoint
                break
                
            await asyncio.sleep(0.1)
            
        if not stream.is_connected or stream.latest_jpeg is None:
            remove_source(source_id)
            raise HTTPException(status_code=408, detail="Timeout waiting for RTSP camera connection or first frame")
    
    # Persist camera & start session
    try:
        db_service.record_camera_source(
            source_id=source.source_id,
            name=request.name or source.name,
            source_type="RTSP",
            location=request.location,
            uri=request.url,
            stream_url=source.stream_url,
            status="CONNECTED",
        )
        db_service.start_session(
            source_id=source.source_id,
            camera_name=request.name or source.name,
            source_type="RTSP",
        )
    except Exception as _dbe:
        pass

    # Auto-start real-time YOLO object detection & virtual fence monitoring for this RTSP stream
    try:
        from app.services.detection_service import get_detector
        get_detector(source_id)
    except Exception as exc:
        pass

    return {
        "message": "RTSP camera registered successfully.",
        "source_id": source.source_id,
        "source_type": source.source_type,
        "status": source.status,
        "stream_url": source.stream_url,
        "original_name": source.original_name,
    }


# ---------------------------------------------------------------------------
# GET /sources
# ---------------------------------------------------------------------------

@router.get("/sources")
def list_sources():
    """Return all currently registered video sources."""
    return {"sources": get_all_sources()}


# ---------------------------------------------------------------------------
# GET /sources/{source_id}
# ---------------------------------------------------------------------------

@router.get("/sources/{source_id}")
def get_source_status(source_id: str):
    """Get the status of a specific video source."""
    source = get_source(source_id)
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source '{source_id}' not found.",
        )
    return source.to_dict()


# ---------------------------------------------------------------------------
# PATCH /sources/{source_id}/status
# ---------------------------------------------------------------------------

@router.patch("/sources/{source_id}/status")
async def update_source_status(source_id: str, request: Request):
    """
    Update the playback status of a registered source.
    Body: { "status": "PLAYING" | "STOPPED" | "ERROR" | "CONNECTED" }
    """
    source = get_source(source_id)
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source '{source_id}' not found.",
        )

    try:
        body = await request.json()
        new_status_str = body.get("status", "").upper()
        new_status = SourceStatus(new_status_str)
    except (ValueError, KeyError):
        valid = [s.value for s in SourceStatus]
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid status. Must be one of: {valid}",
        )

    error_msg = body.get("error_message")
    set_source_status(source_id, new_status, error_msg)

    # Update camera status in DB
    try:
        db_service.record_camera_source(
            source_id=source_id,
            name=source.name,
            source_type=source.source_type,
            status=new_status.value,
        )
    except Exception:
        pass

    updated = get_source(source_id)
    return updated.to_dict()


# ---------------------------------------------------------------------------
# DELETE /sources/{source_id}
# ---------------------------------------------------------------------------

@router.delete("/sources/{source_id}", status_code=status.HTTP_200_OK)
async def delete_source(source_id: str):
    """Remove a video source from the registry (does NOT delete the file)."""
    await stop_rtsp_detection(source_id)
    
    # End session in DB
    try:
        db_service.end_session(source_id, status="TERMINATED")
    except Exception:
        pass

    removed = remove_source(source_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source '{source_id}' not found.",
        )
    # Phase 6: clean up per-source ByteTrack state
    if _HAS_TRACKER:
        _tracker_registry.remove_source(source_id)
    return {"message": f"Source '{source_id}' removed."}

# ---------------------------------------------------------------------------
# GET /mjpeg/{source_id}  — Live RTSP to MJPEG proxy
# ---------------------------------------------------------------------------

@router.get("/mjpeg/{source_id}")
def mjpeg_stream(source_id: str):
    """
    Serve live MJPEG stream for an RTSP camera.
    """
    source = get_source(source_id)
    if not source or source.source_type != "RTSP":
        raise HTTPException(status_code=404, detail="RTSP source not found")
        
    stream = stream_manager.get_stream(source_id)
    if not stream:
        raise HTTPException(status_code=404, detail="Stream is not active")
        
    async def generate_frames():
        while True:
            if stream.error:
                break
                
            jpeg = stream.get_latest_jpeg()
            if jpeg:
                yield (
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n'
                    b'Content-Length: ' + str(len(jpeg)).encode() + b'\r\n\r\n' + 
                    jpeg + b'\r\n'
                )
            await asyncio.sleep(0.05) # ~20fps max

    return StreamingResponse(
        generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


# ---------------------------------------------------------------------------
# GET /stream/{filename}  — Range-aware video streaming
# ---------------------------------------------------------------------------

def _range_streaming_response(file_path: str, media_type: str, request: Request):
    """
    Returns a StreamingResponse that honours the HTTP Range header.
    This lets the browser <video> element seek freely in the uploaded file.
    """
    file_size = os.path.getsize(file_path)
    range_header = request.headers.get("range")

    start = 0
    end = file_size - 1

    if range_header:
        # Parse "bytes=start-end"
        match = re.match(r"bytes=(\d+)-(\d*)", range_header)
        if match:
            start = int(match.group(1))
            end = int(match.group(2)) if match.group(2) else file_size - 1

    end = min(end, file_size - 1)
    content_length = end - start + 1

    def iterfile():
        with open(file_path, "rb") as f:
            f.seek(start)
            remaining = content_length
            while remaining > 0:
                chunk_size = min(CHUNK_SIZE, remaining)
                data = f.read(chunk_size)
                if not data:
                    break
                remaining -= len(data)
                yield data

    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(content_length),
        "Content-Type": media_type,
    }

    status_code = 206 if range_header else 200
    return StreamingResponse(
        iterfile(),
        status_code=status_code,
        headers=headers,
        media_type=media_type,
    )


@router.get("/stream/{filename}")
def stream_video(filename: str, request: Request):
    """
    Serve a previously uploaded video file with full Range-request support.
    Required so that the browser <video> seek bar works correctly.
    """
    # Security: reject any path-traversal attempts
    safe_filename = Path(filename).name
    if safe_filename != filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename.",
        )

    file_path = os.path.join(UPLOADS_DIR, safe_filename)
    if not os.path.isfile(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video file not found on server.",
        )

    media_type, _ = mimetypes.guess_type(file_path)
    media_type = media_type or "video/mp4"

    return _range_streaming_response(file_path, media_type, request)
