import os
import cv2
import json

uploads_dir = "backend/uploads"
files = [f for f in os.listdir(uploads_dir) if f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm'))]
print(f"Total video files in {uploads_dir}: {len(files)}")

video_info = []
for f in files:
    path = os.path.join(uploads_dir, f)
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        print(f"Cannot open {f}")
        continue
    fps = cap.get(cv2.CAP_PROP_FPS)
    count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = count / fps if fps > 0 else 0
    cap.release()
    video_info.append({
        "file": f,
        "size_kb": round(os.path.getsize(path) / 1024, 1),
        "fps": round(fps, 1),
        "frames": count,
        "res": f"{width}x{height}",
        "duration_s": round(duration, 2)
    })

print(f"Found {len(video_info)} readable videos.")
for vi in video_info:
    print(vi)
