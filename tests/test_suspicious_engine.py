"""
Unit Tests for SuspiciousActivityEngine
=======================================
Validates the Unified Suspicious Activity Engine against all requirements:
  1. Engine initialization with default and custom components.
  2. Empty frame returns empty event list.
  3. Single person routing to Running & Crawling detectors.
  4. Multiple person routing in same frame.
  5. Object routing to Throwing detector only.
  6. Running event normalization into SuspiciousActivityEvent.
  7. Crawling event normalization into SuspiciousActivityEvent.
  8. Throwing event normalization into SuspiciousActivityEvent.
  9. Multi-camera source isolation with identical track IDs.
  10. Intra-camera track isolation.
  11. Person and object track namespace separation.
  12. Missing track_id=None safely ignored without crash.
  13. Invalid bounding boxes (inverted, NaN) handled safely without crash.
  14. Duplicate frame submission protection (same frame_index and timestamp).
  15. Duplicate event protection over continuous episodes (zero event flooding).
  16. Robust detector failure isolation (exception in one does not halt others).
  17. Manual cleanup (clear_source, clear_track).
  18. Temporal stale track cleanup across buffer and all detectors.
  19. Multiple distinct activity types in the same frame (running + crawling).
  20. RTSP-compatible source ID processing.
  21. Uploaded-video-compatible source ID processing.
  22. Verification that NO raw frames or image buffers are stored in history.
  23. Throwing detector rejection of vehicle classes (car, truck, etc.).
  24. Preservation of detector-specific telemetry in event metadata.
  25. Immutability of SuspiciousActivityEvent (frozen dataclass).
"""

import sys
from pathlib import Path
from dataclasses import FrozenInstanceError

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent if Path(__file__).resolve().parent.name == "tests" else Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from ai_engine.modules.behavior.suspicious.track_history import TrackHistoryBuffer, TrackObservation
from ai_engine.modules.behavior.suspicious.running_detector import RunningDetector
from ai_engine.modules.behavior.suspicious.crawling_detector import CrawlingDetector
from ai_engine.modules.behavior.suspicious.throwing_detector import ThrowingDetector
from ai_engine.modules.behavior.suspicious.suspicious_engine import (
    SuspiciousActivityEngine,
    SuspiciousActivityEvent,
    ACTIVITY_RUNNING,
    ACTIVITY_CRAWLING,
    ACTIVITY_THROWING,
)


class MockDet:
    """Mock detection mimicking DetectionResult."""
    def __init__(self, track_id, class_name, x1, y1, x2, y2, confidence=0.90):
        self.track_id = track_id
        self.class_name = class_name
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.confidence = confidence


class MockFrameDetections:
    """Mock container mimicking FrameDetections from YOLO."""
    def __init__(self, frame_index, timestamp_sec, detections, raw_frame=None):
        self.frame_index = frame_index
        self.timestamp_sec = timestamp_sec
        self.detections = detections
        self._raw_frame = raw_frame


def test_1_engine_initialization():
    engine = SuspiciousActivityEngine()
    assert engine.history_buffer is not None
    assert engine.running_detector is not None
    assert engine.crawling_detector is not None
    assert engine.throwing_detector is not None
    assert engine.enable_running is True
    assert engine.enable_crawling is True
    assert engine.enable_throwing is True
    print("[PASS] Test 1: Engine initialization with default components succeeded.")


def test_2_empty_frame():
    engine = SuspiciousActivityEngine()
    source = "cam_01"

    assert engine.process_frame(source, []) == []
    assert engine.process_frame(source, None) == []
    assert engine.process_frame("", [MockDet(1, "person", 100, 100, 160, 300)]) == []
    assert engine.process_frame(source, MockFrameDetections(0, 0.0, [])) == []
    assert engine.process_frame(source, {"detections": []}) == []
    print("[PASS] Test 2: Empty frames and empty inputs return empty event list.")


def test_3_single_person_routing():
    engine = SuspiciousActivityEngine()
    source = "cam_01"

    # Person walking normally (speed 0.5 heights/s, aspect 0.3)
    events = []
    for idx in range(6):
        x = 100 + idx * 10
        det = MockDet(1, "person", x, 100, x + 60, 300)
        res = engine.process_frame(source, [det], timestamp_sec=idx * 0.1, frame_index=idx)
        events.extend(res)

    assert len(events) == 0, f"Expected 0 events for normal walking, got {len(events)}"
    assert engine.history_buffer.has_track(source, 1) is True
    print("[PASS] Test 3: Single person routing updates history without false alerts.")


