"""
Unit Tests for TrackHistoryBuffer
=================================
Validates the core foundation of the Suspicious Activity Detection Engine:
  1. New track creates history.
  2. Multiple observations for the same track are ordered chronologically.
  3. Maximum history is capped at 20 observations.
  4. Oldest observation is discarded when the buffer exceeds 20.
  5. Different source_ids remain completely isolated.
  6. Different track_ids remain isolated.
  7. track_id=None is ignored.
  8. get_latest() returns the latest observation.
  9. get_previous() returns the previous observation.
  10. clear_track() removes only the selected track.
  11. clear_source() removes only the selected camera/source.
  12. cleanup_stale() removes tracks that have not been seen for > 3 seconds.
  13. cleanup_stale() does not remove active tracks.
  14. Memory bounds: No raw frames, image crops, or large arrays stored.
"""

import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent if Path(__file__).resolve().parent.name == "tests" else Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from ai_engine.modules.behavior.suspicious.track_history import (
    TrackObservation,
    TrackHistoryBuffer,
    DEFAULT_MAX_HISTORY,
)


class MockDetection:
    """Mock detection mimicking YOLODetector's DetectionResult."""
    def __init__(self, track_id, class_name, confidence, x1, y1, x2, y2):
        self.track_id = track_id
        self.class_name = class_name
        self.confidence = confidence
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2


def test_1_new_track_creates_history():
    buffer = TrackHistoryBuffer(max_history=20)
    det = MockDetection(track_id=101, class_name="person", confidence=0.92, x1=100, y1=150, x2=200, y2=450)
    obs = buffer.update(source_id="cam_01", detection=det, timestamp_sec=1.0, frame_index=10)

    assert obs is not None
    assert obs.track_id == 101
    assert obs.class_name == "person"
    assert obs.confidence == 0.92
    assert obs.width == 100
    assert obs.height == 300
    assert obs.center_x == 150.0
    assert obs.center_y == 300.0
    assert obs.aspect_ratio == round(100 / 300, 4) or abs(obs.aspect_ratio - (100 / 300)) < 1e-4
    assert obs.bottom_center == (150.0, 450.0)

    history = buffer.get_history("cam_01", 101)
    assert len(history) == 1
    assert history[0] == obs
    print("[PASS] Test 1: New track creates valid history observation.")


def test_2_chronological_order():
    buffer = TrackHistoryBuffer(max_history=20)
    source = "cam_01"
    tid = 101

    for i in range(5):
        det = MockDetection(tid, "person", 0.90, 100 + i * 10, 150, 200 + i * 10, 450)
        buffer.update(source, det, timestamp_sec=1.0 + i * 0.1, frame_index=10 + i)

    history = buffer.get_history(source, tid)
    assert len(history) == 5

    # Verify chronological ascending timestamps
    timestamps = [h.timestamp_sec for h in history]
    assert timestamps == sorted(timestamps)
    assert timestamps[0] == 1.0
    assert abs(timestamps[-1] - 1.4) < 1e-5
    print("[PASS] Test 2: Observations are ordered chronologically.")


def test_3_and_4_max_history_cap_and_fifo_eviction():
    buffer = TrackHistoryBuffer(max_history=20)
    source = "cam_01"
    tid = 101

    # Insert 30 observations
    for i in range(30):
        det = MockDetection(tid, "person", 0.90, 100 + i, 150, 200 + i, 450)
        buffer.update(source, det, timestamp_sec=float(i), frame_index=i)

    history = buffer.get_history(source, tid)
    assert len(history) == 20, f"Expected 20, got {len(history)}"

    # Earliest observation should be i=10 (first 10 discarded)
    assert history[0].frame_index == 10
    assert history[0].timestamp_sec == 10.0

    # Latest observation should be i=29
    assert history[-1].frame_index == 29
    assert history[-1].timestamp_sec == 29.0
    print("[PASS] Tests 3 & 4: Maximum history is capped at 20 and FIFO eviction works.")


def test_5_source_isolation():
    buffer = TrackHistoryBuffer(max_history=20)
    tid = 101  # Same track ID on two cameras

    det_a = MockDetection(tid, "person", 0.85, 10, 20, 30, 40)
    det_b = MockDetection(tid, "backpack", 0.75, 500, 600, 700, 800)

    buffer.update("cam_north", det_a, timestamp_sec=5.0, frame_index=100)
    buffer.update("cam_south", det_b, timestamp_sec=12.0, frame_index=200)

    hist_a = buffer.get_history("cam_north", tid)
    hist_b = buffer.get_history("cam_south", tid)

    assert len(hist_a) == 1
    assert hist_a[0].class_name == "person"
    assert hist_a[0].timestamp_sec == 5.0

    assert len(hist_b) == 1
    assert hist_b[0].class_name == "backpack"
    assert hist_b[0].timestamp_sec == 12.0

    # cam_north has 1 track, cam_south has 1 track
    assert buffer.get_track_count("cam_north") == 1
    assert buffer.get_track_count("cam_south") == 1
    print("[PASS] Test 5: Different sources with identical track IDs remain strictly isolated.")


