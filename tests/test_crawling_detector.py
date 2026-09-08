"""
Unit Tests for CrawlingDetector
===============================
Validates the geometric and kinematic Crawling Detector against all requirements:
  1. Standing person -> 0 crawling events.
  2. Normal walking -> 0 crawling events.
  3. Brief bending -> 0 crawling events.
  4. Sitting stationary -> 0 crawling events.
  5. Kneeling stationary -> 0 crawling events.
  6. Brief crouching -> 0 crawling events.
  7. Sustained crawling -> exactly 1 crawling confirmation.
  8. Crawling below minimum duration -> 0 crawling events.
  9. Crawling then continuing -> still exactly 1 event (no duplicate flood).
  10. Stop crawling then crawl again -> exactly 2 distinct confirmations.
  11. Insufficient history -> 0 crawling events.
  12. Non-person object -> 0 crawling events.
  13. track_id=None -> safely ignored without error or state corruption.
  14. Same track ID on different sources -> isolated state.
  15. Bounding-box jitter -> 0 false events.
  16. Extreme box-size jump -> rejected by consistency guard.
  17. Low geometry change without horizontal movement -> 0 crawling events.
  18. Multi-person scene -> only crawler triggers.
  19. Walking -> crawling transition triggers exactly 1 event.
  20. Crawling -> walking transition/reset properly resets state.
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
from ai_engine.modules.behavior.suspicious.crawling_detector import CrawlingDetector, CrawlingDetection


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


def feed_track(buffer, detector, source_id, track_id, class_name, observations_data, dt=0.1, start_t=0.0):
    """
    Feeds a list of (x1, y1, x2, y2) positions to buffer and detector.
    Returns list of emitted CrawlingDetection events.
    """
    events = []
    t = start_t
    for idx, (x1, y1, x2, y2) in enumerate(observations_data):
        det = MockDet(track_id, class_name, x1, y1, x2, y2)
        obs = buffer.update(source_id, det, timestamp_sec=t, frame_index=idx)
        res = detector.process_observation(source_id, obs, buffer)
        if res is not None:
            events.append(res)
        t += dt
    return events


def test_1_standing_person():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = CrawlingDetector()
    source = "cam_01"
    tid = 1

    # Standing: height=200, width=60 (aspect_ratio = 0.30 < 1.05)
    positions = [(100, 100, 160, 300) for _ in range(25)]
    events = feed_track(buffer, detector, source, tid, "person", positions, dt=0.1)

    assert len(events) == 0, f"Expected 0 events for standing person, got {len(events)}"
    assert detector.get_track_state(source, tid) == "NOT_CRAWLING"
    print("[PASS] Test 1: Standing person produces 0 crawling events.")


def test_2_normal_walking():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = CrawlingDetector()
    source = "cam_01"
    tid = 2

    # Walking: height=200, width=65 (aspect_ratio = 0.325), moves 15px per frame
    positions = [(100 + i * 15, 100, 165 + i * 15, 300) for i in range(25)]
    events = feed_track(buffer, detector, source, tid, "person", positions, dt=0.1)

    assert len(events) == 0, f"Expected 0 events for normal walking, got {len(events)}"
    assert detector.get_track_state(source, tid) == "NOT_CRAWLING"
    print("[PASS] Test 2: Normal walking produces 0 crawling events.")


def test_3_brief_bending():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = CrawlingDetector(min_crawling_duration_sec=1.5)
    source = "cam_01"
    tid = 3

    # 1. Standing for 5 frames (0.5s)
    positions = [(100, 100, 160, 300) for _ in range(5)]
    # 2. Bending down to tie shoes for 6 frames (0.6s < 1.5s): width=130, height=100 (aspect=1.3)
    positions += [(100, 200, 230, 300) for _ in range(6)]
    # 3. Standing back up for 8 frames (0.8s)
    positions += [(100, 100, 160, 300) for _ in range(8)]

    events = feed_track(buffer, detector, source, tid, "person", positions, dt=0.1)
    assert len(events) == 0, f"Expected 0 events for brief 0.6s bending, got {len(events)}"
    assert detector.get_track_state(source, tid) == "NOT_CRAWLING"
    print("[PASS] Test 3: Brief bending to tie shoe (< 1.5s) produces 0 crawling events.")


def test_4_sitting_stationary():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = CrawlingDetector(min_crawling_duration_sec=1.5, min_horizontal_speed=0.10)
    source = "cam_01"
    tid = 4

    # Baseline standing for 5 frames
    positions = [(100, 100, 160, 300) for _ in range(5)]
    # Sitting on ground stationary for 25 frames (2.5s > 1.5s): width=120, height=90 (aspect=1.33)
    # But horizontal displacement is ZERO (stays at x=100)
    positions += [(100, 210, 220, 300) for _ in range(25)]

    events = feed_track(buffer, detector, source, tid, "person", positions, dt=0.1)
    assert len(events) == 0, f"Expected 0 events for stationary sitting (no locomotion), got {len(events)}"
    assert detector.get_track_state(source, tid) == "NOT_CRAWLING"
    print("[PASS] Test 4: Stationary sitting for 2.5s produces 0 crawling events (no locomotion).")


def test_5_kneeling_stationary():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = CrawlingDetector()
    source = "cam_01"
    tid = 5

    # Standing for 5 frames
    positions = [(100, 100, 160, 300) for _ in range(5)]
    # Kneeling: height=130, width=80 (aspect=0.615 < 1.05), stationary for 20 frames
    positions += [(100, 170, 180, 300) for _ in range(20)]

    events = feed_track(buffer, detector, source, tid, "person", positions, dt=0.1)
    assert len(events) == 0, f"Expected 0 events for kneeling, got {len(events)}"
    print("[PASS] Test 5: Kneeling produces 0 crawling events.")


def test_6_brief_crouching():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = CrawlingDetector(min_crawling_duration_sec=1.5)
    source = "cam_01"
    tid = 6

    # Standing 5 frames
    positions = [(100, 100, 160, 300) for _ in range(5)]
    # Crouching for 7 frames (0.7s < 1.5s): width=120, height=95 (aspect=1.26)
    positions += [(100 + i * 5, 205, 220 + i * 5, 300) for i in range(7)]
    # Stand back up
    positions += [(135, 100, 195, 300) for _ in range(6)]

    events = feed_track(buffer, detector, source, tid, "person", positions, dt=0.1)
    assert len(events) == 0, f"Expected 0 events for brief crouching, got {len(events)}"
    print("[PASS] Test 6: Brief crouching (< 1.5s) produces 0 crawling events.")


def test_7_sustained_crawling():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = CrawlingDetector(min_crawling_duration_sec=1.5)
    source = "cam_01"
    tid = 7

    # 1. Standing for 5 frames (seed baseline standing height = 200px)
    positions = [(100, 100, 160, 300) for _ in range(5)]

    # 2. Prone crawling for 20 frames (2.0s > 1.5s):
    # Width=130, Height=90 (aspect=1.44 >= 1.05, relative_height = 90/200 = 0.45 <= 0.75)
    # Translating horizontally: 8 px per 0.1s frame (speed = 80px/s = 0.4 heights/s)
    x = 100
    for _ in range(20):
        positions.append((x, 210, x + 130, 300))
        x += 8

    events = feed_track(buffer, detector, source, tid, "person", positions, dt=0.1)
    assert len(events) == 1, f"Expected exactly 1 crawling confirmation, got {len(events)}"
    ev = events[0]
    assert ev.track_id == tid
    assert ev.activity == "CRAWLING"
    # New multi-signal detector: aspect_ratio threshold is 0.8 (was 1.05)
    assert ev.aspect_ratio >= 0.8, f"Expected aspect_ratio >= 0.8, got {ev.aspect_ratio}"
    # New relative height threshold: <= 0.80 (was <= 0.75)
    assert ev.relative_height <= 0.80, f"Expected relative_height <= 0.80, got {ev.relative_height}"
    assert ev.horizontal_speed >= 0.10
    assert ev.duration_sec >= 1.0, f"Expected duration >= 1.0s, got {ev.duration_sec}"
    assert detector.get_track_state(source, tid) == "CRAWLING_CONFIRMED"
    print(f"[PASS] Test 7: Sustained crawling confirmed (Aspect: {ev.aspect_ratio}, RelHeight: {ev.relative_height}, Speed: {ev.horizontal_speed} h/s).")


def test_8_crawling_below_minimum_duration():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = CrawlingDetector(min_crawling_duration_sec=1.5)
    source = "cam_01"
    tid = 8

    # Standing 5 frames
    positions = [(100, 100, 160, 300) for _ in range(5)]
    # Crawls for only 10 frames (1.0s < 1.5s threshold)
    x = 100
    for _ in range(10):
        positions.append((x, 210, x + 130, 300))
        x += 8
    # Stands up for 6 frames
    for _ in range(6):
        positions.append((x, 100, x + 60, 300))

    events = feed_track(buffer, detector, source, tid, "person", positions, dt=0.1)
    assert len(events) == 0, f"Expected 0 events for 1.0s crawl (< 1.5s min), got {len(events)}"
    assert detector.get_track_state(source, tid) == "NOT_CRAWLING"
    print("[PASS] Test 8: Crawling below minimum duration produces 0 events.")


def test_9_crawling_continuing_no_duplicate_spam():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = CrawlingDetector(min_crawling_duration_sec=1.5)
    source = "cam_01"
    tid = 9

    # Standing 5 frames
    positions = [(100, 100, 160, 300) for _ in range(5)]
    # Crawls for 35 frames (3.5s continuous crawling)
    x = 100
    for _ in range(35):
        positions.append((x, 210, x + 130, 300))
        x += 8

    events = feed_track(buffer, detector, source, tid, "person", positions, dt=0.1)
    # Must emit exactly 1 event and NOT flood every frame
    assert len(events) == 1, f"Expected exactly 1 event for continuous 3.5s crawl, got {len(events)}"
    assert detector.get_track_state(source, tid) == "CRAWLING_CONFIRMED"
    print("[PASS] Test 9: Continuous crawling emits exactly 1 event with zero event flooding.")


def test_10_stop_and_crawl_again():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = CrawlingDetector(min_crawling_duration_sec=1.5, stop_duration_sec=1.0)
    source = "cam_01"
    tid = 10

    positions = []
    x = 100
    # Seed standing baseline
    for _ in range(5):
        positions.append((x, 100, x + 60, 300))
        x += 5

    # Episode 1: Crawl for 20 frames (2.0s >= 1.5s) -> triggers event #1
    for _ in range(20):
        positions.append((x, 210, x + 130, 300))
        x += 8

    # Stop & Stand up: Walk upright for 15 frames (1.5s >= 1.0s stop_duration) -> resets to NOT_CRAWLING
    for _ in range(15):
        positions.append((x, 100, x + 60, 300))
        x += 10

    # Episode 2: Crawl again for 20 frames (2.0s) -> triggers event #2
    for _ in range(20):
        positions.append((x, 210, x + 130, 300))
        x += 8

    events = feed_track(buffer, detector, source, tid, "person", positions, dt=0.1)
    assert len(events) == 2, f"Expected exactly 2 distinct crawling episodes, got {len(events)}"
    assert events[0].timestamp_sec < events[1].timestamp_sec
    print("[PASS] Test 10: Crawl -> Stand up -> Crawl again produces exactly 2 distinct confirmations.")


def test_11_insufficient_history():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = CrawlingDetector(min_history_observations=4)
    source = "cam_01"

    # Only 2 observations in buffer
    positions = [(100, 210, 230, 300), (108, 210, 238, 300)]
    events = feed_track(buffer, detector, source, 11, "person", positions, dt=0.1)
    assert len(events) == 0, "Must not evaluate with insufficient history (< 4)"
    print("[PASS] Test 11: Insufficient history produces 0 events.")


def test_12_non_person_object():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = CrawlingDetector(min_crawling_duration_sec=1.5)
    source = "cam_01"

    # A dog or low suitcase moving horizontally (aspect=1.4, height=80)
    positions = [(100 + i * 8, 220, 230 + i * 8, 300) for i in range(25)]
    events_dog = feed_track(buffer, detector, source, 12, "dog", positions, dt=0.1)
    events_bag = feed_track(buffer, detector, source, 13, "suitcase", positions, dt=0.1)

    assert len(events_dog) == 0, "Non-person (dog) must never trigger crawling"
    assert len(events_bag) == 0, "Non-person (suitcase) must never trigger crawling"
    print("[PASS] Test 12: Non-person objects (dog, suitcase) produce 0 crawling events.")


def test_13_track_id_none():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = CrawlingDetector()
    source = "cam_01"

    det = MockDet(None, "person", 100, 210, 230, 300)
    obs = buffer.update(source, det, timestamp_sec=1.0)
    res = detector.process_observation(source, obs, buffer)

    assert obs is None
    assert res is None
    assert detector.get_track_state(source, 1) == "NOT_CRAWLING"
    print("[PASS] Test 13: track_id=None safely ignored without error or state corruption.")


def test_14_source_isolation():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = CrawlingDetector(min_crawling_duration_sec=1.5)
    tid = 14  # Same track ID on two cameras

    # On cam_east: Person crawls
    crawl_pos = [(100, 100, 160, 300) for _ in range(5)]
    x = 100
    for _ in range(20):
        crawl_pos.append((x, 210, x + 130, 300))
        x += 8
    events_east = feed_track(buffer, detector, "cam_east", tid, "person", crawl_pos, dt=0.1)

    # On cam_west: Person stands/walks
    stand_pos = [(100 + i * 10, 100, 160 + i * 10, 300) for i in range(25)]
    events_west = feed_track(buffer, detector, "cam_west", tid, "person", stand_pos, dt=0.1)

    assert len(events_east) == 1, "cam_east must confirm crawling"
    assert len(events_west) == 0, "cam_west must NOT confirm crawling"
    assert detector.get_track_state("cam_east", tid) == "CRAWLING_CONFIRMED"
    assert detector.get_track_state("cam_west", tid) == "NOT_CRAWLING"
    print("[PASS] Test 14: Different sources with identical track IDs remain strictly isolated.")


def test_15_bounding_box_jitter():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = CrawlingDetector()
    source = "cam_01"
    tid = 15

    # Standing person with noisy boundaries (+- 4px jitter)
    import random
    random.seed(99)
    positions = []
    for _ in range(25):
        jx = random.randint(-4, 4)
        jy = random.randint(-4, 4)
        positions.append((100 + jx, 100 + jy, 160 + jx, 300 + jy))

    events = feed_track(buffer, detector, source, tid, "person", positions, dt=0.1)
    assert len(events) == 0, f"Expected 0 events from jitter, got {len(events)}"
    print("[PASS] Test 15: Bounding-box boundary jitter does not trigger false crawling.")


def test_16_extreme_box_size_jump():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = CrawlingDetector(max_box_change_ratio=2.2)
    source = "cam_01"
    tid = 16

    # Normal standing, then sudden anomalous 3x box dimension jump (tracker glitch)
    positions = [
        (100, 100, 160, 300),  # h=200, w=60
        (105, 100, 165, 300),
        (110, 100, 170, 300),
        (115, 100, 175, 300),
        (120, 20, 480, 600),   # anomalous jump: h=580, w=360 (>2.5x)
        (125, 20, 485, 600),
    ]
    events = feed_track(buffer, detector, source, tid, "person", positions, dt=0.1)
    assert len(events) == 0, "Extreme bounding box size jump must be rejected"
    print("[PASS] Test 16: Extreme box-size jump correctly rejected by consistency guard.")


def test_17_low_geometry_without_horizontal_motion():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = CrawlingDetector(min_crawling_duration_sec=1.5, min_horizontal_speed=0.10)
    source = "cam_01"
    tid = 17

    # Person lying prone on the ground, completely still for 30 frames (3.0s)
    # dx = 0, dy = 0 -> speed = 0.0 < 0.10
    positions = [(100, 100, 160, 300) for _ in range(5)]  # standing baseline
    positions += [(100, 220, 230, 300) for _ in range(30)] # lying down motionless

    events = feed_track(buffer, detector, source, tid, "person", positions, dt=0.1)
    assert len(events) == 0, f"Expected 0 events for stationary prone person, got {len(events)}"
    print("[PASS] Test 17: Prone posture without horizontal movement produces 0 crawling events.")


def test_18_multi_person_scene():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = CrawlingDetector(min_crawling_duration_sec=1.5)
    source = "cam_01"

    events = []
    p1_x = 100
    p2_x = 500
    t = 0.0

    # Person 1 walks (w=60, h=200). Person 2 crawls (w=130, h=90, moves 8px/frame)
    # Seed standing history for both
    for idx in range(5):
        d1 = MockDet(1, "person", p1_x, 100, p1_x + 60, 300)
        d2 = MockDet(2, "person", p2_x, 100, p2_x + 60, 300)
        o1 = buffer.update(source, d1, timestamp_sec=t, frame_index=idx)
        o2 = buffer.update(source, d2, timestamp_sec=t, frame_index=idx)
        detector.process_observation(source, o1, buffer)
        detector.process_observation(source, o2, buffer)
        p1_x += 10
        t += 0.1

    # Now Person 2 crawls for 20 frames
    for idx in range(5, 25):
        d1 = MockDet(1, "person", p1_x, 100, p1_x + 60, 300)
        d2 = MockDet(2, "person", p2_x, 210, p2_x + 130, 300)
        o1 = buffer.update(source, d1, timestamp_sec=t, frame_index=idx)
        o2 = buffer.update(source, d2, timestamp_sec=t, frame_index=idx)
        r1 = detector.process_observation(source, o1, buffer)
        r2 = detector.process_observation(source, o2, buffer)
        if r1: events.append(r1)
        if r2: events.append(r2)
        p1_x += 10
        p2_x += 8
        t += 0.1

    assert len(events) == 1, f"Expected 1 event, got {len(events)}"
    assert events[0].track_id == 2, "Only Person 2 (crawler) must trigger"
    assert detector.get_track_state(source, 1) == "NOT_CRAWLING"
    assert detector.get_track_state(source, 2) == "CRAWLING_CONFIRMED"
    print("[PASS] Test 18: In multi-person frame, only the crawler triggers confirmation.")


def test_19_walk_to_crawl_transition():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = CrawlingDetector(min_crawling_duration_sec=1.5)
    source = "cam_01"
    tid = 19

    # 1. Walks upright for 10 frames (1.0s)
    positions = []
    x = 100
    for _ in range(10):
        positions.append((x, 100, x + 60, 300))
        x += 12

    # 2. Drops to ground and crawls for 20 frames (2.0s)
    for _ in range(20):
        positions.append((x, 210, x + 130, 300))
        x += 8

    events = feed_track(buffer, detector, source, tid, "person", positions, dt=0.1)
    assert len(events) == 1, f"Expected exactly 1 transition event, got {len(events)}"
    assert events[0].timestamp_sec >= 2.5
    print("[PASS] Test 19: Walk -> crawl transition produces exactly 1 confirmation.")


def test_20_crawl_to_walk_reset():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = CrawlingDetector(min_crawling_duration_sec=1.5, stop_duration_sec=1.0)
    source = "cam_01"
    tid = 20

    # Seed standing
    positions = [(100, 100, 160, 300) for _ in range(5)]
    # Crawl 20 frames (2.0s) -> confirmed
    x = 100
    for _ in range(20):
        positions.append((x, 210, x + 130, 300))
        x += 8
    # Stand up and walk for 15 frames (1.5s >= 1.0s stop_duration)
    for _ in range(15):
        positions.append((x, 100, x + 60, 300))
        x += 12

    events = feed_track(buffer, detector, source, tid, "person", positions, dt=0.1)
    assert len(events) == 1
    # Verify state reset to NOT_CRAWLING
    assert detector.get_track_state(source, tid) == "NOT_CRAWLING"
    print("[PASS] Test 20: Crawl -> walk transition cleanly resets detector state to NOT_CRAWLING.")


def test_21_regression_running_never_crawling():
    """Regression: Fast running (even with stride bbox contraction) must NEVER trigger Crawling."""
    buffer = TrackHistoryBuffer(max_history=20)
    detector = CrawlingDetector()
    source = "cam_01"
    tid = 21

    # Running person with upright aspect ratio (0.35 - 0.45) moving fast
    positions = []
    x = 100
    for i in range(25):
        # Simulated leg stride: height oscillates 180 to 200, width 70 to 80 (AR = 0.38 - 0.44)
        h = 180 if i % 2 == 0 else 200
        w = 80 if i % 2 == 0 else 70
        positions.append((x, 100, x + w, 100 + h))
        x += 30  # fast running speed = 1.5 heights/s

    events = feed_track(buffer, detector, source, tid, "person", positions, dt=0.1)
    assert len(events) == 0, f"Expected 0 crawling events for running person, got {len(events)}"
    assert detector.get_track_state(source, tid) == "NOT_CRAWLING"
    print("[PASS] Test 21: Running person with stride contraction produces 0 crawling events.")


def test_22_regression_start_already_crawling_detected():
    """Regression: Person entering frame already prone/crawling triggers exactly 1 Crawling event."""
    buffer = TrackHistoryBuffer(max_history=20)
    detector = CrawlingDetector()
    source = "cam_01"
    tid = 22

    # Prone from frame 0: width=180, height=90 (AR = 2.0 > 1.10), moves 4px per frame (speed = 0.22 h/s)
    positions = [(100 + i * 4, 300, 280 + i * 4, 390) for i in range(15)]
    events = feed_track(buffer, detector, source, tid, "person", positions, dt=0.1)

    assert len(events) == 1, f"Expected 1 crawling event for start-already-crawling, got {len(events)}"
    assert events[0].activity == "CRAWLING"
    assert detector.get_track_state(source, tid) == "CRAWLING_CONFIRMED"
    print("[PASS] Test 22: Person entering frame already crawling is correctly confirmed.")


def test_23_regression_different_fps_crawling():
    """Regression: Same crawling motion at 15 FPS, 30 FPS, and 60 FPS is confirmed identically."""
    for fps in [15, 30, 60]:
        buffer = TrackHistoryBuffer(max_history=60)
        detector = CrawlingDetector()
        source = f"cam_{fps}fps"
        tid = 23
        dt = 1.0 / fps
        total_time = 1.5  # 1.5 seconds of crawling
        n_frames = int(total_time * fps)

        # 0.2 body-heights/sec on h=100px -> 20px/sec -> 20 * dt px/frame
        positions = []
        x = 100.0
        for _ in range(n_frames):
            positions.append((int(x), 300, int(x + 150), 400))  # AR = 1.5, h = 100
            x += 20.0 * dt

        events = feed_track(buffer, detector, source, tid, "person", positions, dt=dt)
        assert len(events) == 1, f"Expected 1 crawling event at {fps} FPS, got {len(events)}"
    print("[PASS] Test 23: Crawling detection is invariant across 15, 30, and 60 FPS.")


def test_24_regression_different_scales_crawling():
    """Regression: Crawling detection is invariant to subject scale (50px, 200px, 600px)."""
    for scale_h in [50, 200, 600]:
        buffer = TrackHistoryBuffer(max_history=30)
        detector = CrawlingDetector()
        source = f"cam_scale_{scale_h}"
        tid = 24
        scale_w = int(scale_h * 1.6)  # AR = 1.6

        # Crawl at 0.25 h/s for 1.2s (12 frames at dt=0.1)
        speed_px_per_frame = (0.25 * scale_h) * 0.1
        positions = []
        x = 100.0
        for _ in range(15):
            positions.append((int(x), 200, int(x + scale_w), 200 + scale_h))
            x += speed_px_per_frame

        events = feed_track(buffer, detector, source, tid, "person", positions, dt=0.1)
        assert len(events) == 1, f"Expected 1 crawling event at scale h={scale_h}, got {len(events)}"
    print("[PASS] Test 24: Crawling detection is scale-invariant across 50px, 200px, and 600px.")


def run_all_tests():
    print("==================================================")
    print("RUNNING CRAWLING DETECTOR COMPREHENSIVE TEST SUITE")
    print("==================================================")
    test_1_standing_person()
    test_2_normal_walking()
    test_3_brief_bending()
    test_4_sitting_stationary()
    test_5_kneeling_stationary()
    test_6_brief_crouching()
    test_7_sustained_crawling()
    test_8_crawling_below_minimum_duration()
    test_9_crawling_continuing_no_duplicate_spam()
    test_10_stop_and_crawl_again()
    test_11_insufficient_history()
    test_12_non_person_object()
    test_13_track_id_none()
    test_14_source_isolation()
    test_15_bounding_box_jitter()
    test_16_extreme_box_size_jump()
    test_17_low_geometry_without_horizontal_motion()
    test_18_multi_person_scene()
    test_19_walk_to_crawl_transition()
    test_20_crawl_to_walk_reset()
    test_21_regression_running_never_crawling()
    test_22_regression_start_already_crawling_detected()
    test_23_regression_different_fps_crawling()
    test_24_regression_different_scales_crawling()
    print("==================================================")
    print("ALL 24 CRAWLING DETECTOR TESTS PASSED SUCCESSFULLY!")
    print("==================================================")


if __name__ == "__main__":
    run_all_tests()

