"""
Unit Tests for ThrowingDetector
===============================
Validates the geometric and kinematic Throwing Detector against all requirements:
  1. No objects in frame -> 0 throwing events.
  2. Person alone -> 0 throwing events.
  3. Person walking alone -> 0 throwing events.
  4. Person carrying object -> 0 throwing events (speed and distance locked).
  5. Object stationary near person -> 0 throwing events.
  6. Object moving slowly near person -> 0 throwing events (below speed threshold).
  7. Person-object association established when co-located.
  8. Sustained valid throw -> exactly 1 throwing confirmation event.
  9. Continued post-throw motion -> still exactly 1 event (no duplicate flood).
  10. Two independent throws -> exactly 2 distinct confirmations.
  11. Object speed below threshold -> 0 throwing events.
  12. Object speed not sufficiently greater than person -> 0 throwing events.
  13. Separation not increasing -> 0 throwing events.
  14. Non-monotonic separation -> 0 throwing events (distance collapses).
  15. Poor trajectory consistency -> 0 throwing events (erratic bouncing).
  16. Pure downward drop -> 0 throwing events (drop rejection).
  17. Object starts moving without prior proximity/release (fly-by) -> 0 events.
  18. Vehicle movement -> 0 throwing events (forbidden vehicle class).
  19. Non-allowed object class -> 0 throwing events (e.g. chair).
  20. track_id=None safely ignored without error or state corruption.
  21. Same track IDs on different sources remain strictly isolated.
  22. Multi-person / multi-object scene isolates correct association.
  23. Candidate timeout and reset after inactivity.
  24. Extreme bounding-box jump rejected by consistency guard.
  25. Non-positive dt handled gracefully without crash.
  26. State cleanup correctly prunes stale candidates and sources.
  27. No event flooding over a continuous 100-frame stream.
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
from ai_engine.modules.behavior.suspicious.throwing_detector import (
    ThrowingDetector,
    ThrowingDetection,
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


def feed_pair_track(
    buffer: TrackHistoryBuffer,
    detector: ThrowingDetector,
    source_id: str,
    person_track_id: int,
    object_track_id: int,
    object_class: str,
    person_positions: list,
    object_positions: list,
    dt: float = 0.1,
    start_t: float = 0.0,
):
    """
    Feeds synchronous person and object positions into buffer and evaluates detector.
    Returns list of emitted ThrowingDetection events.
    """
    events = []
    t = start_t
    n = min(len(person_positions), len(object_positions))
    for idx in range(n):
        px1, py1, px2, py2 = person_positions[idx]
        ox1, oy1, ox2, oy2 = object_positions[idx]

        p_det = MockDet(person_track_id, "person", px1, py1, px2, py2)
        o_det = MockDet(object_track_id, object_class, ox1, oy1, ox2, oy2)

        p_obs = buffer.update(source_id, p_det, timestamp_sec=t, frame_index=idx)
        o_obs = buffer.update(source_id, o_det, timestamp_sec=t, frame_index=idx)

        frame_events = detector.process_frame(source_id, [p_obs, o_obs], buffer)
        events.extend(frame_events)
        t += dt

    return events


def test_1_no_objects():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = ThrowingDetector()
    events = detector.process_frame("cam_01", [], buffer)
    assert len(events) == 0
    print("[PASS] Test 1: Empty detections in frame produce 0 throwing events.")


def test_2_person_alone():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = ThrowingDetector()
    source = "cam_01"
    events = []
    for idx in range(10):
        det = MockDet(1, "person", 100, 100, 160, 300)
        obs = buffer.update(source, det, timestamp_sec=idx * 0.1, frame_index=idx)
        res = detector.process_frame(source, [obs], buffer)
        events.extend(res)
    assert len(events) == 0
    print("[PASS] Test 2: Person alone in frame produces 0 throwing events.")


def test_3_person_walking_alone():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = ThrowingDetector()
    source = "cam_01"
    events = []
    for idx in range(20):
        x = 100 + idx * 15
        det = MockDet(1, "person", x, 100, x + 60, 300)
        obs = buffer.update(source, det, timestamp_sec=idx * 0.1, frame_index=idx)
        res = detector.process_frame(source, [obs], buffer)
        events.extend(res)
    assert len(events) == 0
    print("[PASS] Test 3: Person walking alone produces 0 throwing events.")


def test_4_person_carrying_object():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = ThrowingDetector()
    source = "cam_01"
    pid, oid = 1, 2

    # Person walks 20 frames, carrying backpack (both translate at 10px / frame)
    # Distance between them remains exactly 30px constant (separation growth = 0)
    person_pos = [(100 + i * 10, 100, 160 + i * 10, 300) for i in range(20)]
    object_pos = [(140 + i * 10, 180, 180 + i * 10, 220) for i in range(20)]

    events = feed_pair_track(buffer, detector, source, pid, oid, "backpack", person_pos, object_pos)
    assert len(events) == 0, f"Carrying object must not trigger throwing, got {len(events)}"
    assert detector.get_candidate_state(source, pid, oid) == "PERSON_OBJECT_ASSOCIATED"
    print("[PASS] Test 4: Person walking while carrying an object produces 0 throwing events.")


def test_5_object_stationary_near_person():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = ThrowingDetector()
    source = "cam_01"
    pid, oid = 1, 2

    person_pos = [(100, 100, 160, 300) for _ in range(15)]
    object_pos = [(140, 180, 180, 220) for _ in range(15)]

    events = feed_pair_track(buffer, detector, source, pid, oid, "backpack", person_pos, object_pos)
    assert len(events) == 0
    assert detector.get_candidate_state(source, pid, oid) == "PERSON_OBJECT_ASSOCIATED"
    print("[PASS] Test 5: Stationary object near person produces 0 throwing events.")


def test_6_object_moving_slowly_near_person():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = ThrowingDetector(minimum_object_speed=2.0)
    source = "cam_01"
    pid, oid = 1, 2

    person_pos = [(100, 100, 160, 300) for _ in range(15)]
    # Object crawls at 2px per 0.1s frame = 20px/s = 0.1 body-heights/s (< 2.0 threshold)
    object_pos = [(140 + i * 2, 180, 180 + i * 2, 220) for i in range(15)]

    events = feed_pair_track(buffer, detector, source, pid, oid, "bottle", person_pos, object_pos)
    assert len(events) == 0
    print("[PASS] Test 6: Object moving slowly near person (< threshold) produces 0 throwing events.")


def test_7_association_established():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = ThrowingDetector(proximity_threshold_body_heights=1.2)
    source = "cam_01"
    pid, oid = 1, 2

    # Person height 200px (center 130, 200). Object center (160, 200), distance = 30px = 0.15 heights
    p_det = MockDet(pid, "person", 100, 100, 160, 300)
    o_det = MockDet(oid, "backpack", 140, 180, 180, 220)

    p_obs = buffer.update(source, p_det, timestamp_sec=0.0, frame_index=0)
    o_obs = buffer.update(source, o_det, timestamp_sec=0.0, frame_index=0)

    detector.process_frame(source, [p_obs, o_obs], buffer)
    state = detector.get_candidate_state(source, pid, oid)
    assert state == "PERSON_OBJECT_ASSOCIATED", f"Expected PERSON_OBJECT_ASSOCIATED, got {state}"
    print("[PASS] Test 7: Person-object candidate association established upon proximity.")


def test_8_sustained_valid_throw():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = ThrowingDetector(
        minimum_object_speed=2.0,
        confirmation_observations=3,
        minimum_separation_growth=0.3,
    )
    source = "cam_01"
    pid, oid = 1, 2

    # Person stands at (100, 100, 160, 300) (height=200, center=(130, 200))
    person_pos = [(100, 100, 160, 300) for _ in range(10)]

    # Object:
    # Frames 0-3: close to person at (140, 180, 180, 220) (center=(160, 200), dist=30px=0.15h)
    object_pos = [(140, 180, 180, 220) for _ in range(4)]
    # Frame 4: begins rapid horizontal throw! Center moves from 160 -> 210 (dx=+50, v=50/(0.1*200)=2.5 h/s)
    object_pos.append((190, 180, 230, 220)) # center 210, dist 80px = 0.40h
    # Frame 5: center 260 (dx=+50, dist 130px = 0.65h)
    object_pos.append((240, 180, 280, 220))
    # Frame 6: center 310 (dx=+50, dist 180px = 0.90h, growth = 0.90 - 0.40 = 0.50 >= 0.3)
    object_pos.append((290, 180, 330, 220))

    events = feed_pair_track(buffer, detector, source, pid, oid, "backpack", person_pos, object_pos)
    assert len(events) == 1, f"Expected exactly 1 throwing event, got {len(events)}"
    ev = events[0]
    assert ev.activity == "THROWING"
    assert ev.person_track_id == pid
    assert ev.object_track_id == oid
    assert ev.object_class == "backpack"
    assert ev.object_speed_normalized >= 2.0
    assert ev.separation >= 0.5
    assert ev.trajectory_consistency >= 0.70
    assert detector.get_candidate_state(source, pid, oid) == "THROW_CONFIRMED"
    print(f"[PASS] Test 8: Sustained valid throw confirmed (Speed: {ev.object_speed_normalized} h/s, Sep: {ev.separation} h).")


def test_9_continued_motion_no_duplicate():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = ThrowingDetector(confirmation_observations=3)
    source = "cam_01"
    pid, oid = 1, 2

    person_pos = [(100, 100, 160, 300) for _ in range(25)]
    object_pos = [(140, 180, 180, 220) for _ in range(4)]
    # Fast throw for 21 frames continuously
    for i in range(21):
        ox = 190 + i * 50
        object_pos.append((ox, 180, ox + 40, 220))

    events = feed_pair_track(buffer, detector, source, pid, oid, "backpack", person_pos, object_pos)
    assert len(events) == 1, f"Expected exactly 1 event, got {len(events)} (event flood detected)"
    print("[PASS] Test 9: Continued post-throw motion emits exactly 1 event with zero event flooding.")


def test_10_two_independent_throws():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = ThrowingDetector(confirmation_observations=3)
    source = "cam_01"

    # Throw 1: Person 1 throws Object 2 (bottle)
    p_pos1 = [(100, 100, 160, 300) for _ in range(8)]
    o_pos1 = [(140, 180, 180, 220) for _ in range(4)]
    for i in range(4):
        ox = 190 + i * 50
        o_pos1.append((ox, 180, ox + 40, 220))

    events1 = feed_pair_track(buffer, detector, source, 1, 2, "bottle", p_pos1, o_pos1, start_t=0.0)

    # Throw 2: Person 1 throws Object 3 (backpack)
    p_pos2 = [(100, 100, 160, 300) for _ in range(8)]
    o_pos2 = [(140, 180, 180, 220) for _ in range(4)]
    for i in range(4):
        ox = 190 + i * 50
        o_pos2.append((ox, 180, ox + 40, 220))

    events2 = feed_pair_track(buffer, detector, source, 1, 3, "backpack", p_pos2, o_pos2, start_t=2.0)

    total_events = events1 + events2
    assert len(total_events) == 2, f"Expected exactly 2 independent throw events, got {len(total_events)}"
    assert total_events[0].object_track_id == 2
    assert total_events[1].object_track_id == 3
    print("[PASS] Test 10: Two independent throws produce exactly 2 distinct confirmations.")


def test_11_object_speed_below_threshold():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = ThrowingDetector(minimum_object_speed=2.0)
    source = "cam_01"
    pid, oid = 1, 2

    person_pos = [(100, 100, 160, 300) for _ in range(10)]
    object_pos = [(140, 180, 180, 220) for _ in range(4)]
    # Object moves at 25px per 0.1s = 250px/s = 1.25 heights/s (< 2.0 threshold)
    for i in range(6):
        ox = 165 + i * 25
        object_pos.append((ox, 180, ox + 40, 220))

    events = feed_pair_track(buffer, detector, source, pid, oid, "sports ball", person_pos, object_pos)
    assert len(events) == 0, f"Expected 0 events for speed below threshold, got {len(events)}"
    print("[PASS] Test 11: Object speed below threshold produces 0 throwing events.")


def test_12_insufficient_speed_ratio():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = ThrowingDetector(object_to_person_speed_ratio=2.0)
    source = "cam_01"
    pid, oid = 1, 2

    # Person running at 30px per frame (1.5 heights/s)
    person_pos = [(100 + i * 30, 100, 160 + i * 30, 300) for i in range(10)]
    # Object moving slightly faster at 38px per frame (1.9 heights/s, ratio = 1.26 < 2.0)
    object_pos = [(140, 180, 180, 220) for _ in range(4)]
    for i in range(6):
        ox = 140 + 4 * 30 + i * 38
        object_pos.append((ox, 180, ox + 40, 220))

    events = feed_pair_track(buffer, detector, source, pid, oid, "backpack", person_pos, object_pos)
    assert len(events) == 0, "Insufficient speed disparity must reject candidate"
    print("[PASS] Test 12: Object speed not sufficiently greater than person speed produces 0 events.")


def test_13_separation_not_increasing():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = ThrowingDetector(minimum_separation_growth=0.3)
    source = "cam_01"
    pid, oid = 1, 2

    # Person at center (130, 200). Object moves fast in small circle/box, so distance never exceeds 40px
    person_pos = [(100, 100, 160, 300) for _ in range(10)]
    object_pos = [
        (140, 180, 180, 220),
        (140, 180, 180, 220),
        (140, 180, 180, 220),
        (140, 180, 180, 220),
        (150, 170, 190, 210),
        (150, 200, 190, 240),
        (130, 210, 170, 250),
        (120, 180, 160, 220),
    ]

    events = feed_pair_track(buffer, detector, source, pid, oid, "sports ball", person_pos, object_pos)
    assert len(events) == 0
    print("[PASS] Test 13: Separation not increasing produces 0 throwing events.")


def test_14_non_monotonic_separation():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = ThrowingDetector()
    source = "cam_01"
    pid, oid = 1, 2

    person_pos = [(100, 100, 160, 300) for _ in range(10)]
    # Object moves away, then reverses and comes back towards person!
    object_pos = [
        (140, 180, 180, 220),
        (140, 180, 180, 220),
        (140, 180, 180, 220),
        (140, 180, 180, 220),
        (200, 180, 240, 220), # moves out
        (260, 180, 300, 220), # moves further
        (180, 180, 220, 220), # reverses back! Non-monotonic distance drop
        (150, 180, 190, 220),
    ]

    events = feed_pair_track(buffer, detector, source, pid, oid, "sports ball", person_pos, object_pos)
    assert len(events) == 0, f"Non-monotonic separation must reset candidate, got {len(events)}"
    print("[PASS] Test 14: Non-monotonic separation cleanly resets candidate with 0 events.")


def test_15_poor_trajectory_consistency():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = ThrowingDetector(minimum_trajectory_consistency=0.70)
    source = "cam_01"
    pid, oid = 1, 2

    person_pos = [(100, 100, 160, 300) for _ in range(10)]
    # Object moves rapidly in zigzag / bouncing directions
    object_pos = [
        (140, 180, 180, 220),
        (140, 180, 180, 220),
        (140, 180, 180, 220),
        (140, 180, 180, 220),
        (200, 180, 240, 220), # moves right (dx=+60, dy=0)
        (150, 120, 190, 160), # moves up-left (dx=-50, dy=-60) -> cosine sim < 0!
        (220, 180, 260, 220), # moves down-right
    ]

    events = feed_pair_track(buffer, detector, source, pid, oid, "sports ball", person_pos, object_pos)
    assert len(events) == 0, "Inconsistent trajectory vectors must be rejected"
    print("[PASS] Test 15: Poor trajectory consistency rejected with 0 throwing events.")


def test_16_pure_downward_drop():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = ThrowingDetector(drop_vertical_dominance_threshold=2.0)
    source = "cam_01"
    pid, oid = 1, 2

    # Person standing: height 200px (100 to 300).
    person_pos = [(100, 100, 160, 300) for _ in range(10)]
    # Object drops straight down: dx = 0, dy = +50px per frame (falls to ground)
    object_pos = [
        (140, 150, 180, 190),
        (140, 150, 180, 190),
        (140, 150, 180, 190),
        (140, 150, 180, 190),
        (140, 200, 180, 240), # dy = +50, dx = 0
        (140, 250, 180, 290), # dy = +50, dx = 0
        (140, 300, 180, 340), # dy = +50, dx = 0
    ]

    events = feed_pair_track(buffer, detector, source, pid, oid, "backpack", person_pos, object_pos)
    assert len(events) == 0, f"Pure downward drop must be rejected, got {len(events)}"
    print("[PASS] Test 16: Pure downward drop correctly rejected by drop guard.")


def test_17_object_moving_before_association_flyby():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = ThrowingDetector(minimum_object_speed=2.0)
    source = "cam_01"
    pid, oid = 1, 2

    # Person stands at (300, 100, 360, 300)
    person_pos = [(300, 100, 360, 300) for _ in range(10)]
    # Object is already flying fast across screen from left to right (dx = +50px/frame = 2.5 heights/s)
    # Starts far away at x=50, crosses near person at x=320, flies away to x=500
    object_pos = [(50 + i * 50, 180, 90 + i * 50, 220) for i in range(10)]

    events = feed_pair_track(buffer, detector, source, pid, oid, "sports ball", person_pos, object_pos)
    assert len(events) == 0, f"Fly-by object already moving before association must not trigger, got {len(events)}"
    print("[PASS] Test 17: Object moving fast before association (fly-by) produces 0 throwing events.")


def test_18_vehicle_movement():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = ThrowingDetector()
    source = "cam_01"
    pid, oid = 1, 2

    person_pos = [(100, 100, 160, 300) for _ in range(10)]
    # A car departs and speeds away
    car_pos = [(140, 180, 200, 240) for _ in range(4)]
    for i in range(6):
        ox = 190 + i * 50
        car_pos.append((ox, 180, ox + 60, 240))

    events = feed_pair_track(buffer, detector, source, pid, oid, "car", person_pos, car_pos)
    assert len(events) == 0, "Vehicles must never be evaluated as throwable objects"
    print("[PASS] Test 18: Vehicle movement produces 0 throwing events.")


def test_19_non_allowed_object_class():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = ThrowingDetector()
    source = "cam_01"
    pid, oid = 1, 2

    person_pos = [(100, 100, 160, 300) for _ in range(10)]
    chair_pos = [(140, 180, 180, 220) for _ in range(4)]
    for i in range(6):
        ox = 190 + i * 50
        chair_pos.append((ox, 180, ox + 40, 220))

    events = feed_pair_track(buffer, detector, source, pid, oid, "chair", person_pos, chair_pos)
    assert len(events) == 0, "Non-allowed class (chair) must produce 0 events"
    print("[PASS] Test 19: Non-allowed object class (chair) produces 0 throwing events.")


def test_20_track_id_none():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = ThrowingDetector()
    source = "cam_01"

    p_det = MockDet(None, "person", 100, 100, 160, 300)
    o_det = MockDet(2, "backpack", 140, 180, 180, 220)

    p_obs = buffer.update(source, p_det, timestamp_sec=0.0)
    o_obs = buffer.update(source, o_det, timestamp_sec=0.0)

    events = detector.process_frame(source, [p_obs, o_obs], buffer)
    res_pair = detector.process_pair(source, p_obs, o_obs, buffer)

    assert p_obs is None
    assert len(events) == 0
    assert res_pair is None
    print("[PASS] Test 20: track_id=None safely ignored without error or state corruption.")


def test_21_source_isolation():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = ThrowingDetector(confirmation_observations=3)
    pid, oid = 1, 2

    # On cam_east: Valid throw occurs
    p_east = [(100, 100, 160, 300) for _ in range(8)]
    o_east = [(140, 180, 180, 220) for _ in range(4)]
    for i in range(4):
        ox = 190 + i * 50
        o_east.append((ox, 180, ox + 40, 220))
    events_east = feed_pair_track(buffer, detector, "cam_east", pid, oid, "backpack", p_east, o_east)

    # On cam_west: Stationary
    p_west = [(100, 100, 160, 300) for _ in range(8)]
    o_west = [(140, 180, 180, 220) for _ in range(8)]
    events_west = feed_pair_track(buffer, detector, "cam_west", pid, oid, "backpack", p_west, o_west)

    assert len(events_east) == 1, "cam_east must confirm throwing"
    assert len(events_west) == 0, "cam_west must NOT confirm throwing"
    assert detector.get_candidate_state("cam_east", pid, oid) == "THROW_CONFIRMED"
    assert detector.get_candidate_state("cam_west", pid, oid) == "PERSON_OBJECT_ASSOCIATED"
    print("[PASS] Test 21: Different sources with identical track IDs remain strictly isolated.")


def test_22_multi_person_multi_object_scene():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = ThrowingDetector(confirmation_observations=3)
    source = "cam_01"

    # Person 1 (x=100) throws Backpack 10
    # Person 2 (x=600) carries Backpack 20 (stationary/walking)
    events = []
    t = 0.0
    for idx in range(8):
        p1 = MockDet(1, "person", 100, 100, 160, 300)
        p2 = MockDet(2, "person", 600, 100, 660, 300)

        # Backpack 10 throws fast after frame 3
        if idx < 4:
            b10 = MockDet(10, "backpack", 140, 180, 180, 220)
        else:
            bx = 190 + (idx - 4) * 50
            b10 = MockDet(10, "backpack", bx, 180, bx + 40, 220)

        # Backpack 20 stays close to Person 2
        b20 = MockDet(20, "backpack", 640, 180, 680, 220)

        obs_p1 = buffer.update(source, p1, timestamp_sec=t, frame_index=idx)
        obs_p2 = buffer.update(source, p2, timestamp_sec=t, frame_index=idx)
        obs_b10 = buffer.update(source, b10, timestamp_sec=t, frame_index=idx)
        obs_b20 = buffer.update(source, b20, timestamp_sec=t, frame_index=idx)

        frame_events = detector.process_frame(source, [obs_p1, obs_p2, obs_b10, obs_b20], buffer)
        events.extend(frame_events)
        t += 0.1

    assert len(events) == 1, f"Expected exactly 1 event, got {len(events)}"
    assert events[0].person_track_id == 1
    assert events[0].object_track_id == 10
    assert detector.get_candidate_state(source, 1, 10) == "THROW_CONFIRMED"
    assert detector.get_candidate_state(source, 2, 20) == "PERSON_OBJECT_ASSOCIATED"
    print("[PASS] Test 22: Multi-person/multi-object scene isolates correct throw association.")


def test_23_candidate_timeout_and_reset():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = ThrowingDetector(max_candidate_duration_sec=1.0)
    source = "cam_01"
    pid, oid = 1, 2

    # Associated, then starts moving at t=0.4 (RELEASE_SUSPECTED), but times out after 1.5s
    person_pos = [(100, 100, 160, 300) for _ in range(7)]
    object_pos = [
        (140, 180, 180, 220), # t=0.0
        (140, 180, 180, 220), # t=0.1
        (140, 180, 180, 220), # t=0.2
        (140, 180, 180, 220), # t=0.3 (associated)
        (200, 180, 240, 220), # t=0.4 (RELEASE_SUSPECTED)
        (400, 180, 440, 220), # t=0.5 (moves far away: dist > 1.2h)
        (400, 180, 440, 220), # t=1.6 (> 1.0s elapsed from release)
    ]

    events = []
    t = 0.0
    for idx, (px, ox) in enumerate(zip(person_pos, object_pos)):
        p_det = MockDet(pid, "person", *px)
        o_det = MockDet(oid, "backpack", *ox)
        obs_p = buffer.update(source, p_det, timestamp_sec=t, frame_index=idx)
        obs_o = buffer.update(source, o_det, timestamp_sec=t, frame_index=idx)
        events.extend(detector.process_frame(source, [obs_p, obs_o], buffer))
        t = 1.6 if idx == 5 else t + 0.1

    assert len(events) == 0
    assert detector.get_candidate_state(source, pid, oid) == "NO_CANDIDATE"
    print("[PASS] Test 23: Candidate timeout resets state to NO_CANDIDATE.")


def test_24_bounding_box_jump_rejection():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = ThrowingDetector(max_box_change_ratio=2.2)
    source = "cam_01"
    pid, oid = 1, 2

    person_pos = [(100, 100, 160, 300) for _ in range(8)]
    # Object suddenly experiences 3x size jump (glitch)
    object_pos = [
        (140, 180, 180, 220), # w=40, h=40
        (140, 180, 180, 220),
        (140, 180, 180, 220),
        (140, 180, 180, 220),
        (190, 180, 230, 220),
        (240, 180, 380, 340), # w=140, h=160 (3.5x jump!)
    ]

    events = feed_pair_track(buffer, detector, source, pid, oid, "backpack", person_pos, object_pos)
    assert len(events) == 0, "Extreme bounding box size jump must be rejected"
    print("[PASS] Test 24: Bounding-box jump anomaly correctly rejected by consistency guard.")


def test_25_non_positive_dt():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = ThrowingDetector()
    source = "cam_01"

    p_det = MockDet(1, "person", 100, 100, 160, 300)
    o_det = MockDet(2, "backpack", 140, 180, 180, 220)

    obs_p = buffer.update(source, p_det, timestamp_sec=1.0)
    obs_o = buffer.update(source, o_det, timestamp_sec=1.0)
    events1 = detector.process_frame(source, [obs_p, obs_o], buffer)

    # Exact same timestamp (dt = 0)
    events2 = detector.process_frame(source, [obs_p, obs_o], buffer)
    assert len(events1) == 0
    assert len(events2) == 0
    print("[PASS] Test 25: Non-positive dt handled safely without error.")


def test_26_state_cleanup():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = ThrowingDetector()
    source = "cam_01"

    # Associate two pairs
    p_det1 = MockDet(1, "person", 100, 100, 160, 300)
    o_det1 = MockDet(2, "backpack", 140, 180, 180, 220)
    p_det2 = MockDet(3, "person", 500, 100, 560, 300)
    o_det2 = MockDet(4, "bottle", 540, 180, 580, 220)

    o1 = buffer.update(source, p_det1, timestamp_sec=1.0)
    o2 = buffer.update(source, o_det1, timestamp_sec=1.0)
    o3 = buffer.update(source, p_det2, timestamp_sec=1.0)
    o4 = buffer.update(source, o_det2, timestamp_sec=1.0)

    detector.process_frame(source, [o1, o2, o3, o4], buffer)
    assert detector.get_candidate_state(source, 1, 2) == "PERSON_OBJECT_ASSOCIATED"
    assert detector.get_candidate_state(source, 3, 4) == "PERSON_OBJECT_ASSOCIATED"

    # Clear single pair
    detector.clear_pair(source, 1, 2)
    assert detector.get_candidate_state(source, 1, 2) == "NO_CANDIDATE"
    assert detector.get_candidate_state(source, 3, 4) == "PERSON_OBJECT_ASSOCIATED"

    # Clear source
    detector.clear_source(source)
    assert detector.get_candidate_state(source, 3, 4) == "NO_CANDIDATE"
    print("[PASS] Test 26: State cleanup (clear_pair, clear_source) operates correctly.")


def test_27_no_event_flooding_long_stream():
    buffer = TrackHistoryBuffer(max_history=20)
    detector = ThrowingDetector(confirmation_observations=3)
    source = "cam_01"
    pid, oid = 1, 2

    person_pos = [(100, 100, 160, 300) for _ in range(100)]
    object_pos = [(140, 180, 180, 220) for _ in range(4)]
    # Object moves fast for 96 frames
    for i in range(96):
        ox = 190 + i * 30
        object_pos.append((ox, 180, ox + 40, 220))

    events = feed_pair_track(buffer, detector, source, pid, oid, "backpack", person_pos, object_pos)
    assert len(events) == 1, f"Expected exactly 1 event over 100 frames, got {len(events)}"
    print("[PASS] Test 27: Continuous 100-frame stream confirms once with zero event flooding.")


def test_28_throwing_local_track_stitching():
    """
    Verifies that when ByteTrack fragments a fast-flying object into different track IDs
    (Track 10 -> Track 11 -> Track 12 -> Track 13) due to subsampled frames,
    ThrowingDetector conservatively stitches them into a coherent logical trajectory and confirms THROWING.
    """
    buffer = TrackHistoryBuffer(max_history=20)
    detector = ThrowingDetector(confirmation_observations=2)
    source = "cam_01"

    events = []
    # Person stands at (100, 100, 160, 300) (height=200, center=(130, 200))
    p_det = MockDet(1, "person", 100, 100, 160, 300)

    # Frame 0: Sports ball held by person (Track 10)
    b_det0 = MockDet(10, "sports ball", 140, 180, 180, 220)
    o_p0 = buffer.update(source, p_det, timestamp_sec=0.0, frame_index=0)
    o_b0 = buffer.update(source, b_det0, timestamp_sec=0.0, frame_index=0)
    evs0 = detector.process_frame(source, [o_p0, o_b0], buffer)
    events.extend(evs0)

    # Frame 5: Sports ball launched fast (Track 11 - fragmented ByteTrack ID)
    b_det1 = MockDet(11, "sports ball", 220, 160, 260, 200) # center=(240, 180), dx=+80px, v=80/(0.2*200)=2.0 h/s
    o_p1 = buffer.update(source, p_det, timestamp_sec=0.2, frame_index=5)
    o_b1 = buffer.update(source, b_det1, timestamp_sec=0.2, frame_index=5)
    evs1 = detector.process_frame(source, [o_p1, o_b1], buffer)
    events.extend(evs1)

    # Frame 10: Sports ball flying (Track 12 - fragmented ByteTrack ID)
    b_det2 = MockDet(12, "sports ball", 300, 140, 340, 180) # center=(320, 160), dx=+80px
    o_p2 = buffer.update(source, p_det, timestamp_sec=0.4, frame_index=10)
    o_b2 = buffer.update(source, b_det2, timestamp_sec=0.4, frame_index=10)
    evs2 = detector.process_frame(source, [o_p2, o_b2], buffer)
    events.extend(evs2)

    # Frame 15: Sports ball descending (Track 13 - fragmented ByteTrack ID)
    b_det3 = MockDet(13, "sports ball", 380, 160, 420, 200)
    o_p3 = buffer.update(source, p_det, timestamp_sec=0.6, frame_index=15)
    o_b3 = buffer.update(source, b_det3, timestamp_sec=0.6, frame_index=15)
    evs3 = detector.process_frame(source, [o_p3, o_b3], buffer)
    events.extend(evs3)

    assert len(events) == 1, f"Expected exactly 1 confirmed throwing event with stitched trajectory, got {len(events)}"
    ev = events[0]
    assert ev.activity == "THROWING"
    assert ev.person_track_id == 1
    assert ev.object_class == "sports ball"
    assert ev.trajectory_consistency >= 0.70
    print("[PASS] Test 28: Fragmented ByteTrack IDs stitched into coherent THROWING event.")


def test_29_stitching_rejects_incompatible_classes_or_direction():
    """
    Verifies that stitcher strictly refuses to merge different classes or wildly erratic positions.
    """
    buffer = TrackHistoryBuffer(max_history=20)
    detector = ThrowingDetector(confirmation_observations=2)
    source = "cam_01"

    p_det = MockDet(1, "person", 100, 100, 160, 300)
    # Frame 0: bottle held (Track 10)
    b_det = MockDet(10, "bottle", 140, 180, 180, 220)
    o_p0 = buffer.update(source, p_det, timestamp_sec=0.0, frame_index=0)
    o_b0 = buffer.update(source, b_det, timestamp_sec=0.0, frame_index=0)
    detector.process_frame(source, [o_p0, o_b0], buffer)

    # Frame 5: completely different class (backpack) appears 600px away (Track 11)
    diff_det = MockDet(11, "backpack", 700, 180, 740, 220)
    o_p1 = buffer.update(source, p_det, timestamp_sec=0.2, frame_index=5)
    o_d1 = buffer.update(source, diff_det, timestamp_sec=0.2, frame_index=5)
    evs = detector.process_frame(source, [o_p1, o_d1], buffer)

    assert len(evs) == 0, "Must NOT stitch different object class or distant object"
    print("[PASS] Test 29: Incompatible classes and erratic jumps rejected by stitcher.")


def run_all_tests():
    print("==================================================")
    print("RUNNING THROWING DETECTOR COMPREHENSIVE TEST SUITE")
    print("==================================================")
    test_1_no_objects()
    test_2_person_alone()
    test_3_person_walking_alone()
    test_4_person_carrying_object()
    test_5_object_stationary_near_person()
    test_6_object_moving_slowly_near_person()
    test_7_association_established()
    test_8_sustained_valid_throw()
    test_9_continued_motion_no_duplicate()
    test_10_two_independent_throws()
    test_11_object_speed_below_threshold()
    test_12_insufficient_speed_ratio()
    test_13_separation_not_increasing()
    test_14_non_monotonic_separation()
    test_15_poor_trajectory_consistency()
    test_16_pure_downward_drop()
    test_17_object_moving_before_association_flyby()
    test_18_vehicle_movement()
    test_19_non_allowed_object_class()
    test_20_track_id_none()
    test_21_source_isolation()
    test_22_multi_person_multi_object_scene()
    test_23_candidate_timeout_and_reset()
    test_24_bounding_box_jump_rejection()
    test_25_non_positive_dt()
    test_26_state_cleanup()
    test_27_no_event_flooding_long_stream()
    print("==================================================")
    print("ALL 27 THROWING DETECTOR TESTS PASSED SUCCESSFULLY!")
    print("==================================================")


if __name__ == "__main__":
    run_all_tests()
