"""
Track History Buffer — Suspicious Activity Foundation
------------------------------------------------------
Lightweight, bounded in-memory sliding window history buffer for tracked
objects (persons, bags, carried items, etc.) across video sources.

Guarantees:
  - Strict maximum history cap (default: 20 observations per track).
  - Pure in-memory primitive telemetry (timestamps, coordinates, dimensions).
  - ZERO frame copies, image crops, embeddings, or heavy numpy arrays.
  - Complete per-source isolation (RTSP cameras / offline video files).
  - Stale track pruning to guarantee zero memory leaks in continuous 24/7 RTSP operation.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Default maximum history depth per track ID
DEFAULT_MAX_HISTORY: int = 20

# Default seconds of inactivity before a disappeared track is considered stale
DEFAULT_MAX_STALE_SECONDS: float = 3.0


@dataclass(slots=True, frozen=True)
class TrackObservation:
    """
    A single immutable spatial-temporal observation of a tracked object.
    Stores lightweight primitive telemetry only.
    """
    timestamp_sec: float
    frame_index: int
    center_x: float
    center_y: float
    x1: int
    y1: int
    x2: int
    y2: int
    width: int
    height: int
    confidence: float
    class_name: str
    track_id: int

    @property
    def bbox(self) -> Tuple[int, int, int, int]:
        """(x1, y1, x2, y2) bounding box tuple."""
        return (self.x1, self.y1, self.x2, self.y2)

    @property
    def aspect_ratio(self) -> float:
        """
        Width / Height ratio.
        Values < 0.5 typically indicate standing humans;
        values >= 1.0 indicate horizontal or prone postures (crawling/lying).
        """
        return (self.width / self.height) if self.height > 0 else 0.0

    @property
    def bottom_center(self) -> Tuple[float, float]:
        """(center_x, y2) representing feet / ground contact point."""
        return (self.center_x, float(self.y2))


class TrackHistoryBuffer:
    """
    Thread-safe, bounded in-memory track history buffer isolated by source_id.
    
    Structure:
      source_id -> track_id -> collections.deque[TrackObservation](maxlen=max_history)
    """

    def __init__(self, max_history: int = DEFAULT_MAX_HISTORY):
        if max_history < 2:
            raise ValueError(f"max_history must be at least 2, got {max_history}")
        self._max_history: int = max_history
        self._lock = threading.RLock()
        
        # Primary storage: { source_id: { track_id: deque[TrackObservation] } }
        self._sources: Dict[str, Dict[int, deque[TrackObservation]]] = {}
        
        # Last observed timestamp per track: { source_id: { track_id: float } }
        self._last_seen: Dict[str, Dict[int, float]] = {}

    @property
    def max_history(self) -> int:
        return self._max_history

    def update(
        self,
        source_id: str,
        detection: Any,
        timestamp_sec: float,
        frame_index: int = 0,
    ) -> Optional[TrackObservation]:
        """
        Records a new observation for a tracked detection.

        Parameters
        ----------
        source_id : str
            Unique identifier of the video source/camera feed.
        detection : Any
            DetectionResult instance or dictionary with detection fields.
            Must contain a non-None track_id.
        timestamp_sec : float
            Exact stream / media timestamp in seconds.
        frame_index : int, optional
            Sequential frame index, by default 0.

        Returns
        -------
        Optional[TrackObservation]
            The constructed observation if track_id is valid, else None.
        """
        if not source_id:
            return None

        # Extract track_id
        track_id: Optional[int] = None
        if hasattr(detection, "track_id"):
            track_id = detection.track_id
        elif isinstance(detection, dict):
            track_id = detection.get("track_id")

        if track_id is None:
            return None  # Detections without track_id cannot have history

        # Extract coordinates and attributes
        try:
            if hasattr(detection, "x1"):
                x1 = int(round(detection.x1))
                y1 = int(round(detection.y1))
                x2 = int(round(detection.x2))
                y2 = int(round(detection.y2))
                confidence = float(getattr(detection, "confidence", 1.0))
                class_name = str(getattr(detection, "class_name", "unknown")).lower()
            elif isinstance(detection, dict):
                if "bbox" in detection and detection["bbox"]:
                    bbox = detection["bbox"]
                    x1, y1, x2, y2 = int(round(bbox[0])), int(round(bbox[1])), int(round(bbox[2])), int(round(bbox[3]))
                else:
                    x1 = int(round(detection.get("x1", 0)))
                    y1 = int(round(detection.get("y1", 0)))
                    x2 = int(round(detection.get("x2", 0)))
                    y2 = int(round(detection.get("y2", 0)))
                confidence = float(detection.get("confidence", 1.0))
                class_name = str(detection.get("class_name", "unknown")).lower()
            else:
                return None
        except (TypeError, ValueError, IndexError):
            return None

        width = max(0, x2 - x1)
        height = max(0, y2 - y1)
        center_x = float((x1 + x2) / 2.0)
        center_y = float((y1 + y2) / 2.0)

        obs = TrackObservation(
            timestamp_sec=float(timestamp_sec),
            frame_index=int(frame_index),
            center_x=center_x,
            center_y=center_y,
            x1=x1,
            y1=y1,
            x2=x2,
            y2=y2,
            width=width,
            height=height,
            confidence=confidence,
            class_name=class_name,
            track_id=int(track_id),
        )

        with self._lock:
            if source_id not in self._sources:
                self._sources[source_id] = {}
                self._last_seen[source_id] = {}

            if track_id not in self._sources[source_id]:
                self._sources[source_id][track_id] = deque(maxlen=self._max_history)

            self._sources[source_id][track_id].append(obs)
            self._last_seen[source_id][track_id] = float(timestamp_sec)

        return obs

    def get_history(self, source_id: str, track_id: int) -> List[TrackObservation]:
        """
        Return the chronological list of observations (oldest to newest)
        for a tracked object in a specific source.
        """
        with self._lock:
            track_deque = self._sources.get(source_id, {}).get(track_id)
            if not track_deque:
                return []
            return list(track_deque)

    def get_latest(self, source_id: str, track_id: int) -> Optional[TrackObservation]:
        """
        Return the most recent observation for a track, or None if unavailable.
        """
        with self._lock:
            track_deque = self._sources.get(source_id, {}).get(track_id)
            if not track_deque:
                return None
            return track_deque[-1]

    def get_previous(self, source_id: str, track_id: int) -> Optional[TrackObservation]:
        """
        Return the observation immediately prior to the latest one,
        or None if fewer than two observations exist.
        """
        with self._lock:
            track_deque = self._sources.get(source_id, {}).get(track_id)
            if not track_deque or len(track_deque) < 2:
                return None
            return track_deque[-2]

    def clear_track(self, source_id: str, track_id: int) -> bool:
        """
        Removes all history for a specific track ID in a given source.
        Returns True if the track was found and removed, False otherwise.
        """
        with self._lock:
            removed = False
            if source_id in self._sources and track_id in self._sources[source_id]:
                del self._sources[source_id][track_id]
                removed = True
            if source_id in self._last_seen and track_id in self._last_seen[source_id]:
                del self._last_seen[source_id][track_id]
            return removed

    def clear_source(self, source_id: str) -> bool:
        """
        Purges all track history for an entire camera source.
        Returns True if the source was found and cleared, False otherwise.
        """
        with self._lock:
            existed = source_id in self._sources or source_id in self._last_seen
            self._sources.pop(source_id, None)
            self._last_seen.pop(source_id, None)
            return existed

    def cleanup_stale(
        self,
        source_id: str,
        active_track_ids: Optional[Set[int]] = None,
        current_timestamp_sec: Optional[float] = None,
        max_stale_seconds: float = DEFAULT_MAX_STALE_SECONDS,
    ) -> List[int]:
        """
        Removes tracks that have disappeared for longer than max_stale_seconds.
        Active tracks present in the current frame are protected from removal.

        Parameters
        ----------
        source_id : str
            Video source identifier to clean.
        active_track_ids : Optional[Set[int]], optional
            Set of track IDs observed in the current frame. Protected from pruning.
        current_timestamp_sec : Optional[float], optional
            Current frame stream timestamp in seconds. If omitted, inferred from
            the maximum timestamp recorded for this source.
        max_stale_seconds : float, optional
            Disappearance duration before track is pruned, by default 3.0s.

        Returns
        -------
        List[int]
            List of track IDs that were pruned.
        """
        active_ids = active_track_ids or set()
        pruned_ids: List[int] = []

        with self._lock:
            source_last_seen = self._last_seen.get(source_id)
            if not source_last_seen:
                return []

            if current_timestamp_sec is None:
                current_timestamp_sec = max(source_last_seen.values(), default=0.0)

            for tid, last_ts in list(source_last_seen.items()):
                if tid in active_ids:
                    continue  # Active in current frame — protected

                elapsed_since_seen = current_timestamp_sec - last_ts
                if elapsed_since_seen > max_stale_seconds:
                    if tid in self._sources.get(source_id, {}):
                        del self._sources[source_id][tid]
                    del source_last_seen[tid]
                    pruned_ids.append(tid)

            # Clean up empty source map if all tracks were pruned
            if not self._sources.get(source_id):
                self._sources.pop(source_id, None)
                self._last_seen.pop(source_id, None)

        return pruned_ids

    def has_track(self, source_id: str, track_id: int) -> bool:
        """Return True if the track ID has buffered observations in source."""
        with self._lock:
            return bool(self._sources.get(source_id, {}).get(track_id))

    def get_track_count(self, source_id: str) -> int:
        """Return the number of active/buffered tracks for a source."""
        with self._lock:
            return len(self._sources.get(source_id, {}))

    def get_active_tracks(self, source_id: str) -> List[int]:
        """Return a list of all track IDs currently buffered for a source."""
        with self._lock:
            return list(self._sources.get(source_id, {}).keys())
