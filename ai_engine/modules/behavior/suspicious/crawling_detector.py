"""
Crawling Detector — Suspicious Activity Detection Engine
--------------------------------------------------------
Detects sustained prone human locomotion (crawling, sneaking along ground)
using perspective-normalized body posture geometry, ground locomotion kinematics,
and temporal persistence calculated from TrackHistoryBuffer observations.

Key Design Principles:
  1. True Posture + Locomotion Dual Verification:
     Crawling is NEVER determined by bounding-box shrinkage alone.
     A person is evaluated as crawling ONLY when:
       (A) Body posture is genuinely prone (horizontal body orientation or
           verified low-body drop from an established standing baseline).
           Strict guard: Upright aspect ratio (AR <= 0.65) is NEVER prone.
       (B) Ground locomotion is in crawling range (0.015 to 0.65 body-heights/sec).
           Fast locomotion (> 0.65 body-heights/sec) is walking/running, NOT crawling.
       (C) Locomotion and prone posture persist for >= min_crawling_duration_sec (0.8s).
  2. Support for Entering Frame Already Crawling:
     When a person enters the frame already prone (no upright history),
     a strongly prone aspect ratio (AR >= 1.10) confirms prone geometry directly.
  3. Running / Walking False Positive Immunity:
     Running strides and perspective changes that temporarily reduce bbox height
     are rejected because their aspect ratio remains upright (AR <= 0.65) and/or
     their speed exceeds crawling bounds.
  4. Temporal Persistence (Time-Based, FPS-Invariant):
     Measured using media timestamp_sec progression across any frame rate.
  5. One Event Per Episode:
     Emits exactly one CrawlingDetection per continuous crawling episode.
     Resets only after returning to upright for stop_duration_sec.
  6. Pure Standard Library:
     Zero ML models, zero pose inference, zero OpenCV, zero numpy.
"""

from __future__ import annotations

