"""
FaceRecognitionWorker — Phase 6: Decoupled Asynchronous Face Recognition
-------------------------------------------------------------------------
Runs in an isolated background daemon thread.
Receives person crops from the detection pipeline via a bounded thread-safe queue.

Guarantees:
  - submit_crop() is non-blocking (put_nowait) and returns in < 0.05 ms.
  - ByteTrack track-level caching (5-second cooldown per track_id).
  - Isolated execution: Model errors, corrupt crops, or slow CPU inference
    never block or slow down the 30 FPS YOLOv8 stream.
  - Broadcasts standalone WebSocket events ("face_recognition").
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Tuple

import cv2
import numpy as np

from ai_engine.modules.recognition.face_detector import FaceDetector
from ai_engine.modules.recognition.face_embedder import FaceEmbedder, KNOWN_THRESHOLD
from ai_engine.modules.recognition.face_registry import face_registry

logger = logging.getLogger(__name__)

# Cooldown per tracked object (seconds) to prevent redundant face recognition on every frame
TRACK_RECOGNITION_COOLDOWN = 5.0
QUEUE_MAXSIZE = 16


@dataclass
class FaceTask:
    """Task item pushed to the recognition queue."""
    source_id: str
    track_id: Optional[int]
    crop: np.ndarray
    timestamp_sec: float
    bbox: Tuple[int, int, int, int]


class FaceRecognitionWorker:
    """Singleton background worker managing asynchronous face recognition."""

    def __init__(self):
        self._queue: queue.Queue[FaceTask] = queue.Queue(maxsize=QUEUE_MAXSIZE)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Track-level cooldown state: { (source_id, track_id): last_recognition_timestamp }
        self._track_cooldowns: Dict[Tuple[str, int], float] = {}

        # Cache of latest recognized identity: { (source_id, track_id): identity_dict }
        self._track_identities: Dict[Tuple[str, int], dict] = {}

        # Lazy models
        self._detector: Optional[FaceDetector] = None
        self._embedder: Optional[FaceEmbedder] = None
        self.match_threshold: float = KNOWN_THRESHOLD

        # Start the background worker thread
        self.start()

    def _get_detector(self) -> FaceDetector:
        if self._detector is None:
            self._detector = FaceDetector()
        return self._detector

    def _get_embedder(self) -> FaceEmbedder:
        if self._embedder is None:
            self._embedder = FaceEmbedder()
        return self._embedder

    def start(self):
        """Start the background worker thread if not already running."""
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._stop_event.clear()
                self._thread = threading.Thread(
                    target=self._worker_loop,
                    name="face_recognition_worker",
                    daemon=True,
                )
                self._thread.start()
                logger.info("FaceRecognitionWorker daemon thread started.")

    def stop(self):
        """Signal the worker thread to stop."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            logger.info("FaceRecognitionWorker daemon thread stopped.")

    def submit_crop(
        self,
        source_id: str,
        track_id: Optional[int],
        frame: np.ndarray,
        bbox: Tuple[int, int, int, int],
        timestamp_sec: float = 0.0,
    ) -> bool:
        """
        Non-blocking handoff: Slices the person crop from the frame and submits to queue.
        Returns immediately (< 0.05 ms). If queue is full or track is in cooldown, drops gracefully.
        """
        if frame is None or frame.size == 0:
            return False

        # If we have a track_id, check cooldown
        now = time.time()
        if track_id is not None:
            key = (source_id, track_id)
            with self._lock:
                last_time = self._track_cooldowns.get(key, 0.0)
                if (now - last_time) < TRACK_RECOGNITION_COOLDOWN:
                    return False  # Cooldown active; skip duplicate work
                self._track_cooldowns[key] = now

        # Extract person bounding box crop
        x1, y1, x2, y2 = bbox
        fh, fw = frame.shape[:2]
        cx1 = max(0, min(fw - 1, int(x1)))
        cy1 = max(0, min(fh - 1, int(y1)))
        cx2 = max(cx1 + 1, min(fw, int(x2)))
        cy2 = max(cy1 + 1, min(fh, int(y2)))

        person_crop = frame[cy1:cy2, cx1:cx2].copy()
        if person_crop.size == 0 or person_crop.shape[0] < 30 or person_crop.shape[1] < 30:
            logger.info(f"[FACE_TRACE][SUBMIT_REJECT] Crop too small or empty: {person_crop.shape} for source={source_id}, track={track_id}")
            return False

        task = FaceTask(
            source_id=source_id,
            track_id=track_id,
            crop=person_crop,
            timestamp_sec=timestamp_sec,
            bbox=bbox,
        )

        try:
            self._queue.put_nowait(task)
            logger.info(f"[FACE_TRACE][SUBMIT_SUCCESS] source_id={source_id}, track_id={track_id}, crop_dim={person_crop.shape}, queue_size={self._queue.qsize()}")
            return True
        except queue.Full:
            logger.warning(f"[FACE_TRACE][SUBMIT_QUEUE_FULL] Queue is full (16), dropped crop for source={source_id}, track={track_id}")
            return False

    def get_track_identity(self, source_id: str, track_id: int) -> Optional[dict]:
        """Return the latest cached recognition identity for a tracked object."""
        with self._lock:
            if (source_id, track_id) in self._track_identities:
                return self._track_identities[(source_id, track_id)]
            # Check without video extensions or prefix variations
            clean_src = source_id.replace('.mp4', '').replace('.avi', '').replace('.mov', '') if source_id else ""
            if (clean_src, track_id) in self._track_identities:
                return self._track_identities[(clean_src, track_id)]
            for (sid, tid), ident in self._track_identities.items():
                if tid == track_id and (sid == source_id or sid == clean_src or sid.startswith(clean_src) or clean_src.startswith(sid)):
                    return ident
            return None

    def _worker_loop(self):
        """Worker thread processing items from the bounded queue."""
        while not self._stop_event.is_set():
            try:
                task = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue

            try:
                self._process_task(task)
            except Exception as exc:
                logger.error("[FACE_TRACE][WORKER_EXCEPTION] Error processing face task: %s", exc, exc_info=True)
            finally:
                self._queue.task_done()

    def _process_task(self, task: FaceTask):
        """Execute face detection, alignment, embedding extraction, and gallery match."""
        logger.info(f"[FACE_TRACE][WORKER_TASK] Processing task for source_id={task.source_id}, track_id={task.track_id}, crop_shape={task.crop.shape}")
        detector = self._get_detector()
        embedder = self._get_embedder()

        if not detector.is_ready or not embedder.is_ready:
            logger.warning(f"[FACE_TRACE][MODELS_NOT_READY] detector={detector.is_ready}, embedder={embedder.is_ready}")
            return

        # 1. Detect faces within the person crop
        faces = detector.detect_faces(task.crop)
        if not faces:
            logger.info(f"[FACE_TRACE][YUNET_NO_FACES] 0 faces detected in crop {task.crop.shape} for track={task.track_id}")
            return

        # Pick best face (largest / highest confidence)
        best_face = max(faces, key=lambda f: f.confidence * (f.w * f.h))
        logger.info(f"[FACE_TRACE][YUNET_DETECTED] {len(faces)} face(s). Best face: {best_face.w}x{best_face.h}, conf={best_face.confidence:.4f}, is_good_quality={best_face.is_good_quality} ({best_face.quality_reason})")

        # 2. Extract embedding from the aligned face crop
        emb = embedder.extract_embedding(task.crop, best_face.raw_face_array)
        if emb is None:
            logger.warning(f"[FACE_TRACE][SFACE_EMBEDDING_FAILED] Could not extract embedding for track={task.track_id}")
            return

        logger.info(f"[FACE_TRACE][SFACE_EMBEDDING_OK] 128-D vector extracted (norm={np.linalg.norm(emb):.2f}) for track={task.track_id}")

        # 3. Match against personnel gallery
        current_threshold = getattr(self, "match_threshold", KNOWN_THRESHOLD)
        person_info, similarity, status = face_registry.identify_face_embedding(
            emb, threshold=current_threshold
        )

        matched_name = person_info.get("name") if person_info else "None"
        logger.info(f"[FACE_TRACE][GALLERY_MATCH] Compared against {len(face_registry._gallery)} person(s). Similarity={similarity:.4f}, threshold={current_threshold}, status={status}, matched_name={matched_name}")

        if status == "KNOWN_PERSON" and person_info:
            identity_result = {
                "source_id": task.source_id,
                "track_id": task.track_id,
                "status": "KNOWN_PERSON",
                "person_id": person_info.get("person_id"),
                "name": person_info.get("name", "Authorized"),
                "role": person_info.get("role", "Staff"),
                "confidence": round(similarity, 2),
                "similarity": round(similarity, 4),
                "time": datetime.now().strftime("%H:%M:%S"),
            }
        else:
            identity_result = {
                "source_id": task.source_id,
                "track_id": task.track_id,
                "status": "UNKNOWN_PERSON",
                "name": "Unknown Person",
                "role": "Unrecognized Subject",
                "confidence": round(similarity, 2),
                "similarity": round(similarity, 4),
                "time": datetime.now().strftime("%H:%M:%S"),
            }

        # Cache track identity
        if task.track_id is not None:
            with self._lock:
                self._track_identities[(task.source_id, task.track_id)] = identity_result

        # Evidence Snapshot: capture person crop for UNKNOWN_PERSON events only
        # (KNOWN_PERSON events are authorized — no threat snapshot needed)
        if status == "UNKNOWN_PERSON":
            try:
                from app.services.evidence_writer import evidence_writer
                evidence_writer.enqueue_snapshot(
                    frame=task.crop,
                    source_id=task.source_id,
                    event_type="unknown_person_face",
                    track_id=task.track_id,
                    object_class="PERSON",
                    confidence=similarity,
                    timestamp_sec=task.timestamp_sec,
                )
            except Exception as _ev_err:
                logger.error("[Evidence] Snapshot enqueue failed (unknown person): %s", _ev_err)

        # Broadcast standalone WebSocket recognition event
        self._broadcast_recognition_event(task.source_id, identity_result)

        # Database persistence (non-blocking async queue)
        try:
            from app.services.db_service import db_service
            if status == "KNOWN_PERSON":
                db_service.enqueue_detection_event(
                    source_id=task.source_id,
                    event_type="Authorized Personnel Detected",
                    object_class="PERSON",
                    track_id=task.track_id,
                    confidence=similarity,
                    timestamp_sec=task.timestamp_sec,
                    person_name=identity_result.get("name"),
                    person_role=identity_result.get("role"),
                    person_status="KNOWN_PERSON",
                    threat_level="SAFE",
                    severity="Safe",
                    description=f"{identity_result.get('name')} (Authorized: {int(round(similarity * 100))}%) verified. Authorized personnel on site.",
                    bbox=task.bbox,
                )
            else:
                db_service.enqueue_detection_event(
                    source_id=task.source_id,
                    event_type="Unrecognized Face Detected",
                    object_class="PERSON",
                    track_id=task.track_id,
                    confidence=similarity,
                    timestamp_sec=task.timestamp_sec,
                    person_name="Unknown Person",
                    person_role="Unrecognized Subject",
                    person_status="UNKNOWN_PERSON",
                    threat_level="HIGH",
                    severity="High",
                    description=f"Unrecognized face detected ({int(round(similarity * 100))}% match).",
                    bbox=task.bbox,
                )
        except Exception as _dbe:
            logger.error("[Database] Face recognition persistence error: %s", _dbe)

    def _broadcast_recognition_event(self, source_id: str, identity_data: dict):
        """Emit a standalone WebSocket recognition message without modifying existing alert logic."""
        try:
            from app.websockets.manager import manager
            import json

            payload = {
                "type": "face_recognition",
                "source_id": source_id,
                "data": identity_data,
            }

            manager.broadcast_from_thread(json.dumps(payload))
            logger.info(f"[FACE_TRACE][BROADCAST_DISPATCHED] type={payload['type']}, source_id={source_id}, track_id={identity_data.get('track_id')}, status={identity_data.get('status')}, name={identity_data.get('name')}")
        except Exception as exc:
            logger.error("[FACE_TRACE][BROADCAST_ERROR] Failed to broadcast face recognition event: %s", exc, exc_info=True)


# Global singleton worker
face_worker = FaceRecognitionWorker()
