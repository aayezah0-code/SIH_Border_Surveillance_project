import os
import sys
sys.path.insert(0, os.path.abspath("."))

from ai_engine.modules.behavior.suspicious.suspicious_engine import SuspiciousActivityEngine
from ai_engine.modules.detection.yolo_detector import YOLODetector

detector = YOLODetector.get_instance()
engine = SuspiciousActivityEngine()

# Test the 5 videos
test_videos = [
    (r"C:\Users\HP\Downloads\7939015-uhd_2160_3840_24fps.mp4", "THROWING"),
    (r"C:\Users\HP\Downloads\running.mp4", "RUNNING"),
    (r"C:\Users\HP\Downloads\running_test.mp4", "RUNNING"),
    (r"C:\Users\HP\Downloads\running test2.mp4", "RUNNING"),
    (r"C:\Users\HP\Downloads\crawling.mp4", "CRAWLING"),
]

for vpath, expected in test_videos:
    if os.path.exists(vpath):
        # Process using process_video
        res = detector.process_video(vpath, sample_rate=5, confidence=0.40)
        engine.clear_source("test_src")
        events = []
        for fr in res:
            evs = engine.process_frame("test_src", fr)
            for e in evs:
                events.append(e.activity)
        print(f"[{os.path.basename(vpath)}] Expected: {expected} | Emitted: {events} | Success: {expected in events}")
    else:
        print(f"File not found: {vpath}")
