"""
Unit Tests for RunningDetector
==============================
Validates the kinematic Running Detector against all requirements:
  1. Stationary person -> 0 Running detections.
  2. Normal walking below threshold -> 0 Running detections.
  3. Sustained running above threshold -> exactly 1 confirmation.
  4. One isolated fast movement followed by walking -> 0 Running detections.
  5. Running sustained for insufficient observations -> 0 detections.
  6. Running sustained for required observations -> exactly 1 detection.
  7. Non-person object moving quickly -> 0 Running detections.
  8. track_id=None -> 0 detections and no state corruption.
  9. Different source_ids with same track_id -> completely isolated states.
  10. Bounding-box jitter -> should not falsely classify as running.
  11. Extreme bounding-box size jump -> must not create artificial running velocity.
  12. Non-monotonic/noisy movement -> does not trigger false running.
  13. Person starts running after walking -> exactly 1 confirmation at the transition.
  14. Person stops running and later runs again -> two separate running confirmations.
  15. Timestamp dt <= 0 -> safely ignored.
  16. Track cleanup -> stale detector state removed safely.
  17. Multiple persons: person A running, person B walking -> only person A confirms Running.
  18. Regression-style repeated processing -> detector state remains bounded and stable.
"""

import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent if Path(__file__).resolve().parent.name == "tests" else Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from ai_engine.modules.behavior.suspicious.track_history import TrackHistoryBuffer
from ai_engine.modules.behavior.suspicious.running_detector import RunningDetector, RunningDetection


class MockDet:
    """Mock detection for feeder."""
    def __init__(self, track_id, class_name, x1, y1, x2, y2, confidence=0.90):
        self.track_id = track_id
        self.class_name = class_name
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.confidence = confidence


def feed_track(buffer, detector, source_id, track_id, class_name, positions, dt=0.1, start_t=0.0):
    """
    Feeds a series of (x1, y1, x2, y2) positions to buffer and detector.
    Returns list of emitted RunningDetection events.
    """
    events = []
    t = start_t
    for idx, (x1, y1, x2, y2) in enumerate(positions):
        det = MockDet(track_id, class_name, x1, y1, x2, y2)
        obs = buffer.update(source_id, det, timestamp_sec=t, frame_index=idx)
        res = detector.process_observation(source_id, obs, buffer)
        if res is not None:
            events.append(res)
        t += dt
    return events


def test_1_stationary_person():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = RunningDetector(running_threshold=2.0, min_consecutive_frames=5)
    source = "cam_01"
    tid = 1

    # Person stands in one spot (height=200, width=60) for 15 frames
    positions = [(100, 100, 160, 300) for _ in range(15)]
    events = feed_track(buffer, detector, source, tid, "person", positions, dt=0.1)

    assert len(events) == 0, f"Expected 0 events for stationary person, got {len(events)}"
    assert detector.get_track_state(source, tid) == "NOT_RUNNING"
    print("[PASS] Test 1: Stationary person produces 0 running detections.")


def test_2_normal_walking():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = RunningDetector(running_threshold=2.0, min_consecutive_frames=5)
    source = "cam_01"
    tid = 2

    # Person walks at 0.8 body-heights/sec (height=200 -> 160 px/sec -> 16 px per 0.1s frame)
    positions = [(100 + i * 16, 100, 160 + i * 16, 300) for i in range(15)]
    events = feed_track(buffer, detector, source, tid, "person", positions, dt=0.1)

    assert len(events) == 0, f"Expected 0 events for normal walking, got {len(events)}"
    assert detector.get_track_state(source, tid) == "NOT_RUNNING"
    print("[PASS] Test 2: Normal walking below threshold produces 0 running detections.")


