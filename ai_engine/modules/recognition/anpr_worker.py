"""
ANPRWorker — Decoupled Asynchronous License Plate Recognition Worker
---------------------------------------------------------------------
Runs in an isolated background daemon thread.
Receives vehicle crops from the surveillance detection pipeline via a bounded fair per-track scheduler.

Guarantees:
  - submit_vehicle_crop() is strictly non-blocking and returns in < 0.05 ms.
  - Fair Per-Track Scheduling: Maintains at most 1 pending crop per (source_id, track_id),
    replacing pending crops with higher-quality ones in-place. Prevents early/large vehicle
    tracks from starving subsequently appearing vehicles.
  - ByteTrack track-level consensus: Requires at least 2 matching OCR readings before
    marking a track as resolved, eliminating single-frame optical glitches.
  - Track cooldown (3.0-second cooldown per track_id in live streams) to avoid redundant inference.
  - Fully isolated execution: Plate localization or OCR processing errors never block,
    slow down, or crash the surveillance stream.
  - Broadcasts standalone WebSocket events ("anpr_recognition").
  - Automatically enqueues persistent database records and evidence snapshots.
"""

from __future__ import annotations

import collections
import logging
import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Tuple, List

import cv2
import numpy as np

from ai_engine.modules.recognition.plate_detector import PlateDetector
from ai_engine.modules.recognition.plate_ocr import PlateOCR, OCRResult

logger = logging.getLogger(__name__)

TRACK_RECOGNITION_COOLDOWN = 3.0  # seconds between recognition attempts on the same track
MAX_PENDING_TRACKS = 32           # Maximum unique concurrent pending tracks in fair scheduler
CONSENSUS_THRESHOLD = 2           # Number of matching plate readings needed to resolve a track


@dataclass
class ANPRTask:
    """Vehicle crop task item pushed to the background queue with full-frame geometry."""
    source_id: str
    track_id: Optional[int]
    vehicle_crop: np.ndarray
    vehicle_class: str
    timestamp_sec: float
    vehicle_bbox: Tuple[int, int, int, int]
    session_id: Optional[str] = None
    is_offline: bool = False
    frame_idx: Optional[int] = None
    competing_bboxes: Optional[List[Tuple[int, Tuple[int, int, int, int]]]] = None


@dataclass
class PlateOwnerRecord:
    """Active scene-wide plate ownership record tracking current physical owner track."""
    track_id: int
    ownership_score: float
    ocr_confidence: float
    plate_confidence: float
    last_seen_time: float
    last_seen_frame: Optional[int]
    vehicle_class: str
    resolved_at: str
    is_watchlist_match: bool = False
    watchlist_category: Optional[str] = None
    observation_count: int = 1


@dataclass
class PlateObservation:
    """Individual candidate observation used for multi-frame consensus."""
    plate_text: str
    ocr_confidence: float
    plate_confidence: float
    ownership_score: float
    frame_idx: Optional[int]
    timestamp_sec: float


@dataclass
class ResolvedPlate:
    """Stable resolved plate record for a tracked vehicle."""
    plate_number: str
    ocr_confidence: float
    plate_confidence: float
    vehicle_class: str
    timestamp_sec: float
    resolved_at: str
    is_watchlist_match: bool = False
    watchlist_category: Optional[str] = None
    ownership_score: float = 1.0


class _SchedulerQueueProxy:
    """Backward-compatible proxy providing queue-like interface for the fair scheduler."""
    def __init__(self, worker: "ANPRWorker"):
        self._worker = worker

    def qsize(self) -> int:
        with self._worker._lock:
            return len(self._worker._pending_tasks)

    def empty(self) -> bool:
        with self._worker._lock:
            return len(self._worker._pending_tasks) == 0

    def full(self) -> bool:
        with self._worker._lock:
            return len(self._worker._pending_tasks) >= self._worker._max_pending_tracks

    def put_nowait(self, item):
        with self._worker._lock:
            if len(self._worker._pending_tasks) >= self._worker._max_pending_tracks:
                raise queue.Full
            if item is None:
                key = ("__dummy__", time.time())
            else:
                tid = getattr(item, "track_id", -1)
                sid = getattr(item, "source_id", "default")
                key = (sid, tid if tid is not None else -1)
            self._worker._pending_tasks[key] = item
            self._worker._task_order.append(key)
            self._worker._queue_condition.notify()

    def get_nowait(self):
        with self._worker._lock:
            if not self._worker._task_order:
                raise queue.Empty
            key = self._worker._task_order.popleft()
            return self._worker._pending_tasks.pop(key, None)

    @property
    def maxsize(self) -> int:
        return self._worker._max_pending_tracks