import logging
import math
import threading
from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from ai_engine.modules.behavior.suspicious.track_history import (
    TrackHistoryBuffer,
    TrackObservation,
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Default Calibration Parameters
# ──────────────────────────────────────────────────────────────────────────────

# Minimum time (seconds) in prone locomotion to confirm crawling. FPS-invariant.
DEFAULT_MIN_CRAWLING_DURATION_SEC: float = 0.75

# --- Posture Geometry Parameters ---
# Strongly prone aspect ratio (width / height >= 1.05) indicates horizontal body
DEFAULT_MIN_PRONE_ASPECT_RATIO: float = 1.05

# Moderately prone aspect ratio (width / height >= 0.75) for diagonal crawling or drop from standing
DEFAULT_MODERATE_PRONE_ASPECT_RATIO: float = 0.75

# Aspect ratio ceiling at or below which posture is strictly upright (CANNOT be prone)
DEFAULT_UPRIGHT_ASPECT_CEILING: float = 0.65

# Aspect ratio below which a frame is considered clearly upright for standing baseline
DEFAULT_STANDING_ASPECT_RATIO: float = 0.55

# Maximum relative height (curr_h / standing_h) to qualify as dropped posture
DEFAULT_MAX_RELATIVE_HEIGHT: float = 0.65

# Upper sanity guard for aspect ratio
DEFAULT_MAX_ASPECT_RATIO: float = 6.0

# --- Ground Locomotion Parameters ---
# Minimum ground speed in [body-heights / sec] (rejects stationary lying/sitting)
DEFAULT_MIN_HORIZONTAL_SPEED: float = 0.015

# Upper speed bound for crawling (above this is walking/running, NOT crawling)
DEFAULT_MAX_CRAWLING_SPEED: float = 0.55

# Duration of upright posture required to reset state back to NOT_CRAWLING
DEFAULT_STOP_DURATION_SEC: float = 0.80

# Minimum history observations before starting evaluation
DEFAULT_MIN_HISTORY_OBSERVATIONS: int = 3

# Bbox dimension change ratio above which the frame is considered a tracking glitch
DEFAULT_MAX_BOX_CHANGE_RATIO: float = 2.5

# Maximum gap between observations (seconds) before episode reset
DEFAULT_MAX_OBSERVATION_GAP_SEC: float = 1.5


@dataclass(slots=True, frozen=True)
class CrawlingDetection:
    """
    Immutable event emitted when crawling is confirmed for a tracked person.
    """
    track_id: int
    source_id: str
    timestamp_sec: float
    frame_index: int
    duration_sec: float
    aspect_ratio: float
    relative_height: float
    horizontal_speed: float
    activity: str = "CRAWLING"
    confidence: float = 1.0


class _TrackCrawlState:
    """Internal per-track state for crawling detection and hysteresis."""
    __slots__ = (
        "state",
        "crawl_start_ts",
        "crawl_start_point",
        "last_seen_ts",
        "last_confirmed_ts",
        "upright_start_ts",
        "last_processed_ts",
        "standing_height_baseline",
        "standing_width_baseline",
        "last_observation_ts",
    )

    def __init__(self):
        self.state: str = "NOT_CRAWLING"
        self.crawl_start_ts: Optional[float] = None
        self.crawl_start_point: Optional[Tuple[float, float]] = None
        self.last_seen_ts: float = 0.0
        self.last_confirmed_ts: Optional[float] = None
        self.upright_start_ts: Optional[float] = None
        self.last_processed_ts: Optional[float] = None
        self.standing_height_baseline: Optional[float] = None
        self.standing_width_baseline: Optional[float] = None
        self.last_observation_ts: Optional[float] = None


class CrawlingDetector:
    """
    Posture-and-locomotion verified, FPS-invariant, perspective-robust crawling detector.

    Consumes observations from TrackHistoryBuffer and emits CrawlingDetection events.
    """

    def __init__(
        self,
        min_crawling_duration_sec: float = DEFAULT_MIN_CRAWLING_DURATION_SEC,
        min_prone_aspect_ratio: float = DEFAULT_MIN_PRONE_ASPECT_RATIO,
        moderate_prone_aspect_ratio: float = DEFAULT_MODERATE_PRONE_ASPECT_RATIO,
        upright_aspect_ceiling: float = DEFAULT_UPRIGHT_ASPECT_CEILING,
        max_relative_height: float = DEFAULT_MAX_RELATIVE_HEIGHT,
        min_horizontal_speed: float = DEFAULT_MIN_HORIZONTAL_SPEED,
        max_crawling_speed: float = DEFAULT_MAX_CRAWLING_SPEED,
        standing_aspect_ratio: float = DEFAULT_STANDING_ASPECT_RATIO,
        stop_duration_sec: float = DEFAULT_STOP_DURATION_SEC,
        min_history_observations: int = DEFAULT_MIN_HISTORY_OBSERVATIONS,
        max_box_change_ratio: float = DEFAULT_MAX_BOX_CHANGE_RATIO,
        max_observation_gap_sec: float = DEFAULT_MAX_OBSERVATION_GAP_SEC,
        # Legacy compat parameter aliases
        min_aspect_ratio: Optional[float] = None,
        max_aspect_ratio: float = DEFAULT_MAX_ASPECT_RATIO,
        min_geometric_signals: int = 2,
        aspect_ratio_change_multiplier: float = 1.5,
        max_area_ratio: float = 0.70,
    ):
        if min_crawling_duration_sec <= 0:
            raise ValueError(f"min_crawling_duration_sec must be positive, got {min_crawling_duration_sec}")

        self.min_crawling_duration_sec = float(min_crawling_duration_sec)
        self.min_prone_aspect_ratio = float(min_aspect_ratio) if min_aspect_ratio is not None else float(min_prone_aspect_ratio)
        self.moderate_prone_aspect_ratio = float(moderate_prone_aspect_ratio)
        self.upright_aspect_ceiling = float(upright_aspect_ceiling)
        self.max_relative_height = float(max_relative_height)
        self.min_horizontal_speed = float(min_horizontal_speed)
        self.max_crawling_speed = float(max_crawling_speed)
        self.standing_aspect_ratio = float(standing_aspect_ratio)
        self.stop_duration_sec = float(stop_duration_sec)
        self.min_history_observations = int(min_history_observations)
        self.max_box_change_ratio = float(max_box_change_ratio)
        self.max_observation_gap_sec = float(max_observation_gap_sec)
        self.max_aspect_ratio = float(max_aspect_ratio)

        # Legacy attributes kept for property inspection
        self.min_aspect_ratio = self.min_prone_aspect_ratio
        self.min_geometric_signals = min_geometric_signals
        self.aspect_ratio_change_multiplier = aspect_ratio_change_multiplier
        self.max_area_ratio = max_area_ratio

        self._lock = threading.RLock()
        # Internal state map: { source_id: { track_id: _TrackCrawlState } }
        self._states: Dict[str, Dict[int, _TrackCrawlState]] = {}

    def _get_track_state(self, source_id: str, track_id: int) -> _TrackCrawlState:
        if source_id not in self._states:
            self._states[source_id] = {}
        if track_id not in self._states[source_id]:
            self._states[source_id][track_id] = _TrackCrawlState()
        return self._states[source_id][track_id]

    def process_observation(
        self,
        source_id: str,
        observation: Optional[TrackObservation],
        history_buffer: TrackHistoryBuffer,
    ) -> Optional[CrawlingDetection]:
        """
        Evaluates a single new observation against the track's history for crawling behavior.

        Returns a CrawlingDetection when confirmed, else None.
        """
        if observation is None:
            return None

        # Rule 1: Only PERSON class is evaluated
        if observation.class_name != "person":
            return None

        # Rule 2: Must have a valid track_id
        if observation.track_id is None:
            return None

        track_id = observation.track_id

        with self._lock:
            tstate = self._get_track_state(source_id, track_id)

            # Avoid duplicate evaluation on the exact same frame timestamp
            if (
                tstate.last_processed_ts is not None
                and observation.timestamp_sec <= tstate.last_processed_ts
            ):
                return None

            tstate.last_seen_ts = observation.timestamp_sec
            tstate.last_processed_ts = observation.timestamp_sec

            # Retrieve chronological history
            history = history_buffer.get_history(source_id, track_id)
            if len(history) < self.min_history_observations:
                return None

            prev_obs = history[-2]
            curr_obs = observation

            # Rule 3: Bounding-box consistency guard (tracking glitch rejection)
            h_prev, h_curr = prev_obs.height, curr_obs.height
            w_prev, w_curr = prev_obs.width, curr_obs.width

            if h_prev <= 0 or h_curr <= 0 or w_prev <= 0 or w_curr <= 0:
                return None

            h_ratio = max(h_prev, h_curr) / min(h_prev, h_curr)
            w_ratio = max(w_prev, w_curr) / min(w_prev, w_curr)
            if h_ratio > self.max_box_change_ratio or w_ratio > self.max_box_change_ratio:
                # Extreme box size anomaly — reset candidate crawl timer
                tstate.crawl_start_ts = None
                tstate.crawl_start_point = None
                return None

            # Rule 4: Track gap guard
            if tstate.last_observation_ts is not None:
                gap = curr_obs.timestamp_sec - tstate.last_observation_ts
                if gap > self.max_observation_gap_sec:
                    tstate.crawl_start_ts = None
                    tstate.crawl_start_point = None

            tstate.last_observation_ts = curr_obs.timestamp_sec

            curr_aspect = curr_obs.aspect_ratio
            curr_height = float(curr_obs.height)

            # ── Standing Baseline Update ──────────────────────────────────────
            # Update baseline ONLY from clearly upright frames (AR <= standing_aspect_ratio)
            if curr_aspect <= self.standing_aspect_ratio and curr_height > 0:
                if tstate.standing_height_baseline is None or curr_height > tstate.standing_height_baseline:
                    tstate.standing_height_baseline = curr_height
                if tstate.standing_width_baseline is None or curr_obs.width > tstate.standing_width_baseline:
                    tstate.standing_width_baseline = float(curr_obs.width)

            # ── Evaluate Prone Posture ────────────────────────────────────────
            # Posture Condition 1: Strongly prone by aspect ratio (horizontal orientation)
            is_strongly_prone = (curr_aspect >= self.min_prone_aspect_ratio)

            # Posture Condition 2: Dropped from verified standing baseline
            is_dropped_prone = False
            if tstate.standing_height_baseline is not None and tstate.standing_height_baseline > 0:
                rel_h = curr_height / tstate.standing_height_baseline
                if rel_h <= self.max_relative_height and curr_aspect >= self.moderate_prone_aspect_ratio:
                    is_dropped_prone = True

            # Posture Condition 3: Diagonal prone / start-already-crawling (AR in moderate prone range)
            is_diagonal_prone = (curr_aspect >= self.moderate_prone_aspect_ratio)

            # Strict Upright Guard: If aspect ratio is upright (<= upright_aspect_ceiling),
            # it is physically IMPOSSIBLE to be prone (e.g. standing/walking/running stride deformation)
            is_prone_posture = (
                (is_strongly_prone or is_dropped_prone or is_diagonal_prone)
                and (curr_aspect > self.upright_aspect_ceiling)
                and (curr_aspect <= self.max_aspect_ratio)
            )

            baseline_height = tstate.standing_height_baseline if tstate.standing_height_baseline else curr_height
            if baseline_height <= 0:
                return None

            curr_bottom_center = curr_obs.bottom_center

            if is_prone_posture:
                tstate.upright_start_ts = None

                # Initialize candidate crawl episode
                if tstate.crawl_start_ts is None or tstate.crawl_start_point is None:
                    tstate.crawl_start_ts = curr_obs.timestamp_sec
                    tstate.crawl_start_point = curr_bottom_center

                elapsed_crawl_time = curr_obs.timestamp_sec - tstate.crawl_start_ts

                # ── Ground Locomotion Verification ────────────────────────────
                # Net ground displacement from episode start point
                dx = curr_bottom_center[0] - tstate.crawl_start_point[0]
                dy = curr_bottom_center[1] - tstate.crawl_start_point[1]
                ground_dist_px = math.sqrt(dx * dx + dy * dy)

                if elapsed_crawl_time > 0.05:
                    avg_speed_norm = (ground_dist_px / elapsed_crawl_time) / baseline_height
                else:
                    avg_speed_norm = 0.0

                # Locomotion must be within genuine crawling speed bounds
                # Reject stationary postures (speed < min) AND fast walking/running (speed > max)
                has_locomotion = (self.min_horizontal_speed <= avg_speed_norm <= self.max_crawling_speed)

                # ── Temporal Persistence Confirmation ─────────────────────────
                if (
                    tstate.state == "NOT_CRAWLING"
                    and elapsed_crawl_time >= self.min_crawling_duration_sec
                    and has_locomotion
                ):
                    # Transition to CRAWLING_CONFIRMED — emit exactly once
                    tstate.state = "CRAWLING_CONFIRMED"
                    tstate.last_confirmed_ts = curr_obs.timestamp_sec

                    rel_height = curr_height / baseline_height
                    confidence = self._compute_confidence(curr_aspect, rel_height, avg_speed_norm, elapsed_crawl_time)

                    logger.info(
                        "[CRAWLING_CONFIRMED] Source '%s' Track #%d: "
                        "Aspect=%.2f RelH=%.2f Speed=%.2f h/s Duration=%.2fs baseline_h=%.0fpx",
                        source_id,
                        track_id,
                        curr_aspect,
                        rel_height,
                        avg_speed_norm,
                        elapsed_crawl_time,
                        baseline_height,
                    )

                    return CrawlingDetection(
                        track_id=track_id,
                        source_id=source_id,
                        timestamp_sec=curr_obs.timestamp_sec,
                        frame_index=curr_obs.frame_index,
                        duration_sec=round(elapsed_crawl_time, 3),
                        aspect_ratio=round(curr_aspect, 3),
                        relative_height=round(rel_height, 3),
                        horizontal_speed=round(avg_speed_norm, 3),
                        activity="CRAWLING",
                        confidence=confidence,
                    )

            else:
                # Not in prone posture (person is standing, walking, running, upright)
                tstate.crawl_start_ts = None
                tstate.crawl_start_point = None

                if tstate.upright_start_ts is None:
                    tstate.upright_start_ts = curr_obs.timestamp_sec

                # Hysteresis reset: remain upright for stop_duration_sec → reset to NOT_CRAWLING
                if tstate.state == "CRAWLING_CONFIRMED":
                    upright_elapsed = curr_obs.timestamp_sec - tstate.upright_start_ts
                    if upright_elapsed >= self.stop_duration_sec:
                        tstate.state = "NOT_CRAWLING"
                        tstate.upright_start_ts = None
                        logger.debug(
                            "[CRAWLING_RESET] Source '%s' Track #%d returned to NOT_CRAWLING",
                            source_id,
                            track_id,
                        )

            return None

    def _compute_confidence(
        self,
        aspect_ratio: float,
        rel_height: float,
        speed_norm: float,
        elapsed_sec: float,
    ) -> float:
        """
        Computes a confidence score based on posture distinctiveness,
        locomotion consistency, and duration.
        """
        # Posture score: higher aspect ratio & lower relative height -> higher confidence
        ar_score = min(1.0, max(0.0, (aspect_ratio - 0.85) / 1.0))
        h_score = min(1.0, max(0.0, (1.0 - rel_height) / 0.5))
        posture_score = 0.6 * ar_score + 0.4 * h_score

        # Duration score: saturates at 2x minimum duration
        duration_score = min(1.0, elapsed_sec / (self.min_crawling_duration_sec * 2.0))

        # Locomotion score: positive for verified movement
        loco_score = min(1.0, speed_norm / 0.25) if speed_norm > 0 else 0.0

        combined = 0.45 * posture_score + 0.35 * duration_score + 0.20 * loco_score
        return round(max(0.70, min(0.98, combined * 0.30 + 0.68)), 4)

    def process_track(
        self,
        source_id: str,
        track_id: int,
        history_buffer: TrackHistoryBuffer,
    ) -> Optional[CrawlingDetection]:
        """
        Convenience method: evaluates the latest observation for track_id in source_id.
        """
        latest = history_buffer.get_latest(source_id, track_id)
        return self.process_observation(source_id, latest, history_buffer)

    def get_track_state(self, source_id: str, track_id: int) -> str:
        """Returns 'NOT_CRAWLING' or 'CRAWLING_CONFIRMED'."""
        with self._lock:
            state = self._states.get(source_id, {}).get(track_id)
            return state.state if state else "NOT_CRAWLING"

    def clear_track(self, source_id: str, track_id: int) -> bool:
        """Removes state for a specific track. Returns True if removed."""
        with self._lock:
            if source_id in self._states and track_id in self._states[source_id]:
                del self._states[source_id][track_id]
                return True
            return False

    def clear_source(self, source_id: str) -> int:
        """Removes all track states for a source. Returns count of removed tracks."""
        with self._lock:
            if source_id in self._states:
                count = len(self._states[source_id])
                del self._states[source_id]
                return count
            return 0

    def cleanup(
        self,
        source_id: str,
        active_track_ids: Optional[Set[int]] = None,
        current_timestamp_sec: Optional[float] = None,
        max_stale_seconds: float = 3.0,
    ) -> Set[int]:
        """Removes tracks that are no longer active or stale. Returns set of pruned track IDs."""
        with self._lock:
            if source_id not in self._states:
                return set()
            active = active_track_ids if active_track_ids is not None else set()
            curr_ts = current_timestamp_sec if current_timestamp_sec is not None else 0.0
            pruned = set()
            for tid, state in list(self._states[source_id].items()):
                if tid not in active:
                    if (curr_ts - state.last_seen_ts) > max_stale_seconds:
                        pruned.add(tid)
                        del self._states[source_id][tid]
            return pruned

    cleanup_stale_tracks = cleanup
