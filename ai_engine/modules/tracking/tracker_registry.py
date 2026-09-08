"""
Tracker Registry — Phase 6
---------------------------
Keeps per-source ByteTrack reset state so that:
  - Each video source gets a fresh tracker when analysis starts.
  - Tracker IDs from source A are never confused with IDs from source B.
  - Re-analysis of the same source correctly resets the tracker.

The actual ByteTrack state lives inside Ultralytics model.predictor.
We reset it by setting model.predictor = None before each new source run.
This registry tracks which source_id is currently "active" so the
YOLODetector knows when to reset.
"""

from __future__ import annotations
import logging

logger = logging.getLogger(__name__)


class TrackerRegistry:
    """
    Lightweight registry tracking which source_id was last analysed.
    Used by YOLODetector to decide whether to reset the ByteTrack state.
    """

    def __init__(self):
        self._active_source: str | None = None
        # Set of track IDs already alerted per source  (source_id -> set[int])
        self._seen_track_ids: dict[str, set[int]] = {}

    def prepare_for_source(self, source_id: str) -> bool:
        """
        Called before processing a new source.
        Returns True if the tracker should be reset (different source or re-analysis).
        Always resets, so re-running the same source also gets a fresh tracker.
        """
        self._active_source = source_id
        # Clear seen tracks for this source so dedup starts fresh
        self._seen_track_ids[source_id] = set()
        logger.info("[TrackerRegistry] Prepared for source: %s", source_id)
        return True  # Always reset tracker for a clean run

    def is_track_seen(self, source_id: str, track_id: int) -> bool:
        """Return True if we have already emitted an alert for this track ID."""
        return track_id in self._seen_track_ids.get(source_id, set())

    def mark_track_seen(self, source_id: str, track_id: int):
        """Record that an alert has been emitted for this track ID."""
        self._seen_track_ids.setdefault(source_id, set()).add(track_id)

    def remove_source(self, source_id: str):
        """Clean up when a source is deleted."""
        self._seen_track_ids.pop(source_id, None)
        if self._active_source == source_id:
            self._active_source = None
        logger.info("[TrackerRegistry] Removed tracking state for source: %s", source_id)


# Singleton — imported by detection_service and detection_router
tracker_registry = TrackerRegistry()