def test_4_multiple_person_routing():
    engine = SuspiciousActivityEngine()
    source = "cam_01"

    # 3 persons walking
    for idx in range(5):
        d1 = MockDet(1, "person", 100 + idx * 5, 100, 160 + idx * 5, 300)
        d2 = MockDet(2, "person", 300 + idx * 5, 100, 360 + idx * 5, 300)
        d3 = MockDet(3, "person", 500 + idx * 5, 100, 560 + idx * 5, 300)
        engine.process_frame(source, [d1, d2, d3], timestamp_sec=idx * 0.1, frame_index=idx)

    assert engine.history_buffer.get_track_count(source) == 3
    assert set(engine.history_buffer.get_active_tracks(source)) == {1, 2, 3}
    print("[PASS] Test 4: Multiple persons in same frame tracked with distinct histories.")


def test_5_object_routing():
    engine = SuspiciousActivityEngine()
    source = "cam_01"

    # Stationary backpack near person
    for idx in range(5):
        p = MockDet(1, "person", 100, 100, 160, 300)
        b = MockDet(10, "backpack", 140, 180, 180, 220)
        engine.process_frame(source, [p, b], timestamp_sec=idx * 0.1, frame_index=idx)

    assert engine.history_buffer.has_track(source, 1) is True
    assert engine.history_buffer.has_track(source, 10) is True
    # Backpack must be routed to throwing detector as an associated object, not evaluated as runner or crawler
    assert engine.running_detector.get_track_state(source, 10) == "NOT_RUNNING"
    assert engine.crawling_detector.get_track_state(source, 10) == "NOT_CRAWLING"
    assert engine.throwing_detector.get_candidate_state(source, 1, 10) == "PERSON_OBJECT_ASSOCIATED"
    print("[PASS] Test 5: Non-person object correctly routed to throwing candidate, not running/crawling.")


def test_6_running_event_normalization():
    engine = SuspiciousActivityEngine()
    source = "cam_01"
    pid = 101

    events = []
    # Feed running sequence: 50px per 0.1s frame (person height = 200 -> speed = 2.5 heights/s)
    # Needs at least 4 history frames + 5 consecutive running frames = 9+ frames
    for idx in range(12):
        x = 100 + idx * 50
        det = MockDet(pid, "person", x, 100, x + 60, 300)
        res = engine.process_frame(source, [det], timestamp_sec=idx * 0.1, frame_index=idx)
        events.extend(res)

    assert len(events) == 1, f"Expected 1 running event, got {len(events)}"
    ev = events[0]
    assert isinstance(ev, SuspiciousActivityEvent)
    assert ev.activity == ACTIVITY_RUNNING
    assert ev.source_id == source
    assert ev.track_id == pid
    assert ev.object_track_id is None
    # Confidence is now evidence-based (not a fixed constant)
    assert 0.65 <= ev.confidence <= 1.0, f"Expected confidence in [0.65, 1.0], got {ev.confidence}"
    assert ev.score == ev.confidence  # score mirrors confidence
    assert "normalized_speed" in ev.metadata
    assert ev.metadata["normalized_speed"] >= 2.0
    assert "duration_sec" in ev.metadata
    assert "body_height_px" in ev.metadata
    print(f"[PASS] Test 6: Running event normalized correctly (Speed: {ev.metadata['normalized_speed']} h/s, Conf: {ev.confidence}).")


def test_7_crawling_event_normalization():
    engine = SuspiciousActivityEngine()
    source = "cam_01"
    pid = 102

    events = []
    # 1. Standing history (5 frames)
    t = 0.0
    for idx in range(5):
        det = MockDet(pid, "person", 100, 100, 160, 300)
        engine.process_frame(source, [det], timestamp_sec=t, frame_index=idx)
        t += 0.1

    # 2. Prone crawling (20 frames = 2.0s >= 1.5s, width=130, height=90, aspect=1.44, dx=8px/frame)
    x = 100
    for idx in range(5, 25):
        det = MockDet(pid, "person", x, 210, x + 130, 300)
        res = engine.process_frame(source, [det], timestamp_sec=t, frame_index=idx)
        events.extend(res)
        x += 8
        t += 0.1

    # Filter to only crawling events (RUNNING should not fire at crawling speed 0.89 h/s)
    crawling_events = [e for e in events if e.activity == ACTIVITY_CRAWLING]
    assert len(crawling_events) == 1, f"Expected 1 crawling event, got {len(crawling_events)} (total events: {len(events)})"
    ev = crawling_events[0]
    assert isinstance(ev, SuspiciousActivityEvent)
    assert ev.activity == ACTIVITY_CRAWLING
    assert ev.source_id == source
    assert ev.track_id == pid
    assert ev.object_track_id is None
    # With the new multi-signal detector, aspect_ratio threshold is 0.8 (from 1.05)
    assert ev.metadata["aspect_ratio"] >= 0.8, f"Expected aspect_ratio >= 0.8, got {ev.metadata['aspect_ratio']}"
    assert ev.metadata["relative_height"] <= 0.80, f"Expected rel_height <= 0.80, got {ev.metadata['relative_height']}"
    assert ev.metadata["horizontal_speed"] >= 0.10
    print(f"[PASS] Test 7: Crawling event normalized correctly (Aspect: {ev.metadata['aspect_ratio']}, RelHeight: {ev.metadata['relative_height']}).")


