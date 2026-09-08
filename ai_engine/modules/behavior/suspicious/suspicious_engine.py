"""
Unified Suspicious Activity Engine — Sentinel AI Surveillance Platform
------------------------------------------------------------------------
Orchestrates spatial-temporal suspicious activity detection across video sources.
Coordinates TrackHistoryBuffer, RunningDetector, CrawlingDetector, and ThrowingDetector.

Key Design Principles:
  1. Pipeline Abstraction:
     Consumes tracked detections from the YOLOv8 + ByteTrack pipeline
     (e.g., FrameDetections, list of DetectionResult, or dictionaries).
  2. Pure Telemetry Ingestion:
     Extracts primitive spatial-temporal bounding-box telemetry into TrackHistoryBuffer.
     Zero raw frame storage, zero numpy copies, zero OpenCV/ML dependencies.
  3. Class-Based Dispatch & Routing:
     - "person" tracks -> RunningDetector and CrawlingDetector
     - "person" + candidate throwable objects -> ThrowingDetector
     - Vehicles (car, truck, bus, etc.) and non-throwable classes are strictly ignored
     - Missing track IDs and invalid bounding boxes are safely rejected without crashing
  4. Robust Detector Failure Isolation:
     Individual detector errors are caught, logged, and isolated. A failure in RunningDetector
     never halts Crawling or Throwing detection.
  5. Normalized Event Model:
     Emits immutable SuspiciousActivityEvent objects with standardized activity values
     ("RUNNING", "CRAWLING", "THROWING") while preserving detector-specific telemetry in metadata.
  6. Duplicate & Episode Protection:
     Guarantees that each continuous suspicious activity episode emits exactly once.
     Re-arming occurs only when the subject clearly resets back to normal behavior.
  7. Multi-Source Isolation:
     All tracking, internal states, and duplicate filters are strictly isolated by source_id.
"""

from __future__ import annotations

import logging
import math
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from ai_engine.modules.behavior.suspicious.track_history import (
    TrackHistoryBuffer,
    TrackObservation,
)
from ai_engine.modules.behavior.suspicious.running_detector import (
    RunningDetector,
    RunningDetection,
)
from ai_engine.modules.behavior.suspicious.crawling_detector import (
    CrawlingDetector,
    CrawlingDetection,
)
from ai_engine.modules.behavior.suspicious.throwing_detector import (
    ThrowingDetector,
    ThrowingDetection,
)

logger = logging.getLogger(__name__)

# Canonical Normalized Activity Literals
ACTIVITY_RUNNING: str = "RUNNING"
ACTIVITY_CRAWLING: str = "CRAWLING"
ACTIVITY_THROWING: str = "THROWING"

VALID_ACTIVITIES: Set[str] = {
    ACTIVITY_RUNNING,
    ACTIVITY_CRAWLING,
    ACTIVITY_THROWING,
}


@dataclass(slots=True, frozen=True)
class SuspiciousActivityEvent:
    """
    Immutable structured event emitted upon confirmed suspicious activity.
    Standardized across Running, Crawling, and Throwing detectors.
    """
    activity: str                           # "RUNNING", "CRAWLING", "THROWING"
    source_id: str                          # Camera feed or stream identifier
    track_id: int                           # Primary subject track ID (person)
    timestamp_sec: float                    # Media / stream timestamp in seconds
    confidence: float                       # Detection confidence [0.0 - 1.0]
    metadata: Dict[str, Any]                # Detector-specific telemetry dictionary
    object_track_id: Optional[int] = None   # For throwing: track ID of the thrown object
    frame_index: int = 0                    # Sequential frame index
    score: float = 1.0                      # Threat / confidence score [0.0 - 1.0]

    def to_dict(self) -> Dict[str, Any]:
        """Serializes event to a standard dictionary."""
        return {
            "activity": self.activity,
            "source_id": self.source_id,
            "track_id": self.track_id,
            "object_track_id": self.object_track_id,
            "timestamp_sec": round(self.timestamp_sec, 3),
            "frame_index": self.frame_index,
            "confidence": round(self.confidence, 4),
            "score": round(self.score, 4),
            "metadata": dict(self.metadata),
        }


def _running_to_event(detection: RunningDetection) -> SuspiciousActivityEvent:
    """Converts a confirmed RunningDetection into a normalized SuspiciousActivityEvent."""
    return SuspiciousActivityEvent(
        activity=ACTIVITY_RUNNING,
        source_id=detection.source_id,
        track_id=detection.track_id,
        timestamp_sec=detection.timestamp_sec,
        confidence=detection.confidence,
        score=detection.confidence,
        frame_index=detection.frame_index,
        metadata={
            "normalized_speed": detection.normalized_speed,
            "raw_speed_px": detection.raw_speed_px,
            "body_height_px": detection.body_height_px,
            "duration_sec": detection.duration_sec,
            "consecutive_frames": detection.consecutive_frames,
        },
    )


