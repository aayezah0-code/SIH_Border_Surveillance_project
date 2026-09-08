import os
import sys
sys.path.insert(0, os.path.abspath("."))

import cv2
import torch
import numpy as np
from ultralytics import YOLO
from ai_engine.modules.detection.yolo_detector import YOLODetector, PRIORITY_CLASSES

video_path = r"C:\Users\HP\Downloads\7939015-uhd_2160_3840_24fps.mp4"

detector = YOLODetector.get_instance()
model = detector._model
names = model.names
device_str = "cuda:0" if torch.cuda.is_available() else "cpu"

cap = cv2.VideoCapture(video_path)
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

print(f"Total frames in video: {total_frames}")

# Trace every single frame for all objects
frame_detections = {}
for f in range(total_frames):
    ret, frame = cap.read()
    if not ret or frame is None:
        break
    h, w = frame.shape[:2]
    scale = 832 / max(h, w)
    nw, nh = int(w * scale), int(h * scale)
    proc_frame = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
    scale_back_x = w / nw
    scale_back_y = h / nh

    res = model.predict(source=proc_frame, conf=0.10, imgsz=832, verbose=False, device=device_str)
    
    dets = []
    if res[0].boxes is not None:
        for box in res[0].boxes:
            c_id = int(box.cls[0].item())
            c_conf = float(box.conf[0].item())
            c_name = names.get(c_id, str(c_id))
            xyxy = box.xyxy[0].tolist()
            bx1 = int(round(xyxy[0] * scale_back_x))
            by1 = int(round(xyxy[1] * scale_back_y))
            bx2 = int(round(xyxy[2] * scale_back_x))
            by2 = int(round(xyxy[3] * scale_back_y))
            dets.append({
                "class_id": c_id,
                "class_name": c_name,
                "conf": c_conf,
                "bbox": (bx1, by1, bx2, by2),
                "w": bx2 - bx1,
                "h": by2 - by1
            })
    frame_detections[f] = dets
cap.release()

print("\n--- NON-PERSON DETECTIONS ACROSS ALL FRAMES (conf >= 0.10) ---")
for f, dets in frame_detections.items():
    non_person = [d for d in dets if d["class_name"] != "person"]
    if non_person:
        print(f"Frame {f:3d} (t={f/24.0:.2f}s): {[(d['class_name'], round(d['conf'], 3), d['bbox']) for d in non_person]}")

# Now let's test what ByteTrack does when running process_video on this video
print("\n--- LIVE PIPELINE EXECUTION (process_video with sample_rate=5 and sample_rate=1) ---")
for sr in [5, 1]:
    res = detector.process_video(video_path, max_frames=300, sample_rate=sr, confidence=0.40)
    print(f"\nsample_rate={sr}: Processed {len(res)} frames")
    for fr in res:
        non_person = [d for d in fr.detections if d.class_name != "person"]
        if non_person:
            print(f"  Frame {fr.frame_index} (t={fr.timestamp_sec:.2f}s): {[(d.class_name, d.confidence, d.track_id, d.bbox) for d in non_person]}")