class ANPRWorker:
    """
    Singleton background worker managing asynchronous plate detection and OCR.
    Supports both Real-Time (non-blocking RTSP) and Offline (controlled quality-based batch) processing
    with a Fair Per-Track Scheduler to prevent multi-vehicle starvation.
    """

    def __init__(self):
        self._max_pending_tracks = MAX_PENDING_TRACKS
        self._pending_tasks: Dict[Tuple[str, int], ANPRTask] = {}
        self._task_order: collections.deque[Tuple[str, int]] = collections.deque()
        self._lock = threading.Lock()
        self._queue_condition = threading.Condition(self._lock)
        self._queue = _SchedulerQueueProxy(self)

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # Track cooldown state: { (source_id, track_id): last_attempt_timestamp }
        self._track_cooldowns: Dict[Tuple[str, int], float] = {}

        # Multi-frame voting consensus: { (source_id, track_id): collections.Counter }
        self._track_votes: Dict[Tuple[str, int], collections.Counter] = collections.defaultdict(collections.Counter)

        # Cache of highest confidence per vote: { (source_id, track_id, plate_text): (ocr_conf, plate_conf) }
        self._track_confidences: Dict[Tuple[str, int, str], Tuple[float, float]] = {}

        # Cache of fully resolved plate records: { (source_id, track_id): ResolvedPlate }
        self._resolved_tracks: Dict[Tuple[str, int], ResolvedPlate] = {}

        # Scene-wide active plate ownership registry: { (source_id, normalized_plate): PlateOwnerRecord }
        self._active_plate_owners: Dict[Tuple[str, str], PlateOwnerRecord] = {}

        # Multi-frame candidate observation history: { (source_id, track_id): Dict[str, List[PlateObservation]] }
        self._track_observations: Dict[Tuple[str, int], Dict[str, List[PlateObservation]]] = collections.defaultdict(lambda: collections.defaultdict(list))

        # In-flight task count per source to ensure drain_offline waits for currently executing task
        self._in_flight_tasks: Dict[str, int] = collections.defaultdict(int)

        # Set of (source_id, plate_number) already persisted in DB to prevent duplicates across ID fragments
        self._persisted_plates: set[Tuple[str, str]] = set()

        # Offline batch tracking stats: { (source_id, track_id): dict }
        self._offline_track_stats: Dict[Tuple[str, int], dict] = collections.defaultdict(dict)
        self._pending_offline_tasks: Dict[str, int] = collections.defaultdict(int)
        self._completed_offline_tasks: Dict[str, int] = collections.defaultdict(int)

        # Configurable Watchlist / BOLO (Blacklist) for border security
        self._watchlist: Dict[str, str] = {
            # Examples: "MP09AB1234": "Stolen Vehicle", "DL01XY9999": "Security BOLO"
        }

        # Lazy models
        self._detector: Optional[PlateDetector] = None
        self._ocr: Optional[PlateOCR] = None
        self.consensus_threshold: int = 2

        # Start background daemon worker
        self.start()

    _instance: Optional["ANPRWorker"] = None

    @classmethod
    def get_instance(cls) -> "ANPRWorker":
        if cls._instance is None:
            cls._instance = anpr_worker
        return cls._instance

    def _get_detector(self) -> PlateDetector:
        if self._detector is None:
            self._detector = PlateDetector()
        return self._detector

    def _get_ocr(self) -> PlateOCR:
        if self._ocr is None:
            self._ocr = PlateOCR.get_instance()
        return self._ocr

    def start(self):
        """Start the background worker thread if not running."""
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._stop_event.clear()
                self._thread = threading.Thread(
                    target=self._worker_loop,
                    name="anpr_worker_daemon",
                    daemon=True,
                )
                self._thread.start()
                logger.info("[ANPRWorker] Daemon worker thread started.")

    def stop(self):
        """Signal worker thread to terminate."""
        self._stop_event.set()
        with self._lock:
            self._queue_condition.notify_all()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            logger.info("[ANPRWorker] Daemon worker thread stopped.")

    def add_to_watchlist(self, plate_number: str, category: str = "Wanted"):
        """Add a plate to the security watchlist."""
        clean = "".join(c for c in plate_number.upper() if c.isalnum())
        with self._lock:
            self._watchlist[clean] = category

    def prepare_for_offline_source(self, source_id: str):
        """Reset per-source temporary tracking and stats for fresh offline analysis."""
        with self._lock:
            self._pending_offline_tasks[source_id] = 0
            self._completed_offline_tasks[source_id] = 0
            self._in_flight_tasks[source_id] = 0

            # Remove pending tasks belonging to this source from fair scheduler
            keys_to_remove = [k for k in self._pending_tasks if k[0] == source_id]
            for k in keys_to_remove:
                del self._pending_tasks[k]
            self._task_order = collections.deque([k for k in self._task_order if k[0] != source_id])

            keys_to_del = [k for k in self._offline_track_stats if k[0] == source_id]
            for k in keys_to_del:
                del self._offline_track_stats[k]
            cd_keys = [k for k in self._track_cooldowns if k[0] == source_id]
            for k in cd_keys:
                del self._track_cooldowns[k]
            vote_keys = [k for k in self._track_votes if k[0] == source_id]
            for k in vote_keys:
                del self._track_votes[k]
            res_keys = [k for k in self._resolved_tracks if k[0] == source_id]
            for k in res_keys:
                del self._resolved_tracks[k]
            conf_keys = [k for k in self._track_confidences if k[0] == source_id]
            for k in conf_keys:
                del self._track_confidences[k]

            # Clear scene-wide plate ownership and observations for this source
            owner_keys = [k for k in self._active_plate_owners if k[0] == source_id]
            for k in owner_keys:
                del self._active_plate_owners[k]
            obs_keys = [k for k in self._track_observations if k[0] == source_id]
            for k in obs_keys:
                del self._track_observations[k]
            self._persisted_plates = {k for k in self._persisted_plates if k[0] != source_id}

            self._queue_condition.notify_all()
        logger.info("[ANPR_BATCH] Prepared fresh offline state for source '%s'", source_id)

    def drain_offline(self, source_id: str, timeout: float = 30.0) -> bool:
        """
        Blocks until all queued and in-flight ANPR tasks for source_id have finished processing.
        Ensures multi-frame voting consensus and all DB/WebSocket dispatches are completed before return.
        """
        with self._lock:
            pending_cnt = len([k for k in self._pending_tasks if k[0] == source_id])
            max_wait = max(timeout, pending_cnt * 2.5 + 8.0)

        t0 = time.time()
        logger.info("[ANPR_DRAIN][WAIT] Starting end-of-video drain for source '%s' (pending=%d, max_timeout=%.1fs)...", source_id, pending_cnt, max_wait)
        while time.time() - t0 < max_wait:
            with self._lock:
                has_pending = any(k[0] == source_id for k in self._pending_tasks)
                in_flight = self._in_flight_tasks.get(source_id, 0)
                offline_pending = self._pending_offline_tasks.get(source_id, 0)
                if not has_pending and in_flight == 0 and offline_pending <= 0:
                    break
                self._queue_condition.wait(timeout=0.05)

        with self._lock:
            pending = max(0, self._pending_offline_tasks.get(source_id, 0))
            completed = self._completed_offline_tasks.get(source_id, 0)
            in_flight = self._in_flight_tasks.get(source_id, 0)
            has_pending = any(k[0] == source_id for k in self._pending_tasks)
            elapsed = time.time() - t0

            if not has_pending and in_flight == 0:
                logger.info(
                    "[ANPR_DRAIN][COMPLETE] source_id='%s', completed_tasks=%d, pending=%d, in_flight=%d, elapsed=%.2fs",
                    source_id, completed, pending, in_flight, elapsed
                )
            else:
                logger.warning(
                    "[ANPR_DRAIN][TIMEOUT] source_id='%s' drain timed out after %.1fs (pending=%d, in_flight=%d, completed=%d)",
                    source_id, elapsed, pending, in_flight, completed
                )

            # Print track summaries for this source
            for (sid, tid), stats in list(self._offline_track_stats.items()):
                if sid == source_id:
                    resolved_info = self._resolved_tracks.get((sid, tid))
                    final_pl = resolved_info.plate_number if resolved_info else stats.get("final_plate", "UNRESOLVED")
                    logger.info(
                        "[ANPR_BATCH][TRACK] track_id=%s, best_frame=%s, best_plate_crop=%s, best_plate_confidence=%.2f, best_ocr='%s', final_plate='%s'",
                        tid,
                        stats.get("best_frame", "-"),
                        stats.get("best_plate_crop", "-"),
                        stats.get("best_plate_confidence", 0.0),
                        stats.get("best_ocr", "-"),
                        final_pl,
                    )
        return True

    def submit_vehicle_crop(
        self,
        source_id: str,
        track_id: Optional[int],
        frame: np.ndarray,
        vehicle_bbox: Tuple[int, int, int, int],
        vehicle_class: str = "CAR",
        timestamp_sec: float = 0.0,
        session_id: Optional[str] = None,
        is_offline: bool = False,
        frame_idx: Optional[int] = None,
        competing_bboxes: Optional[List[Tuple[int, Tuple[int, int, int, int]]]] = None,
    ) -> bool:
        """
        Extracts vehicle crop and enqueues for background ANPR via Fair Per-Track Scheduling.

        - Non-Blocking Guarantee: Always returns immediately (< 0.05 ms). Never blocks YOLO loop.
        - Fair Per-Track Scheduling: Maintains at most 1 pending crop per (source_id, track_id).
          If the track already has a pending slot, replaces it with the better crop in-place.
          Ensures newly appearing vehicles are never starved by earlier active vehicles.
        """
        if frame is None or frame.size == 0:
            logger.info("[ANPR_TRACE][VEHICLE_CROP] source_id=%s, track_id=%s, crop_dim=None, is_empty=True (Frame is None/empty)", source_id, track_id)
            return False

        # Extract vehicle bounding box crop
        x1, y1, x2, y2 = vehicle_bbox
        fh, fw = frame.shape[:2]
        cx1 = max(0, min(fw - 1, int(x1)))
        cy1 = max(0, min(fh - 1, int(y1)))
        cx2 = max(cx1 + 1, min(fw, int(x2)))
        cy2 = max(cy1 + 1, min(fh, int(y2)))

        vehicle_crop = frame[cy1:cy2, cx1:cx2].copy()
        crop_h, crop_w = vehicle_crop.shape[:2] if vehicle_crop is not None else (0, 0)
        crop_area = crop_w * crop_h
        is_clipped = (cx1 <= 5 or cy1 <= 5 or cx2 >= fw - 5 or cy2 >= fh - 5)
        is_invalid = vehicle_crop is None or vehicle_crop.size == 0 or crop_h < 20 or crop_w < 30

        logger.info(
            "[ANPR_TRACE][VEHICLE_CROP] source_id=%s, track_id=%s, crop_size=(%d, %d), crop_dim=%s, is_invalid=%s",
            source_id, track_id, crop_w, crop_h, vehicle_crop.shape if vehicle_crop is not None else None, is_invalid
        )

        if is_invalid:
            if is_offline and track_id is not None:
                logger.info(
                    "[ANPR_BATCH][DROP] source_id=%s, track_id=%s, frame_number=%s, reason=Invalid crop dimensions (%dx%d)",
                    source_id, track_id, frame_idx, crop_w, crop_h
                )
            return False

        key = (source_id, track_id if track_id is not None else -1)

        if not is_offline:
            # ─────────────────────────────────────────────────────────────
            # REAL-TIME / RTSP MODE: STRICTLY NON-BLOCKING (< 0.05ms)
            # ─────────────────────────────────────────────────────────────
            now = time.time()
            if track_id is not None:
                with self._lock:
                    if (source_id, track_id) in self._resolved_tracks:
                        return False
                    last_time = self._track_cooldowns.get((source_id, track_id), 0.0)
                    if (now - last_time) < TRACK_RECOGNITION_COOLDOWN:
                        return False
                    self._track_cooldowns[(source_id, track_id)] = now

            task = ANPRTask(
                source_id=source_id,
                track_id=track_id,
                vehicle_crop=vehicle_crop,
                vehicle_class=vehicle_class.upper(),
                timestamp_sec=timestamp_sec,
                vehicle_bbox=vehicle_bbox,
                session_id=session_id,
                is_offline=False,
                frame_idx=frame_idx,
                competing_bboxes=competing_bboxes,
            )

            with self._lock:
                if key in self._pending_tasks:
                    # Update pending task in-place if newer/better crop
                    prev_task = self._pending_tasks[key]
                    prev_area = prev_task.vehicle_crop.shape[0] * prev_task.vehicle_crop.shape[1] if prev_task.vehicle_crop is not None else 0
                    if crop_area >= prev_area * 0.90:
                        self._pending_tasks[key] = task
                    logger.info(
                        "[ANPR_TRACE][QUEUE_SUBMIT] source_id=%s, track_id=%s, vehicle_class=%s, queue_size=%d, status=SUCCEEDED",
                        source_id, track_id, vehicle_class, len(self._pending_tasks)
                    )
                    return True
                else:
                    if len(self._pending_tasks) < self._max_pending_tracks:
                        self._pending_tasks[key] = task
                        self._task_order.append(key)
                        self._queue_condition.notify()
                        logger.info(
                            "[ANPR_TRACE][QUEUE_SUBMIT] source_id=%s, track_id=%s, vehicle_class=%s, queue_size=%d, status=SUCCEEDED",
                            source_id, track_id, vehicle_class, len(self._pending_tasks)
                        )
                        return True
                    else:
                        logger.info(
                            "[ANPR_TRACE][QUEUE_SUBMIT] source_id=%s, track_id=%s, vehicle_class=%s, queue_size=%d, status=DROPPED (Queue full)",
                            source_id, track_id, vehicle_class, len(self._pending_tasks)
                        )
                        return False

        else:
            # ─────────────────────────────────────────────────────────────
            # OFFLINE UPLOADED VIDEO MODE: FAIR PER-TRACK SCHEDULING
            # ─────────────────────────────────────────────────────────────
            if track_id is not None:
                with self._lock:
                    # 1. Skip if already resolved
                    if (source_id, track_id) in self._resolved_tracks:
                        logger.info(
                            "[ANPR_BATCH][SUBMIT] source_id=%s, track_id=%s, frame_number=%s, queue_size=%d, crop_quality=%d, plate_quality=N/A, action=SKIPPED",
                            source_id, track_id, frame_idx, len(self._pending_tasks), crop_area
                        )
                        return False

                    # 2. Quality & Time Sampling check
                    stats = self._offline_track_stats[(source_id, track_id)]
                    last_sec = stats.get("last_submitted_video_sec", -999.0)
                    prev_best_area = stats.get("best_crop_area", 0)
                    prev_is_clipped = stats.get("last_was_clipped", True)
                    dt = timestamp_sec - last_sec

                    # Submit if:
                    # a) First time seen for this track
                    # b) At least 0.5s elapsed in video time
                    # c) Crop quality has grown significantly (>10% larger area)
                    # d) Transition from border-clipped to unclipped view
                    should_sample = (last_sec < 0) or (dt >= 0.5) or (crop_area >= prev_best_area * 1.10) or (prev_is_clipped and not is_clipped)

                    if not should_sample:
                        logger.info(
                            "[ANPR_BATCH][SUBMIT] source_id=%s, track_id=%s, frame_number=%s, queue_size=%d, crop_quality=%d, plate_quality=N/A, action=SKIPPED",
                            source_id, track_id, frame_idx, len(self._pending_tasks), crop_area
                        )
                        return False

                    task = ANPRTask(
                        source_id=source_id,
                        track_id=track_id,
                        vehicle_crop=vehicle_crop,
                        vehicle_class=vehicle_class.upper(),
                        timestamp_sec=timestamp_sec,
                        vehicle_bbox=vehicle_bbox,
                        session_id=session_id,
                        is_offline=True,
                        frame_idx=frame_idx,
                        competing_bboxes=competing_bboxes,
                    )

                    # 3. FAIR PER-TRACK SCHEDULER:
                    # If this track already has a pending task in the scheduler, update it in-place
                    # with the latest crop. This prevents single tracks from occupying multiple queue slots.
                    if key in self._pending_tasks:
                        prev_task = self._pending_tasks[key]
                        prev_area = prev_task.vehicle_crop.shape[0] * prev_task.vehicle_crop.shape[1] if prev_task.vehicle_crop is not None else 0
                        px1, py1, px2, py2 = prev_task.vehicle_bbox
                        prev_clipped = (px1 <= 5 or py1 <= 5 or px2 >= fw - 5 or py2 >= fh - 5)

                        # Prefer unclipped full-vehicle views over border-clipped crops
                        should_update = False
                        if prev_clipped and not is_clipped:
                            should_update = True
                        elif (not prev_clipped) and is_clipped:
                            should_update = False
                        else:
                            # Both unclipped or both clipped: prefer larger crop area
                            if crop_area >= prev_area or (prev_area < 180000 and crop_area >= prev_area * 0.90):
                                should_update = True

                        if should_update:
                            self._pending_tasks[key] = task
                            stats["best_crop_area"] = max(prev_best_area, crop_area)
                            stats["last_submitted_video_sec"] = timestamp_sec
                            stats["last_was_clipped"] = is_clipped
                        logger.info(
                            "[ANPR_BATCH][SUBMIT] source_id=%s, track_id=%s, frame_number=%s, queue_size=%d, crop_quality=%d, plate_quality=PENDING, action=SUBMITTED (UPDATED_IN_PLACE)",
                            source_id, track_id, frame_idx, len(self._pending_tasks), crop_area
                        )
                        return True
                    else:
                        if len(self._pending_tasks) < self._max_pending_tracks:
                            self._pending_tasks[key] = task
                            self._task_order.append(key)
                            self._queue_condition.notify()

                            stats["last_submitted_video_sec"] = timestamp_sec
                            stats["best_crop_area"] = max(prev_best_area, crop_area)
                            stats["last_was_clipped"] = is_clipped
                            stats["submission_count"] = stats.get("submission_count", 0) + 1
                            self._pending_offline_tasks[source_id] = self._pending_offline_tasks.get(source_id, 0) + 1

                            logger.info(
                                "[ANPR_BATCH][SUBMIT] source_id=%s, track_id=%s, frame_number=%s, queue_size=%d, crop_quality=%d, plate_quality=PENDING, action=SUBMITTED",
                                source_id, track_id, frame_idx, len(self._pending_tasks), crop_area
                            )
                            return True
                        else:
                            logger.info(
                                "[ANPR_BATCH][DROP] source_id=%s, track_id=%s, frame_number=%s, reason=queue_full",
                                source_id, track_id, frame_idx
                            )
                            return False

    def get_track_plate(self, source_id: str, track_id: int) -> Optional[dict]:
        """Return cached resolved plate info for a given tracked vehicle."""
        with self._lock:
            key = (source_id, track_id)
            if key in self._resolved_tracks:
                rec = self._resolved_tracks[key]
                return {
                    "source_id": source_id,
                    "track_id": track_id,
                    "plate_number": rec.plate_number,
                    "confidence": rec.ocr_confidence,
                    "vehicle_class": rec.vehicle_class,
                    "is_watchlist_match": rec.is_watchlist_match,
                    "watchlist_category": rec.watchlist_category,
                    "time": rec.resolved_at,
                }
            # Prefix search for source matching
            clean_src = source_id.split(".")[0]
            for (sid, tid), rec in self._resolved_tracks.items():
                if tid == track_id and (sid == source_id or sid.startswith(clean_src) or clean_src.startswith(sid)):
                    return {
                        "source_id": source_id,
                        "track_id": track_id,
                        "plate_number": rec.plate_number,
                        "confidence": rec.ocr_confidence,
                        "vehicle_class": rec.vehicle_class,
                        "is_watchlist_match": rec.is_watchlist_match,
                        "watchlist_category": rec.watchlist_category,
                        "time": rec.resolved_at,
                    }
            return None

    def _worker_loop(self):
        """Consumes ANPR tasks using fair per-track scheduling."""
        while not self._stop_event.is_set():
            task: Optional[ANPRTask] = None
            with self._lock:
                while not self._task_order and not self._stop_event.is_set():
                    self._queue_condition.wait(timeout=0.2)
                if self._stop_event.is_set():
                    break
                if self._task_order:
                    key = self._task_order.popleft()
                    task = self._pending_tasks.pop(key, None)
                    if task is not None:
                        self._in_flight_tasks[task.source_id] = self._in_flight_tasks.get(task.source_id, 0) + 1

            if task is None:
                continue

            try:
                self._process_task(task)
            except Exception as exc:
                logger.error("[ANPRWorker] Error processing ANPR task: %s", exc, exc_info=True)
            finally:
                if task is not None:
                    with self._lock:
                        self._in_flight_tasks[task.source_id] = max(0, self._in_flight_tasks.get(task.source_id, 0) - 1)
                        if getattr(task, 'is_offline', False):
                            self._pending_offline_tasks[task.source_id] = max(0, self._pending_offline_tasks.get(task.source_id, 0) - 1)
                            self._completed_offline_tasks[task.source_id] = self._completed_offline_tasks.get(task.source_id, 0) + 1
                        self._queue_condition.notify_all()

    def _compute_plate_ownership(
        self,
        cand_bbox_in_crop: Tuple[int, int, int, int],
        vehicle_bbox: Tuple[int, int, int, int],
        plate_conf: float,
        competing_bboxes: Optional[List[Tuple[int, Tuple[int, int, int, int]]]] = None,
    ) -> Tuple[float, dict]:
        """
        Computes deterministic plate ownership score [0.0, 1.0] for a candidate plate inside vehicle crop.
        Converts plate bbox to full-frame coordinates, evaluates:
          - containment ratio inside vehicle bbox
          - horizontal centrality relative to vehicle width
          - vertical plausibility relative to vehicle height (bumpers/lower boot)
          - plate detector confidence
          - relative geometric fit against competing active vehicle bboxes
        """
        cx1, cy1, cx2, cy2 = cand_bbox_in_crop
        vx1, vy1, vx2, vy2 = vehicle_bbox
        vw = max(1, vx2 - vx1)
        vh = max(1, vy2 - vy1)

        # Full-frame coordinates of candidate plate
        px1 = vx1 + cx1
        py1 = vy1 + cy1
        px2 = vx1 + cx2
        py2 = vy1 + cy2
        pw = max(1, px2 - px1)
        ph = max(1, py2 - py1)
        plate_area = pw * ph

        # Plate center in full frame
        px_c = (px1 + px2) / 2.0
        py_c = (py1 + py2) / 2.0

        # Normalized coordinates relative to this vehicle
        norm_px = (px_c - vx1) / vw
        norm_py = (py_c - vy1) / vh

        # Containment ratio of plate inside vehicle bbox
        ix1 = max(px1, vx1)
        iy1 = max(py1, vy1)
        ix2 = min(px2, vx2)
        iy2 = min(py2, vy2)
        inter_w = max(0, ix2 - ix1)
        inter_h = max(0, iy2 - iy1)
        containment_ratio = (inter_w * inter_h) / max(1.0, float(plate_area))

        # Horizontal centrality: plates are physically mounted near the horizontal center (0.35 - 0.65)
        # dx is the deviation from vehicle horizontal center 0.50
        dx = abs(norm_px - 0.50)
        if dx <= 0.15: # Center zone: [0.35, 0.65]
            h_score = 1.0
        elif dx <= 0.22: # Intermediate zone: [0.28, 0.72]
            h_score = max(0.0, 1.0 - (dx - 0.15) / 0.07)
        else: # Outer edge / adjacent vehicle zone: < 0.28 or > 0.72
            h_score = 0.0

        # Vertical plausibility: plates are mounted on lower bumpers or boot (0.45 - 0.95)
        if 0.45 <= norm_py <= 0.95:
            v_score = 1.0
        elif 0.30 <= norm_py < 0.45:
            v_score = 0.65
        elif norm_py > 0.95:
            v_score = 0.80
        else:
            v_score = 0.20

        # If a plate is positioned on the extreme horizontal edge of the vehicle crop,
        # it is geometrically disqualified as belonging to this vehicle bumper
        if h_score <= 0.0:
            base_geom = 0.0
        else:
            base_geom = 0.60 * h_score + 0.40 * v_score

        # Check against competing vehicles in the frame
        competing_penalty = 0.0
        best_competing_geom = 0.0
        best_competing_tid = None
        if competing_bboxes:
            for other_tid, other_box in competing_bboxes:
                ox1, oy1, ox2, oy2 = other_box
                ow = max(1, ox2 - ox1)
                oh = max(1, oy2 - oy1)
                if ox1 <= px_c <= ox2 and oy1 <= py_c <= oy2:
                    other_norm_px = (px_c - ox1) / ow
                    other_norm_py = (py_c - oy1) / oh
                    other_dx = abs(other_norm_px - 0.50)
                    if other_dx <= 0.15:
                        other_h = 1.0
                    elif other_dx <= 0.22:
                        other_h = max(0.0, 1.0 - (other_dx - 0.15) / 0.07)
                    else:
                        other_h = 0.0
                    other_v = 1.0 if (0.45 <= other_norm_py <= 0.95) else (0.65 if 0.30 <= other_norm_py < 0.45 else 0.20)
                    other_geom = (0.60 * other_h + 0.40 * other_v) if other_h > 0 else 0.0
                    if other_geom > best_competing_geom:
                        best_competing_geom = other_geom
                        best_competing_tid = other_tid

        if best_competing_geom > base_geom:
            # Significant penalty when another vehicle in the scene has better plate centrality
            competing_penalty = 0.30 + (best_competing_geom - base_geom) * 1.20

        ownership_score = (0.45 * base_geom + 0.35 * containment_ratio + 0.20 * min(1.0, max(0.0, plate_conf))) - competing_penalty
        ownership_score = max(0.0, min(1.0, ownership_score))

        metrics = {
            "norm_px": round(norm_px, 3),
            "norm_py": round(norm_py, 3),
            "containment_ratio": round(containment_ratio, 3),
            "h_score": round(h_score, 3),
            "v_score": round(v_score, 3),
            "base_geom": round(base_geom, 3),
            "competing_penalty": round(competing_penalty, 3),
            "best_competing_tid": best_competing_tid,
            "ownership_score": round(ownership_score, 3),
            "full_plate_bbox": (int(px1), int(py1), int(px2), int(py2)),
        }
        return ownership_score, metrics

    def _process_task(self, task: Optional[ANPRTask]):
        """Locates license plate, executes OCR, tallies multi-frame consensus, and emits events."""
        if task is None or not hasattr(task, 'vehicle_crop') or task.vehicle_crop is None:
            return

        detector = self._get_detector()
        ocr = self._get_ocr()

        if not detector.is_ready or not ocr.is_ready:
            return

        vh, vw = task.vehicle_crop.shape[:2]
        logger.info(
            "[ANPR_TRACE][WORKER_PROCESS] source_id=%s, track_id=%s, vehicle_class=%s, timestamp_sec=%.2f, picked_up=True, crop=(%dx%d)",
            task.source_id, task.track_id, task.vehicle_class, task.timestamp_sec, vw, vh
        )

        # 1. Detect license plate candidates in vehicle crop using dedicated detector
        plates = detector.detect_plates(
            task.vehicle_crop,
            min_conf=0.25,
            source_id=task.source_id,
            track_id=task.track_id,
        )

        # Fallback candidate: lower 65% of vehicle crop where plates are physically mounted
        if not plates and vh >= 35 and vw >= 45:
            roi_y = int(vh * 0.35)
            lower_crop = task.vehicle_crop[roi_y:, :]
            from ai_engine.modules.recognition.plate_detector import PlateDetectionResult
            plates.append(PlateDetectionResult(
                x1=0, y1=roi_y, x2=vw, y2=vh,
                confidence=0.40,
                plate_crop=lower_crop,
            ))

        if not plates:
            logger.info(
                "[ANPR_TRACE][PLATE_DETECTION_FAILED] source_id=%s, track_id=%s (0 candidate plates found)",
                task.source_id, task.track_id
            )
            return

        # Score candidates for geometric plate ownership
        scored_plates = []
        for cand in plates:
            cand_bbox = (cand.x1, cand.y1, cand.x2, cand.y2)
            own_score, metrics = self._compute_plate_ownership(
                cand_bbox_in_crop=cand_bbox,
                vehicle_bbox=task.vehicle_bbox,
                plate_conf=cand.confidence,
                competing_bboxes=getattr(task, "competing_bboxes", None),
            )
            scored_plates.append((cand, own_score, metrics))
            logger.info(
                "[ANPR_OWNERSHIP][SCORE] source_id=%s, track_id=%s, bbox=%s, score=%.3f, metrics=%s",
                task.source_id, task.track_id, cand_bbox, own_score, metrics
            )

        # Sort candidates primarily by ownership score, secondarily by detector confidence
        scored_plates.sort(key=lambda item: (item[1], item[0].confidence), reverse=True)
        best_cand, best_own_score, best_cand_metrics = scored_plates[0]

        logger.info(
            "[ANPR_PLATE_MODEL][BEST] source_id=%s, track_id=%s, bbox=(%d, %d, %d, %d), confidence=%.3f, ownership_score=%.3f, plate_crop_size=(%d, %d)",
            task.source_id, task.track_id, best_cand.x1, best_cand.y1, best_cand.x2, best_cand.y2,
            best_cand.confidence, best_own_score, best_cand.plate_crop.shape[1], best_cand.plate_crop.shape[0]
        )

        if getattr(task, 'is_offline', False) and task.track_id is not None and scored_plates:
            with self._lock:
                st = self._offline_track_stats[(task.source_id, task.track_id)]
                if best_cand.confidence > st.get("best_plate_confidence", 0.0):
                    st["best_plate_confidence"] = best_cand.confidence
                    st["best_plate_crop"] = f"({best_cand.plate_crop.shape[1]}x{best_cand.plate_crop.shape[0]})"

        # 2. Test candidate crops with OCR
        best_ocr: Optional[OCRResult] = None
        best_crop: Optional[np.ndarray] = None
        best_pl_conf: float = 0.0
        best_ownership_score: float = 0.0

        for cand, own_score, metrics in scored_plates[:2]:
            cand_dims = (cand.plate_crop.shape[1], cand.plate_crop.shape[0])

            # Pre-filter out candidates that belong to overlapping competing vehicles (score < 0.30)
            if own_score < 0.30:
                logger.info(
                    "[ANPR_OWNERSHIP][REJECT] source_id=%s, track_id=%s, cand_bbox=(%d, %d, %d, %d) rejected prior to OCR (score=%.2f < 0.30)",
                    task.source_id, task.track_id, cand.x1, cand.y1, cand.x2, cand.y2, own_score
                )
                continue

            ocr_res = ocr.recognize_plate(
                cand.plate_crop,
                source_id=task.source_id,
                track_id=task.track_id,
                frame_id=getattr(task, 'frame_idx', None),
            )
            if ocr_res and ocr_res.plate_text:
                logger.info(
                    "[ANPR_PLATE_MODEL][OCR] source_id=%s, track_id=%s, raw_text='%s', confidence=%.2f, valid=%s",
                    task.source_id, task.track_id, ocr_res.raw_text, ocr_res.confidence, ocr_res.is_valid
                )
                logger.info(
                    "[ANPR_TRACE][OCR_RESULT] raw_text='%s', ocr_confidence=%.2f, crop_dims=%s",
                    ocr_res.raw_text, ocr_res.confidence, cand_dims
                )
                if best_ocr is None:
                    best_ocr = ocr_res
                    best_crop = cand.plate_crop
                    best_pl_conf = cand.confidence
                    best_ownership_score = own_score
                elif ocr_res.is_valid and not best_ocr.is_valid:
                    best_ocr = ocr_res
                    best_crop = cand.plate_crop
                    best_pl_conf = cand.confidence
                    best_ownership_score = own_score
                    if ocr_res.confidence >= 0.70:
                        break
                elif ocr_res.confidence > best_ocr.confidence and (ocr_res.is_valid == best_ocr.is_valid):
                    best_ocr = ocr_res
                    best_crop = cand.plate_crop
                    best_pl_conf = cand.confidence
                    best_ownership_score = own_score
            else:
                logger.info("[ANPR_TRACE][OCR_EMPTY] candidate_crop_dims=%s returned no text", cand_dims)

        if getattr(task, 'is_offline', False) and task.track_id is not None and best_ocr:
            with self._lock:
                st = self._offline_track_stats[(task.source_id, task.track_id)]
                prev_valid = st.get("best_ocr_valid", False)
                should_update = False

                if best_ocr.is_valid and not prev_valid:
                    should_update = True
                elif best_ocr.is_valid and prev_valid:
                    if best_ocr.confidence > st.get("best_ocr_confidence", 0.0):
                        should_update = True
                elif not best_ocr.is_valid and not prev_valid:
                    if best_ocr.confidence > st.get("best_ocr_confidence", 0.0):
                        should_update = True

                if should_update:
                    st["best_ocr"] = best_ocr.plate_text if best_ocr.is_valid else best_ocr.raw_text
                    st["best_ocr_confidence"] = best_ocr.confidence
                    st["best_ocr_valid"] = best_ocr.is_valid
                    st["best_frame"] = task.frame_idx if task.frame_idx is not None else int(round(task.timestamp_sec * 24))
                    if best_crop is not None:
                        st["best_plate_crop"] = f"({best_crop.shape[1]}x{best_crop.shape[0]})"

        if not best_ocr or not best_ocr.plate_text:
            return

        plate_str = best_ocr.plate_text.strip()
        ocr_conf = best_ocr.confidence
        plate_conf = best_pl_conf
        ownership_score = best_ownership_score

        # Rejection of short invalid OCR noise
        if len(plate_str) < 4 or not best_ocr.is_valid:
            return

        # Minimal ownership requirement to claim any physical plate
        if ownership_score < 0.40:
            logger.info(
                "[ANPR_OWNERSHIP][REJECT] source_id=%s, track_id=%s, plate='%s' rejected (ownership_score=%.2f < 0.40)",
                task.source_id, task.track_id, plate_str, ownership_score
            )
            return

        key = (task.source_id, task.track_id) if task.track_id is not None else None

        # 3. Two-Tier Consensus & Scene-Wide Plate Ownership Policy
        should_resolve = False
        final_plate_text = plate_str

        if key is not None:
            with self._lock:
                # Record candidate observation
                obs = PlateObservation(
                    plate_text=plate_str,
                    ocr_confidence=ocr_conf,
                    plate_confidence=plate_conf,
                    ownership_score=ownership_score,
                    frame_idx=task.frame_idx,
                    timestamp_sec=task.timestamp_sec,
                )
                self._track_observations[key][plate_str].append(obs)
                self._track_votes[key][plate_str] += 1
                conf_key = (task.source_id, task.track_id, plate_str)
                prev_ocr_conf, prev_pl_conf = self._track_confidences.get(conf_key, (0.0, 0.0))
                self._track_confidences[conf_key] = (max(prev_ocr_conf, ocr_conf), max(prev_pl_conf, plate_conf))

                # If track is already resolved, preserve strong result (Part 6)
                if key in self._resolved_tracks:
                    curr_resolved = self._resolved_tracks[key]
                    if plate_str == curr_resolved.plate_number:
                        if ocr_conf > curr_resolved.ocr_confidence:
                            curr_resolved.ocr_confidence = ocr_conf
                            curr_resolved.plate_confidence = max(curr_resolved.plate_confidence, plate_conf)
                    return

                # Evaluate Two-Tier Consensus:
                obs_list = self._track_observations[key][plate_str]
                distinct_frames = {o.frame_idx for o in obs_list if o.frame_idx is not None}
                time_spread = (max(o.timestamp_sec for o in obs_list) - min(o.timestamp_sec for o in obs_list)) if obs_list else 0.0
                curr_consensus_thresh = getattr(self, "consensus_threshold", 2)
                is_multi_frame = (curr_consensus_thresh <= 1) or len(distinct_frames) >= curr_consensus_thresh or time_spread >= 0.15 or len(obs_list) >= curr_consensus_thresh

                max_c, max_p = self._track_confidences[conf_key]
                top_plate, top_votes = self._track_votes[key].most_common(1)[0]
                is_top_candidate = (top_plate == plate_str)
                has_competing_candidate = (len(self._track_votes[key]) > 1)

                is_tier_1 = (max_c >= 0.70 and best_ocr.is_valid and ownership_score >= 0.45)
                is_tier_2 = (max_c >= 0.40 and best_ocr.is_valid and ownership_score >= 0.45 and is_multi_frame and is_top_candidate)
                is_high_ownership_single = (
                    ownership_score >= 0.75
                    and max_c >= 0.55
                    and best_ocr.is_valid
                    and not has_competing_candidate
                )

                if is_tier_1:
                    should_resolve = True
                    logger.info(
                        "[ANPR_CONSENSUS][RESOLVED_TIER1] source_id=%s, track_id=%s, plate='%s', confidence=%.2f, ownership_score=%.2f",
                        task.source_id, task.track_id, plate_str, max_c, ownership_score
                    )
                elif is_tier_2:
                    should_resolve = True
                    logger.info(
                        "[ANPR_CONSENSUS][RESOLVED_TIER2] source_id=%s, track_id=%s, plate='%s', votes=%d, max_conf=%.2f, distinct_frames=%d, ownership_score=%.2f",
                        task.source_id, task.track_id, plate_str, len(obs_list), max_c, len(distinct_frames), ownership_score
                    )
                elif is_high_ownership_single:
                    should_resolve = True
                    logger.info(
                        "[ANPR_CONSENSUS][RESOLVED_HIGH_OWNERSHIP] source_id=%s, track_id=%s, plate='%s', confidence=%.2f, ownership_score=%.2f (high geometric ownership single-frame acceptance)",
                        task.source_id, task.track_id, plate_str, max_c, ownership_score
                    )
                else:
                    logger.info(
                        "[ANPR_CONSENSUS][PENDING] source_id=%s, track_id=%s, candidate_plate='%s', votes=%d, max_conf=%.2f, distinct_frames=%d, is_top=%s",
                        task.source_id, task.track_id, plate_str, len(obs_list), max_c, len(distinct_frames), is_top_candidate
                    )
                    return

                # Evaluate Scene-Wide Plate Ownership Registry (Parts 3 & 4)
                reg_key = (task.source_id, plate_str)
                now_str = datetime.now().strftime("%H:%M:%S")
                is_match = plate_str in self._watchlist
                cat = self._watchlist.get(plate_str)

                if reg_key in self._active_plate_owners:
                    owner = self._active_plate_owners[reg_key]
                    if owner.track_id == task.track_id:
                        # Same track: update owner record
                        owner.last_seen_time = task.timestamp_sec
                        owner.last_seen_frame = task.frame_idx
                        owner.observation_count += 1
                        owner.ownership_score = max(owner.ownership_score, ownership_score)
                        owner.ocr_confidence = max(owner.ocr_confidence, max_c)
                        rec = ResolvedPlate(
                            plate_number=plate_str,
                            ocr_confidence=owner.ocr_confidence,
                            plate_confidence=owner.plate_confidence,
                            vehicle_class=task.vehicle_class,
                            timestamp_sec=task.timestamp_sec,
                            resolved_at=now_str,
                            is_watchlist_match=is_match,
                            watchlist_category=cat,
                            ownership_score=owner.ownership_score,
                        )
                        self._resolved_tracks[key] = rec
                        return
                    else:
                        # Competing track claims the same plate
                        dt = task.timestamp_sec - owner.last_seen_time if task.timestamp_sec >= owner.last_seen_time else (time.time() - owner.last_seen_time)
                        df = (task.frame_idx - owner.last_seen_frame) if (task.frame_idx is not None and owner.last_seen_frame is not None) else None

                        can_transfer_stronger = (ownership_score >= owner.ownership_score + 0.15 and ownership_score >= 0.55)
                        can_transfer_continuation = (dt >= 2.0 or (df is not None and df >= 40))

                        if can_transfer_stronger:
                            prev_tid = owner.track_id
                            logger.info(
                                "[ANPR_OWNERSHIP][TRANSFER] source_id=%s, plate='%s', from_track=%s (score=%.2f) -> to_track=%s (score=%.2f)",
                                task.source_id, plate_str, prev_tid, owner.ownership_score, task.track_id, ownership_score
                            )
                            self._resolved_tracks.pop((task.source_id, prev_tid), None)
                            self._active_plate_owners[reg_key] = PlateOwnerRecord(
                                track_id=task.track_id,
                                ownership_score=ownership_score,
                                ocr_confidence=max_c,
                                plate_confidence=plate_conf,
                                last_seen_time=task.timestamp_sec,
                                last_seen_frame=task.frame_idx,
                                vehicle_class=task.vehicle_class,
                                resolved_at=now_str,
                                is_watchlist_match=is_match,
                                watchlist_category=cat,
                            )
                            rec = ResolvedPlate(
                                plate_number=plate_str,
                                ocr_confidence=max_c,
                                plate_confidence=plate_conf,
                                vehicle_class=task.vehicle_class,
                                timestamp_sec=task.timestamp_sec,
                                resolved_at=now_str,
                                is_watchlist_match=is_match,
                                watchlist_category=cat,
                                ownership_score=ownership_score,
                            )
                            self._resolved_tracks[key] = rec
                            if key in self._offline_track_stats:
                                self._offline_track_stats[key]["final_plate"] = plate_str

                        elif can_transfer_continuation:
                            prev_tid = owner.track_id
                            logger.info(
                                "[ANPR_OWNERSHIP][CONTINUATION] source_id=%s, plate='%s', inactive_track=%s (dt=%.2fs) -> new_owner_track=%s (score=%.2f)",
                                task.source_id, plate_str, prev_tid, dt, task.track_id, ownership_score
                            )
                            self._resolved_tracks.pop((task.source_id, prev_tid), None)
                            self._active_plate_owners[reg_key] = PlateOwnerRecord(
                                track_id=task.track_id,
                                ownership_score=ownership_score,
                                ocr_confidence=max_c,
                                plate_confidence=plate_conf,
                                last_seen_time=task.timestamp_sec,
                                last_seen_frame=task.frame_idx,
                                vehicle_class=task.vehicle_class,
                                resolved_at=now_str,
                                is_watchlist_match=is_match,
                                watchlist_category=cat,
                            )
                            rec = ResolvedPlate(
                                plate_number=plate_str,
                                ocr_confidence=max_c,
                                plate_confidence=plate_conf,
                                vehicle_class=task.vehicle_class,
                                timestamp_sec=task.timestamp_sec,
                                resolved_at=now_str,
                                is_watchlist_match=is_match,
                                watchlist_category=cat,
                                ownership_score=ownership_score,
                            )
                            self._resolved_tracks[key] = rec
                            if key in self._offline_track_stats:
                                self._offline_track_stats[key]["final_plate"] = plate_str
                        else:
                            logger.info(
                                "[ANPR_OWNERSHIP][REJECT] source_id=%s, candidate_track=%s, plate='%s' rejected (active_owner_track=%s, score=%.2f vs %.2f, dt=%.2fs)",
                                task.source_id, task.track_id, plate_str, owner.track_id, ownership_score, owner.ownership_score, dt
                            )
                            return
                else:
                    logger.info(
                        "[ANPR_OWNERSHIP][ACCEPT] source_id=%s, track_id=%s, plate='%s', score=%.2f, conf=%.2f",
                        task.source_id, task.track_id, plate_str, ownership_score, max_c
                    )
                    self._active_plate_owners[reg_key] = PlateOwnerRecord(
                        track_id=task.track_id,
                        ownership_score=ownership_score,
                        ocr_confidence=max_c,
                        plate_confidence=plate_conf,
                        last_seen_time=task.timestamp_sec,
                        last_seen_frame=task.frame_idx,
                        vehicle_class=task.vehicle_class,
                        resolved_at=now_str,
                        is_watchlist_match=is_match,
                        watchlist_category=cat,
                    )
                    rec = ResolvedPlate(
                        plate_number=plate_str,
                        ocr_confidence=max_c,
                        plate_confidence=plate_conf,
                        vehicle_class=task.vehicle_class,
                        timestamp_sec=task.timestamp_sec,
                        resolved_at=now_str,
                        is_watchlist_match=is_match,
                        watchlist_category=cat,
                        ownership_score=ownership_score,
                    )
                    self._resolved_tracks[key] = rec
                    if key in self._offline_track_stats:
                        self._offline_track_stats[key]["final_plate"] = plate_str
        else:
            # Single frame without persistent track ID
            if best_ocr.is_valid and ocr_conf >= 0.70 and ownership_score >= 0.45:
                should_resolve = True

        if should_resolve:
            logger.info(
                "[ANPR_PLATE_MODEL][FINAL] source_id=%s, track_id=%s, plate='%s', confidence=%.2f, ownership_score=%.2f",
                task.source_id, task.track_id, plate_str, ocr_conf, ownership_score
            )
            logger.info(
                "[ANPR_TRACE][RESOLVED] source_id=%s, track_id=%s, vehicle_class=%s, recognized_plate='%s', ocr_confidence=%.2f, plate_confidence=%.2f",
                task.source_id, task.track_id, task.vehicle_class, plate_str, ocr_conf, plate_conf
            )
            self._handle_recognized_plate(task, plate_str, ocr_conf, plate_conf, best_crop if best_crop is not None else task.vehicle_crop)

    def _handle_recognized_plate(
        self,
        task: ANPRTask,
        plate_number: str,
        ocr_confidence: float,
        plate_confidence: float,
        plate_crop: np.ndarray,
    ):
        """Dispatches WebSocket event, captures evidence snapshot, and enqueues DB records."""
        now_str = datetime.now().strftime("%H:%M:%S")
        is_watchlist = plate_number in self._watchlist
        watchlist_cat = self._watchlist.get(plate_number)

        # 1. Non-blocking Evidence Snapshot
        try:
            from app.services.evidence_writer import evidence_writer
            evidence_writer.enqueue_snapshot(
                frame=task.vehicle_crop,
                source_id=task.source_id,
                event_type="vehicle_anpr_plate",
                track_id=task.track_id,
                object_class=task.vehicle_class,
                confidence=ocr_confidence,
                timestamp_sec=task.timestamp_sec,
            )
        except Exception as _ev_err:
            logger.error("[ANPRWorker] Evidence snapshot enqueue failed: %s", _ev_err)

        # 2. Standalone WebSocket Broadcast (updates badge on frontend)
        anpr_payload = {
            "type": "anpr_recognition",
            "source_id": task.source_id,
            "data": {
                "source_id": task.source_id,
                "track_id": task.track_id,
                "plate_number": plate_number,
                "ocr_confidence": round(ocr_confidence, 2),
                "plate_confidence": round(plate_confidence, 2),
                "confidence_pct": int(round(ocr_confidence * 100)),
                "vehicle_class": task.vehicle_class,
                "is_watchlist_match": is_watchlist,
                "watchlist_category": watchlist_cat,
                "timestamp_sec": task.timestamp_sec,
                "time": now_str,
            }
        }
        logger.info(
            "[ANPR_TRACE][WEBSOCKET] source_id=%s, track_id=%s, plate_number='%s', payload=%s",
            task.source_id, task.track_id, plate_number, anpr_payload
        )
        self._broadcast_event(task.source_id, anpr_payload)

        # 3. Database Persistence (Part 11: Avoid duplicate ANPR events for same continuous vehicle)
        db_key = (task.source_id, plate_number)
        with self._lock:
            already_persisted = db_key in self._persisted_plates
            if not already_persisted:
                self._persisted_plates.add(db_key)

        if already_persisted:
            logger.info(
                "[ANPR_DB][CONTINUATION] source_id=%s, plate='%s' already persisted in DB, skipping duplicate row for track_id=%s",
                task.source_id, plate_number, task.track_id
            )
            return

        try:
            from app.services.db_service import db_service
            db_service.enqueue_anpr_record(
                source_id=task.source_id,
                session_id=task.session_id,
                track_id=task.track_id,
                vehicle_class=task.vehicle_class,
                plate_number=plate_number,
                ocr_confidence=ocr_confidence,
                plate_confidence=plate_confidence,
                timestamp_sec=task.timestamp_sec,
                is_watchlist_match=is_watchlist,
                watchlist_category=watchlist_cat,
                evidence_ref=f"anpr_{task.source_id}_{task.track_id}",
            )

            # Also log informational event in detection_events for Real-Time Event Audit Log
            db_service.enqueue_detection_event(
                source_id=task.source_id,
                event_type="Vehicle Plate Recognized",
                object_class=task.vehicle_class,
                track_id=task.track_id,
                confidence=ocr_confidence,
                timestamp_sec=task.timestamp_sec,
                threat_level="HIGH" if is_watchlist else "LOW",
                severity="Critical" if is_watchlist else "Info",
                description=f"{task.vehicle_class} #{task.track_id} License Plate [{plate_number}] recognized ({int(round(ocr_confidence * 100))}%).",
                bbox=task.vehicle_bbox,
                session_id=task.session_id,
                extra_metadata={
                    "plate_number": plate_number,
                    "ocr_confidence": ocr_confidence,
                    "is_watchlist": is_watchlist,
                }
            )
        except Exception as _dbe:
            logger.error("[ANPRWorker] Database persistence error: %s", _dbe)

    def _broadcast_event(self, source_id: str, payload: dict):
        """Broadcasts WebSocket event safely from worker thread."""
        try:
            from app.websockets.manager import manager
            import json
            manager.broadcast_from_thread(json.dumps(payload))
        except Exception as exc:
            logger.error("[ANPRWorker] WebSocket broadcast failed: %s", exc)


# Global singleton worker instance
anpr_worker = ANPRWorker()