def test_6_track_id_isolation():
    buffer = TrackHistoryBuffer(max_history=20)
    source = "cam_01"

    det_1 = MockDetection(101, "person", 0.90, 10, 20, 30, 40)
    det_2 = MockDetection(102, "suitcase", 0.80, 50, 60, 70, 80)

    buffer.update(source, det_1, timestamp_sec=1.0)
    buffer.update(source, det_2, timestamp_sec=1.0)

    assert len(buffer.get_history(source, 101)) == 1
    assert buffer.get_history(source, 101)[0].class_name == "person"

    assert len(buffer.get_history(source, 102)) == 1
    assert buffer.get_history(source, 102)[0].class_name == "suitcase"
    print("[PASS] Test 6: Different track IDs in same source remain strictly isolated.")


def test_7_none_track_id_ignored():
    buffer = TrackHistoryBuffer(max_history=20)
    det_none = MockDetection(None, "person", 0.90, 10, 20, 30, 40)
    obs = buffer.update("cam_01", det_none, timestamp_sec=1.0)

    assert obs is None
    assert buffer.get_track_count("cam_01") == 0
    assert buffer.get_history("cam_01", 1) == []
    print("[PASS] Test 7: Detection with track_id=None is safely ignored.")


def test_8_and_9_get_latest_and_previous():
    buffer = TrackHistoryBuffer(max_history=20)
    source = "cam_01"
    tid = 101

    # Empty buffer
    assert buffer.get_latest(source, tid) is None
    assert buffer.get_previous(source, tid) is None

    # Single observation
    buffer.update(source, MockDetection(tid, "person", 0.9, 10, 10, 20, 20), timestamp_sec=1.0)
    latest = buffer.get_latest(source, tid)
    prev = buffer.get_previous(source, tid)

    assert latest is not None
    assert latest.timestamp_sec == 1.0
    assert prev is None  # Only 1 observation, so no previous

    # Second observation
    buffer.update(source, MockDetection(tid, "person", 0.9, 15, 15, 25, 25), timestamp_sec=2.0)
    latest = buffer.get_latest(source, tid)
    prev = buffer.get_previous(source, tid)

    assert latest is not None
    assert latest.timestamp_sec == 2.0
    assert prev is not None
    assert prev.timestamp_sec == 1.0

    # Third observation
    buffer.update(source, MockDetection(tid, "person", 0.9, 20, 20, 30, 30), timestamp_sec=3.0)
    latest = buffer.get_latest(source, tid)
    prev = buffer.get_previous(source, tid)

    assert latest.timestamp_sec == 3.0
    assert prev.timestamp_sec == 2.0
    print("[PASS] Tests 8 & 9: get_latest() and get_previous() return correct observations.")


def test_10_clear_track():
    buffer = TrackHistoryBuffer(max_history=20)
    source = "cam_01"

    buffer.update(source, MockDetection(101, "person", 0.9, 10, 10, 20, 20), timestamp_sec=1.0)
    buffer.update(source, MockDetection(102, "person", 0.9, 10, 10, 20, 20), timestamp_sec=1.0)

    assert buffer.has_track(source, 101)
    assert buffer.has_track(source, 102)

    removed = buffer.clear_track(source, 101)
    assert removed is True
    assert not buffer.has_track(source, 101)
    assert buffer.get_history(source, 101) == []
    # Track 102 still present
    assert buffer.has_track(source, 102)

    # Clearing non-existent track returns False
    assert buffer.clear_track(source, 999) is False
    print("[PASS] Test 10: clear_track() removes only the targeted track.")


def test_11_clear_source():
    buffer = TrackHistoryBuffer(max_history=20)

    buffer.update("cam_01", MockDetection(101, "person", 0.9, 10, 10, 20, 20), timestamp_sec=1.0)
    buffer.update("cam_01", MockDetection(102, "car", 0.9, 10, 10, 20, 20), timestamp_sec=1.0)
    buffer.update("cam_02", MockDetection(201, "person", 0.9, 10, 10, 20, 20), timestamp_sec=1.0)

    assert buffer.get_track_count("cam_01") == 2
    assert buffer.get_track_count("cam_02") == 1

    removed = buffer.clear_source("cam_01")
    assert removed is True
    assert buffer.get_track_count("cam_01") == 0
    assert buffer.get_history("cam_01", 101) == []

    # cam_02 unaffected
    assert buffer.get_track_count("cam_02") == 1
    assert buffer.has_track("cam_02", 201)
    print("[PASS] Test 11: clear_source() completely purges selected camera without affecting others.")