def test_8_throwing_event_normalization():
    engine = SuspiciousActivityEngine()
    source = "cam_01"
    pid, oid = 103, 203

    events = []
    # 4 frames close/associated
    t = 0.0
    for idx in range(4):
        p = MockDet(pid, "person", 100, 100, 160, 300)
        b = MockDet(oid, "backpack", 140, 180, 180, 220)
        engine.process_frame(source, [p, b], timestamp_sec=t, frame_index=idx)
        t += 0.1

    # Rapid throw: object accelerates forward at 50px/frame (2.5 heights/s) for 3 frames
    for idx in range(4, 7):
        p = MockDet(pid, "person", 100, 100, 160, 300)
        ox = 140 + (idx - 3) * 50
        b = MockDet(oid, "backpack", ox, 180, ox + 40, 220)
        res = engine.process_frame(source, [p, b], timestamp_sec=t, frame_index=idx)
        events.extend(res)
        t += 0.1

    assert len(events) == 1, f"Expected 1 throwing event, got {len(events)}"
    ev = events[0]
    assert isinstance(ev, SuspiciousActivityEvent)
    assert ev.activity == ACTIVITY_THROWING
    assert ev.source_id == source
    assert ev.track_id == pid
    assert ev.object_track_id == oid
    assert ev.metadata["object_class"] == "backpack"
    assert ev.metadata["object_speed_normalized"] >= 2.0
    assert ev.metadata["separation"] >= 0.4
    assert ev.metadata["trajectory_consistency"] >= 0.70
    print(f"[PASS] Test 8: Throwing event normalized correctly with object_track_id={ev.object_track_id}.")


def test_9_source_isolation():
    engine = SuspiciousActivityEngine()
    tid = 1

    # On cam_alpha: person runs
    events_alpha = []
    for idx in range(12):
        x = 100 + idx * 50
        d = MockDet(tid, "person", x, 100, x + 60, 300)
        events_alpha.extend(engine.process_frame("cam_alpha", [d], timestamp_sec=idx * 0.1, frame_index=idx))

    # On cam_beta: person stands still
    events_beta = []
    for idx in range(12):
        d = MockDet(tid, "person", 100, 100, 160, 300)
        events_beta.extend(engine.process_frame("cam_beta", [d], timestamp_sec=idx * 0.1, frame_index=idx))

    assert len(events_alpha) == 1
    assert len(events_beta) == 0
    assert events_alpha[0].source_id == "cam_alpha"
    print("[PASS] Test 9: Different camera sources with identical track IDs remain strictly isolated.")


def test_10_intra_source_track_isolation():
    engine = SuspiciousActivityEngine()
    source = "cam_01"

    # Track 1 runs, Track 2 walks
    events = []
    for idx in range(12):
        d1 = MockDet(1, "person", 100 + idx * 50, 100, 160 + idx * 50, 300) # running
        d2 = MockDet(2, "person", 500 + idx * 10, 100, 560 + idx * 10, 300) # walking
        res = engine.process_frame(source, [d1, d2], timestamp_sec=idx * 0.1, frame_index=idx)
        events.extend(res)

    assert len(events) == 1
    assert events[0].track_id == 1
    print("[PASS] Test 10: In multi-track frame, only qualifying runner triggers confirmation.")