def test_3_sustained_running():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = RunningDetector(running_threshold=2.0, min_consecutive_frames=5)
    source = "cam_01"
    tid = 3

    # Person runs at 2.6 body-heights/sec (height=200 -> 520 px/sec -> 52 px per 0.1s frame)
    # First 4 frames build history buffer, then 5 consecutive qualifying frames trigger running
    positions = [(100 + i * 52, 100, 160 + i * 52, 300) for i in range(12)]
    events = feed_track(buffer, detector, source, tid, "person", positions, dt=0.1)

    assert len(events) == 1, f"Expected exactly 1 confirmation, got {len(events)}"
    ev = events[0]
    assert ev.track_id == tid
    assert ev.activity == "RUNNING"
    assert ev.normalized_speed >= 2.0
    assert ev.consecutive_frames >= 3, f"Expected >= 3 qualifying samples in window, got {ev.consecutive_frames}"
    assert detector.get_track_state(source, tid) == "RUNNING_CONFIRMED"
    print(f"[PASS] Test 3: Sustained running triggered exactly 1 event (Speed: {ev.normalized_speed} h/s).")


def test_4_isolated_fast_movement():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = RunningDetector(running_threshold=2.0, min_consecutive_frames=5)
    source = "cam_01"
    tid = 4

    # 5 frames walking, 1 fast jump/step (50 px), followed by 6 frames walking
    positions = []
    x = 100
    for _ in range(5):
        positions.append((x, 100, x + 60, 300))
        x += 16  # walking
    # Single fast step
    x += 60
    positions.append((x, 100, x + 60, 300))
    # Return to walking
    for _ in range(6):
        x += 16
        positions.append((x, 100, x + 60, 300))

    events = feed_track(buffer, detector, source, tid, "person", positions, dt=0.1)
    assert len(events) == 0, f"Expected 0 events for single isolated fast step, got {len(events)}"
    print("[PASS] Test 4: Isolated fast step rejected by temporal confirmation.")


def test_5_insufficient_duration():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = RunningDetector(running_threshold=2.0, min_consecutive_frames=5)
    source = "cam_01"
    tid = 5

    # 4 frames walking, then only 3 frames running, then stop
    positions = []
    x = 100
    for _ in range(4):
        positions.append((x, 100, x + 60, 300))
        x += 16
    for _ in range(3):  # only 3 running frames (need 5)
        positions.append((x, 100, x + 60, 300))
        x += 55
    for _ in range(4):
        positions.append((x, 100, x + 60, 300))
        x += 5

    events = feed_track(buffer, detector, source, tid, "person", positions, dt=0.1)
    assert len(events) == 0, f"Expected 0 events for running < 5 frames, got {len(events)}"
    print("[PASS] Test 5: Running for 3 frames (< 5 frames required) produces 0 detections.")


def test_6_required_duration_triggers():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = RunningDetector(running_threshold=2.0, min_consecutive_frames=5)
    source = "cam_01"
    tid = 6

    # Exactly required consecutive frames running
    positions = []
    x = 100
    for _ in range(4):  # seed history
        positions.append((x, 100, x + 60, 300))
        x += 50
    for _ in range(5):  # 5 consecutive running frames
        positions.append((x, 100, x + 60, 300))
        x += 50

    events = feed_track(buffer, detector, source, tid, "person", positions, dt=0.1)
    assert len(events) == 1, f"Expected exactly 1 detection, got {len(events)}"
    assert events[0].consecutive_frames >= 3, f"Expected >= 3 samples in window, got {events[0].consecutive_frames}"
    print("[PASS] Test 6: Running for required duration triggers exactly 1 detection.")


def test_7_non_person_fast_object():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = RunningDetector(running_threshold=2.0, min_consecutive_frames=5)
    source = "cam_01"

    # Fast moving car
    car_positions = [(100 + i * 100, 100, 300 + i * 100, 200) for i in range(12)]
    events_car = feed_track(buffer, detector, source, 701, "car", car_positions, dt=0.1)
    assert len(events_car) == 0, "Car must never trigger running"

    # Fast moving backpack / thrown object
    bag_positions = [(100 + i * 80, 100, 150 + i * 80, 150) for i in range(12)]
    events_bag = feed_track(buffer, detector, source, 702, "backpack", bag_positions, dt=0.1)
    assert len(events_bag) == 0, "Backpack must never trigger running"
    print("[PASS] Test 7: Fast non-person objects (car, backpack) produce 0 running detections.")


