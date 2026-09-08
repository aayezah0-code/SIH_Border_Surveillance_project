import os
import sys
sys.path.insert(0, os.path.abspath("."))

from ai_engine.modules.behavior.suspicious.suspicious_engine import SuspiciousActivityEngine
from ai_engine.modules.detection.yolo_detector import YOLODetector

detector = YOLODetector.get_instance()
engine = SuspiciousActivityEngine()

# Test the 4 verified videos with current detector
test_videos = [
    ("data/uploads/running.mp4", "RUNNING"),
    ("data/uploads/running_test.mp4", "RUNNING"),
    ("data/uploads/running test2.mp4", "RUNNING"),
    ("data/uploads/crawling.mp4", "CRAWLING"),
]

for vpath, expected in test_videos:
    if os.path.exists(vpath):
        res = detector.process_video(vpath, sample_rate=5, confidence=0.40)
        engine.clear_source("test")
        events = []
        for fr in res:
            evs = engine.process_frame("test", fr)
            for e in evs:
                events.append(e.activity)
        print(f"{vpath}: Expected {expected} | Got {events}")
    else:
        print(f"File not found: {vpath}")