def test_11_person_object_track_separation():
    engine = SuspiciousActivityEngine()
    source = "cam_01"

    # Person has track_id=5, Backpack has track_id=5 (distinct class namespaces)
    p = MockDet(5, "person", 100, 100, 160, 300)
    b = MockDet(5, "backpack", 140, 180, 180, 220)

    # Throwing detector expects person_id != object_id
    res = engine.process_frame(source, [p, b], timestamp_sec=0.0, frame_index=0)
    assert res == []
    print("[PASS] Test 11: Person and object class namespaces properly separated.")


def test_12_missing_track_id_handled_safely():
    engine = SuspiciousActivityEngine()
    source = "cam_01"

    # Detection without track_id
    d_none = MockDet(None, "person", 100, 100, 160, 300)
    d_valid = MockDet(1, "person", 200, 100, 260, 300)

    res = engine.process_frame(source, [d_none, d_valid], timestamp_sec=0.1, frame_index=1)
    assert res == []
    assert engine.history_buffer.has_track(source, 1) is True
    print("[PASS] Test 12: Missing track_id=None safely ignored without crash or state corruption.")


def test_13_invalid_bbox_handled_safely():
    engine = SuspiciousActivityEngine()
    source = "cam_01"

    # Inverted box (x2 < x1)
    d_inv = MockDet(1, "person", 200, 100, 100, 300)
    # NaN box
    d_nan = MockDet(2, "person", float("nan"), 100, 200, 300)
    # Normal box
    d_ok = MockDet(3, "person", 100, 100, 160, 300)

    res = engine.process_frame(source, [d_inv, d_nan, d_ok], timestamp_sec=0.1, frame_index=1)
    assert res == []
    assert engine.history_buffer.has_track(source, 3) is True
    assert engine.history_buffer.has_track(source, 1) is False
    assert engine.history_buffer.has_track(source, 2) is False
    print("[PASS] Test 13: Invalid bounding boxes (inverted, NaN) handled safely without crash.")


def test_14_duplicate_frame_protection():
    engine = SuspiciousActivityEngine()
    source = "cam_01"

    det = MockDet(1, "person", 100, 100, 160, 300)
    # First submission
    res1 = engine.process_frame(source, [det], timestamp_sec=1.5, frame_index=15)
    # Exact duplicate submission (same frame_index and same timestamp)
    res2 = engine.process_frame(source, [det], timestamp_sec=1.5, frame_index=15)

    assert res1 == []
    assert res2 == []
    # TrackHistoryBuffer must only contain 1 observation, not 2
    assert len(engine.history_buffer.get_history(source, 1)) == 1
    print("[PASS] Test 14: Duplicate frame submission ignored; zero double-buffering in TrackHistory.")


def test_15_duplicate_event_protection():
    engine = SuspiciousActivityEngine()
    source = "cam_01"
    pid = 1

    # Continuous running for 30 frames
    events = []
    for idx in range(30):
        x = 100 + idx * 50
        det = MockDet(pid, "person", x, 100, x + 60, 300)
        res = engine.process_frame(source, [det], timestamp_sec=idx * 0.1, frame_index=idx)
        events.extend(res)

    assert len(events) == 1, f"Expected exactly 1 event over 30 frames of continuous running, got {len(events)}"
    print("[PASS] Test 15: Continuous running episode produces exactly 1 event with zero event flooding.")


def test_16_detector_failure_isolation():
    class FaultyRunningDetector(RunningDetector):
        def process_observation(self, source_id, observation, history_buffer):
            raise RuntimeError("Simulated running detector catastrophic crash!")

    faulty_runner = FaultyRunningDetector()
    engine = SuspiciousActivityEngine(running_detector=faulty_runner)
    source = "cam_01"

    # Even though running detector crashes, crawling detector should execute cleanly
    t = 0.0
    for idx in range(5):
        d = MockDet(1, "person", 100, 100, 160, 300)
        engine.process_frame(source, [d], timestamp_sec=t, frame_index=idx)
        t += 0.1

    events = []
    x = 100
    for idx in range(5, 25):
        d = MockDet(1, "person", x, 210, x + 130, 300) # crawling
        res = engine.process_frame(source, [d], timestamp_sec=t, frame_index=idx)
        events.extend(res)
        x += 8
        t += 0.1

    # Crawling event should still be detected despite running detector failure!
    assert len(events) == 1
    assert events[0].activity == ACTIVITY_CRAWLING
    print("[PASS] Test 16: Detector failure isolated; crawling proceeded despite running detector crash.")