def test_8_none_track_id():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = RunningDetector()
    source = "cam_01"

    # Detection with track_id=None
    det = MockDet(None, "person", 100, 100, 160, 300)
    obs = buffer.update(source, det, timestamp_sec=1.0)
    res = detector.process_observation(source, obs, buffer)

    assert obs is None
    assert res is None
    assert detector.get_track_state(source, 1) == "NOT_RUNNING"
    print("[PASS] Test 8: track_id=None is safely ignored without state corruption.")


def test_9_source_isolation():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = RunningDetector(running_threshold=2.0, min_consecutive_frames=5)
    tid = 99  # Same track ID on two cameras

    # On cam_north: person runs
    run_positions = [(100 + i * 50, 100, 160 + i * 50, 300) for i in range(10)]
    events_north = feed_track(buffer, detector, "cam_north", tid, "person", run_positions, dt=0.1)

    # On cam_south: person walks
    walk_positions = [(100 + i * 10, 100, 160 + i * 10, 300) for i in range(10)]
    events_south = feed_track(buffer, detector, "cam_south", tid, "person", walk_positions, dt=0.1)

    assert len(events_north) == 1, "cam_north must detect running"
    assert len(events_south) == 0, "cam_south must NOT detect running"
    assert detector.get_track_state("cam_north", tid) == "RUNNING_CONFIRMED"
    assert detector.get_track_state("cam_south", tid) == "NOT_RUNNING"
    print("[PASS] Test 9: Different camera sources with same track ID remain completely isolated.")


def test_10_bounding_box_jitter():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = RunningDetector(running_threshold=2.0, min_consecutive_frames=5)
    source = "cam_01"
    tid = 10

    # Person walking slowly with random boundary jitter (+- 3px)
    import random
    random.seed(42)
    positions = []
    x = 100
    for _ in range(15):
        jx = random.randint(-3, 3)
        jy = random.randint(-3, 3)
        positions.append((x + jx, 100 + jy, x + 60 + jx, 300 + jy))
        x += 10  # 10 px per 0.1s = 0.5 heights/s

    events = feed_track(buffer, detector, source, tid, "person", positions, dt=0.1)
    assert len(events) == 0, f"Expected 0 events with box jitter, got {len(events)}"
    print("[PASS] Test 10: Bounding box boundary jitter does not trigger false running.")


def test_11_extreme_box_size_jump():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = RunningDetector(running_threshold=2.0, min_consecutive_frames=5, max_box_change_ratio=2.0)
    source = "cam_01"
    tid = 11

    # Normal standing person (h=200) suddenly gets tracker-swapped to full-screen box (h=600)
    positions = [
        (100, 100, 160, 300),  # h=200
        (110, 100, 170, 300),
        (120, 100, 180, 300),
        (130, 100, 190, 300),
        (140, 50, 440, 650),   # sudden 3x jump in height (h=600)
        (150, 50, 450, 650),
    ]
    events = feed_track(buffer, detector, source, tid, "person", positions, dt=0.1)
    assert len(events) == 0, "Extreme bounding box size jump must be rejected"
    print("[PASS] Test 11: Extreme bounding box size jump correctly rejected.")


def test_12_noisy_oscillating_movement():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = RunningDetector(running_threshold=2.0, min_consecutive_frames=5)
    source = "cam_01"
    tid = 12

    # Person pacing back and forth rapidly over 10 pixels (fidgeting/turning)
    positions = []
    x = 100
    for i in range(15):
        offset = 15 if i % 2 == 0 else -15
        positions.append((x + offset, 100, x + 60 + offset, 300))

    events = feed_track(buffer, detector, source, tid, "person", positions, dt=0.1)
    # Velocity direction oscillates; smoothed average should not sustain running
    assert len(events) == 0, f"Expected 0 events for oscillating fidgeting, got {len(events)}"
    print("[PASS] Test 12: Noisy oscillating fidgeting movement does not trigger running.")


