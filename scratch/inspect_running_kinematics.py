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

def inspect_running_video(video_path, sid):
    detector = YOLODetector.get_instance()
    history_buffer = TrackHistoryBuffer(max_history=120)
    print("\n" + "=" * 80)
    print("INSPECTING:", os.path.basename(video_path))
    print("=" * 80)

    def on_frame(frame_data):
        for det in frame_data.detections:
            if det.track_id is not None and det.class_name == "person":
                obs = history_buffer.update(sid, det, frame_data.timestamp_sec, frame_data.frame_index)
                if obs:
                    hist = history_buffer.get_history(sid, det.track_id)
                    if len(hist) >= 2:
                        prev = hist[-2]
                        dt = obs.timestamp_sec - prev.timestamp_sec
                        if dt > 0:
                            dx = obs.bottom_center[0] - prev.bottom_center[0]
                            dy = obs.bottom_center[1] - prev.bottom_center[1]
                            dist_px = math.sqrt(dx*dx + dy*dy)
                            h = obs.height
                            v_inst = (dist_px / dt) / h if h > 0 else 0
                            if v_inst > 0.4:
                                print(f"F#{frame_data.frame_index:03d} T={frame_data.timestamp_sec:.2f}s | Trk#{det.track_id} | v_inst={v_inst:.2f} h/s | dt={dt:.3f}s | dist={dist_px:.1f}px | bbox=[{det.x1},{det.y1},{det.x2},{det.y2}] h={h}")

    detector.process_video(video_path, max_frames=300, sample_rate=1, on_frame_processed=on_frame)

if __name__ == "__main__":
    for v in ["C:/Users/HP/Downloads/running.mp4", "C:/Users/HP/Downloads/running_test.mp4", "C:/Users/HP/Downloads/running test2.mp4"]:
        if os.path.exists(v):
            inspect_running_video(v, os.path.basename(v))