def test_17_cleanup():
    engine = SuspiciousActivityEngine()
    source = "cam_01"

    # Seed tracks
    for idx in range(3):
        d = MockDet(1, "person", 100, 100, 160, 300)
        engine.process_frame(source, [d], timestamp_sec=idx * 0.1, frame_index=idx)

    assert engine.history_buffer.has_track(source, 1) is True
    engine.clear_track(source, 1)
    assert engine.history_buffer.has_track(source, 1) is False

    # Seed again and clear source
    d = MockDet(2, "person", 100, 100, 160, 300)
    engine.process_frame(source, [d], timestamp_sec=1.0, frame_index=10)
    assert engine.history_buffer.has_track(source, 2) is True

    engine.clear_source(source)
    assert engine.history_buffer.has_track(source, 2) is False
    print("[PASS] Test 17: Manual cleanup (clear_track, clear_source) operates properly.")


def test_18_stale_track_cleanup():
    engine = SuspiciousActivityEngine()
    source = "cam_01"

    # Track 1 seen at t=1.0s
    d = MockDet(1, "person", 100, 100, 160, 300)
    engine.process_frame(source, [d], timestamp_sec=1.0, frame_index=10)

    assert engine.history_buffer.has_track(source, 1) is True

    # 5 seconds later, cleanup with max_stale_seconds=3.0
    summary = engine.cleanup(source, active_track_ids=set(), current_timestamp_sec=6.0, max_stale_seconds=3.0)
    assert 1 in summary["pruned_history_tracks"]
    assert engine.history_buffer.has_track(source, 1) is False
    print("[PASS] Test 18: Stale track cleanup successfully pruned inactive tracks.")


def test_19_multiple_activity_types_in_same_frame():
    engine = SuspiciousActivityEngine()
    source = "cam_01"

    # Person 1 running, Person 2 crawling
    # 1. Seed standing baseline for Person 2 (crawling)
    t = 0.0
    for idx in range(5):
        d2 = MockDet(2, "person", 500, 100, 560, 300)
        engine.process_frame(source, [d2], timestamp_sec=t, frame_index=idx)
        t += 0.1

    all_events = []
    p1_x = 100
    p2_x = 500
    for idx in range(5, 25):
        # Person 1 running fast (50px/frame = 2.5 heights/s)
        d1 = MockDet(1, "person", p1_x, 100, p1_x + 60, 300)
        # Person 2 prone crawling (aspect=1.44, rel_height=0.45, speed=0.4 heights/s)
        d2 = MockDet(2, "person", p2_x, 210, p2_x + 130, 300)

        res = engine.process_frame(source, [d1, d2], timestamp_sec=t, frame_index=idx)
        all_events.extend(res)

        p1_x += 50
        p2_x += 8
        t += 0.1

    activities = [e.activity for e in all_events]
    assert ACTIVITY_RUNNING in activities
    assert ACTIVITY_CRAWLING in activities
    print("[PASS] Test 19: Multiple distinct activity types (RUNNING & CRAWLING) detected in same stream.")


def test_20_rtsp_compatible_source_id():
    engine = SuspiciousActivityEngine()
    rtsp_source = "rtsp://admin:pass@192.168.1.108:554/Streaming/Channels/101"

    events = []
    for idx in range(12):
        x = 100 + idx * 50
        d = MockDet(1, "person", x, 100, x + 60, 300)
        events.extend(engine.process_frame(rtsp_source, [d], timestamp_sec=idx * 0.1, frame_index=idx))

    assert len(events) == 1
    assert events[0].source_id == rtsp_source
    print("[PASS] Test 20: Complex RTSP URL source ID handled cleanly.")


def test_21_uploaded_video_source_id():
    engine = SuspiciousActivityEngine()
    video_source = "border_patrol_sector_4_night.mp4"

    events = []
    for idx in range(12):
        x = 100 + idx * 50
        d = MockDet(1, "person", x, 100, x + 60, 300)
        events.extend(engine.process_frame(video_source, [d], timestamp_sec=idx * 0.1, frame_index=idx))

    assert len(events) == 1
    assert events[0].source_id == video_source
    print("[PASS] Test 21: Uploaded video filename source ID handled cleanly.")


