import os
import sys
import glob
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from ai_engine.modules.detection.yolo_detector import YOLODetector

unique_videos = [
    ("Thowing.mp4", "backend/uploads/849705c0-d52f-439d-90ec-ddebb44ed905.mp4"),
    ("throwing.mp4", "backend/uploads/16ad194b-5764-4157-ace1-3e2e225df2fe.mp4"),
    ("crawling.mp4", "backend/uploads/1878f2eb-ca3f-4083-ba22-1b0008918f02.mp4"),
    ("running_test2.mp4", "backend/uploads/2bb13eb0-a0d0-4fc6-a60c-ef4117893b7f.mp4"),
    ("running_test.mp4", "backend/uploads/3c328e96-4b11-4bb3-b78c-c588eac26b9a.mp4"),
    ("running.mp4", "backend/uploads/f631aed7-39cb-498d-abfa-b3e3aaa3e595.mp4"),
    ("033aefba.mp4", "backend/uploads/033aefba-c2e7-4a0d-9ccd-0ef649f9ee0f.mp4"),
    ("car_road_scene.mp4", "backend/uploads/03a886bc-d8eb-4b7d-8838-8ec35b5c7a8b.mp4"),
    ("WIN_20260830.mp4", "backend/uploads/040134c4-6d7d-4a32-a78f-647e0484c7d4.mp4"),
    ("0947fa59.mp4", "backend/uploads/0947fa59-4230-4d78-b0cf-7caaccfd20a0.mp4"),
    ("0daa7954.mp4", "backend/uploads/0daa7954-f137-4da4-9c00-1438538005b8.mp4"),
    ("15722036.mp4", "backend/uploads/16b114eb-9846-4780-b4dd-18a83d51425c.mp4"),
    ("10132252.mp4", "backend/uploads/22c6657a-9a56-4c80-884e-494376beb4b7.mp4"),
    ("9481660.mp4", "backend/uploads/23093425-c422-4fd2-a68e-439c8db33a68.mp4"),
    ("14968619.mp4", "backend/uploads/2633ca1e-d7ee-4df6-be82-6d5d4ce53803.mp4"),
    ("5310933.mp4", "backend/uploads/4bee2e49-e24f-4ce4-88bd-25616ac06c0f.mp4"),
    ("test_anpr.mp4", "backend/uploads/7d4c19a2-2a98-4192-869b-e41efb673c28.mp4"),
]

det = YOLODetector.get_instance()

print(f"Scanning {len(unique_videos)} videos for any throwable/handheld object detections...")
for name, vpath in unique_videos:
    if not os.path.exists(vpath):
        continue
    det._reset_tracker()
    class_counts = {}
    total_f = [0]
    
    def on_f(fd):
        total_f[0] += 1
        for d in fd.detections:
            cls = d.class_name
            class_counts[cls] = class_counts.get(cls, 0) + 1

    try:
        det.process_video(
            video_path=vpath,
            max_frames=50, # Sample 50 frames
            sample_rate=5,
            confidence=0.25,
            on_frame_processed=on_f,
        )
        print(f"[{name}] Frames: {total_f[0]}, Classes: {class_counts}")
    except Exception as e:
        print(f"[{name}] Error: {e}")
