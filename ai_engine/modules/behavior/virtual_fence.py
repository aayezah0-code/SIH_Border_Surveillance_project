import logging
from dataclasses import dataclass
from typing import Optional, Tuple, List
import cv2
import numpy as np

logger = logging.getLogger(__name__)

@dataclass
class FenceConfig:
    type: str  # 'zone' or 'line'
    points: List[Tuple[float, float]]  # normalized coordinates (x, y) [0.0 - 1.0]
    loitering_duration: Optional[float] = None  # in seconds (e.g. 10.0, 20.0, 30.0, 60.0, 300.0)

class VirtualFenceRegistry:
    """
    In-memory registry to store virtual fence configurations per video source.
    Also tracks which objects are currently inside the zone or have crossed the line
    to prevent duplicate alerts, and manages loitering timers for UNKNOWN_PERSONs.
    """
    def __init__(self):
        # Maps source_id -> FenceConfig
        self._configs: dict[str, FenceConfig] = {}
        # Maps source_id -> set of track_ids currently inside the zone
        self._active_intrusions: dict[str, set[int]] = {}
        # Maps source_id -> dict of track_id -> last seen bottom-center (x,y)
        self._last_positions: dict[str, dict[int, Tuple[float, float]]] = {}
        # Maps source_id -> set of track_ids that have crossed the line recently
        self._line_crossed: dict[str, set[int]] = {}
        # Maps source_id -> dict of track_id -> timestamp_sec when track first entered zone
        self._zone_dwell_start: dict[str, dict[int, float]] = {}
        # Maps source_id -> set of track_ids that have already triggered a loitering alert in their current stay
        self._loitering_alerted: dict[str, set[int]] = {}
        # Maps source_id -> dict of track_id -> last seen timestamp_sec in frame
        self._last_seen_time: dict[str, dict[int, float]] = {}

    def set_fence(self, source_id: str, fence_type: str, points: List[Tuple[float, float]], loitering_duration: Optional[float] = None):
        if not points:
            self.clear_fence(source_id)
            return
            
        self._configs[source_id] = FenceConfig(type=fence_type, points=points, loitering_duration=loitering_duration)
        self._active_intrusions[source_id] = set()
        self._last_positions[source_id] = {}
        self._line_crossed[source_id] = set()
        self._zone_dwell_start[source_id] = {}
        self._loitering_alerted[source_id] = set()
        self._last_seen_time[source_id] = {}
        logger.info(f"[Virtual Fence] Set {fence_type} for source '{source_id}' with {len(points)} points (loitering: {loitering_duration}s)")

    def clear_fence(self, source_id: str):
        self._configs.pop(source_id, None)
        self._active_intrusions.pop(source_id, None)
        self._last_positions.pop(source_id, None)
        self._line_crossed.pop(source_id, None)
        self._zone_dwell_start.pop(source_id, None)
        self._loitering_alerted.pop(source_id, None)
        self._last_seen_time.pop(source_id, None)
        logger.info(f"[Virtual Fence] Cleared fence for source '{source_id}'")

    def get_fence(self, source_id: str) -> Optional[FenceConfig]:
        return self._configs.get(source_id)

    def prepare_for_source(self, source_id: str):
        """Called when a new analysis run starts for a source to clear previous state."""
        self._active_intrusions[source_id] = set()
        self._last_positions[source_id] = {}
        self._line_crossed[source_id] = set()
        self._zone_dwell_start[source_id] = {}
        self._loitering_alerted[source_id] = set()
        self._last_seen_time[source_id] = {}

    def _segments_intersect(self, p1, p2, p3, p4) -> bool:
        """Helper to check if line segment (p1, p2) intersects with (p3, p4)."""
        def ccw(A, B, C):
            return (C[1] - A[1]) * (B[0] - A[0]) > (B[1] - A[1]) * (C[0] - A[0])
        return ccw(p1, p3, p4) != ccw(p2, p3, p4) and ccw(p1, p2, p3) != ccw(p1, p2, p4)

    def check_intrusion(
        self, 
        source_id: str, 
        track_id: int, 
        bbox_norm: Tuple[float, float, float, float],
        frame_width: int,
        frame_height: int
    ) -> Optional[str]:
        """
        Checks if the tracked object caused an intrusion event.
        Returns the event type ('zone_intrusion' or 'line_crossing') if a NEW event occurred, else None.
        """
        config = self.get_fence(source_id)
        if not config or not config.points:
            return None

        # Calculate coordinates in normalized and pixel space
        nx1, ny1, nx2, ny2 = bbox_norm
        nx_center = (nx1 + nx2) / 2.0
        ny_bottom = ny2
        ny_top = ny1
        ny_center = (ny1 + ny2) / 2.0
        
        # Test key points of bounding box (center, bottom, top, and corners)
        pts_to_test = [
            (float(nx_center * frame_width), float(ny_bottom * frame_height)), # bottom-center (feet/ground)
            (float(nx_center * frame_width), float(ny_center * frame_height)), # center
            (float(nx_center * frame_width), float(ny_top * frame_height)),    # top-center (head)
            (float(nx1 * frame_width), float(ny1 * frame_height)),             # top-left
            (float(nx2 * frame_width), float(ny1 * frame_height)),             # top-right
            (float(nx1 * frame_width), float(ny2 * frame_height)),             # bottom-left
            (float(nx2 * frame_width), float(ny2 * frame_height)),             # bottom-right
        ]
        current_pt = pts_to_test[0]

        event_type = None

        if config.type == 'zone' and len(config.points) >= 3:
            # Check point in polygon using denormalized pixel coordinates
            pixel_poly_points = [(float(px * frame_width), float(py * frame_height)) for (px, py) in config.points]
            poly = np.array(pixel_poly_points, dtype=np.float32)
            
            # Returns +1 for inside, 0 for edge, -1 for outside
            is_inside = any(cv2.pointPolygonTest(poly, pt, measureDist=False) >= 0 for pt in pts_to_test)
            
            if source_id not in self._active_intrusions:
                self._active_intrusions[source_id] = set()
            currently_tracked = track_id in self._active_intrusions[source_id]

            if is_inside and not currently_tracked:
                # NEW intrusion
                self._active_intrusions[source_id].add(track_id)
                event_type = 'zone_intrusion'
            elif not is_inside and currently_tracked:
                # Object left the zone
                self._active_intrusions[source_id].remove(track_id)

        elif config.type == 'line' and len(config.points) >= 2:
            pixel_line_points = [(float(px * frame_width), float(py * frame_height)) for (px, py) in config.points]
            if source_id not in self._last_positions:
                self._last_positions[source_id] = {}
            if source_id not in self._line_crossed:
                self._line_crossed[source_id] = set()
                
            last_pt = self._last_positions[source_id].get(track_id)
            if last_pt:
                # Only alert once per track_id for line crossing
                if track_id not in self._line_crossed[source_id]:
                    pts = pixel_line_points
                    for i in range(len(pts) - 1):
                        if self._segments_intersect(last_pt, current_pt, pts[i], pts[i+1]):
                            event_type = 'line_crossing'
                            self._line_crossed[source_id].add(track_id)
                            break

            # Update last position
            self._last_positions[source_id][track_id] = current_pt

        return event_type

    def check_loitering(
        self,
        source_id: str,
        track_id: int,
        current_timestamp_sec: float,
        is_person: bool = True,
    ) -> Optional[dict]:
        """
        Evaluates loitering duration for an UNKNOWN_PERSON inside an active restricted zone.
        Returns a dict with {'duration': float, 'threshold': float} if a NEW loitering alert 
        should fire, else None.
        
        Strict Requirements:
        - Only applies to restricted zones (type == 'zone') with loitering_duration > 0.
        - KNOWN_PERSON / authorized military personnel are strictly EXEMPT (never triggers).
        - If face recognition is still pending, withholds alert until identity resolves.
        - Emits exactly ONE alert per continuous stay inside the zone.
        """
        if not is_person:
            return None

        # Update last seen timestamp for this track
        if source_id not in self._last_seen_time:
            self._last_seen_time[source_id] = {}
        self._last_seen_time[source_id][track_id] = current_timestamp_sec

        config = self.get_fence(source_id)
        if not config or config.type != 'zone' or not config.loitering_duration or config.loitering_duration <= 0:
            return None

        active_zone_tracks = self._active_intrusions.get(source_id, set())
        if track_id not in active_zone_tracks:
            # Person is not inside zone; clear dwell timer if present
            if source_id in self._zone_dwell_start:
                self._zone_dwell_start[source_id].pop(track_id, None)
            if source_id in self._loitering_alerted:
                self._loitering_alerted[source_id].discard(track_id)
            return None

        # Check Face Recognition identity state
        try:
            from ai_engine.modules.recognition.face_worker import face_worker
            identity = face_worker.get_track_identity(source_id, track_id)
        except Exception:
            identity = None

        # 1. KNOWN_PERSON exemption: Authorized personnel NEVER trigger loitering
        if identity and identity.get("status") == "KNOWN_PERSON":
            if source_id in self._zone_dwell_start:
                self._zone_dwell_start[source_id].pop(track_id, None)
            if source_id in self._loitering_alerted:
                self._loitering_alerted[source_id].discard(track_id)
            return None

        # 2. Track entry time for UNKNOWN_PERSON
        if source_id not in self._zone_dwell_start:
            self._zone_dwell_start[source_id] = {}

        if track_id not in self._zone_dwell_start[source_id]:
            self._zone_dwell_start[source_id][track_id] = current_timestamp_sec

        dwell_start = self._zone_dwell_start[source_id][track_id]
        elapsed = current_timestamp_sec - dwell_start

        # 3. Check if configured loitering duration is reached
        if elapsed >= config.loitering_duration:
            # If identity is still pending/unresolved and we're early in grace window, withhold
            if identity is None and elapsed < 5.0:
                return None

            if source_id not in self._loitering_alerted:
                self._loitering_alerted[source_id] = set()

            if track_id not in self._loitering_alerted[source_id]:
                self._loitering_alerted[source_id].add(track_id)
                return {
                    "duration": round(elapsed, 1),
                    "threshold": config.loitering_duration,
                }

        return None

    def cleanup_exited_tracks(self, source_id: str, current_frame_track_ids: set[int], current_timestamp_sec: float = 0.0):
        """
        Cleans up dwell timers and loitering alerted flags for tracks that have exited 
        the restricted zone or disappeared from tracking for a sustained period.
        """
        active_in_zone = self._active_intrusions.get(source_id, set())

        if source_id in self._zone_dwell_start:
            for tid in list(self._zone_dwell_start[source_id].keys()):
                # Confirmed out of polygon
                is_out_of_zone = tid not in active_in_zone
                # Disappeared from frame for sustained time (> 3.0s)
                last_seen = self._last_seen_time.get(source_id, {}).get(tid, current_timestamp_sec)
                has_disappeared = (current_timestamp_sec - last_seen) > 3.0

                if is_out_of_zone or (tid not in current_frame_track_ids and has_disappeared):
                    self._zone_dwell_start[source_id].pop(tid, None)
                    if source_id in self._loitering_alerted:
                        self._loitering_alerted[source_id].discard(tid)

fence_registry = VirtualFenceRegistry()
