"""
Database Service
----------------
Provides a non-blocking asynchronous persistence layer for Sentinel AI.

Design & Guarantees:
  - Background daemon thread drains a bounded queue (maxsize=1000).
  - Calling threads (YOLO detection, ByteTrack, WebSocket broadcaster, etc.)
    enqueue items in < 0.05ms with zero blocking.
  - If the database is busy or encounters an error, the exception is caught
    and logged; the surveillance pipeline is NEVER blocked or crashed.
  - WAL mode and connection pooling in SQLite allow concurrent readers (APIs)
    and single writer (DB worker) without database locks.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import queue
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.db.database import SessionLocal, get_db_context, init_db
from app.db.models import (
    CameraSourceModel,
    SurveillanceSessionModel,
    DetectionEventModel,
    ThreatAlertModel,
    IntrusionEventModel,
    EvidenceSnapshotModel,
    PersonnelModel,
    PersonnelImageModel,
    VehicleANPRModel,
)

logger = logging.getLogger(__name__)


@dataclass
class DBTask:
    action: str
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)


class DatabaseService:
    """
    Singleton database persistence service with asynchronous background queue worker.
    """

    _MAX_QUEUE_SIZE = 1000

    def __init__(self):
        self._queue: queue.Queue[Optional[DBTask]] = queue.Queue(maxsize=self._MAX_QUEUE_SIZE)
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        
        # Track active session IDs per source: { source_id: session_id }
        self._active_sessions: Dict[str, str] = {}

        # Auto-init tables on startup
        init_db()

        # Start worker thread
        self.start()

    def start(self):
        """Start the background persistence worker thread."""
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._stop_event.clear()
                self._thread = threading.Thread(
                    target=self._worker_loop,
                    name="db-persistence-worker",
                    daemon=True,
                )
                self._thread.start()
                logger.info("[DatabaseService] Background persistence worker started.")

    def stop(self):
        """Signal background worker to stop gracefully."""
        self._stop_event.set()
        try:
            self._queue.put_nowait(None)
        except Exception:
            pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            logger.info("[DatabaseService] Background persistence worker stopped.")

    # ── Non-blocking Public Ingestion APIs ─────────────────────────────────────

    def record_camera_source(
        self,
        source_id: str,
        name: str,
        source_type: str = "RTSP",
        location: Optional[str] = None,
        uri: Optional[str] = None,
        stream_url: Optional[str] = None,
        status: str = "CONNECTED",
    ) -> None:
        """Register or update a camera source in the database."""
        self._enqueue(
            "upsert_camera",
            {
                "source_id": source_id,
                "name": name,
                "location": location,
                "source_type": source_type,
                "uri": uri,
                "stream_url": stream_url,
                "status": status,
            },
        )

    def start_session(
        self,
        source_id: str,
        camera_name: Optional[str] = None,
        source_type: str = "RTSP",
        session_id: Optional[str] = None,
    ) -> str:
        """Create a new surveillance session record."""
        sid = session_id or f"sess_{uuid.uuid4().hex[:12]}"
        with self._lock:
            self._active_sessions[source_id] = sid

        self._enqueue(
            "start_session",
            {
                "session_id": sid,
                "source_id": source_id,
                "camera_name": camera_name,
                "source_type": source_type,
                "start_time": datetime.utcnow(),
                "status": "ACTIVE",
            },
        )
        return sid

    def get_active_session_id(self, source_id: str) -> Optional[str]:
        """Return the current active session ID for the given source."""
        with self._lock:
            return self._active_sessions.get(source_id)

    def end_session(
        self,
        source_id: str,
        status: str = "COMPLETED",
        error: Optional[str] = None,
    ) -> None:
        """End the active surveillance session for a source."""
        with self._lock:
            sid = self._active_sessions.pop(source_id, None)

        if sid:
            self._enqueue(
                "end_session",
                {
                    "session_id": sid,
                    "end_time": datetime.utcnow(),
                    "status": status,
                    "connection_error": error,
                },
            )

    def enqueue_detection_event(
        self,
        source_id: str,
        event_type: str,
        object_class: str = "PERSON",
        track_id: Optional[int] = None,
        confidence: Optional[float] = None,
        timestamp_sec: float = 0.0,
        person_name: Optional[str] = None,
        person_role: Optional[str] = None,
        person_status: Optional[str] = None,
        threat_level: str = "LOW",
        severity: str = "Info",
        description: Optional[str] = None,
        evidence_ref: Optional[str] = None,
        bbox: Optional[Tuple[float, float, float, float]] = None,
        session_id: Optional[str] = None,
        extra_metadata: Optional[dict] = None,
    ) -> str:
        """
        Non-blocking enqueue of a detection event.
        Guarantees KNOWN_PERSON is recorded with threat_level='SAFE'.
        """
        event_id = f"evt_{uuid.uuid4().hex[:12]}"
        sess_id = session_id or self.get_active_session_id(source_id)

        # Semantics safety: Ensure KNOWN_PERSON is marked as SAFE
        if person_status == "KNOWN_PERSON" or (person_name and person_name != "Unknown Person" and threat_level not in ("CRITICAL", "HIGH")):
            threat_level = "SAFE"
            severity = "Safe"

        data = {
            "event_id": event_id,
            "source_id": source_id,
            "session_id": sess_id,
            "timestamp": datetime.utcnow(),
            "timestamp_sec": timestamp_sec,
            "event_type": event_type,
            "object_class": object_class.upper() if object_class else "PERSON",
            "track_id": track_id,
            "confidence": round(confidence, 4) if confidence is not None else None,
            "person_name": person_name,
            "person_role": person_role,
            "person_status": person_status,
            "threat_level": threat_level.upper(),
            "severity": severity,
            "description": description,
            "evidence_ref": evidence_ref,
            "bbox_x1": bbox[0] if bbox else None,
            "bbox_y1": bbox[1] if bbox else None,
            "bbox_x2": bbox[2] if bbox else None,
            "bbox_y2": bbox[3] if bbox else None,
            "extra_metadata": json.dumps(extra_metadata) if extra_metadata else None,
            "status": "Logged",
        }
        self._enqueue("insert_detection_event", data)
        return event_id

    def enqueue_threat_alert(
        self,
        source_id: str,
        alert_type: str,
        threat_level: str = "HIGH",
        severity: str = "Critical",
        track_id: Optional[int] = None,
        object_class: str = "PERSON",
        person_name: Optional[str] = None,
        confidence: Optional[float] = None,
        is_intrusion: bool = False,
        event_type: Optional[str] = None,
        camera_label: Optional[str] = None,
        description: Optional[str] = None,
        evidence_ref: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """Non-blocking enqueue of a threat alert."""
        alert_id = f"alt_{uuid.uuid4().hex[:12]}"
        sess_id = session_id or self.get_active_session_id(source_id)

        conf_pct = int(round(confidence * 100)) if confidence is not None and confidence <= 1.0 else (int(confidence) if confidence is not None else None)

        data = {
            "alert_id": alert_id,
            "source_id": source_id,
            "session_id": sess_id,
            "timestamp": datetime.utcnow(),
            "alert_type": alert_type,
            "severity": severity,
            "threat_level": threat_level.upper(),
            "track_id": track_id,
            "object_class": object_class.upper() if object_class else "PERSON",
            "person_name": person_name,
            "confidence": round(confidence, 4) if confidence is not None else None,
            "confidence_pct": conf_pct,
            "is_intrusion": is_intrusion,
            "event_type": event_type,
            "camera_label": camera_label,
            "description": description,
            "evidence_ref": evidence_ref,
        }
        self._enqueue("insert_threat_alert", data)
        return alert_id

    def enqueue_intrusion_event(
        self,
        source_id: str,
        event_type: str,  # zone_intrusion, line_crossing, loitering
        track_id: Optional[int] = None,
        object_class: str = "PERSON",
        person_name: Optional[str] = None,
        person_status: str = "UNKNOWN_PERSON",
        duration_sec: Optional[float] = None,
        threshold_sec: Optional[float] = None,
        severity: str = "Critical",
        description: Optional[str] = None,
        evidence_ref: Optional[str] = None,
        timestamp_sec: float = 0.0,
        session_id: Optional[str] = None,
    ) -> str:
        """Non-blocking enqueue of an intrusion or loitering event."""
        intrusion_id = f"int_{uuid.uuid4().hex[:12]}"
        sess_id = session_id or self.get_active_session_id(source_id)

        data = {
            "intrusion_id": intrusion_id,
            "source_id": source_id,
            "session_id": sess_id,
            "timestamp": datetime.utcnow(),
            "timestamp_sec": timestamp_sec,
            "event_type": event_type,
            "track_id": track_id,
            "object_class": object_class.upper() if object_class else "PERSON",
            "person_name": person_name,
            "person_status": person_status,
            "duration_sec": duration_sec,
            "threshold_sec": threshold_sec,
            "severity": severity,
            "description": description,
            "evidence_ref": evidence_ref,
        }
        self._enqueue("insert_intrusion_event", data)
        return intrusion_id

    def enqueue_evidence_snapshot(
        self,
        filename: str,
        filepath: str,
        url: str,
        source_id: str,
        event_type: Optional[str] = None,
        track_id: Optional[int] = None,
        object_class: Optional[str] = None,
        confidence: Optional[float] = None,
        timestamp_sec: float = 0.0,
        event_id: Optional[str] = None,
    ) -> str:
        """Non-blocking enqueue of an evidence image record."""
        evidence_id = f"evi_{uuid.uuid4().hex[:12]}"
        data = {
            "evidence_id": evidence_id,
            "event_id": event_id,
            "source_id": source_id,
            "timestamp": datetime.utcnow(),
            "timestamp_sec": timestamp_sec,
            "filename": filename,
            "filepath": filepath,
            "url": url,
            "event_type": event_type,
            "track_id": track_id,
            "object_class": object_class.upper() if object_class else None,
            "confidence": round(confidence, 4) if confidence is not None else None,
        }
        self._enqueue("insert_evidence_snapshot", data)
        return evidence_id

    def enqueue_anpr_record(
        self,
        source_id: str,
        plate_number: str,
        ocr_confidence: float,
        plate_confidence: Optional[float] = None,
        vehicle_class: str = "CAR",
        track_id: Optional[int] = None,
        timestamp_sec: float = 0.0,
        session_id: Optional[str] = None,
        is_watchlist_match: bool = False,
        watchlist_category: Optional[str] = None,
        evidence_ref: Optional[str] = None,
    ) -> str:
        """Non-blocking enqueue of an ANPR license plate recognition record."""
        anpr_id = f"anpr_{uuid.uuid4().hex[:12]}"
        sess_id = session_id or self.get_active_session_id(source_id)

        data = {
            "anpr_id": anpr_id,
            "source_id": source_id,
            "session_id": sess_id,
            "timestamp": datetime.utcnow(),
            "timestamp_sec": timestamp_sec,
            "track_id": track_id,
            "vehicle_class": vehicle_class.upper() if vehicle_class else "CAR",
            "plate_number": plate_number.upper(),
            "ocr_confidence": round(ocr_confidence, 4),
            "plate_confidence": round(plate_confidence, 4) if plate_confidence is not None else None,
            "is_watchlist_match": is_watchlist_match,
            "watchlist_category": watchlist_category,
            "evidence_ref": evidence_ref,
            "status": "Recognized",
        }
        self._enqueue("insert_anpr_record", data)
        return anpr_id

    def enqueue_suspicious_activity(
        self,
        source_id: Optional[str] = None,
        activity: Optional[str] = None,
        track_id: Optional[int] = None,
        timestamp_sec: Optional[float] = None,
        confidence: float = 1.0,
        object_track_id: Optional[int] = None,
        frame_index: int = 0,
        metadata: Optional[dict] = None,
        score: float = 1.0,
        threat_level: Optional[str] = None,
        severity: Optional[str] = None,
        camera_label: Optional[str] = None,
        description: Optional[str] = None,
        bbox: Optional[Tuple[float, float, float, float]] = None,
        session_id: Optional[str] = None,
        event: Optional[Any] = None,
    ) -> Optional[Tuple[str, str]]:
        """
        Non-blocking enqueue of a confirmed suspicious activity event into the
        existing ThreatAlertModel (threat_alerts table) and DetectionEventModel
        (detection_events table / Event Audit Log).

        Returns client-side (alert_id, event_id) immediately without waiting
        for database write operations.
        """
        try:
            # If a SuspiciousActivityEvent instance was passed directly
            if event is not None:
                source_id = getattr(event, "source_id", source_id)
                activity = getattr(event, "activity", activity)
                track_id = getattr(event, "track_id", track_id)
                timestamp_sec = getattr(event, "timestamp_sec", timestamp_sec)
                confidence = getattr(event, "confidence", confidence)
                object_track_id = getattr(event, "object_track_id", object_track_id)
                frame_index = getattr(event, "frame_index", frame_index)
                metadata = getattr(event, "metadata", metadata)
                score = getattr(event, "score", score)

            if not source_id or not activity or track_id is None:
                logger.warning(
                    "[DatabaseService] Invalid suspicious activity event payload (source_id=%s, activity=%s, track_id=%s)",
                    source_id, activity, track_id
                )
                return None

            act_upper = str(activity).upper()
            t_sec = float(timestamp_sec) if timestamp_sec is not None else 0.0

            # Severity mapping aligned with application security conventions
            if threat_level is None or severity is None:
                if act_upper in ("THROWING", "CRAWLING"):
                    derived_threat_level = "CRITICAL"
                    derived_severity = "Critical"
                else:
                    derived_threat_level = "HIGH"
                    derived_severity = "High"
                threat_level = threat_level or derived_threat_level
                severity = severity or derived_severity

            alert_title = f"SUSPICIOUS ACTIVITY — {act_upper}"
            event_type_name = "SUSPICIOUS_ACTIVITY"
            cam_label = camera_label or str(source_id).replace('_', ' ').title()

            if not description:
                if object_track_id is not None:
                    desc = f"Suspicious activity ({act_upper}) confirmed for PERSON #{track_id} throwing OBJECT #{object_track_id} at {t_sec:.1f}s."
                else:
                    desc = f"Suspicious activity ({act_upper}) confirmed for PERSON #{track_id} at {t_sec:.1f}s."
            else:
                desc = description

            # 1. Enqueue Threat Alert
            alert_id = self.enqueue_threat_alert(
                source_id=source_id,
                alert_type=alert_title,
                threat_level=threat_level,
                severity=severity,
                track_id=track_id,
                object_class="PERSON",
                confidence=confidence,
                is_intrusion=False,
                event_type=event_type_name,
                camera_label=cam_label,
                description=desc,
                session_id=session_id,
            )

            # 2. Enqueue Detection Event (Event Audit Log) with telemetry metadata
            extra_meta = {
                "activity_subtype": act_upper,
                "object_track_id": object_track_id,
                "frame_index": frame_index,
                "score": round(score, 4),
                "telemetry": dict(metadata) if metadata else {},
            }
            event_id = self.enqueue_detection_event(
                source_id=source_id,
                event_type=event_type_name,
                object_class="PERSON",
                track_id=track_id,
                confidence=confidence,
                timestamp_sec=t_sec,
                threat_level=threat_level,
                severity=severity,
                description=desc,
                bbox=bbox,
                session_id=session_id,
                extra_metadata=extra_meta,
            )

            return alert_id, event_id

        except Exception as exc:
            logger.error("[DatabaseService] Error enqueuing suspicious activity: %s", exc, exc_info=True)
            return None

    def _enqueue(self, action: str, data: Dict[str, Any]):
        """Helper to enqueue a task without blocking the calling thread."""
        task = DBTask(action=action, data=data)
        try:
            self._queue.put_nowait(task)
        except queue.Full:
            logger.warning("[DatabaseService] Queue full (%d items); dropping task: %s", self._MAX_QUEUE_SIZE, action)
        except Exception as exc:
            logger.error("[DatabaseService] Failed to enqueue task: %s", exc)

    # ── Background Worker Loop ─────────────────────────────────────────────────

    def _worker_loop(self):
        """Worker thread processing tasks sequentially with SQLite."""
        while not self._stop_event.is_set():
            try:
                task = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if task is None:
                break

            try:
                self._process_task(task)
            except Exception as exc:
                logger.error("[DatabaseService] Error executing DB task '%s': %s", task.action, exc, exc_info=True)
            finally:
                self._queue.task_done()

    def _process_task(self, task: DBTask):
        """Execute a single database mutation."""
        action = task.action
        data = task.data

        with get_db_context() as db:
            if action == "upsert_camera":
                source_id = data["source_id"]
                cam = db.query(CameraSourceModel).filter_by(source_id=source_id).first()
                if not cam:
                    cam = CameraSourceModel(**data)
                    db.add(cam)
                else:
                    for k, v in data.items():
                        if v is not None:
                            setattr(cam, k, v)
                    cam.updated_at = datetime.utcnow()

            elif action == "start_session":
                # Ensure camera exists
                cam = db.query(CameraSourceModel).filter_by(source_id=data["source_id"]).first()
                if not cam:
                    cam = CameraSourceModel(
                        source_id=data["source_id"],
                        name=data.get("camera_name") or data["source_id"],
                        source_type=data.get("source_type", "RTSP"),
                        status="CONNECTED",
                    )
                    db.add(cam)
                    db.flush()

                sess = SurveillanceSessionModel(**data)
                db.add(sess)

            elif action == "end_session":
                sess = db.query(SurveillanceSessionModel).filter_by(session_id=data["session_id"]).first()
                if sess:
                    sess.end_time = data.get("end_time") or datetime.utcnow()
                    sess.status = data.get("status", "COMPLETED")
                    if data.get("connection_error"):
                        sess.connection_error = data["connection_error"]

            elif action == "insert_detection_event":
                evt = DetectionEventModel(**data)
                db.add(evt)
                # Increment total events count for active session if present
                if data.get("session_id"):
                    sess = db.query(SurveillanceSessionModel).filter_by(session_id=data["session_id"]).first()
                    if sess:
                        sess.total_events = (sess.total_events or 0) + 1

            elif action == "insert_threat_alert":
                alt = ThreatAlertModel(**data)
                db.add(alt)

            elif action == "insert_intrusion_event":
                intr = IntrusionEventModel(**data)
                db.add(intr)

            elif action == "insert_evidence_snapshot":
                evi = EvidenceSnapshotModel(**data)
                db.add(evi)

            elif action == "insert_anpr_record":
                anpr_rec = VehicleANPRModel(**data)
                db.add(anpr_rec)


    # ── Synchronous Query Methods for APIs ─────────────────────────────────────

    def get_events(
        self,
        db: Session,
        source_id: Optional[str] = None,
        session_id: Optional[str] = None,
        event_type: Optional[str] = None,
        threat_level: Optional[str] = None,
        person_name: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query detection events with filtering and pagination."""
        query = db.query(DetectionEventModel)

        if source_id:
            query = query.filter(DetectionEventModel.source_id.like(f"{source_id}%"))
        if session_id:
            query = query.filter(DetectionEventModel.session_id == session_id)
        if event_type:
            query = query.filter(DetectionEventModel.event_type.ilike(f"%{event_type}%"))
        if threat_level:
            query = query.filter(DetectionEventModel.threat_level == threat_level.upper())
        if person_name:
            query = query.filter(DetectionEventModel.person_name.ilike(f"%{person_name}%"))
        if start_time:
            query = query.filter(DetectionEventModel.timestamp >= start_time)
        if end_time:
            query = query.filter(DetectionEventModel.timestamp <= end_time)

        total = query.count()
        records = query.order_by(desc(DetectionEventModel.timestamp)).offset(offset).limit(limit).all()
        return [r.to_dict() for r in records], total

    def get_sessions(
        self,
        db: Session,
        source_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query surveillance sessions."""
        query = db.query(SurveillanceSessionModel)
        if source_id:
            query = query.filter(SurveillanceSessionModel.source_id.like(f"{source_id}%"))
        if status:
            query = query.filter(SurveillanceSessionModel.status == status.upper())

        total = query.count()
        records = query.order_by(desc(SurveillanceSessionModel.start_time)).offset(offset).limit(limit).all()
        return [r.to_dict() for r in records], total

    def get_session_by_id(self, db: Session, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session details by ID."""
        sess = db.query(SurveillanceSessionModel).filter_by(session_id=session_id).first()
        return sess.to_dict() if sess else None

    def get_alerts(
        self,
        db: Session,
        source_id: Optional[str] = None,
        threat_level: Optional[str] = None,
        is_intrusion: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query threat alerts."""
        query = db.query(ThreatAlertModel)
        if source_id:
            query = query.filter(ThreatAlertModel.source_id.like(f"{source_id}%"))
        if threat_level:
            query = query.filter(ThreatAlertModel.threat_level == threat_level.upper())
        if is_intrusion is not None:
            query = query.filter(ThreatAlertModel.is_intrusion == is_intrusion)

        total = query.count()
        records = query.order_by(desc(ThreatAlertModel.timestamp)).offset(offset).limit(limit).all()
        return [r.to_dict() for r in records], total

    def get_intrusions(
        self,
        db: Session,
        source_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query intrusion and loitering events."""
        query = db.query(IntrusionEventModel)
        if source_id:
            query = query.filter(IntrusionEventModel.source_id.like(f"{source_id}%"))
        if event_type:
            query = query.filter(IntrusionEventModel.event_type == event_type)

        total = query.count()
        records = query.order_by(desc(IntrusionEventModel.timestamp)).offset(offset).limit(limit).all()
        return [r.to_dict() for r in records], total

    def get_evidence(
        self,
        db: Session,
        source_id: Optional[str] = None,
        track_id: Optional[int] = None,
        event_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query evidence snapshot records from database."""
        query = db.query(EvidenceSnapshotModel)
        if source_id:
            clean = source_id.split('.')[0]
            query = query.filter(EvidenceSnapshotModel.source_id.like(f"{clean}%"))
        if track_id is not None:
            query = query.filter(EvidenceSnapshotModel.track_id == track_id)
        if event_type:
            query = query.filter(EvidenceSnapshotModel.event_type == event_type)

        total = query.count()
        records = query.order_by(desc(EvidenceSnapshotModel.timestamp)).offset(offset).limit(limit).all()
        return [r.to_dict() for r in records], total

    def generate_csv_events(
        self,
        db: Session,
        source_id: Optional[str] = None,
        session_id: Optional[str] = None,
        event_type: Optional[str] = None,
        threat_level: Optional[str] = None,
        limit: int = 5000,
    ) -> str:
        """
        Generate complete CSV string from actual persisted detection events.
        Includes all required columns with proper escaping.
        """
        events, _ = self.get_events(
            db=db,
            source_id=source_id,
            session_id=session_id,
            event_type=event_type,
            threat_level=threat_level,
            limit=limit,
            offset=0,
        )

        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

        # Required columns
        headers = [
            "Event ID",
            "Date",
            "Time",
            "Camera / Source",
            "Session",
            "Event Type",
            "Detected Object",
            "Track ID",
            "Person Name",
            "Person Status",
            "Threat Level",
            "Severity",
            "Confidence",
            "Evidence Reference",
            "Status",
        ]
        writer.writerow(headers)

        for ev in events:
            # Parse date and time from timestamp
            ts_str = ev.get("timestamp") or ""
            date_part = ""
            time_part = ""
            if ts_str:
                try:
                    dt = datetime.fromisoformat(ts_str)
                    date_part = dt.strftime("%Y-%m-%d")
                    time_part = dt.strftime("%H:%M:%S")
                except Exception:
                    parts = ts_str.split("T")
                    date_part = parts[0]
                    time_part = parts[1][:8] if len(parts) > 1 else ""

            conf_str = f"{round(ev.get('confidence', 0) * 100)}%" if ev.get("confidence") is not None else "N/A"

            row = [
                ev.get("event_id", ""),
                date_part,
                time_part,
                ev.get("source_id", ""),
                ev.get("session_id", "") or "N/A",
                ev.get("event_type", ""),
                ev.get("object_class", ""),
                str(ev.get("track_id")) if ev.get("track_id") is not None else "N/A",
                ev.get("person_name") or "N/A",
                ev.get("person_status") or "N/A",
                ev.get("threat_level", "LOW"),
                ev.get("severity", "Info"),
                conf_str,
                ev.get("evidence_ref") or "N/A",
                ev.get("status", "Logged"),
            ]
            writer.writerow(row)

        return output.getvalue()

    def get_anpr_records(
        self,
        db: Session,
        source_id: Optional[str] = None,
        plate_number: Optional[str] = None,
        vehicle_class: Optional[str] = None,
        is_watchlist_match: Optional[bool] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query ANPR license plate records with filtering and pagination."""
        query = db.query(VehicleANPRModel)

        if source_id:
            query = query.filter(VehicleANPRModel.source_id.like(f"{source_id}%"))
        if plate_number:
            query = query.filter(VehicleANPRModel.plate_number.ilike(f"%{plate_number}%"))
        if vehicle_class:
            query = query.filter(VehicleANPRModel.vehicle_class == vehicle_class.upper())
        if is_watchlist_match is not None:
            query = query.filter(VehicleANPRModel.is_watchlist_match == is_watchlist_match)
        if start_time:
            query = query.filter(VehicleANPRModel.timestamp >= start_time)
        if end_time:
            query = query.filter(VehicleANPRModel.timestamp <= end_time)

        total = query.count()
        records = query.order_by(desc(VehicleANPRModel.timestamp)).offset(offset).limit(limit).all()
        return [r.to_dict() for r in records], total

    def get_anpr_record_by_id(self, db: Session, anpr_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve single ANPR record by ID."""
        rec = db.query(VehicleANPRModel).filter_by(anpr_id=anpr_id).first()
        return rec.to_dict() if rec else None

    def generate_csv_anpr_records(
        self,
        db: Session,
        source_id: Optional[str] = None,
        plate_number: Optional[str] = None,
        vehicle_class: Optional[str] = None,
        limit: int = 5000,
    ) -> str:
        """
        Generate complete CSV string from actual persisted ANPR records.
        """
        records, _ = self.get_anpr_records(
            db=db,
            source_id=source_id,
            plate_number=plate_number,
            vehicle_class=vehicle_class,
            limit=limit,
            offset=0,
        )

        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

        headers = [
            "ANPR ID",
            "Date",
            "Time",
            "Camera / Source",
            "Session",
            "Plate Number",
            "Vehicle Class",
            "Track ID",
            "OCR Confidence",
            "Plate Confidence",
            "Watchlist Status",
            "Watchlist Category",
            "Evidence Reference",
            "Status",
        ]
        writer.writerow(headers)

        for rec in records:
            ts_str = rec.get("timestamp") or ""
            date_part = ""
            time_part = ""
            if ts_str:
                try:
                    dt = datetime.fromisoformat(ts_str)
                    date_part = dt.strftime("%Y-%m-%d")
                    time_part = dt.strftime("%H:%M:%S")
                except Exception:
                    parts = ts_str.split("T")
                    date_part = parts[0]
                    time_part = parts[1][:8] if len(parts) > 1 else ""

            ocr_conf = f"{round(rec.get('ocr_confidence', 0) * 100)}%" if rec.get("ocr_confidence") is not None else "N/A"
            plate_conf = f"{round(rec.get('plate_confidence', 0) * 100)}%" if rec.get("plate_confidence") is not None else "N/A"

            row = [
                rec.get("anpr_id", ""),
                date_part,
                time_part,
                rec.get("source_id", ""),
                rec.get("session_id", "") or "N/A",
                rec.get("plate_number", ""),
                rec.get("vehicle_class", "CAR"),
                str(rec.get("track_id")) if rec.get("track_id") is not None else "N/A",
                ocr_conf,
                plate_conf,
                "MATCH" if rec.get("is_watchlist_match") else "CLEAR",
                rec.get("watchlist_category") or "N/A",
                rec.get("evidence_ref") or "N/A",
                rec.get("status", "Recognized"),
            ]
            writer.writerow(row)

        return output.getvalue()


# Module-level singleton
db_service = DatabaseService()