def test_13_walk_then_run_transition():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = RunningDetector(running_threshold=2.0, min_consecutive_frames=5)
    source = "cam_01"
    tid = 13

    # 1. Walks for 8 frames
    positions = []
    x = 100
    for _ in range(8):
        positions.append((x, 100, x + 60, 300))
        x += 15  # walking
    # 2. Accelerates into sprint for 12 frames (1.2s > 0.4s min_running_duration)
    for _ in range(12):
        positions.append((x, 100, x + 60, 300))
        x += 50  # running: 50px/0.1s / 200px = 2.5 h/s > running_threshold=2.0

    events = feed_track(buffer, detector, source, tid, "person", positions, dt=0.1)
    assert len(events) == 1, f"Expected exactly 1 transition event, got {len(events)}"
    # Verify the event occurred after the walk sequence (>= 0.8s elapsed)
    assert events[0].timestamp_sec >= 0.8
    print("[PASS] Test 13: Walking to running transition produces exactly 1 confirmation.")


def test_14_stop_and_run_again():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = RunningDetector(
        running_threshold=2.0,
        min_consecutive_frames=5,
        stop_threshold=0.4,
        stop_consecutive_frames=3,
        stop_duration_sec=0.5,   # stop resets after 0.5s below stop_threshold
    )
    source = "cam_01"
    tid = 14

    positions = []
    x = 100
    # Episode 1: Run for 10 frames (1.0s) -> trigger #1
    for _ in range(10):
        positions.append((x, 100, x + 60, 300))
        x += 50
    # Stop: Stand still for 8 frames (0.8s > 0.5s stop_duration) -> reset to NOT_RUNNING
    for _ in range(8):
        positions.append((x, 100, x + 60, 300))
    # Episode 2: Run again for 10 frames (1.0s) -> trigger #2
    for _ in range(10):
        positions.append((x, 100, x + 60, 300))
        x += 50

    events = feed_track(buffer, detector, source, tid, "person", positions, dt=0.1)
    assert len(events) == 2, f"Expected 2 distinct running episodes, got {len(events)}"
    assert events[0].timestamp_sec < events[1].timestamp_sec
    print("[PASS] Test 14: Stop and run again correctly produces 2 separate confirmations.")


def test_15_invalid_timestamp_dt():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = RunningDetector()
    source = "cam_01"
    tid = 15

    # Frames fed with dt = 0.0 or negative timestamps
    positions = [(100, 100, 160, 300), (200, 100, 260, 300)]
    det1 = MockDet(tid, "person", *positions[0])
    det2 = MockDet(tid, "person", *positions[1])

    obs1 = buffer.update(source, det1, timestamp_sec=5.0)
    r1 = detector.process_observation(source, obs1, buffer)
    assert r1 is None

    # Exact same timestamp (dt = 0)
    obs2 = buffer.update(source, det2, timestamp_sec=5.0)
    r2 = detector.process_observation(source, obs2, buffer)
    assert r2 is None

    # Negative timestamp jump (clock glitch)
    obs3 = buffer.update(source, det2, timestamp_sec=4.0)
    r3 = detector.process_observation(source, obs3, buffer)
    assert r3 is None
    print("[PASS] Test 15: Non-positive dt (0 or backwards jump) safely handled.")


