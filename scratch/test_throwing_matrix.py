import math
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from ai_engine.modules.behavior.suspicious.track_history import TrackHistoryBuffer
from ai_engine.modules.behavior.suspicious.throwing_detector import ThrowingDetector
from ai_engine.modules.behavior.suspicious.suspicious_engine import SuspiciousActivityEngine

class MockDet:
    def __init__(self, track_id, class_name, x1, y1, x2, y2, confidence=0.90):
        self.track_id = track_id
        self.class_name = class_name
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.confidence = confidence

def run_positive_test(name, obj_class, fps, resolution, direction, num_frames=12):
    buffer = TrackHistoryBuffer()
    detector = ThrowingDetector()
    engine = SuspiciousActivityEngine(history_buffer=buffer, throwing_detector=detector)
    source = f"cam_{name.replace(' ', '_')}"

    w, h = resolution
    dt = 1.0 / fps
    p_h = 200 # person height 200px
    p_w = 60
    p_x1, p_y1 = w // 4, h // 2
    p_x2, p_y2 = p_x1 + p_w, p_y1 + p_h

    # Direction vectors
    dir_map = {
        "right": (50, 0),
        "left": (-50, 0),
        "up_right_arc": (45, -35),
        "high_parabolic": (40, -40),
    }
    dx, dy = dir_map.get(direction, (50, 0))

    events = []
    t = 0.0
    
    # Initial 3 frames co-located (held)
    o_w, o_h = 40, 40
    curr_ox = p_x1 + 30
    curr_oy = p_y1 + 80

    for f_idx in range(num_frames):
        if f_idx >= 3:
            # Airborne flight
            curr_ox += dx
            if direction == "high_parabolic":
                # Gravity curve
                curr_oy += (dy + (f_idx - 3) * 15)
            elif direction == "up_right_arc":
                curr_oy += (dy + (f_idx - 3) * 8)
            else:
                curr_oy += dy

        p_det = MockDet(1, "person", p_x1, p_y1, p_x2, p_y2)
        o_det = MockDet(2, obj_class, curr_ox, curr_oy, curr_ox + o_w, curr_oy + o_h)

        from ai_engine.modules.detection.yolo_detector import FrameDetections
        fd = FrameDetections(
            frame_index=f_idx,
            timestamp_sec=t,
            detections=[p_det, o_det],
            frame_width=w,
            frame_height=h,
        )
        res = engine.process_frame(source, fd, timestamp_sec=t, frame_index=f_idx)
        events.extend(res)
        t += dt

    passed = (len(events) == 1 and events[0].activity == "THROWING")
    return passed, len(events), events[0] if events else None

def run_negative_test(name, scenario_fn):
    buffer = TrackHistoryBuffer()
    detector = ThrowingDetector()
    engine = SuspiciousActivityEngine(history_buffer=buffer, throwing_detector=detector)
    source = f"cam_neg_{name.replace(' ', '_')}"

    events = scenario_fn(buffer, detector, engine, source)
    throwing_events = [e for e in events if e.activity == "THROWING"]
    passed = (len(throwing_events) == 0)
    return passed, len(throwing_events)

