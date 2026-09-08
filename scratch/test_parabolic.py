import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from ai_engine.modules.behavior.suspicious.track_history import TrackHistoryBuffer, TrackObservation
from ai_engine.modules.behavior.suspicious.throwing_detector import ThrowingDetector

def test_parabolic_throw():
    print("=== TESTING PARABOLIC / HIGH-ARC THROW OVER FENCE ===")
    buffer = TrackHistoryBuffer()
    detector = ThrowingDetector()
    source = "cam_01"

    # Person stands at (100, 100, 160, 300) (height 200px, center=(130, 200))
    # Object thrown UP and to the right over a fence, then arcs DOWN:
    # Frame 0: (140, 180, 180, 220) (t=0.0)
    # Frame 1: (140, 180, 180, 220) (t=0.1)
    # Frame 2: (190, 140, 230, 180) (t=0.2, dx=+50, dy=-40, flying up-right! initial release vector = (0.78, -0.62))
    # Frame 3: (240, 120, 280, 160) (t=0.3, dx=+50, dy=-20, apex)
    # Frame 4: (290, 150, 330, 190) (t=0.4, dx=+50, dy=+30, falling down-right! unit_v = (0.86, +0.51))
    # Cosine sim with release_vector = 0.78*0.86 + (-0.62)*(0.51) = 0.67 - 0.32 = 0.35! < 0.65 threshold!

    class MockDet:
        def __init__(self, track_id, class_name, x1, y1, x2, y2, confidence=0.90):
            self.track_id = track_id
            self.class_name = class_name
            self.x1 = x1; self.y1 = y1; self.x2 = x2; self.y2 = y2
            self.confidence = confidence

    frames_obj = [
        (140, 180, 180, 220),
        (140, 180, 180, 220),
        (190, 140, 230, 180),
        (240, 120, 280, 160),
        (290, 150, 330, 190),
        (340, 200, 380, 240),
    ]

    events = []
    for idx, o_box in enumerate(frames_obj):
        p_det = MockDet(1, "person", 100, 100, 160, 300)
        o_det = MockDet(2, "backpack", *o_box)
        p_obs = buffer.update(source, p_det, timestamp_sec=idx*0.1, frame_index=idx)
        o_obs = buffer.update(source, o_det, timestamp_sec=idx*0.1, frame_index=idx)
        res = detector.process_frame(source, [p_obs, o_obs], buffer)
        events.extend(res)
        state = detector.get_candidate_state(source, 1, 2)
        print(f"Frame {idx}: Candidate State -> {state}, Events emitted -> {len(res)}")

    print(f"Total Confirmed Events: {len(events)}")

test_parabolic_throw()
