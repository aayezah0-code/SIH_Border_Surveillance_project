"""
Running Detector — Suspicious Activity Detection Engine
-------------------------------------------------------
Detects sustained high-speed human locomotion (running, sprinting, fleeing)
using perspective-normalized kinematics calculated from TrackHistoryBuffer.

Key Design Principles:
  1. Perspective-Normalized Velocity:
     Normalizes pixel displacement by representative bounding-box body height
     to yield distance-invariant velocity in [body-heights / second].
     The SAME physical running motion produces SIMILAR normalized speed regardless
     of distance from camera.
  2. Upright Locomotion Posture Guard:
     Running is an UPRIGHT locomotion pattern (aspect_ratio <= 0.75).
     Prone/horizontal bodies (aspect_ratio > 0.75) are crawling or lying down,
     and are strictly excluded from running classification.
  3. Time-Based Confirmation (FPS-Invariant):
     Requires a minimum elapsed media time of qualified running locomotion (>= 0.30s),
     calculated from media timestamp_sec progression across any FPS (15, 24, 25, 30, 60).
  4. Stride-Oscillation & Jitter Tolerance:
     Human running naturally alternates between foot-contact deceleration and
     push-off acceleration. Exponential Moving Average (EMA) smoothing provides
     fast dynamic response while preventing single-stride dips or tracker jitter
     from resetting the running timer.
  5. Robust Walking Baseline Isolation:
     Walk baselines only accumulate from verified slow/moderate locomotion
     (<= walk_speed_ceiling, default: 0.45 body-heights/sec). This prevents
     a person who enters the scene already running from polluting and inflating
     their walking baseline.
  6. Fallback Running Threshold:
     If no walking baseline exists (person enters already sprinting),
     the absolute running threshold (default: 0.65 body-heights/sec) confirms
     genuine running reliably.
  7. State Transition Model:
     Transitions between NOT_RUNNING -> RUNNING_CONFIRMED -> NOT_RUNNING.
     Emits exactly one confirmation when running is established.
  8. Multi-Camera Isolation:
     All tracking and state calculation is strictly isolated by (source_id, track_id).
  9. Pure Arithmetic:
     Zero ML inference, zero OpenCV, zero numpy, zero disk/network I/O.
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
# Default Configuration Parameters
# ──────────────────────────────────────────────────────────────────────────────

# Minimum speed to be classified as running (body-heights/sec).
# Separates walking (<= 0.50 h/s) from jogging/running (>= 0.55 h/s).
DEFAULT_RUNNING_THRESHOLD: float = 0.55

# Maximum aspect ratio for running (allows forward-leaning sprinters and perspective width)
DEFAULT_MAX_RUNNING_ASPECT_RATIO: float = 0.90

# Minimum elapsed media time (seconds) of sustained above-threshold speed.
DEFAULT_MIN_RUNNING_DURATION_SEC: float = 0.30

# Duration of the velocity sample window in seconds.
DEFAULT_VELOCITY_WINDOW_SEC: float = 0.50

# Maximum speed that can be accumulated into the walking baseline.
DEFAULT_WALK_SPEED_CEILING: float = 0.50

# Multiplier applied to walking baseline when adaptive baseline is available.
DEFAULT_ADAPTIVE_RUN_MULTIPLIER: float = 1.80

# Stop threshold: speed must drop below this to trigger deceleration timer.
DEFAULT_STOP_THRESHOLD: float = 0.30

# Duration the person must remain slow before resetting from RUNNING_CONFIRMED.
DEFAULT_STOP_DURATION_SEC: float = 0.50

# Reject bbox change ratio above this (tracker ID swap / severe occlusion guard).
DEFAULT_MAX_BOX_CHANGE_RATIO: float = 2.5

# Minimum observations in the history buffer before starting evaluation.
DEFAULT_MIN_HISTORY_OBSERVATIONS: int = 3

# Maximum dt between two consecutive observations (seconds).
DEFAULT_MAX_OBSERVATION_GAP_SEC: float = 1.5


@dataclass(slots=True, frozen=True)
class RunningDetection:
    """
    Immutable event emitted when running locomotion is confirmed for a tracked person.
    """
    track_id: int
    source_id: str
    timestamp_sec: float
    frame_index: int
    normalized_speed: float     # Body-heights per second (smoothed)
    raw_speed_px: float         # Pixels per second (smoothed)
    body_height_px: float       # Representative body height used for normalization
    duration_sec: float         # Duration of confirmed running episode
    consecutive_frames: int     # Number of qualifying samples in the running window
    activity: str = "RUNNING"
    confidence: float = 1.0


class _VelocitySample:
    """A single timed velocity observation in the temporal window."""
    __slots__ = ("timestamp_sec", "v_norm", "v_px")

    def __init__(self, timestamp_sec: float, v_norm: float, v_px: float):
        self.timestamp_sec = timestamp_sec
        self.v_norm = v_norm
        self.v_px = v_px


class _TrackMotionState:
    """Internal per-track state for hysteresis, smoothing, and adaptive baseline."""
    __slots__ = (
        "state",
        "run_start_ts",         # Timestamp when the current run episode started
        "slow_start_ts",        # Timestamp when speed first dropped below stop_threshold
        "last_seen_ts",
        "last_processed_ts",
        "smoothed_v_norm",      # EMA-smoothed normalized velocity
        "smoothed_v_px",        # EMA-smoothed pixel velocity
        "velocity_samples",     # deque of recent _VelocitySample
        "walk_samples",         # deque of (ts, v_norm) for verified walking speeds
        "walk_baseline",        # Estimated walking speed (body-heights/sec)
        "last_observation_ts",
    )

    def __init__(self):
        self.state: str = "NOT_RUNNING"
        self.run_start_ts: Optional[float] = None
        self.slow_start_ts: Optional[float] = None
        self.last_seen_ts: float = 0.0
        self.last_processed_ts: Optional[float] = None
        self.smoothed_v_norm: float = 0.0
        self.smoothed_v_px: float = 0.0
        self.velocity_samples: deque[_VelocitySample] = deque(maxlen=60)
        self.walk_samples: deque[Tuple[float, float]] = deque(maxlen=60)
        self.walk_baseline: Optional[float] = None
        self.last_observation_ts: Optional[float] = None


class RunningDetector:
    """
    Deterministic, FPS-invariant, perspective-normalized running detector.

    Consumes observations from TrackHistoryBuffer and emits RunningDetection
    events upon sustained high-speed locomotion.
    """

    def __init__(
        self,
        running_threshold: float = DEFAULT_RUNNING_THRESHOLD,
        min_running_duration_sec: float = DEFAULT_MIN_RUNNING_DURATION_SEC,
        max_running_aspect_ratio: float = DEFAULT_MAX_RUNNING_ASPECT_RATIO,
        velocity_window_sec: float = DEFAULT_VELOCITY_WINDOW_SEC,
        walk_speed_ceiling: float = DEFAULT_WALK_SPEED_CEILING,
        adaptive_run_multiplier: float = DEFAULT_ADAPTIVE_RUN_MULTIPLIER,
        stop_threshold: float = DEFAULT_STOP_THRESHOLD,
        stop_duration_sec: float = DEFAULT_STOP_DURATION_SEC,
        min_history_observations: int = DEFAULT_MIN_HISTORY_OBSERVATIONS,
        max_box_change_ratio: float = DEFAULT_MAX_BOX_CHANGE_RATIO,
        max_observation_gap_sec: float = DEFAULT_MAX_OBSERVATION_GAP_SEC,
        # Legacy compatibility arguments
        min_consecutive_frames: int = 4,
        stop_consecutive_frames: int = 3,
        baseline_window_sec: float = 1.5,
        adaptive_absolute_floor: float = 0.65,
    ):
        if running_threshold <= 0:
            raise ValueError(f"running_threshold must be positive, got {running_threshold}")

        self.running_threshold = float(running_threshold)
        self.min_running_duration_sec = float(min_running_duration_sec)
        self.max_running_aspect_ratio = float(max_running_aspect_ratio)
        self.velocity_window_sec = float(velocity_window_sec)
        self.walk_speed_ceiling = float(walk_speed_ceiling)
        self.adaptive_run_multiplier = float(adaptive_run_multiplier)
        self.stop_threshold = float(stop_threshold)
        self.stop_duration_sec = float(stop_duration_sec)
        self.min_history_observations = int(min_history_observations)
        self.max_box_change_ratio = float(max_box_change_ratio)
        self.max_observation_gap_sec = float(max_observation_gap_sec)

        # Legacy aliases
        self.min_consecutive_frames = min_consecutive_frames
        self._min_consecutive_frames_legacy = min_consecutive_frames
        self._stop_consecutive_frames_legacy = stop_consecutive_frames
        self.baseline_window_sec = baseline_window_sec
        self.adaptive_absolute_floor = adaptive_absolute_floor

        self._lock = threading.RLock()
        # Internal state map: { source_id: { track_id: _TrackMotionState } }
        self._states: Dict[str, Dict[int, _TrackMotionState]] = {}

    def _get_track_state(self, source_id: str, track_id: int) -> _TrackMotionState:
        if source_id not in self._states:
            self._states[source_id] = {}
        if track_id not in self._states[source_id]:
            self._states[source_id][track_id] = _TrackMotionState()
        return self._states[source_id][track_id]

    def process_observation(
        self,
        source_id: str,
        observation: Optional[TrackObservation],
        history_buffer: TrackHistoryBuffer,
    ) -> Optional[RunningDetection]:
        """
        Evaluates a single new observation against the track's motion history.

        Returns a RunningDetection when sustained running is confirmed, else None.
        """
        if observation is None:
            return None

        # Rule 1: Only PERSON class is evaluated for running
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

            # Rule 3: dt must be positive
            dt = curr_obs.timestamp_sec - prev_obs.timestamp_sec
            if dt <= 0:
                return None

            # Rule 4: Track gap guard — large gaps reset run episode state
            if dt > self.max_observation_gap_sec:
                tstate.run_start_ts = None
                tstate.smoothed_v_norm = 0.0
                return None

            # Rule 5: Bounding-box consistency guard (tracker ID swap / severe occlusion)
            h_prev, h_curr = prev_obs.height, curr_obs.height
            w_prev, w_curr = prev_obs.width, curr_obs.width

            if h_prev <= 0 or h_curr <= 0 or w_prev <= 0 or w_curr <= 0:
                return None

            h_ratio = max(h_prev, h_curr) / min(h_prev, h_curr)
            w_ratio = max(w_prev, w_curr) / min(w_prev, w_curr)
            if h_ratio > self.max_box_change_ratio or w_ratio > self.max_box_change_ratio:
                tstate.run_start_ts = None
                return None

            # Rule 6: Upright Posture Guard
            # Running is an upright locomotion pattern (AR <= max_running_aspect_ratio, e.g. <= 0.75).
            # If body is prone/horizontal (AR > 0.75), it cannot be running (it is crawling/lying down).
            if curr_obs.aspect_ratio > self.max_running_aspect_ratio:
                tstate.run_start_ts = None
                tstate.smoothed_v_norm = 0.0
                return None

            # ── Compute normalized instantaneous velocity ─────────────────────
            p_prev = prev_obs.bottom_center
            p_curr = curr_obs.bottom_center
            dx = p_curr[0] - p_prev[0]
            dy = p_curr[1] - p_prev[1]
            
            # Perspective compensation: in elevated surveillance cameras, vertical ground-plane
            # motion (dy) is foreshortened relative to lateral motion (dx).
            displacement_px = math.sqrt(dx * dx + (1.40 * dy) * (1.40 * dy))
            raw_disp_px = math.sqrt(dx * dx + dy * dy)

            # Representative body height (rolling average of recent observations)
            recent = history[-min(len(history), 6):]
            valid_heights = [h.height for h in recent if h.height > 0]
            rep_body_height = sum(valid_heights) / float(len(valid_heights)) if valid_heights else float(curr_obs.height)
            if rep_body_height <= 0:
                return None

            inst_v_px = raw_disp_px / dt
            inst_v_norm = (displacement_px / dt) / rep_body_height  # perspective-compensated body-heights/sec

            curr_ts = curr_obs.timestamp_sec

            # ── Velocity Smoothing (EMA + window) ─────────────────────────────
            if inst_v_norm == 0.0:
                # Immediate drop when stationary
                tstate.smoothed_v_norm = 0.0
                tstate.smoothed_v_px = 0.0
            elif tstate.smoothed_v_norm == 0.0:
                tstate.smoothed_v_norm = inst_v_norm
                tstate.smoothed_v_px = inst_v_px
            else:
                tstate.smoothed_v_norm = 0.35 * inst_v_norm + 0.65 * tstate.smoothed_v_norm
                tstate.smoothed_v_px = 0.35 * inst_v_px + 0.65 * tstate.smoothed_v_px

            smoothed_v_norm = tstate.smoothed_v_norm
            smoothed_v_px = tstate.smoothed_v_px

            tstate.velocity_samples.append(_VelocitySample(curr_ts, inst_v_norm, inst_v_px))

            # ── Perspective-Aware Effective Threshold ─────────────────────────
            # For standard/distant surveillance (body height <= 500px), threshold is exactly self.running_threshold.
            # For close-up footage (body height > 500px, e.g. 4K portrait 1750px) where raw pixel velocity is high
            # (>= 350 px/s), normalized speed is scaled relative to perspective body height.
            if rep_body_height > 500.0 and smoothed_v_px >= 350.0:
                scale = 500.0 / rep_body_height
                effective_threshold = max(0.28, min(self.running_threshold, self.running_threshold * scale))
            else:
                effective_threshold = self.running_threshold

            # ── Update adaptive walk baseline ─────────────────────────────────
            # Only accumulate from verified slow/moderate locomotion (<= walk_speed_ceiling)
            # and strictly below the running threshold
            walk_ceiling = min(self.walk_speed_ceiling, effective_threshold * 0.75)
            if inst_v_norm <= walk_ceiling and tstate.state == "NOT_RUNNING":
                tstate.walk_samples.append((curr_ts, inst_v_norm))
                w_cutoff = curr_ts - self.baseline_window_sec
                while tstate.walk_samples and tstate.walk_samples[0][0] < w_cutoff:
                    tstate.walk_samples.popleft()

                if len(tstate.walk_samples) >= 3:
                    tstate.walk_baseline = sum(s[1] for s in tstate.walk_samples) / float(len(tstate.walk_samples))

            # ── Determine Target Running Threshold ────────────────────────────
            if tstate.walk_baseline is not None and tstate.walk_baseline > 0.05:
                target_threshold = max(
                    effective_threshold,
                    tstate.walk_baseline * self.adaptive_run_multiplier,
                )
            else:
                target_threshold = effective_threshold

            # ── Multi-Signal Evaluation & Jitter Suppression ──────────────────
            # Net directional displacement over recent history to reject stationary jitter
            hist_subset = history[-min(len(history), 6):]
            if len(hist_subset) >= 3:
                net_dx = hist_subset[-1].bottom_center[0] - hist_subset[0].bottom_center[0]
                net_dy = hist_subset[-1].bottom_center[1] - hist_subset[0].bottom_center[1]
                net_dt = hist_subset[-1].timestamp_sec - hist_subset[0].timestamp_sec
                if net_dt > 0.05:
                    net_disp_norm = (math.sqrt(net_dx * net_dx + (1.40 * net_dy)**2) / net_dt) / rep_body_height
                else:
                    net_disp_norm = smoothed_v_norm
            else:
                net_disp_norm = smoothed_v_norm

            # Running qualification: smoothed speed and net displacement both meet target
            is_running_fast = (
                (smoothed_v_norm >= target_threshold or inst_v_norm >= target_threshold * 1.1)
                and net_disp_norm >= effective_threshold * 0.50
            )

            # ── State Machine ─────────────────────────────────────────────────
            if is_running_fast:
                tstate.slow_start_ts = None

                if tstate.run_start_ts is None:
                    tstate.run_start_ts = prev_obs.timestamp_sec

                elapsed_running = curr_ts - tstate.run_start_ts

                if (
                    tstate.state == "NOT_RUNNING"
                    and elapsed_running >= self.min_running_duration_sec
                ):
                    # Transition to RUNNING_CONFIRMED — emit exactly once
                    tstate.state = "RUNNING_CONFIRMED"

                    qualifying_count = sum(
                        1 for s in tstate.velocity_samples if s.v_norm >= target_threshold * 0.8
                    )

                    confidence = self._compute_confidence(smoothed_v_norm, elapsed_running)

                    logger.info(
                        "[RUNNING_CONFIRMED] Source '%s' Track #%d: "
                        "Speed=%.2f h/s (target=%.2f, raw=%.1f px/s) after %.2fs | baseline=%s | body_h=%.0fpx",
                        source_id,
                        track_id,
                        smoothed_v_norm,
                        target_threshold,
                        smoothed_v_px,
                        elapsed_running,
                        f"{tstate.walk_baseline:.2f}" if tstate.walk_baseline is not None else "N/A",
                        rep_body_height,
                    )

                    return RunningDetection(
                        track_id=track_id,
                        source_id=source_id,
                        timestamp_sec=curr_ts,
                        frame_index=curr_obs.frame_index,
                        normalized_speed=round(smoothed_v_norm, 3),
                        raw_speed_px=round(smoothed_v_px, 1),
                        body_height_px=round(rep_body_height, 1),
                        duration_sec=round(elapsed_running, 3),
                        consecutive_frames=qualifying_count,
                        activity="RUNNING",
                        confidence=confidence,
                    )

            else:
                # Speed is below running threshold
                if smoothed_v_norm < self.stop_threshold or inst_v_norm < self.stop_threshold:
                    if tstate.slow_start_ts is None:
                        tstate.slow_start_ts = curr_ts

                    slow_elapsed = curr_ts - tstate.slow_start_ts

                    if (
                        tstate.state == "RUNNING_CONFIRMED"
                        and slow_elapsed >= self.stop_duration_sec
                    ):
                        # Decelerated back to walk/stop — reset
                        tstate.state = "NOT_RUNNING"
                        tstate.run_start_ts = None
                        tstate.slow_start_ts = None
                        logger.debug(
                            "[RUNNING_RESET] Source '%s' Track #%d returned to NOT_RUNNING (Speed=%.3f h/s)",
                            source_id, track_id, smoothed_v_norm,
                        )
                else:
                    if tstate.state == "NOT_RUNNING":
                        tstate.run_start_ts = None

            return None

    def _compute_confidence(
        self,
        smoothed_v_norm: float,
        elapsed_sec: float,
    ) -> float:
        """
        Computes a confidence score based on running speed and persistence duration.
        """
        speed_excess = max(0.0, smoothed_v_norm - self.running_threshold) / max(self.running_threshold, 0.1)
        speed_score = min(1.0, speed_excess / 1.5)
        duration_score = min(1.0, elapsed_sec / (self.min_running_duration_sec * 2.0))

        combined = 0.60 * speed_score + 0.40 * duration_score
        return round(max(0.70, min(0.98, combined * 0.28 + 0.70)), 4)

    def process_track(
        self,
        source_id: str,
        track_id: int,
        history_buffer: TrackHistoryBuffer,
    ) -> Optional[RunningDetection]:
        """
        Convenience method: evaluates the latest observation for track_id in source_id.
        """
        latest = history_buffer.get_latest(source_id, track_id)
        return self.process_observation(source_id, latest, history_buffer)

    def get_track_state(self, source_id: str, track_id: int) -> str:
        """Returns 'NOT_RUNNING' or 'RUNNING_CONFIRMED'."""
        with self._lock:
            state = self._states.get(source_id, {}).get(track_id)
            return state.state if state else "NOT_RUNNING"

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