def test_suite():
    print("=" * 80)
    print("RUNNING GENERALIZED THROWING POSITIVE AND NEGATIVE TEST MATRIX")
    print("=" * 80)

    # POSITIVE TESTS
    pos_cases = [
        ("Sports Ball Throw (30 FPS, 1080p, Right)", "sports ball", 30.0, (1920, 1080), "right"),
        ("Bottle Toss (24 FPS, 720p, High Parabolic)", "bottle", 24.0, (1280, 720), "high_parabolic"),
        ("Backpack Throw (20 FPS, 480p, Up-Right Arc)", "backpack", 20.0, (640, 480), "up_right_arc"),
        ("Frisbee Hurling (60 FPS, 1080p, Left)", "frisbee", 60.0, (1920, 1080), "left"),
        ("Suitcase Chuck (25 FPS, 720p, Right)", "suitcase", 25.0, (1280, 720), "right"),
        ("Handbag Throw (30 FPS, 1080p, High Parabolic)", "handbag", 30.0, (1920, 1080), "high_parabolic"),
        ("Package Toss (24 FPS, 720p, Up-Right Arc)", "package", 24.0, (1280, 720), "up_right_arc"),
    ]

    print("\n--- POSITIVE THROWING SCENARIOS ---")
    pos_pass_count = 0
    for name, obj_cls, fps, res, direction in pos_cases:
        passed, count, ev = run_positive_test(name, obj_cls, fps, res, direction)
        status = "PASS" if passed else "FAIL"
        if passed:
            pos_pass_count += 1
            print(f"[{status}] {name} -> Confirmed 1 event (speed={ev.metadata['object_speed_normalized']}h/s, sep={ev.metadata['separation']}h)")
        else:
            print(f"[{status}] {name} -> Expected 1 event, got {count}")

    # NEGATIVE TESTS
    def neg_holding(b, d, eng, src):
        # Person standing, holding object for 20 frames
        evs = []
        for i in range(20):
            p = MockDet(1, "person", 100, 100, 160, 300)
            o = MockDet(2, "backpack", 130, 180, 170, 220)
            from ai_engine.modules.detection.yolo_detector import FrameDetections
            evs.extend(eng.process_frame(src, FrameDetections(i, i*0.1, [p, o], 640, 480), i*0.1, i))
        return evs

    def neg_walking(b, d, eng, src):
        # Person walking while carrying object
        evs = []
        for i in range(20):
            x = 100 + i * 8
            p = MockDet(1, "person", x, 100, x + 60, 300)
            o = MockDet(2, "bottle", x + 30, 180, x + 70, 220)
            from ai_engine.modules.detection.yolo_detector import FrameDetections
            evs.extend(eng.process_frame(src, FrameDetections(i, i*0.1, [p, o], 640, 480), i*0.1, i))
        return evs

    def neg_running(b, d, eng, src):
        # Person running while carrying object (both moving at same high speed)
        evs = []
        for i in range(20):
            x = 100 + i * 25
            p = MockDet(1, "person", x, 100, x + 60, 300)
            o = MockDet(2, "backpack", x + 30, 180, x + 70, 220)
            from ai_engine.modules.detection.yolo_detector import FrameDetections
            evs.extend(eng.process_frame(src, FrameDetections(i, i*0.1, [p, o], 640, 480), i*0.1, i))
        return evs

    def neg_placing_down(b, d, eng, src):
        # Object placed on ground (slow downward movement, settles)
        evs = []
        for i in range(20):
            p = MockDet(1, "person", 100, 100, 160, 300)
            y = 180 + min(i * 4, 100) # moves slowly down 4px/frame (<0.2 heights/s)
            o = MockDet(2, "backpack", 130, y, 170, y + 40)
            from ai_engine.modules.detection.yolo_detector import FrameDetections
            evs.extend(eng.process_frame(src, FrameDetections(i, i*0.1, [p, o], 640, 480), i*0.1, i))
        return evs

    def neg_falling(b, d, eng, src):
        # Object pure vertical gravity drop (dx=0, dy=+60)
        evs = []
        for i in range(10):
            p = MockDet(1, "person", 100, 100, 160, 300)
            y = 150 + (i * 50 if i >= 3 else 0)
            o = MockDet(2, "backpack", 130, y, 170, y + 40)
            from ai_engine.modules.detection.yolo_detector import FrameDetections
            evs.extend(eng.process_frame(src, FrameDetections(i, i*0.1, [p, o], 640, 480), i*0.1, i))
        return evs

    def neg_stationary(b, d, eng, src):
        # Stationary object near person
        evs = []
        for i in range(20):
            p = MockDet(1, "person", 100, 100, 160, 300)
            o = MockDet(2, "bottle", 200, 260, 230, 300)
            from ai_engine.modules.detection.yolo_detector import FrameDetections
            evs.extend(eng.process_frame(src, FrameDetections(i, i*0.1, [p, o], 640, 480), i*0.1, i))
        return evs

    def neg_arm_waving(b, d, eng, src):
        # Person waving arms (no object detection at all)
        evs = []
        for i in range(20):
            p = MockDet(1, "person", 100, 100, 160, 300)
            from ai_engine.modules.detection.yolo_detector import FrameDetections
            evs.extend(eng.process_frame(src, FrameDetections(i, i*0.1, [p], 640, 480), i*0.1, i))
        return evs

    neg_cases = [
        ("Person Holding Object", neg_holding),
        ("Person Walking with Object", neg_walking),
        ("Person Running while Carrying Object", neg_running),
        ("Object Being Placed Down", neg_placing_down),
        ("Object Pure Falling/Dropping", neg_falling),
        ("Stationary Object Near Person", neg_stationary),
        ("Person Waving Arms Without Object", neg_arm_waving),
    ]

    print("\n--- NEGATIVE SCENARIOS (MUST EMIT 0 THROWS) ---")
    neg_pass_count = 0
    for name, fn in neg_cases:
        passed, count = run_negative_test(name, fn)
        status = "PASS" if passed else "FAIL"
        if passed:
            neg_pass_count += 1
            print(f"[{status}] {name} -> 0 false throwing events.")
        else:
            print(f"[{status}] {name} -> FALSE POSITIVE: got {count} throwing events!")

    print("\n" + "=" * 80)
    print(f"POSITIVE TESTS: {pos_pass_count} / {len(pos_cases)} PASSED")
    print(f"NEGATIVE TESTS: {neg_pass_count} / {len(neg_cases)} PASSED")
    print("=" * 80)

if __name__ == "__main__":
    test_suite()