def _crawling_to_event(detection: CrawlingDetection) -> SuspiciousActivityEvent:
    """Converts a confirmed CrawlingDetection into a normalized SuspiciousActivityEvent."""
    return SuspiciousActivityEvent(
        activity=ACTIVITY_CRAWLING,
        source_id=detection.source_id,
        track_id=detection.track_id,
        timestamp_sec=detection.timestamp_sec,
        confidence=detection.confidence,
        score=detection.confidence,
        frame_index=detection.frame_index,
        metadata={
            "aspect_ratio": detection.aspect_ratio,
            "relative_height": detection.relative_height,
            "horizontal_speed": detection.horizontal_speed,
            "duration_sec": detection.duration_sec,
        },
    )


def _throwing_to_event(detection: ThrowingDetection) -> SuspiciousActivityEvent:
    """Converts a confirmed ThrowingDetection into a normalized SuspiciousActivityEvent."""
    return SuspiciousActivityEvent(
        activity=ACTIVITY_THROWING,
        source_id=detection.source_id,
        track_id=detection.person_track_id,
        object_track_id=detection.object_track_id,
        timestamp_sec=detection.timestamp_sec,
        confidence=detection.confidence,
        score=detection.score,
        frame_index=detection.frame_index,
        metadata={
            "object_class": detection.object_class,
            "object_speed_normalized": detection.object_speed_normalized,
            "person_speed_normalized": detection.person_speed_normalized,
            "separation": detection.separation,
            "trajectory_consistency": detection.trajectory_consistency,
            "duration_sec": detection.duration_sec,
        },
    )


