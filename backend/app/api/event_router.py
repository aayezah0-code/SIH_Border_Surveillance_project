"""
Events, Sessions, Alerts, and CSV Export API Router
---------------------------------------------------
Provides query and export endpoints for surveillance data stored in SQLite.

Endpoints:
  GET /api/v1/events            — List detection events with filtering & pagination
  GET /api/v1/events/export/csv — Export surveillance events as downloadable CSV
  GET /api/v1/sessions          — List surveillance sessions
  GET /api/v1/sessions/{id}     — Get session details and statistics
  GET /api/v1/alerts            — Query threat alerts
  GET /api/v1/intrusions        — Query intrusion and loitering events
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.db_service import db_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Surveillance Events & Sessions"])


# ---------------------------------------------------------------------------
# GET /events
# ---------------------------------------------------------------------------

@router.get("/events")
def list_events(
    source_id: Optional[str] = Query(default=None, description="Filter by camera/source ID"),
    session_id: Optional[str] = Query(default=None, description="Filter by session ID"),
    event_type: Optional[str] = Query(default=None, description="Filter by event type"),
    threat_level: Optional[str] = Query(default=None, description="Filter by threat level (SAFE, LOW, MEDIUM, HIGH, CRITICAL)"),
    person_name: Optional[str] = Query(default=None, description="Filter by person name"),
    start_time: Optional[datetime] = Query(default=None, description="Filter start ISO timestamp"),
    end_time: Optional[datetime] = Query(default=None, description="Filter end ISO timestamp"),
    limit: int = Query(default=100, ge=1, le=1000, description="Max records to return"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    db: Session = Depends(get_db),
):
    """Retrieve filtered surveillance detection events."""
    records, total = db_service.get_events(
        db=db,
        source_id=source_id,
        session_id=session_id,
        event_type=event_type,
        threat_level=threat_level,
        person_name=person_name,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        offset=offset,
    )
    return {
        "count": len(records),
        "total": total,
        "offset": offset,
        "limit": limit,
        "events": records,
    }


# ---------------------------------------------------------------------------
# GET /events/export/csv
# ---------------------------------------------------------------------------

@router.get("/events/export/csv")
def export_events_csv(
    source_id: Optional[str] = Query(default=None),
    session_id: Optional[str] = Query(default=None),
    event_type: Optional[str] = Query(default=None),
    threat_level: Optional[str] = Query(default=None),
    limit: int = Query(default=5000, ge=1, le=50000),
    db: Session = Depends(get_db),
):
    """
    Download a formatted CSV file containing real persisted surveillance events.
    Includes headers: Event ID, Date, Time, Camera/Source, Session, Event Type,
    Detected Object, Track ID, Person Name, Person Status, Threat Level, Severity,
    Confidence, Evidence Reference, Status.
    """
    csv_data = db_service.generate_csv_events(
        db=db,
        source_id=source_id,
        session_id=session_id,
        event_type=event_type,
        threat_level=threat_level,
        limit=limit,
    )

    filename = f"sentinel_events_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache",
        },
    )


# ---------------------------------------------------------------------------
# GET /sessions
# ---------------------------------------------------------------------------

@router.get("/sessions")
def list_sessions(
    source_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """List surveillance sessions."""
    sessions, total = db_service.get_sessions(
        db=db,
        source_id=source_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return {
        "count": len(sessions),
        "total": total,
        "offset": offset,
        "limit": limit,
        "sessions": sessions,
    }


@router.get("/sessions/{session_id}")
def get_session(session_id: str, db: Session = Depends(get_db)):
    """Retrieve details for a specific surveillance session."""
    sess = db_service.get_session_by_id(db=db, session_id=session_id)
    if not sess:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Surveillance session '{session_id}' not found.",
        )
    return sess


# ---------------------------------------------------------------------------
# GET /alerts
# ---------------------------------------------------------------------------

@router.get("/alerts")
def list_alerts(
    source_id: Optional[str] = Query(default=None),
    threat_level: Optional[str] = Query(default=None),
    is_intrusion: Optional[bool] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Retrieve recorded threat alerts."""
    alerts, total = db_service.get_alerts(
        db=db,
        source_id=source_id,
        threat_level=threat_level,
        is_intrusion=is_intrusion,
        limit=limit,
        offset=offset,
    )
    return {
        "count": len(alerts),
        "total": total,
        "alerts": alerts,
    }


# ---------------------------------------------------------------------------
# GET /intrusions
# ---------------------------------------------------------------------------

@router.get("/intrusions")
def list_intrusions(
    source_id: Optional[str] = Query(default=None),
    event_type: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Retrieve recorded restricted-zone intrusions and loitering events."""
    intrusions, total = db_service.get_intrusions(
        db=db,
        source_id=source_id,
        event_type=event_type,
        limit=limit,
        offset=offset,
    )
    return {
        "count": len(intrusions),
        "total": total,
        "intrusions": intrusions,
    }
