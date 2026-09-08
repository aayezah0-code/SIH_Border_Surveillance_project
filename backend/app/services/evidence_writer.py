"""
Evidence Writer Service
-----------------------
Provides a non-blocking background worker that saves surveillance evidence
snapshots (JPEG frames) for security events.

Architecture:
  - A single daemon Thread consumes from a Queue[EvidenceTask].
  - The caller (detection_router) enqueues with enqueue_snapshot() — returns instantly.
  - The worker saves the JPEG, updates the in-memory evidence index, and logs.
  - If any save fails, the error is logged and the pipeline is unaffected.

Evidence directory: backend/data/evidence/
Filename format:    YYYY-MM-DD_HH-MM-SS_<source_id>_<event_type>_<uuid_short>.jpg
"""

from __future__ import annotations

import logging
import os
import queue
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ── Evidence storage directory ─────────────────────────────────────────────────
_BACKEND_ROOT = Path(__file__).resolve().parents[2]  # .../backend/
EVIDENCE_DIR = _BACKEND_ROOT / "data" / "evidence"
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)


# ── In-memory evidence index ───────────────────────────────────────────────────
# List of evidence metadata records (newest first).
_evidence_index: List[Dict[str, Any]] = []
_index_lock = threading.Lock()


@dataclass
class EvidenceTask:
    """One snapshot capture task enqueued by the detection pipeline."""
    frame: np.ndarray           # Raw BGR frame from OpenCV
    source_id: str
    event_type: str             # e.g. "zone_intrusion", "line_crossing", "unknown_person", "priority_alert"
    track_id: Optional[int]
    object_class: Optional[str]
    confidence: Optional[float]
    timestamp_sec: float        # Seconds since stream start / video timestamp
    event_id: Optional[str] = None


