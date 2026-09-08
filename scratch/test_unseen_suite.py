import os
import sys
import math
import logging

logging.basicConfig(level=logging.WARNING)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
sys.path.insert(0, BACKEND_DIR)
sys.path.insert(0, BASE_DIR)

from ai_engine.modules.detection.yolo_detector import YOLODetector
from ai_engine.modules.behavior.suspicious.track_history import TrackHistoryBuffer
from scratch.test_candidate_detectors import CandidateCrawlingDetector, CandidateRunningDetector

downloads_dir = os.path.expanduser("~/Downloads")
unseen_videos = [
    "12021304_1080_1920_60fps.mp4",
    "14968619_2160_3840_30fps.mp4",
    "15722036-uhd_3840_2160_24fps.mp4",
    "15914649_1080_1920_30fps.mp4",
    "5222540-uhd_3840_2160_30fps.mp4",
    "9481660-uhd_3840_2160_24fps.mp4",
    "car_road_scene.mp4",
]

detector = YOLODetector.get_instance()

for vname in unseen_videos:
    vpath = os.path.join(downloads_dir, vname)
    if not os.path.exists(vpath):
        continue

    print("\n" + "=" * 80)
    print(f"TESTING UNSEEN VIDEO: {vname}")
    print("=" * 80)

    history_buffer = TrackHistoryBuffer(max_history=120)
    crawling_det = CandidateCrawlingDetector()
    running_det = CandidateRunningDetector()
    confirmed_events = []

    def on_frame(frame_data):
        sid = vname
        for det in frame_data.detections:
            if det.track_id is not None and det.class_name == "person":
                obs = history_buffer.update(sid, det, frame_data.timestamp_sec, frame_data.frame_index)
                if obs:
                    r_res = running_det.process_observation(sid, obs, history_buffer)
                    if r_res:
                        confirmed_events.append(r_res)
                        print(f"  >>> CONFIRMED RUNNING: Track #{r_res['track_id']} at {r_res['timestamp_sec']:.2f}s (Speed={r_res['normalized_speed']:.2f} h/s)")
                    c_res = crawling_det.process_observation(sid, obs, history_buffer)
                    if c_res:
                        confirmed_events.append(c_res)
                        print(f"  >>> CONFIRMED CRAWLING: Track #{c_res['track_id']} at {c_res['timestamp_sec']:.2f}s (AR={c_res['aspect_ratio']:.2f}, Speed={c_res['horizontal_speed']:.2f} h/s)")

    detector.process_video(vpath, max_frames=200, sample_rate=1, on_frame_processed=on_frame)
    res_summary = [(e['activity'], e['track_id'], round(e['timestamp_sec'], 2)) for e in confirmed_events]
    print(f"RESULT for {vname}: {len(confirmed_events)} events -> {res_summary}")