def test_12_and_13_cleanup_stale_and_active_protection():
    buffer = TrackHistoryBuffer(max_history=20)
    source = "cam_01"

    # Track 101: seen at t=10.0
    buffer.update(source, MockDetection(101, "person", 0.9, 10, 10, 20, 20), timestamp_sec=10.0)
    # Track 102: seen at t=12.5
    buffer.update(source, MockDetection(102, "backpack", 0.9, 10, 10, 20, 20), timestamp_sec=12.5)
    # Track 103: seen at t=14.0
    buffer.update(source, MockDetection(103, "person", 0.9, 10, 10, 20, 20), timestamp_sec=14.0)

    # Current time t = 14.0, max_stale = 3.0s
    # Stale threshold = 14.0 - 3.0 = 11.0s
    # Track 101: last seen at 10.0s (elapsed 4.0s > 3.0s) -> STALE
    # Track 102: last seen at 12.5s (elapsed 1.5s <= 3.0s) -> ACTIVE
    # Track 103: in active_track_ids -> PROTECTED

    pruned = buffer.cleanup_stale(
        source_id=source,
        active_track_ids={103},
        current_timestamp_sec=14.0,
        max_stale_seconds=3.0,
    )

    assert pruned == [101], f"Expected [101], got {pruned}"
    assert not buffer.has_track(source, 101)
    assert buffer.has_track(source, 102)
    assert buffer.has_track(source, 103)
    print("[PASS] Tests 12 & 13: Stale tracks (>3.0s) pruned, active tracks protected.")


def test_14_memory_safety():
    """Verify that TrackObservation only contains primitive scalar fields."""
    obs = TrackObservation(
        timestamp_sec=1.5,
        frame_index=45,
        center_x=120.0,
        center_y=240.0,
        x1=100,
        y1=200,
        x2=140,
        y2=280,
        width=40,
        height=80,
        confidence=0.88,
        class_name="person",
        track_id=5,
    )

    # Check that no frame, image crop, or large object can be part of slots
    allowed_slots = {
        "timestamp_sec", "frame_index", "center_x", "center_y",
        "x1", "y1", "x2", "y2", "width", "height",
        "confidence", "class_name", "track_id",
    }
    assert set(TrackObservation.__slots__) == allowed_slots
    assert not hasattr(obs, "__dict__"), "TrackObservation must be slot-based for memory compactness"
    assert not hasattr(obs, "raw_frame")
    assert not hasattr(obs, "crop")
    assert not hasattr(obs, "embedding")
    print("[PASS] Test 14: TrackObservation is memory-bounded with slots and zero heavy objects.")


def test_dict_compatibility():
    """Verify buffer accepts dicts as well as objects."""
    buffer = TrackHistoryBuffer(max_history=20)
    det_dict = {
        "track_id": 55,
        "class_name": "bottle",
        "confidence": 0.78,
        "x1": 50,
        "y1": 60,
        "x2": 70,
        "y2": 120,
    }
    obs = buffer.update("cam_01", det_dict, timestamp_sec=0.5, frame_index=1)
    assert obs is not None
    assert obs.track_id == 55
    assert obs.class_name == "bottle"
    assert obs.width == 20
    assert obs.height == 60
    print("[PASS] Compatibility: Dict-formatted detections supported seamlessly.")


def run_all_tests():
    print("==================================================")
    print("RUNNING TRACK HISTORY BUFFER UNIT TESTS")
    print("==================================================")
    test_1_new_track_creates_history()
    test_2_chronological_order()
    test_3_and_4_max_history_cap_and_fifo_eviction()
    test_5_source_isolation()
    test_6_track_id_isolation()
    test_7_none_track_id_ignored()
    test_8_and_9_get_latest_and_previous()
    test_10_clear_track()
    test_11_clear_source()
    test_12_and_13_cleanup_stale_and_active_protection()
    test_14_memory_safety()
    test_dict_compatibility()
    print("==================================================")
    print("ALL 14 UNIT TESTS PASSED SUCCESSFULLY!")
    print("==================================================")


if __name__ == "__main__":
    run_all_tests()
