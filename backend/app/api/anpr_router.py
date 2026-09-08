"""
ANPR API Router
----------------
Provides REST query and CSV export endpoints for Automatic Number Plate Recognition records.

Endpoints:
  GET  /api/v1/anpr/records          — Query recognized vehicle plate records with filters & pagination
  GET  /api/v1/anpr/records/{id}     — Retrieve specific ANPR record details
  GET  /api/v1/anpr/export/csv       — Download formatted CSV of persisted ANPR records
  POST /api/v1/anpr/watchlist        — Register plate on watchlist / BOLO list
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.db_service import db_service
from ai_engine.modules.recognition.anpr_worker import anpr_worker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/anpr", tags=["Automatic Number Plate Recognition (ANPR)"])


class WatchlistRequest(BaseModel):
    plate_number: str
    category: str = "Wanted"


# ---------------------------------------------------------------------------
# GET /records
# ---------------------------------------------------------------------------

@router.get("/records")
def list_anpr_records(
    source_id: Optional[str] = Query(default=None, description="Filter by camera/source ID"),
    plate_number: Optional[str] = Query(default=None, description="Search by plate number substring"),
    vehicle_class: Optional[str] = Query(default=None, description="Filter by vehicle class (CAR, TRUCK, BUS, MOTORCYCLE)"),
    is_watchlist_match: Optional[bool] = Query(default=None, description="Filter watchlist matches"),
    start_time: Optional[datetime] = Query(default=None, description="Start timestamp ISO"),
    end_time: Optional[datetime] = Query(default=None, description="End timestamp ISO"),
    limit: int = Query(default=100, ge=1, le=1000, description="Max records to return"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    db: Session = Depends(get_db),
):
    """Retrieve filtered ANPR records from the database."""
    records, total = db_service.get_anpr_records(
        db=db,
        source_id=source_id,
        plate_number=plate_number,
        vehicle_class=vehicle_class,
        is_watchlist_match=is_watchlist_match,
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
        "records": records,
    }


# ---------------------------------------------------------------------------
# GET /records/{anpr_id}
# ---------------------------------------------------------------------------

@router.get("/records/{anpr_id}")
def get_anpr_record(anpr_id: str, db: Session = Depends(get_db)):
    """Retrieve single ANPR record details by anpr_id."""
    rec = db_service.get_anpr_record_by_id(db=db, anpr_id=anpr_id)
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ANPR record '{anpr_id}' not found.",
        )
    return rec


# ---------------------------------------------------------------------------
# GET /export/csv
# ---------------------------------------------------------------------------

@router.get("/export/csv")
def export_anpr_csv(
    source_id: Optional[str] = Query(default=None),
    plate_number: Optional[str] = Query(default=None),
    vehicle_class: Optional[str] = Query(default=None),
    limit: int = Query(default=5000, ge=1, le=50000),
    db: Session = Depends(get_db),
):
    """
    Download a formatted CSV file containing real persisted ANPR records.
    """
    csv_data = db_service.generate_csv_anpr_records(
        db=db,
        source_id=source_id,
        plate_number=plate_number,
        vehicle_class=vehicle_class,
        limit=limit,
    )

    filename = f"sentinel_anpr_records_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache",
        },
    )


# ---------------------------------------------------------------------------
# POST /watchlist
# ---------------------------------------------------------------------------

@router.post("/watchlist", status_code=status.HTTP_201_CREATED)
def add_to_watchlist(req: WatchlistRequest):
    """Register a plate on the security watchlist."""
    anpr_worker.add_to_watchlist(req.plate_number, req.category)
    return {
        "status": "success",
        "message": f"Plate '{req.plate_number.upper()}' added to watchlist category '{req.category}'.",
    }
