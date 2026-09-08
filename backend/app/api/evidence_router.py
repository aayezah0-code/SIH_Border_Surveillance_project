"""
Evidence API Router
-------------------
Endpoints:
  GET  /api/v1/evidence                   — List evidence records (filter by source_id, track_id, event_type).
  GET  /api/v1/evidence/image/{filename}  — Serve a saved evidence JPEG.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse

from app.services.evidence_writer import evidence_writer, EVIDENCE_DIR

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/evidence", tags=["Evidence Capture"])


# ---------------------------------------------------------------------------
# GET /api/v1/evidence
# ---------------------------------------------------------------------------

@router.get("")
def list_evidence(
    source_id: Optional[str] = Query(default=None, description="Filter by camera/source UUID"),
    track_id: Optional[int]  = Query(default=None, description="Filter by ByteTrack track ID"),
    event_type: Optional[str] = Query(default=None, description="Filter by event type"),
    limit: int = Query(default=100, ge=1, le=500, description="Max records to return"),
):
    """
    Return a list of evidence snapshot records.
    Each record contains metadata and a URL to retrieve the actual image.

    source_id matching is prefix-tolerant — pass the raw UUID even if
    the backend truncated it in the filename.
    """
    records = evidence_writer.get_evidence_list(
        source_id=source_id,
        track_id=track_id,
        event_type=event_type,
        limit=limit,
    )
    return {
        "count": len(records),
        "total": evidence_writer.get_evidence_count(),
        "evidence": records,
    }


# ---------------------------------------------------------------------------
# GET /api/v1/evidence/image/{filename}
# ---------------------------------------------------------------------------

@router.get("/image/{filename}")
def get_evidence_image(filename: str):
    """
    Serve a saved evidence JPEG by filename.
    Validates that the file exists in the evidence directory (path traversal safe).
    """
    # Prevent path traversal: ensure only the basename is used
    safe_name = Path(filename).name
    filepath = EVIDENCE_DIR / safe_name

    if not filepath.exists() or not filepath.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence file '{safe_name}' not found.",
        )

    return FileResponse(
        path=str(filepath),
        media_type="image/jpeg",
        filename=safe_name,
        headers={"Cache-Control": "public, max-age=3600"},
    )
