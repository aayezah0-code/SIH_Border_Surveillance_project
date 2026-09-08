import os
import cv2

downloads_dir = os.path.expanduser("~/Downloads")
files = [
    "12021304_1080_1920_60fps.mp4",
    "14968619_2160_3840_30fps.mp4",
    "15722036-uhd_3840_2160_24fps.mp4",
    "15914649_1080_1920_30fps.mp4",
    "5222540-uhd_3840_2160_30fps.mp4",
    "9481660-uhd_3840_2160_24fps.mp4",
    "car_road_scene.mp4",
    "demo.mp4",
]

for fname in files:
    fpath = os.path.join(downloads_dir, fname)
    if os.path.exists(fpath):
        cap = cv2.VideoCapture(fpath)
        fps = cap.get(cv2.CAP_PROP_FPS)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fc = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        dur = fc / fps if fps > 0 else 0
        cap.release()
        print(f"{fname:35s} | {w:4d}x{h:4d} | {fps:5.1f} fps | {fc:4d} frames | {dur:5.2f}s")