def test_16_track_cleanup():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = RunningDetector()
    source = "cam_01"

    # Feed tracks 101, 102, 103
    p1 = [(100 + i * 50, 100, 160 + i * 50, 300) for i in range(6)]
    p2 = [(200 + i * 50, 100, 260 + i * 50, 300) for i in range(6)]
    p3 = [(300 + i * 50, 100, 360 + i * 50, 300) for i in range(6)]

    feed_track(buffer, detector, source, 101, "person", p1, dt=0.1, start_t=1.0)
    feed_track(buffer, detector, source, 102, "person", p2, dt=0.1, start_t=5.0)
    feed_track(buffer, detector, source, 103, "person", p3, dt=0.1, start_t=6.0)

    # Current time = 6.5s. Track 101 last seen at 1.5s (elapsed 5.0s > 3.0s) -> stale
    pruned = detector.cleanup(source, active_track_ids={103}, current_timestamp_sec=6.5, max_stale_seconds=3.0)
    assert 101 in pruned
    assert 103 not in pruned
    assert detector.get_track_state(source, 101) == "NOT_RUNNING"  # purged
    print("[PASS] Test 16: Track cleanup successfully prunes stale detector state.")


def test_17_multiple_persons_separation():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = RunningDetector(running_threshold=2.0, min_consecutive_frames=5)
    source = "cam_01"

    # Frame by frame: Person 1 runs (50px/frame), Person 2 walks (12px/frame)
    events = []
    p1_x = 100
    p2_x = 500
    t = 0.0

    for idx in range(12):
        d1 = MockDet(1, "person", p1_x, 100, p1_x + 60, 300)
        d2 = MockDet(2, "person", p2_x, 100, p2_x + 60, 300)

        o1 = buffer.update(source, d1, timestamp_sec=t, frame_index=idx)
        o2 = buffer.update(source, d2, timestamp_sec=t, frame_index=idx)

        r1 = detector.process_observation(source, o1, buffer)
        r2 = detector.process_observation(source, o2, buffer)

        if r1: events.append(r1)
        if r2: events.append(r2)

        p1_x += 50  # running
        p2_x += 12  # walking
        t += 0.1

    assert len(events) == 1, f"Expected 1 event, got {len(events)}"
    assert events[0].track_id == 1, "Only the running person must trigger alert"
    assert detector.get_track_state(source, 1) == "RUNNING_CONFIRMED"
    assert detector.get_track_state(source, 2) == "NOT_RUNNING"
    print("[PASS] Test 17: In multi-person frame, only the runner triggers confirmation.")


def test_18_regression_repeated_processing():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = RunningDetector(running_threshold=2.0, min_consecutive_frames=5)
    source = "cam_01"

    # Simulate 100 continuous frames of running
    positions = [(100 + i * 50, 100, 160 + i * 50, 300) for i in range(100)]
    events = feed_track(buffer, detector, source, 18, "person", positions, dt=0.1)

    # State must confirm once and NOT flood (remain in RUNNING_CONFIRMED)
    assert len(events) == 1, f"Expected exactly 1 confirmation over 100 frames, got {len(events)}"
    assert detector.get_track_state(source, 18) == "RUNNING_CONFIRMED"
    print("[PASS] Test 18: Repeated 100-frame stream confirms once with zero event flooding.")


def test_19_regression_running_without_walking_baseline():
    """Regression: Person entering frame already running (no prior walk baseline) triggers Running."""
    buffer = TrackHistoryBuffer(max_history=20)
    detector = RunningDetector()
    source = "cam_01"
    tid = 19

    # Sprints from frame 0: 30px per 0.1s frame on h=200 -> speed = 1.5 h/s
    positions = [(100 + i * 30, 100, 160 + i * 30, 300) for i in range(12)]
    events = feed_track(buffer, detector, source, tid, "person", positions, dt=0.1)

    assert len(events) == 1, f"Expected 1 running event without baseline, got {len(events)}"
    assert events[0].activity == "RUNNING"
    assert detector.get_track_state(source, tid) == "RUNNING_CONFIRMED"
    print("[PASS] Test 19: Genuine running without prior walk baseline correctly triggers running.")


