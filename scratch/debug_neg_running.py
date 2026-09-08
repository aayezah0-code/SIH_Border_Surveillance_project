import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from ai_engine.modules.behavior.suspicious.track_history import TrackHistoryBuffer
from ai_engine.modules.behavior.suspicious.throwing_detector import ThrowingDetector

class MockDet:
    def __init__(self, track_id, class_name, x1, y1, x2, y2, confidence=0.90):
        self.track_id = track_id
        self.class_name = class_name
        self.x1 = x1; self.y1 = y1; self.x2 = x2; self.y2 = y2
        self.confidence = confidence

b = TrackHistoryBuffer()
d = ThrowingDetector()
src = "test"

for i in range(10):
    x = 100 + i * 25
    p = MockDet(1, "person", x, 100, x + 60, 300)
    o = MockDet(2, "backpack", x + 30, 180, x + 70, 220)
    p_obs = b.update(src, p, timestamp_sec=i*0.1, frame_index=i)
    o_obs = b.update(src, o, timestamp_sec=i*0.1, frame_index=i)
    evs = d.process_frame(src, [p_obs, o_obs], b)
    c_state = d.get_candidate_state(src, 1, 2)
    print(f"Frame {i}: c_state={c_state}, events={len(evs)}")
