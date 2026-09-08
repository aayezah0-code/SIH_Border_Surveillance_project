"""
Throwing Detector — Suspicious Activity Detection Engine
--------------------------------------------------------
Detects deliberate human throwing actions involving a person and a nearby object
(e.g., throwing packages over fences, tossing contraband, hurling projectiles)
using multi-signal spatial-temporal kinematics calculated from TrackHistoryBuffer.

Key Design Principles:
  1. Person-Object Proximity & Association:
     The candidate object must initially be co-located with the person
     (distance <= proximity_threshold_body_heights, default: 1.2 person heights).
     Objects that were already flying before entering proximity are rejected as fly-bys.
  2. Kinetic Disparity & Acceleration:
     At release, the object must exhibit meaningful motion
     (speed >= minimum_object_speed, default: 2.0 body-heights/sec) that exceeds
     the person's speed by a configurable factor (default: >= 2.0x).
  3. Monotonic Separation:
     The distance between person and object must consistently grow over time
     (cumulative growth >= minimum_separation_growth, default: 0.3 body-heights).
     Rejects carrying, placing down, walking away, and oscillating tracking noise.
  4. Directional Trajectory Consistency:
     The object must maintain consistent directional displacement in ballistic flight
     (cosine similarity >= minimum_trajectory_consistency, default: 0.70).
  5. Drop Rejection Guard:
     Distinguishes dropped objects from thrown objects by evaluating vertical dominance
     (dy > 0 with dy / |dx| >= threshold and horizontal speed < min_horizontal_speed).
  6. Temporal Confirmation & No Event Flooding:
     Requires N consecutive qualifying observations (default: 3-4 frames) to confirm.
     Emits exactly ONE ThrowingDetection event per continuous throw episode.
  7. Multi-Camera & Track Isolation:
     All candidate states strictly isolated by (source_id, person_track_id, object_track_id).
  8. Pure Standard Library:
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

# Default Calibration Parameters
DEFAULT_PROXIMITY_THRESHOLD_BODY_HEIGHTS: float = 1.2   # Maximum initial distance (in body heights) between person & object
DEFAULT_MINIMUM_OBJECT_SPEED: float = 1.2               # Minimum object speed in [body-heights / second] (calibrated for high-res & close-up footage)
DEFAULT_OBJECT_TO_PERSON_SPEED_RATIO: float = 2.0       # Object speed must exceed person speed by at least 2.0x
DEFAULT_MINIMUM_SEPARATION_GROWTH: float = 0.25         # Minimum cumulative distance increase in body heights
DEFAULT_MINIMUM_TRAJECTORY_CONSISTENCY: float = 0.65    # Minimum cosine similarity between successive/release directions
DEFAULT_CONFIRMATION_OBSERVATIONS: int = 2              # Qualifying frames required (time-based guard also applies)
DEFAULT_MIN_THROW_DURATION_SEC: float = 0.12            # Minimum throw episode duration (FPS-invariant time-based gate)
DEFAULT_MAX_CANDIDATE_DURATION_SEC: float = 3.0         # Maximum elapsed time allowed for a throw episode
DEFAULT_MAX_BOX_CHANGE_RATIO: float = 2.2               # Rejects sudden bounding box jump > 2.2x
DEFAULT_DROP_VERTICAL_DOMINANCE_THRESHOLD: float = 2.0  # Ratio dy / |dx| where dy > 0 to identify downward gravity drop
DEFAULT_MIN_THROW_HORIZONTAL_SPEED: float = 0.4         # Minimum horizontal speed in body heights/s to avoid drop rejection

# Permitted throwable object classes (COCO-style tracking labels)
DEFAULT_ALLOWED_OBJECT_CLASSES: Set[str] = {
    "backpack", "handbag", "suitcase", "bottle", "sports ball",
    "umbrella", "frisbee", "baseball bat", "baseball glove",
    "skateboard", "surfboard", "tennis racket", "box", "package",
    "ball", "rock", "stone", "cup", "book", "cell phone", "knife"
}

# Explicitly forbidden classes that must NEVER be evaluated as throwable objects
FORBIDDEN_CLASSES: Set[str] = {
    "person", "car", "truck", "bus", "train", "motorcycle",
    "bicycle", "boat", "airplane", "traffic light", "fire hydrant",
    "stop sign", "parking meter", "bench", "chair", "couch", "bed", "dining table"
}


@dataclass(slots=True, frozen=True)
class ThrowingDetection:
    """
    Immutable event emitted when a throwing action is confirmed between a person and object.
    """
    person_track_id: int
    object_track_id: int
    source_id: str
    timestamp_sec: float
    frame_index: int
    object_class: str
    duration_sec: float
    object_speed_normalized: float    # Object speed in [body-heights / sec]
    person_speed_normalized: float    # Person speed in [body-heights / sec]
    separation: float                 # Current separation distance in [body-heights]
    trajectory_consistency: float     # Cosine similarity metric [0.0 - 1.0]
    activity: str = "THROWING"
    confidence: float = 1.0
    score: float = 1.0


class _ThrowCandidateState:
    """Internal per-(person, object) candidate state machine and telemetry."""
    __slots__ = (
        "state",                   # "PERSON_OBJECT_ASSOCIATED", "RELEASE_SUSPECTED", "THROW_CONFIRMED"
        "associated_ts",           # When proximity was first established
        "release_ts",              # When release acceleration was first detected
        "release_point",           # (x, y) center of object at moment of release
        "release_vector",          # (dx, dy) unit vector of initial release
        "release_dist_norm",       # Distance at release in body heights
        "prev_dist_norm",          # Distance at previous observation
        "qualifying_count",        # Consecutive observations meeting throwing criteria
        "last_seen_ts",            # Last observation timestamp
        "last_processed_ts",       # For deduplicating exact same frame timestamps
        "confirmed_ts",            # Timestamp when confirmed
        "emitted",                 # Boolean: has confirmation event been emitted for this episode
        "trajectory_vectors",      # deque of recent displacement unit vectors
        "speed_history",           # deque of recent object speeds
        "initial_speed_was_slow",  # Ensures object was not already flying when association began
    )

    def __init__(self, associated_ts: float, initial_dist_norm: float, initial_speed_was_slow: bool = True):
        self.state: str = "PERSON_OBJECT_ASSOCIATED"
        self.associated_ts: float = associated_ts
        self.release_ts: Optional[float] = None
        self.release_point: Optional[Tuple[float, float]] = None
        self.release_vector: Optional[Tuple[float, float]] = None
        self.release_dist_norm: float = initial_dist_norm
        self.prev_dist_norm: float = initial_dist_norm
        self.qualifying_count: int = 0
        self.last_seen_ts: float = associated_ts
        self.last_processed_ts: Optional[float] = None
        self.confirmed_ts: Optional[float] = None
        self.emitted: bool = False
        self.trajectory_vectors: deque[Tuple[float, float]] = deque(maxlen=8)
        self.speed_history: deque[float] = deque(maxlen=8)
        self.initial_speed_was_slow: bool = initial_speed_was_slow


class _LogicalObjectTrack:
    """
    A throwing-local stitched trajectory for a throwable object.
    Stitches fragmented ByteTrack observations across frame intervals into a
    single coherent kinematic trajectory with a persistent logical trajectory ID.
    """
    __slots__ = (
        "logical_id",             # Unique integer ID (e.g. 1, 2, 3...)
        "logical_label",          # Human-readable label, e.g. "THROW_OBJ_1"
        "class_name",             # Object class name
        "current_bytetrack_id",   # Latest ByteTrack ID from detector
        "history",                # deque[TrackObservation]
        "last_seen_ts",           # Timestamp of latest observation
        "last_seen_frame",        # Frame index of latest observation
        "last_center",            # (center_x, center_y)
        "last_velocity",          # (vx, vy) in px/s
        "last_width",             # int
        "last_height",            # int
    )

    def __init__(self, logical_id: int, first_obs: TrackObservation):
        self.logical_id: int = logical_id
        self.logical_label: str = f"THROW_OBJ_{logical_id}"
        self.class_name: str = first_obs.class_name.strip().lower()
        self.current_bytetrack_id: int = first_obs.track_id
        self.history: deque[TrackObservation] = deque(maxlen=20)
        self.history.append(first_obs)
        self.last_seen_ts: float = first_obs.timestamp_sec
        self.last_seen_frame: int = first_obs.frame_index
        self.last_center: Tuple[float, float] = (first_obs.center_x, first_obs.center_y)
        self.last_velocity: Tuple[float, float] = (0.0, 0.0)
        self.last_width: int = first_obs.width
        self.last_height: int = first_obs.height

    def add_observation(self, obs: TrackObservation) -> None:
        dt = obs.timestamp_sec - self.last_seen_ts
        if dt > 0:
            vx = (obs.center_x - self.last_center[0]) / dt
            vy = (obs.center_y - self.last_center[1]) / dt
            self.last_velocity = (vx, vy)
        self.current_bytetrack_id = obs.track_id
        self.last_seen_ts = obs.timestamp_sec
        self.last_seen_frame = obs.frame_index
        self.last_center = (obs.center_x, obs.center_y)
        self.last_width = obs.width
        self.last_height = obs.height
        self.history.append(obs)


class ThrowingDetector:
    """
    Deterministic geometric and kinematic throwing detector.
    Consumes observations from TrackHistoryBuffer and emits ThrowingDetection events.
    """

    def __init__(
        self,
        proximity_threshold_body_heights: float = DEFAULT_PROXIMITY_THRESHOLD_BODY_HEIGHTS,
        minimum_object_speed: float = DEFAULT_MINIMUM_OBJECT_SPEED,
        object_to_person_speed_ratio: float = DEFAULT_OBJECT_TO_PERSON_SPEED_RATIO,
        minimum_separation_growth: float = DEFAULT_MINIMUM_SEPARATION_GROWTH,
        minimum_trajectory_consistency: float = DEFAULT_MINIMUM_TRAJECTORY_CONSISTENCY,
        confirmation_observations: int = DEFAULT_CONFIRMATION_OBSERVATIONS,
        max_candidate_duration_sec: float = DEFAULT_MAX_CANDIDATE_DURATION_SEC,
        max_box_change_ratio: float = DEFAULT_MAX_BOX_CHANGE_RATIO,
        allowed_object_classes: Optional[Set[str]] = None,
        drop_vertical_dominance_threshold: float = DEFAULT_DROP_VERTICAL_DOMINANCE_THRESHOLD,
        min_throw_horizontal_speed: float = DEFAULT_MIN_THROW_HORIZONTAL_SPEED,
        min_throw_duration_sec: float = DEFAULT_MIN_THROW_DURATION_SEC,
        max_stitch_gap_sec: float = 1.2,
    ):
        if proximity_threshold_body_heights <= 0:
            raise ValueError(f"proximity_threshold_body_heights must be positive, got {proximity_threshold_body_heights}")
        if minimum_object_speed <= 0:
            raise ValueError(f"minimum_object_speed must be positive, got {minimum_object_speed}")
        if confirmation_observations < 1:
            raise ValueError(f"confirmation_observations must be >= 1, got {confirmation_observations}")

        self.proximity_threshold_body_heights = float(proximity_threshold_body_heights)
        self.minimum_object_speed = float(minimum_object_speed)
        self.object_to_person_speed_ratio = float(object_to_person_speed_ratio)
        self.minimum_separation_growth = float(minimum_separation_growth)
        self.minimum_trajectory_consistency = float(minimum_trajectory_consistency)
        self.confirmation_observations = int(confirmation_observations)
        self.max_candidate_duration_sec = float(max_candidate_duration_sec)
        self.max_box_change_ratio = float(max_box_change_ratio)
        self.drop_vertical_dominance_threshold = float(drop_vertical_dominance_threshold)
        self.min_throw_horizontal_speed = float(min_throw_horizontal_speed)
        self.min_throw_duration_sec = float(min_throw_duration_sec)
        self.max_stitch_gap_sec = float(max_stitch_gap_sec)

        if allowed_object_classes is not None:
            self.allowed_object_classes = {str(c).strip().lower() for c in allowed_object_classes}
        else:
            self.allowed_object_classes = set(DEFAULT_ALLOWED_OBJECT_CLASSES)

        self._lock = threading.RLock()
        # Internal candidate state map: { source_id: { (person_track_id, logical_obj_id): _ThrowCandidateState } }
        self._candidates: Dict[str, Dict[Tuple[int, int], _ThrowCandidateState]] = {}
        # Throwing-local stitched logical tracks: { source_id: { logical_id: _LogicalObjectTrack } }
        self._logical_tracks: Dict[str, Dict[int, _LogicalObjectTrack]] = {}
        self._next_logical_id: Dict[str, int] = {}
        self._bytetrack_to_logical: Dict[str, Dict[int, int]] = {}

    def _get_rep_person_height(
        self,
        source_id: str,
        person_obs: TrackObservation,
        history_buffer: TrackHistoryBuffer,
    ) -> float:
        """Calculates smoothed representative person height over recent history."""
        history = history_buffer.get_history(source_id, person_obs.track_id)
        if history:
            recent = history[-min(len(history), 6):]
            valid_heights = [h.height for h in recent if h.height > 0]
            if valid_heights:
                return sum(valid_heights) / float(len(valid_heights))
        return float(person_obs.height) if person_obs.height > 0 else 0.0

    def _get_or_stitch_logical_track(
        self,
        source_id: str,
        obs: TrackObservation,
        rep_height: float,
    ) -> _LogicalObjectTrack:
        """
        Retrieves an existing logical object track or conservatively stitches a newly
        fragmented ByteTrack observation to an active throwing candidate trajectory.
        """
        if source_id not in self._logical_tracks:
            self._logical_tracks[source_id] = {}
            self._next_logical_id[source_id] = 1
            self._bytetrack_to_logical[source_id] = {}

        source_logical = self._logical_tracks[source_id]
        bt_map = self._bytetrack_to_logical[source_id]
        obj_cls = obs.class_name.strip().lower()

        # 1. Direct active mapping check
        if obs.track_id in bt_map:
            lid = bt_map[obs.track_id]
            if lid in source_logical and source_logical[lid].class_name == obj_cls:
                track = source_logical[lid]
                track.add_observation(obs)
                return track

        # 2. Conservative Stitching search across active logical tracks
        best_track: Optional[_LogicalObjectTrack] = None
        best_pred_dist: float = float("inf")

        curr_area = max(1.0, float(obs.width * obs.height))

        for track in source_logical.values():
            if track.class_name != obj_cls:
                continue

            dt = obs.timestamp_sec - track.last_seen_ts
            if dt <= 0 or dt > self.max_stitch_gap_sec:
                continue

            # Bounding box area ratio consistency (permits 3D rotation, rejects mismatched objects)
            prev_area = max(1.0, float(track.last_width * track.last_height))
            area_ratio = max(prev_area, curr_area) / min(prev_area, curr_area)
            if area_ratio > (self.max_box_change_ratio * 3.0):
                continue

            # Spatial & Kinematic plausibility
            dx = obs.center_x - track.last_center[0]
            dy = obs.center_y - track.last_center[1]
            disp = math.sqrt(dx * dx + dy * dy)

            has_vel = (track.last_velocity != (0.0, 0.0) and len(track.history) >= 2)
            if has_vel:
                vx, vy = track.last_velocity
                pred_x = track.last_center[0] + vx * dt
                pred_y = track.last_center[1] + vy * dt
                pred_dist = math.sqrt((obs.center_x - pred_x) ** 2 + (obs.center_y - pred_y) ** 2)

                v_speed = math.sqrt(vx * vx + vy * vy)
                dot = (dx * vx + dy * vy) / (disp * (v_speed + 1e-6))
                
                # Direction cannot reverse 180 degrees in mid-air
                if dot < -0.2:
                    continue
                # Displacement speed cap (at most 8 body heights/sec)
                max_plausible_disp = max(100.0, rep_height * 8.0 * dt)
                if disp > max_plausible_disp:
                    continue
            else:
                pred_dist = disp
                # Initial launch radius cap (at most 2.5 body heights)
                max_launch_disp = max(150.0, rep_height * 2.5)
                if disp > max_launch_disp:
                    continue

            if pred_dist < best_pred_dist:
                best_pred_dist = pred_dist
                best_track = track

        if best_track is not None:
            # Stitched match confirmed!
            bt_map[obs.track_id] = best_track.logical_id
            best_track.add_observation(obs)
            return best_track

        # 3. Create fresh logical track
        new_lid = self._next_logical_id[source_id]
        self._next_logical_id[source_id] += 1
        new_track = _LogicalObjectTrack(logical_id=new_lid, first_obs=obs)
        source_logical[new_lid] = new_track
        bt_map[obs.track_id] = new_lid
        return new_track

    def _evaluate_pair(
        self,
        source_id: str,
        person_obs: TrackObservation,
        object_track: _LogicalObjectTrack,
        history_buffer: TrackHistoryBuffer,
    ) -> Optional[ThrowingDetection]:
        """
        Internal evaluation of a person and stitched logical object trajectory.
        Must be called within self._lock.
        """
        person_track_id = person_obs.track_id
        logical_obj_id = object_track.logical_id

        # Basic ID guards
        if person_track_id is None or logical_obj_id is None:
            return None
        if person_obs.class_name != "person":
            return None

        obj_history = object_track.history
        if not obj_history:
            return None
        curr_obj = obj_history[-1]

        if person_track_id == curr_obj.track_id:
            return None

        obj_cls = curr_obj.class_name.strip().lower()
        if obj_cls == "person" or obj_cls in FORBIDDEN_CLASSES or obj_cls not in self.allowed_object_classes:
            return None

        pair_key = (person_track_id, logical_obj_id)
        if source_id not in self._candidates:
            self._candidates[source_id] = {}

        candidate = self._candidates[source_id].get(pair_key)

        # Frame deduplication
        curr_ts = curr_obj.timestamp_sec
        if candidate is not None and candidate.last_processed_ts is not None:
            if curr_ts <= candidate.last_processed_ts:
                return None

        # Representative person height for normalization
        rep_person_height = self._get_rep_person_height(source_id, person_obs, history_buffer)
        if rep_person_height <= 0:
            return None

        # Object history and kinematic retrieval
        if len(obj_history) < 2:
            # Need at least 2 object observations to calculate velocity
            # Check if within initial proximity
            dx = curr_obj.center_x - person_obs.center_x
            dy = curr_obj.center_y - person_obs.center_y
            dist_norm = math.sqrt(dx * dx + dy * dy) / rep_person_height
            if dist_norm <= self.proximity_threshold_body_heights and candidate is None:
                self._candidates[source_id][pair_key] = _ThrowCandidateState(
                    associated_ts=curr_ts,
                    initial_dist_norm=dist_norm,
                    initial_speed_was_slow=True,
                )
            return None

        prev_obj = obj_history[-2]

        # Bounding-box consistency guard for object (permits 3D orientation rotation in flight)
        if prev_obj.height <= 0 or curr_obj.height <= 0 or prev_obj.width <= 0 or curr_obj.width <= 0:
            return None
        prev_area = prev_obj.width * prev_obj.height
        curr_area = curr_obj.width * curr_obj.height
        area_ratio = max(prev_area, curr_area) / max(1.0, min(prev_area, curr_area))
        if area_ratio > (self.max_box_change_ratio * 3.0):
            # Extreme box jump glitch — reset candidate
            self._candidates[source_id].pop(pair_key, None)
            return None

        # Person history and bounding-box consistency
        pers_history = history_buffer.get_history(source_id, person_track_id)
        prev_pers = pers_history[-2] if len(pers_history) >= 2 else None
        if prev_pers is not None:
            if prev_pers.height > 0 and person_obs.height > 0 and prev_pers.width > 0 and person_obs.width > 0:
                ph_ratio = max(prev_pers.height, person_obs.height) / min(prev_pers.height, person_obs.height)
                pw_ratio = max(prev_pers.width, person_obs.width) / min(prev_pers.width, person_obs.width)
                if ph_ratio > self.max_box_change_ratio or pw_ratio > self.max_box_change_ratio:
                    self._candidates[source_id].pop(pair_key, None)
                    return None

        # Compute dt
        dt_obj = curr_obj.timestamp_sec - prev_obj.timestamp_sec
        if dt_obj <= 0:
            return None

        # Compute object velocity
        dx_obj = curr_obj.center_x - prev_obj.center_x
        dy_obj = curr_obj.center_y - prev_obj.center_y
        disp_obj_px = math.sqrt(dx_obj * dx_obj + dy_obj * dy_obj)
        v_obj_px = disp_obj_px / dt_obj
        v_obj_norm = v_obj_px / rep_person_height  # [body-heights / sec]

        # Compute person velocity
        v_pers_norm = 0.0
        if prev_pers is not None:
            dt_pers = person_obs.timestamp_sec - prev_pers.timestamp_sec
            if dt_pers > 0:
                dx_pers = person_obs.center_x - prev_pers.center_x
                dy_pers = person_obs.center_y - prev_pers.center_y
                disp_pers_px = math.sqrt(dx_pers * dx_pers + dy_pers * dy_pers)
                v_pers_norm = (disp_pers_px / dt_pers) / rep_person_height

        # Current distance between person and object
        dx_po = curr_obj.center_x - person_obs.center_x
        dy_po = curr_obj.center_y - person_obs.center_y
        dist_px = math.sqrt(dx_po * dx_po + dy_po * dy_po)
        dist_norm = dist_px / rep_person_height  # [body-heights]

        # Drop Rejection Check:
        # Downward motion (dy > 0) dominated by gravity with insufficient horizontal speed
        is_drop = False
        if dy_obj > 0 and disp_obj_px > 0:
            abs_dx = abs(dx_obj)
            v_horiz_norm = (abs_dx / dt_obj) / rep_person_height
            drop_ratio = dy_obj / (abs_dx + 1e-4)
            if (
                drop_ratio >= self.drop_vertical_dominance_threshold
                and v_horiz_norm < self.min_throw_horizontal_speed
            ):
                is_drop = True

        # State Machine Evaluation
        if candidate is None:
            # Attempt to form new association
            if dist_norm <= self.proximity_threshold_body_heights:
                was_slow = (v_obj_norm < self.minimum_object_speed)
                candidate = _ThrowCandidateState(
                    associated_ts=curr_ts,
                    initial_dist_norm=dist_norm,
                    initial_speed_was_slow=was_slow,
                )
                self._candidates[source_id][pair_key] = candidate
            return None

        # Update candidate timestamps
        candidate.last_seen_ts = curr_ts
        candidate.last_processed_ts = curr_ts

        # Candidate State 1: PERSON_OBJECT_ASSOCIATED
        if candidate.state == "PERSON_OBJECT_ASSOCIATED":
            if not candidate.initial_speed_was_slow:
                if v_obj_norm < self.minimum_object_speed:
                    candidate.initial_speed_was_slow = True
                else:
                    return None

            has_speed = (v_obj_norm >= self.minimum_object_speed)
            has_disparity = (
                v_obj_norm >= (v_pers_norm * self.object_to_person_speed_ratio)
                and (v_obj_norm - v_pers_norm) >= 0.8
            )
            has_separation = (dist_norm > candidate.prev_dist_norm or dist_norm >= candidate.release_dist_norm)
            not_drop = not is_drop
            has_disp = (disp_obj_px > 0.1)

            if has_speed and has_disparity and has_separation and not_drop and has_disp:
                # Transition to RELEASE_SUSPECTED!
                candidate.state = "RELEASE_SUSPECTED"
                candidate.release_ts = curr_ts
                candidate.release_point = (curr_obj.center_x, curr_obj.center_y)
                unit_v = (dx_obj / disp_obj_px, dy_obj / disp_obj_px)
                candidate.release_vector = unit_v
                candidate.trajectory_vectors.clear()
                candidate.trajectory_vectors.append(unit_v)
                candidate.speed_history.clear()
                candidate.speed_history.append(v_obj_norm)
                candidate.release_dist_norm = dist_norm
                candidate.prev_dist_norm = dist_norm
                candidate.qualifying_count = 1
                return None
            else:
                if dist_norm <= self.proximity_threshold_body_heights:
                    candidate.prev_dist_norm = dist_norm
                else:
                    self._candidates[source_id].pop(pair_key, None)
                return None

        # Candidate State 2: RELEASE_SUSPECTED
        elif candidate.state == "RELEASE_SUSPECTED":
            elapsed_release = curr_ts - (candidate.release_ts or curr_ts)
            if elapsed_release > self.max_candidate_duration_sec:
                self._candidates[source_id].pop(pair_key, None)
                return None

            if v_obj_norm < (self.minimum_object_speed * 0.6):
                self._candidates[source_id].pop(pair_key, None)
                return None

            if is_drop:
                self._candidates[source_id].pop(pair_key, None)
                return None

            if dist_norm < (candidate.prev_dist_norm - 0.05):
                self._candidates[source_id].pop(pair_key, None)
                return None

            if disp_obj_px > 0.1 and candidate.release_vector is not None:
                curr_unit_v = (dx_obj / disp_obj_px, dy_obj / disp_obj_px)
                rel_v = candidate.release_vector
                
                step_sim = 1.0
                if candidate.trajectory_vectors:
                    prev_v = candidate.trajectory_vectors[-1]
                    step_sim = curr_unit_v[0] * prev_v[0] + curr_unit_v[1] * prev_v[1]
                
                direct_sim = curr_unit_v[0] * rel_v[0] + curr_unit_v[1] * rel_v[1]
                same_horiz_dir = (curr_unit_v[0] * rel_v[0] >= -0.1) if abs(rel_v[0]) > 0.2 else True
                
                is_consistent = (
                    direct_sim >= self.minimum_trajectory_consistency
                    or (step_sim >= 0.50 and same_horiz_dir)
                )
                
                if not is_consistent:
                    self._candidates[source_id].pop(pair_key, None)
                    return None
                candidate.trajectory_vectors.append(curr_unit_v)
            else:
                return None

            candidate.qualifying_count += 1
            candidate.prev_dist_norm = dist_norm
            candidate.speed_history.append(v_obj_norm)

            elapsed_release = curr_ts - (candidate.release_ts or curr_ts)
            separation_growth = dist_norm - candidate.release_dist_norm
            if (
                candidate.qualifying_count >= self.confirmation_observations
                and elapsed_release >= self.min_throw_duration_sec
                and separation_growth >= self.minimum_separation_growth
            ):
                candidate.state = "THROW_CONFIRMED"
                candidate.confirmed_ts = curr_ts
                candidate.emitted = True

                duration = max(0.0, curr_ts - (candidate.release_ts or curr_ts))
                avg_speed = sum(candidate.speed_history) / float(len(candidate.speed_history))
                rel_v = candidate.release_vector
                avg_consistency = sum(
                    v[0] * rel_v[0] + v[1] * rel_v[1] for v in candidate.trajectory_vectors
                ) / float(len(candidate.trajectory_vectors))

                logger.info(
                    "[THROWING_CONFIRMED] Source '%s' Person #%d -> Object #%d (%s, Logical %s): "
                    "Speed=%.2f h/s, PersonSpeed=%.2f h/s, Separation=%.2f heights, "
                    "Consistency=%.2f, Duration=%.2fs over %d frames",
                    source_id,
                    person_track_id,
                    curr_obj.track_id,
                    curr_obj.class_name,
                    object_track.logical_label,
                    avg_speed,
                    v_pers_norm,
                    dist_norm,
                    avg_consistency,
                    duration,
                    candidate.qualifying_count,
                )

                return ThrowingDetection(
                    person_track_id=person_track_id,
                    object_track_id=curr_obj.track_id,
                    source_id=source_id,
                    timestamp_sec=curr_obj.timestamp_sec,
                    frame_index=curr_obj.frame_index,
                    object_class=curr_obj.class_name,
                    duration_sec=round(duration, 2),
                    object_speed_normalized=round(avg_speed, 2),
                    person_speed_normalized=round(v_pers_norm, 2),
                    separation=round(dist_norm, 2),
                    trajectory_consistency=round(avg_consistency, 2),
                    activity="THROWING",
                    confidence=round(curr_obj.confidence, 4),
                    score=round(curr_obj.confidence, 4),
                )

            return None

        # Candidate State 3: THROW_CONFIRMED
        elif candidate.state == "THROW_CONFIRMED":
            if (
                dist_norm <= self.proximity_threshold_body_heights
                and v_obj_norm < self.minimum_object_speed
            ):
                candidate.state = "PERSON_OBJECT_ASSOCIATED"
                candidate.emitted = False
                candidate.release_ts = None
                candidate.release_point = None
                candidate.release_vector = None
                candidate.qualifying_count = 0
                candidate.initial_speed_was_slow = True
                candidate.prev_dist_norm = dist_norm
                candidate.release_dist_norm = dist_norm
                candidate.trajectory_vectors.clear()
                candidate.speed_history.clear()
            elif (
                candidate.confirmed_ts is not None
                and (curr_ts - candidate.confirmed_ts) > (self.max_candidate_duration_sec * 2)
            ):
                self._candidates[source_id].pop(pair_key, None)

            return None

        return None

    def process_frame(
        self,
        source_id: str,
        observations: List[TrackObservation],
        history_buffer: TrackHistoryBuffer,
    ) -> List[ThrowingDetection]:
        """
        Evaluates all active detections in a frame for potential throwing events.
        Pairs persons with candidate throwable objects.

        Parameters
        ----------
        source_id : str
            Camera / stream identifier.
        observations : List[TrackObservation]
            List of observations recorded in the current frame.
        history_buffer : TrackHistoryBuffer
            Buffer holding historical observations for all tracks.

        Returns
        -------
        List[ThrowingDetection]
            List of newly confirmed throwing events in this frame (if any).
        """
        if not source_id or not observations:
            return []

        persons = [
            o for o in observations
            if o is not None and o.track_id is not None and o.class_name == "person"
        ]
        objects = [
            o for o in observations
            if o is not None and o.track_id is not None and o.class_name != "person"
            and o.class_name.strip().lower() in self.allowed_object_classes
            and o.class_name.strip().lower() not in FORBIDDEN_CLASSES
        ]

        if not persons or not objects:
            return []

        confirmed_events: List[ThrowingDetection] = []
        with self._lock:
            # Estimate representative person height from active persons
            rep_height = 0.0
            for pers in persons:
                h = self._get_rep_person_height(source_id, pers, history_buffer)
                if h > rep_height:
                    rep_height = h
            if rep_height <= 0:
                rep_height = max([float(p.height) for p in persons if p.height > 0] or [100.0])

            # Stitch throwable objects into logical trajectories
            logical_tracks: List[_LogicalObjectTrack] = []
            for obj in objects:
                lt = self._get_or_stitch_logical_track(source_id, obj, rep_height)
                logical_tracks.append(lt)

            # Evaluate each person against each active logical object track
            for pers in persons:
                for ltrack in logical_tracks:
                    event = self._evaluate_pair(source_id, pers, ltrack, history_buffer)
                    if event is not None:
                        confirmed_events.append(event)

            # Prune stale logical tracks (> 3.0s unseen)
            curr_ts = max(o.timestamp_sec for o in observations)
            if source_id in self._logical_tracks:
                stale_lids = [
                    lid for lid, lt in self._logical_tracks[source_id].items()
                    if (curr_ts - lt.last_seen_ts) > 3.0
                ]
                for lid in stale_lids:
                    del self._logical_tracks[source_id][lid]
                if source_id in self._bytetrack_to_logical:
                    self._bytetrack_to_logical[source_id] = {
                        bt_id: lid for bt_id, lid in self._bytetrack_to_logical[source_id].items()
                        if lid in self._logical_tracks[source_id]
                    }

        return confirmed_events

    def process_pair(
        self,
        source_id: str,
        person_obs: Optional[TrackObservation],
        object_obs: Optional[TrackObservation],
        history_buffer: TrackHistoryBuffer,
    ) -> Optional[ThrowingDetection]:
        """
        Evaluates a specific person-object pair for throwing kinematics.

        Parameters
        ----------
        source_id : str
            Camera / stream identifier.
        person_obs : Optional[TrackObservation]
            Observation for candidate person.
        object_obs : Optional[TrackObservation]
            Observation for candidate thrown object.
        history_buffer : TrackHistoryBuffer
            History buffer containing recent observations.

        Returns
        -------
        Optional[ThrowingDetection]
            Emits ThrowingDetection if throwing is confirmed, else None.
        """
        if not source_id or person_obs is None or object_obs is None:
            return None
        if person_obs.track_id is None or object_obs.track_id is None:
            return None
        if person_obs.class_name != "person":
            return None
        obj_cls = object_obs.class_name.strip().lower()
        if obj_cls == "person" or obj_cls in FORBIDDEN_CLASSES or obj_cls not in self.allowed_object_classes:
            return None

        with self._lock:
            rep_h = self._get_rep_person_height(source_id, person_obs, history_buffer)
            if rep_h <= 0:
                rep_h = float(person_obs.height) if person_obs.height > 0 else 100.0
            ltrack = self._get_or_stitch_logical_track(source_id, object_obs, rep_h)
            return self._evaluate_pair(source_id, person_obs, ltrack, history_buffer)

    def process_observation(
        self,
        source_id: str,
        observation: Optional[TrackObservation],
        history_buffer: TrackHistoryBuffer,
        other_observations: Optional[List[TrackObservation]] = None,
    ) -> List[ThrowingDetection]:
        """
        Evaluates an observation against active scene objects or candidates.
        If other_observations is provided, pairs observation with them;
        otherwise searches active buffered tracks in history_buffer.
        """
        if observation is None:
            return []
        all_obs = [observation]
        if other_observations:
            all_obs.extend([o for o in other_observations if o is not None])
        else:
            # Look up active tracks in history buffer
            active_ids = history_buffer.get_active_tracks(source_id)
            for tid in active_ids:
                if tid != observation.track_id:
                    latest = history_buffer.get_latest(source_id, tid)
                    if latest is not None:
                        all_obs.append(latest)

        return self.process_frame(source_id, all_obs, history_buffer)

    def get_candidate_state(self, source_id: str, person_track_id: int, object_track_id: int) -> str:
        """
        Returns candidate state for a pair:
        'NO_CANDIDATE', 'PERSON_OBJECT_ASSOCIATED', 'RELEASE_SUSPECTED', or 'THROW_CONFIRMED'.
        """
        with self._lock:
            source_cands = self._candidates.get(source_id, {})
            cand = source_cands.get((person_track_id, object_track_id))
            if cand:
                return cand.state
            bt_map = self._bytetrack_to_logical.get(source_id, {})
            if object_track_id in bt_map:
                lid = bt_map[object_track_id]
                cand = source_cands.get((person_track_id, lid))
                if cand:
                    return cand.state
            return "NO_CANDIDATE"

    def clear_pair(self, source_id: str, person_track_id: int, object_track_id: int) -> bool:
        """Removes a specific candidate pair."""
        with self._lock:
            if source_id in self._candidates:
                source_cands = self._candidates[source_id]
                removed = False
                if (person_track_id, object_track_id) in source_cands:
                    del source_cands[(person_track_id, object_track_id)]
                    removed = True
                bt_map = self._bytetrack_to_logical.get(source_id, {})
                if object_track_id in bt_map:
                    lid = bt_map[object_track_id]
                    if (person_track_id, lid) in source_cands:
                        del source_cands[(person_track_id, lid)]
                        removed = True
                return removed
            return False

    def clear_track(self, source_id: str, track_id: int) -> bool:
        """Removes all candidates involving track_id (either as person or object)."""
        with self._lock:
            if source_id not in self._candidates:
                return False
            to_delete = [
                pair for pair in self._candidates[source_id].keys()
                if pair[0] == track_id or pair[1] == track_id
            ]
            for pair in to_delete:
                del self._candidates[source_id][pair]
            return len(to_delete) > 0

    def clear_source(self, source_id: str) -> bool:
        """Removes all detector state for a source."""
        with self._lock:
            self._logical_tracks.pop(source_id, None)
            self._next_logical_id.pop(source_id, None)
            self._bytetrack_to_logical.pop(source_id, None)
            return bool(self._candidates.pop(source_id, None))

    def cleanup(
        self,
        source_id: str,
        active_track_ids: Optional[Set[int]] = None,
        current_timestamp_sec: Optional[float] = None,
        max_stale_seconds: float = 3.0,
    ) -> List[Tuple[int, int]]:
        """
        Removes candidate pairs that have disappeared for > max_stale_seconds.
        """
        active_ids = active_track_ids or set()
        pruned_pairs: List[Tuple[int, int]] = []

        with self._lock:
            source_cands = self._candidates.get(source_id)
            if not source_cands:
                return []

            if current_timestamp_sec is None:
                current_timestamp_sec = max((c.last_seen_ts for c in source_cands.values()), default=0.0)

            for pair, c in list(source_cands.items()):
                p_id, o_id = pair
                if p_id in active_ids and o_id in active_ids:
                    continue

                if (current_timestamp_sec - c.last_seen_ts) > max_stale_seconds:
                    del source_cands[pair]
                    pruned_pairs.append(pair)

            if not source_cands:
                self._candidates.pop(source_id, None)

        return pruned_pairs