def test_22_no_raw_frames_stored_in_history():
    engine = SuspiciousActivityEngine()
    source = "cam_01"

    # Attach large dummy byte buffer to simulate raw image frame
    fake_frame = bytearray(1920 * 1080 * 3)
    frame_container = MockFrameDetections(
        frame_index=1,
        timestamp_sec=0.1,
        detections=[MockDet(1, "person", 100, 100, 160, 300)],
        raw_frame=fake_frame,
    )

    engine.process_frame(source, frame_container)
    history = engine.history_buffer.get_history(source, 1)
    assert len(history) == 1
    obs = history[0]

    # Verify obs is a pure primitive TrackObservation
    assert isinstance(obs, TrackObservation)
    assert not hasattr(obs, "_raw_frame")
    assert not hasattr(obs, "frame")
    assert not hasattr(obs, "image")
    print("[PASS] Test 22: Verified zero raw frame / image storage in TrackHistoryBuffer.")


def test_23_throwing_rejects_vehicle_classes():
    engine = SuspiciousActivityEngine()
    source = "cam_01"
    pid, vid = 1, 99

    # Person stands near a car; car drives away fast
    events = []
    t = 0.0
    for idx in range(8):
        p = MockDet(pid, "person", 100, 100, 160, 300)
        cx = 140 if idx < 4 else 140 + (idx - 3) * 50
        c = MockDet(vid, "car", cx, 150, cx + 100, 250)
        events.extend(engine.process_frame(source, [p, c], timestamp_sec=t, frame_index=idx))
        t += 0.1

    assert len(events) == 0, f"Vehicles must never trigger throwing events, got {len(events)}"
    print("[PASS] Test 23: Throwing detector correctly rejects vehicle classes (car).")


def test_24_detector_metadata_preservation():
    engine = SuspiciousActivityEngine()
    source = "cam_01"

    # Trigger a running event
    events = []
    for idx in range(12):
        x = 100 + idx * 50
        d = MockDet(1, "person", x, 100, x + 60, 300)
        events.extend(engine.process_frame(source, [d], timestamp_sec=idx * 0.1, frame_index=idx))

    assert len(events) == 1
    ev = events[0]
    meta = ev.metadata
    assert "normalized_speed" in meta
    assert "raw_speed_px" in meta
    assert "body_height_px" in meta
    assert "duration_sec" in meta
    assert "consecutive_frames" in meta
    # Test to_dict serialization
    ev_dict = ev.to_dict()
    assert ev_dict["activity"] == "RUNNING"
    assert ev_dict["metadata"]["normalized_speed"] == meta["normalized_speed"]
    print("[PASS] Test 24: Detector-specific telemetry accurately preserved in event metadata and to_dict().")


def test_25_event_immutability():
    engine = SuspiciousActivityEngine()
    source = "cam_01"

    events = []
    for idx in range(12):
        x = 100 + idx * 50
        d = MockDet(1, "person", x, 100, x + 60, 300)
        events.extend(engine.process_frame(source, [d], timestamp_sec=idx * 0.1, frame_index=idx))

    assert len(events) == 1
    ev = events[0]

    # Attempt to mutate attributes on frozen dataclass
    mutated = False
    try:
        ev.activity = "WALKING"  # type: ignore
        mutated = True
    except (FrozenInstanceError, AttributeError):
        pass

    assert mutated is False, "SuspiciousActivityEvent must be strictly immutable"
    print("[PASS] Test 25: SuspiciousActivityEvent is strictly immutable (FrozenInstanceError on mutation).")


def run_all_tests():
    print("==================================================")
    print("RUNNING SUSPICIOUS ACTIVITY ENGINE TEST SUITE")
    print("==================================================")
    test_1_engine_initialization()
    test_2_empty_frame()
    test_3_single_person_routing()
    test_4_multiple_person_routing()
    test_5_object_routing()
    test_6_running_event_normalization()
    test_7_crawling_event_normalization()
    test_8_throwing_event_normalization()
    test_9_source_isolation()
    test_10_intra_source_track_isolation()
    test_11_person_object_track_separation()
    test_12_missing_track_id_handled_safely()
    test_13_invalid_bbox_handled_safely()
    test_14_duplicate_frame_protection()
    test_15_duplicate_event_protection()
    test_16_detector_failure_isolation()
    test_17_cleanup()
    test_18_stale_track_cleanup()
    test_19_multiple_activity_types_in_same_frame()
    test_20_rtsp_compatible_source_id()
    test_21_uploaded_video_source_id()
    test_22_no_raw_frames_stored_in_history()
    test_23_throwing_rejects_vehicle_classes()
    test_24_detector_metadata_preservation()
    test_25_event_immutability()
    print("==================================================")
    print("ALL 25 SUSPICIOUS ENGINE TESTS PASSED SUCCESSFULLY!")
    print("==================================================")


if __name__ == "__main__":
    run_all_tests()