def test_20_regression_crawling_never_running():
    """Regression: Prone crawling (even fast crawling) must NEVER trigger Running."""
    buffer = TrackHistoryBuffer(max_history=20)
    detector = RunningDetector()
    source = "cam_01"
    tid = 20

    # Crawling person with prone aspect ratio (AR = 1.8) moving at 0.5 h/s
    positions = [(100 + i * 10, 300, 280 + i * 10, 400) for i in range(20)]
    events = feed_track(buffer, detector, source, tid, "person", positions, dt=0.1)

    assert len(events) == 0, f"Expected 0 running events for crawling person, got {len(events)}"
    assert detector.get_track_state(source, tid) == "NOT_RUNNING"
    print("[PASS] Test 20: Prone crawling motion never triggers running.")


def test_21_regression_different_fps_running():
    """Regression: Same running motion at 15 FPS, 25 FPS, 30 FPS, and 60 FPS is confirmed identically."""
    for fps in [15, 25, 30, 60]:
        buffer = TrackHistoryBuffer(max_history=60)
        detector = RunningDetector()
        source = f"cam_{fps}fps"
        tid = 21
        dt = 1.0 / fps
        total_time = 1.2  # 1.2 seconds of running
        n_frames = int(total_time * fps)

        # 1.2 body-heights/sec on h=200px -> 240px/sec -> 240 * dt px/frame
        positions = []
        x = 100.0
        for _ in range(n_frames):
            positions.append((int(x), 100, int(x + 60), 300))
            x += 240.0 * dt

        events = feed_track(buffer, detector, source, tid, "person", positions, dt=dt)
        assert len(events) == 1, f"Expected 1 running event at {fps} FPS, got {len(events)}"
    print("[PASS] Test 21: Running detection is invariant across 15, 25, 30, and 60 FPS.")


def test_22_regression_different_scales_running():
    """Regression: Running detection is invariant to subject scale (50px, 200px, 800px)."""
    for scale_h in [50, 200, 800]:
        buffer = TrackHistoryBuffer(max_history=30)
        detector = RunningDetector()
        source = f"cam_scale_{scale_h}"
        tid = 22
        scale_w = int(scale_h * 0.35)  # AR = 0.35

        # Run at 1.4 h/s for 1.0s (10 frames at dt=0.1)
        speed_px_per_frame = (1.4 * scale_h) * 0.1
        positions = []
        x = 100.0
        for _ in range(12):
            positions.append((int(x), 100, int(x + scale_w), 100 + scale_h))
            x += speed_px_per_frame

        events = feed_track(buffer, detector, source, tid, "person", positions, dt=0.1)
        assert len(events) == 1, f"Expected 1 running event at scale h={scale_h}, got {len(events)}"
    print("[PASS] Test 22: Running detection is scale-invariant across 50px, 200px, and 800px.")


def run_all_tests():
    print("==================================================")
    print("RUNNING DETECTOR COMPREHENSIVE TEST SUITE")
    print("==================================================")
    test_1_stationary_person()
    test_2_normal_walking()
    test_3_sustained_running()
    test_4_isolated_fast_movement()
    test_5_insufficient_duration()
    test_6_required_duration_triggers()
    test_7_non_person_fast_object()
    test_8_none_track_id()
    test_9_source_isolation()
    test_10_bounding_box_jitter()
    test_11_extreme_box_size_jump()
    test_12_noisy_oscillating_movement()
    test_13_walk_then_run_transition()
    test_14_stop_and_run_again()
    test_15_invalid_timestamp_dt()
    test_16_track_cleanup()
    test_17_multiple_persons_separation()
    test_18_regression_repeated_processing()
    test_19_regression_running_without_walking_baseline()
    test_20_regression_crawling_never_running()
    test_21_regression_different_fps_running()
    test_22_regression_different_scales_running()
    print("==================================================")
    print("ALL 22 RUNNING DETECTOR TESTS PASSED SUCCESSFULLY!")
    print("==================================================")


if __name__ == "__main__":
    run_all_tests()