class EvidenceWriter:
    """
    Singleton background worker that dequeues EvidenceTasks and saves JPEGs.
    Thread-safe: enqueue_snapshot() may be called from any thread.
    """

    _MAX_QUEUE_SIZE = 50   # Drop frames if the writer falls too far behind
    _JPEG_QUALITY = 80     # Compression quality (0-100)

    def __init__(self):
        self._queue: queue.Queue[Optional[EvidenceTask]] = queue.Queue(
            maxsize=self._MAX_QUEUE_SIZE
        )
        self._thread = threading.Thread(
            target=self._worker,
            name="evidence-writer",
            daemon=True,
        )
        # Track dedup: skip duplicate per-track snapshots within a 30-second window
        # Key: (source_id, event_type, track_id)  Value: last_saved_timestamp (monotonic)
        self._track_snap_times: Dict[tuple, float] = {}
        self._DEDUP_WINDOW = 30.0   # seconds

        self._thread.start()
        # Load any evidence files already on disk (survives backend restart)
        self._load_existing_evidence()
        logger.info("[EvidenceWriter] Background worker started. Evidence dir: %s", EVIDENCE_DIR)

    # ── Public API ─────────────────────────────────────────────────────────────

    def enqueue_snapshot(
        self,
        frame: np.ndarray,
        source_id: str,
        event_type: str,
        track_id: Optional[int] = None,
        object_class: Optional[str] = None,
        confidence: Optional[float] = None,
        timestamp_sec: float = 0.0,
        event_id: Optional[str] = None,
        skip_dedup: bool = False,
    ) -> None:
        """
        Non-blocking: enqueue a frame for evidence capture.
        Returns immediately; the actual JPEG save happens in the background.
        If the queue is full, the snapshot is silently dropped (pipeline safety).
        Duplicate snapshots for the same (source, event_type, track_id) within
        DEDUP_WINDOW seconds are suppressed unless skip_dedup=True (e.g. for
        confirmed suspicious activity episodes managed by SuspiciousActivityEngine).
        """
        if frame is None or frame.size == 0:
            return

        # Dedup: suppress same-track/same-event within time window unless skip_dedup is True
        if not skip_dedup:
            import time as _time
            now_mono = _time.monotonic()
            dedup_key = (source_id, event_type, track_id)
            last = self._track_snap_times.get(dedup_key, 0.0)
            if (now_mono - last) < self._DEDUP_WINDOW:
                return
            self._track_snap_times[dedup_key] = now_mono

        try:
            task = EvidenceTask(
                frame=frame.copy(),   # copy so caller can reuse its frame buffer
                source_id=source_id,
                event_type=event_type,
                track_id=track_id,
                object_class=object_class,
                confidence=confidence,
                timestamp_sec=timestamp_sec,
                event_id=event_id,
            )
            self._queue.put_nowait(task)
        except queue.Full:
            logger.debug("[EvidenceWriter] Queue full — evidence snapshot dropped for %s/%s", source_id, event_type)

    def get_evidence_list(
        self,
        source_id: Optional[str] = None,
        track_id: Optional[int] = None,
        event_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Return evidence records, optionally filtered by source_id, track_id, event_type.
        source_id matching is prefix-safe: the stored source_id may be truncated to 30 chars
        in filenames but the full UUID is stored in the record; the query source_id may have
        an extra .mp4 extension. We match if either is a prefix of the other.
        """
        with _index_lock:
            records = list(_evidence_index)
        if source_id:
            clean = source_id.split('.')[0]  # strip .mp4 / .avi etc.
            records = [
                r for r in records
                if _source_id_matches(r.get('source_id', ''), clean)
            ]
        if track_id is not None:
            records = [r for r in records if r.get('track_id') == track_id]
        if event_type:
            records = [r for r in records if r.get('event_type') == event_type]
        return records[:limit]

    def get_evidence_count(self) -> int:
        with _index_lock:
            return len(_evidence_index)

    # ── Startup disk scan ──────────────────────────────────────────────────────

    def _load_existing_evidence(self) -> None:
        """
        Scan EVIDENCE_DIR on startup and rebuild the in-memory index from
        existing JPEG files so evidence survives backend restarts.

        Filename format (from _save_snapshot):
          YYYY-MM-DD_HH-MM-SS_<safe_source_id_30>_<safe_event_type_20>_<uuid8>.jpg
        """
        try:
            jpg_files = sorted(
                EVIDENCE_DIR.glob("*.jpg"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,  # newest first
            )
            loaded = 0
            for fp in jpg_files:
                try:
                    record = self._record_from_filename(fp)
                    if record:
                        with _index_lock:
                            _evidence_index.append(record)
                        loaded += 1
                except Exception:
                    pass

            logger.info("[EvidenceWriter] Loaded %d existing evidence records from disk.", loaded)
        except Exception as exc:
            logger.warning("[EvidenceWriter] Could not load existing evidence: %s", exc)

    def _record_from_filename(self, filepath: Path) -> Optional[Dict[str, Any]]:
        """
        Parse a JPEG filename and produce an evidence metadata record.
        Pattern: YYYY-MM-DD_HH-MM-SS_<source_id>_<event_type>_<uuid8>.jpg
        Returns None for unrecognised filenames.
        """
        name = filepath.stem
        parts = name.split("_")
        if len(parts) < 5:
            return None

        date_part = parts[0]
        time_part = parts[1]
        try:
            captured_at = datetime.strptime(
                f"{date_part} {time_part}", "%Y-%m-%d %H-%M-%S"
            ).isoformat()
        except ValueError:
            captured_at = None

        # Everything between time and uuid8 is source_id + event_type
        middle = "_".join(parts[2:-1])

        KNOWN_EVENT_KEYS = {
            "zone_intrusion":       "zone_intrusion",
            "line_crossing":        "line_crossing",
            "unknown_person_face":  "unknown_person_face",
            "priority_person_aler": "priority_person_alert",
            "suspicious_activity":  "suspicious_activity",
        }

        event_type = None
        source_id = middle
        for key, canonical in KNOWN_EVENT_KEYS.items():
            idx = middle.rfind("_" + key)
            if idx != -1:
                source_id = middle[:idx].lstrip("_") or middle
                event_type = canonical
                break

        return {
            "filename":      filepath.name,
            "filepath":      str(filepath),
            "source_id":     source_id,
            "event_type":    event_type,
            "track_id":      None,
            "object_class":  None,
            "confidence":    None,
            "timestamp_sec": 0.0,
            "captured_at":   captured_at,
            "url":           f"/api/v1/evidence/image/{filepath.name}",
        }

    # ── Worker ─────────────────────────────────────────────────────────────────

    def _worker(self):
        """Daemon thread — processes tasks until the process exits."""
        while True:
            try:
                task = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue

            if task is None:  # Sentinel: graceful shutdown
                break

            self._save_snapshot(task)

    def _save_snapshot(self, task: EvidenceTask) -> None:
        """Save a single evidence JPEG and update the index."""
        try:
            now = datetime.now()
            date_str = now.strftime("%Y-%m-%d_%H-%M-%S")
            short_id = uuid.uuid4().hex[:8]
            safe_source = _safe_filename(task.source_id)[:30]
            safe_event  = _safe_filename(task.event_type)[:20]
            filename = f"{date_str}_{safe_source}_{safe_event}_{short_id}.jpg"
            filepath = EVIDENCE_DIR / filename

            success = cv2.imwrite(
                str(filepath),
                task.frame,
                [cv2.IMWRITE_JPEG_QUALITY, self._JPEG_QUALITY],
            )

            if not success:
                logger.error("[EvidenceWriter] cv2.imwrite failed for %s", filepath)
                return

            record: Dict[str, Any] = {
                "filename":       filename,
                "filepath":       str(filepath),
                "source_id":      task.source_id,
                "event_type":     task.event_type,
                "track_id":       task.track_id,
                "object_class":   task.object_class,
                "confidence":     round(task.confidence, 3) if task.confidence is not None else None,
                "timestamp_sec":  round(task.timestamp_sec, 2),
                "captured_at":    now.isoformat(),
                "url":            f"/api/v1/evidence/image/{filename}",
                "event_id":       task.event_id,
            }

            with _index_lock:
                _evidence_index.insert(0, record)
                # Keep index bounded to 500 most-recent records
                if len(_evidence_index) > 500:
                    _evidence_index.pop()

            # Enqueue snapshot to database
            try:
                from app.services.db_service import db_service
                db_service.enqueue_evidence_snapshot(
                    filename=filename,
                    filepath=str(filepath),
                    url=record["url"],
                    source_id=task.source_id,
                    event_type=task.event_type,
                    track_id=task.track_id,
                    object_class=task.object_class,
                    confidence=task.confidence,
                    timestamp_sec=task.timestamp_sec,
                    event_id=task.event_id,
                )
            except Exception as _dbe:
                logger.error("[EvidenceWriter] Failed to record snapshot in DB: %s", _dbe)

            logger.info(
                "[EvidenceWriter] Saved evidence: %s (event=%s, source=%s, track=%s)",
                filename, task.event_type, task.source_id, task.track_id,
            )

        except Exception as exc:
            logger.error("[EvidenceWriter] Snapshot save error: %s", exc, exc_info=True)



# ── Helpers ────────────────────────────────────────────────────────────────────

def _safe_filename(s: str) -> str:
    """Replace characters unsafe for filenames with underscores."""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in s)


def _source_id_matches(stored: str, query: str) -> bool:
    """
    Flexible source_id match that handles:
    - Exact match: 'abc' == 'abc'
    - Prefix match: stored='0daa7954-f137-4da4-9c00-1438538005b8',
                    query='0daa7954-f137-4da4-9c00-143853' (truncated in filename)
    - Extension stripped: query may have .mp4 etc. already stripped by caller
    Both directions are checked so either can be the prefix.
    """
    if not stored or not query:
        return False
    return (stored == query or
            stored.startswith(query) or
            query.startswith(stored))


# ── Module-level singleton ─────────────────────────────────────────────────────
evidence_writer = EvidenceWriter()
