"""
Video Ingestion Service
-----------------------
Manages the current video source state in memory.
Designed to be modular — future phases will extend this to:
  - RTSP/IP camera streams
  - Webcam/live feeds
  - Multiple concurrent cameras
"""

import os
from enum import Enum
from typing import Optional

from app.services.stream_manager import stream_manager

UPLOADS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "uploads")


class SourceType(str, Enum):
    FILE = "FILE"
    RTSP = "RTSP"
    WEBCAM = "WEBCAM"
    IP_CAMERA = "IP_CAMERA"


class SourceStatus(str, Enum):
    IDLE = "IDLE"
    CONNECTED = "CONNECTED"
    PLAYING = "PLAYING"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


class VideoSource:
    """Represents a single video source."""

    def __init__(
        self,
        source_id: str,
        source_type: SourceType,
        uri: str,
        name: str,
        original_name: str = "",
        stream_url: str = "",
    ):
        self.source_id = source_id
        self.source_type = source_type
        self.uri = uri               # file path, RTSP url, device index
        self.name = name             # internal / stored filename
        self.original_name = original_name  # original upload filename
        self.stream_url = stream_url        # URL the frontend uses to play the video
        self.status = SourceStatus.CONNECTED
        self.error_message: Optional[str] = None

    def to_dict(self):
        return {
            "source_id": self.source_id,
            "source_type": self.source_type,
            "uri": self.uri,
            "name": self.name,
            "original_name": self.original_name,
            "stream_url": self.stream_url,
            "status": self.status,
            "error_message": self.error_message,
        }


# ── In-memory registry (Phase 4 will persist this to the DB) ──
_sources: dict[str, VideoSource] = {}


def get_all_sources() -> list[dict]:
    # Ensure any video in UPLOADS_DIR is registered
    if os.path.exists(UPLOADS_DIR):
        for fname in os.listdir(UPLOADS_DIR):
            fpath = os.path.join(UPLOADS_DIR, fname)
            if os.path.isfile(fpath) and fname.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm', '.m4v')):
                stem = os.path.splitext(fname)[0]
                if stem not in _sources and fname not in _sources:
                    register_file_source(stem, fname, fname)
    return [s.to_dict() for s in _sources.values()]


def get_source(source_id: str) -> Optional[VideoSource]:
    if source_id in _sources:
        return _sources[source_id]
    # Check uploads directory
    if os.path.exists(UPLOADS_DIR):
        for ext in ["", ".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"]:
            fname = f"{source_id}{ext}" if not source_id.endswith(ext) or ext == "" else source_id
            fpath = os.path.join(UPLOADS_DIR, fname)
            if os.path.exists(fpath) and os.path.isfile(fpath):
                return register_file_source(source_id, fname, fname)
    return None


def register_file_source(
    source_id: str,
    filename: str,
    original_name: str = "",
) -> VideoSource:
    """Register a newly uploaded video file as a source."""
    uri = os.path.join(UPLOADS_DIR, filename)
    stream_url = f"/api/v1/video/stream/{filename}"
    source = VideoSource(
        source_id=source_id,
        source_type=SourceType.FILE,
        uri=uri,
        name=filename,
        original_name=original_name or filename,
        stream_url=stream_url,
    )
    source.status = SourceStatus.PLAYING
    _sources[source_id] = source
    return source


def remove_source(source_id: str) -> bool:
    if source_id in _sources:
        source = _sources[source_id]
        if source.source_type == SourceType.RTSP:
            stream_manager.remove_stream(source_id)
        del _sources[source_id]
        return True
    return False


def register_rtsp_source(
    source_id: str,
    rtsp_url: str,
    name: str,
    location: str = "",
) -> VideoSource:
    """Register a new RTSP camera source."""
    stream_url = f"/api/v1/video/mjpeg/{source_id}"
    source = VideoSource(
        source_id=source_id,
        source_type=SourceType.RTSP,
        uri=rtsp_url,
        name=name,
        original_name=location, # Using original_name field to store location/sector
        stream_url=stream_url,
    )
    source.status = SourceStatus.IDLE
    _sources[source_id] = source
    
    # Start the background stream capture
    stream_manager.add_stream(source_id, rtsp_url)
    
    return source


def set_source_status(
    source_id: str, status: SourceStatus, error: Optional[str] = None
):
    if source_id in _sources:
        _sources[source_id].status = status
        _sources[source_id].error_message = error