class SuspiciousActivityEngine:
    """
    Unified coordinator for suspicious activity detectors across surveillance feeds.
    Thread-safe, bounded, zero-overhead pipeline wrapper.
    """

    def __init__(
        self,
        history_buffer: Optional[TrackHistoryBuffer] = None,
        running_detector: Optional[RunningDetector] = None,
        crawling_detector: Optional[CrawlingDetector] = None,
        throwing_detector: Optional[ThrowingDetector] = None,
        enable_running: bool = True,
        enable_crawling: bool = True,
        enable_throwing: bool = True,
        duplicate_cooldown_sec: float = 0.5,
    ):
        self.history_buffer = history_buffer if history_buffer is not None else TrackHistoryBuffer()
        self.running_detector = running_detector if running_detector is not None else RunningDetector()
        self.crawling_detector = crawling_detector if crawling_detector is not None else CrawlingDetector()
        self.throwing_detector = throwing_detector if throwing_detector is not None else ThrowingDetector()

        self.enable_running = bool(enable_running)
        self.enable_crawling = bool(enable_crawling)
        self.enable_throwing = bool(enable_throwing)
        self.duplicate_cooldown_sec = float(duplicate_cooldown_sec)

        self._lock = threading.RLock()
        # Duplicate frame guard: { source_id: (last_frame_index, last_timestamp_sec) }
        self._last_frame_info: Dict[str, Tuple[int, float]] = {}
        # Duplicate event cooldown tracking: { (source_id, activity, track_id, object_track_id): last_emitted_ts }
        self._last_emitted_event_ts: Dict[Tuple[str, str, int, Optional[int]], float] = {}
        # Error log throttle tracking: { error_key: last_log_ts }
        self._last_error_log_ts: Dict[str, float] = {}

    def process_frame(
        self,
        source_id: str,
        frame_data: Any,
        timestamp_sec: Optional[float] = None,
        frame_index: Optional[int] = None,
    ) -> List[SuspiciousActivityEvent]:
        """
        Main entry point for suspicious activity detection on a frame.
        Extracts detections, feeds TrackHistoryBuffer, dispatches to detectors,
        and returns confirmed SuspiciousActivityEvent instances.

        Parameters
        ----------
        source_id : str
            Camera or stream source identifier.
        frame_data : Any
            FrameDetections instance, list of DetectionResult, or dictionary containing detections.
        timestamp_sec : Optional[float]
            Stream / media timestamp in seconds. Inferred from frame_data if omitted.
        frame_index : Optional[int]
            Sequential frame index. Inferred from frame_data if omitted.

        Returns
        -------
        List[SuspiciousActivityEvent]
            List of newly confirmed suspicious activity events (if any).
        """
        if not source_id or frame_data is None:
            return []

        # ── 1. Unpack frame_data container ──────────────────────────────────
        raw_detections: List[Any] = []
        inferred_ts: float = timestamp_sec if timestamp_sec is not None else 0.0
        inferred_idx: int = frame_index if frame_index is not None else 0

        if hasattr(frame_data, "detections"):
            raw_detections = getattr(frame_data, "detections", [])
            if timestamp_sec is None:
                inferred_ts = float(getattr(frame_data, "timestamp_sec", 0.0))
            if frame_index is None:
                inferred_idx = int(getattr(frame_data, "frame_index", 0))
        elif isinstance(frame_data, list):
            raw_detections = frame_data
        elif isinstance(frame_data, dict):
            raw_detections = frame_data.get("detections", [])
            if timestamp_sec is None:
                inferred_ts = float(frame_data.get("timestamp_sec", 0.0))
            if frame_index is None:
                inferred_idx = int(frame_data.get("frame_index", 0))
        else:
            return []

        # ── 2. Duplicate Frame Protection ───────────────────────────────────
        with self._lock:
            last = self._last_frame_info.get(source_id)
            if last is not None and last[0] == inferred_idx and last[1] == inferred_ts:
                logger.debug(
                    "[SUSPICIOUS_ENGINE] Duplicate frame submission ignored (source='%s', frame=%d, ts=%.3f)",
                    source_id, inferred_idx, inferred_ts
                )
                return []
            self._last_frame_info[source_id] = (inferred_idx, inferred_ts)

        if not raw_detections:
            return []

        # ── 3. Parse and Feed Observations to TrackHistoryBuffer ────────────
        active_observations: List[TrackObservation] = []
        person_observations: List[TrackObservation] = []
        object_observations: List[TrackObservation] = []

        for det in raw_detections:
            if det is None:
                continue

            # Safely extract track_id
            track_id = getattr(det, "track_id", None)
            if track_id is None and isinstance(det, dict):
                track_id = det.get("track_id")

            if track_id is None:
                # Untracked detections cannot have temporal history
                continue

            # Safely validate bounding box dimensions
            try:
                if hasattr(det, "x1"):
                    x1, y1, x2, y2 = det.x1, det.y1, det.x2, det.y2
                elif isinstance(det, dict) and "bbox" in det:
                    x1, y1, x2, y2 = det["bbox"]
                elif isinstance(det, dict):
                    x1, y1, x2, y2 = det.get("x1", 0), det.get("y1", 0), det.get("x2", 0), det.get("y2", 0)
                else:
                    continue

                if math.isnan(x1) or math.isnan(y1) or math.isnan(x2) or math.isnan(y2):
                    continue
                if x2 <= x1 or y2 <= y1:
                    continue
            except (TypeError, ValueError):
                continue

            # Update TrackHistoryBuffer (pure numeric telemetry only, NO raw frames)
            obs = self.history_buffer.update(
                source_id=source_id,
                detection=det,
                timestamp_sec=inferred_ts,
                frame_index=inferred_idx,
            )
            if obs is not None:
                active_observations.append(obs)
                if obs.class_name == "person":
                    person_observations.append(obs)
                else:
                    object_observations.append(obs)

        # ── 4. Dispatch to Detectors with Failure Isolation ─────────────────
        confirmed_events: List[SuspiciousActivityEvent] = []

        # 4A. Running Detector
        if self.enable_running and person_observations:
            for p_obs in person_observations:
                try:
                    res = self.running_detector.process_observation(
                        source_id=source_id,
                        observation=p_obs,
                        history_buffer=self.history_buffer,
                    )
                    if res is not None:
                        event = _running_to_event(res)
                        if self._check_and_record_event(event):
                            confirmed_events.append(event)
                except Exception as e:
                    self._log_throttled_error("RUNNING_ERROR", source_id, f"Person Track #{p_obs.track_id}", e, inferred_ts)

        # 4B. Crawling Detector (with Behavioral Mutual Exclusion)
        if self.enable_crawling and person_observations:
            for p_obs in person_observations:
                # Step 3: Prevent crawling confirmation if subject is actively confirmed running
                if self.enable_running and self.running_detector.get_track_state(source_id, p_obs.track_id) == "RUNNING_CONFIRMED":
                    continue

                try:
                    res = self.crawling_detector.process_observation(
                        source_id=source_id,
                        observation=p_obs,
                        history_buffer=self.history_buffer,
                    )
                    if res is not None:
                        event = _crawling_to_event(res)
                        if self._check_and_record_event(event):
                            confirmed_events.append(event)
                except Exception as e:
                    self._log_throttled_error("CRAWLING_ERROR", source_id, f"Person Track #{p_obs.track_id}", e, inferred_ts)

        # 4C. Throwing Detector
        if self.enable_throwing and person_observations and object_observations:
            try:
                res_list = self.throwing_detector.process_frame(
                    source_id=source_id,
                    observations=active_observations,
                    history_buffer=self.history_buffer,
                )
                for t_res in res_list:
                    if t_res is not None:
                        event = _throwing_to_event(t_res)
                        if self._check_and_record_event(event):
                            confirmed_events.append(event)
            except Exception as e:
                self._log_throttled_error("THROWING_ERROR", source_id, "Frame", e, inferred_ts)

        return confirmed_events

    def _log_throttled_error(
        self,
        err_type: str,
        source_id: str,
        label: str,
        error: Exception,
        current_ts: float,
        throttle_sec: float = 2.0,
    ) -> None:
        """Logs an error with throttling to avoid log spam every frame."""
        with self._lock:
            key = f"{err_type}_{source_id}_{label}"
            last_ts = self._last_error_log_ts.get(key, -999.0)
            if (current_ts - last_ts) >= throttle_sec:
                self._last_error_log_ts[key] = current_ts
                logger.error("[SUSPICIOUS_ENGINE][%s] Source '%s' %s: %s", err_type, source_id, label, error)

    def _check_and_record_event(self, event: SuspiciousActivityEvent) -> bool:
        """
        Lightweight duplicate event guard.
        Suppresses events with the exact same activity and track keys within duplicate_cooldown_sec.
        """
        with self._lock:
            key = (event.source_id, event.activity, event.track_id, event.object_track_id)
            last_ts = self._last_emitted_event_ts.get(key)
            if last_ts is not None:
                if (event.timestamp_sec - last_ts) < self.duplicate_cooldown_sec:
                    return False
            self._last_emitted_event_ts[key] = event.timestamp_sec
            return True

    def cleanup(
        self,
        source_id: str,
        active_track_ids: Optional[Set[int]] = None,
        current_timestamp_sec: Optional[float] = None,
        max_stale_seconds: float = 3.0,
    ) -> Dict[str, Any]:
        """
        Performs stale state cleanup across TrackHistoryBuffer, all detectors,
        and internal engine deduplication maps.
        """
        with self._lock:
            pruned_history = self.history_buffer.cleanup_stale(
                source_id=source_id,
                active_track_ids=active_track_ids,
                current_timestamp_sec=current_timestamp_sec,
                max_stale_seconds=max_stale_seconds,
            )
            pruned_running = self.running_detector.cleanup(
                source_id=source_id,
                active_track_ids=active_track_ids,
                current_timestamp_sec=current_timestamp_sec,
                max_stale_seconds=max_stale_seconds,
            )
            pruned_crawling = self.crawling_detector.cleanup(
                source_id=source_id,
                active_track_ids=active_track_ids,
                current_timestamp_sec=current_timestamp_sec,
                max_stale_seconds=max_stale_seconds,
            )
            pruned_throwing = self.throwing_detector.cleanup(
                source_id=source_id,
                active_track_ids=active_track_ids,
                current_timestamp_sec=current_timestamp_sec,
                max_stale_seconds=max_stale_seconds,
            )

            # Clean stale duplicate cooldown entries
            active_ids = active_track_ids or set()
            cur_ts = current_timestamp_sec
            if cur_ts is None and source_id in self._last_frame_info:
                cur_ts = self._last_frame_info[source_id][1]
            now_ts = cur_ts or 0.0

            stale_keys = [
                k for k, ts in self._last_emitted_event_ts.items()
                if k[0] == source_id and k[2] not in active_ids and (now_ts - ts) > max_stale_seconds
            ]
            for k in stale_keys:
                del self._last_emitted_event_ts[k]

            return {
                "pruned_history_tracks": pruned_history,
                "pruned_running_tracks": pruned_running,
                "pruned_crawling_tracks": pruned_crawling,
                "pruned_throwing_pairs": pruned_throwing,
            }

    def clear_source(self, source_id: str) -> bool:
        """Purges all buffer, detector, and engine state for a source."""
        with self._lock:
            h_cleared = self.history_buffer.clear_source(source_id)
            r_cleared = self.running_detector.clear_source(source_id)
            c_cleared = self.crawling_detector.clear_source(source_id)
            t_cleared = self.throwing_detector.clear_source(source_id)
            self._last_frame_info.pop(source_id, None)

            to_del = [k for k in self._last_emitted_event_ts if k[0] == source_id]
            for k in to_del:
                del self._last_emitted_event_ts[k]

            return h_cleared or r_cleared or c_cleared or t_cleared

    def clear_track(self, source_id: str, track_id: int) -> bool:
        """Purges history and detector state for a specific track ID."""
        with self._lock:
            h_cleared = self.history_buffer.clear_track(source_id, track_id)
            r_cleared = self.running_detector.clear_track(source_id, track_id)
            c_cleared = self.crawling_detector.clear_track(source_id, track_id)
            t_cleared = self.throwing_detector.clear_track(source_id, track_id)

            to_del = [k for k in self._last_emitted_event_ts if k[0] == source_id and (k[2] == track_id or k[3] == track_id)]
            for k in to_del:
                del self._last_emitted_event_ts[k]

            return h_cleared or r_cleared or c_cleared or t_cleared
