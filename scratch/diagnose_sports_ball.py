import os
import sys
sys.path.insert(0, os.path.abspath("."))

import cv2
import torch
import numpy as np
from ultralytics import YOLO
from ai_engine.modules.detection.yolo_detector import YOLODetector, PRIORITY_CLASSES

video_path = r"C:\Users\HP\Downloads\7939015-uhd_2160_3840_24fps.mp4"

print("=" * 70)
print("SPORTS BALL THROWING PIPELINE DIAGNOSIS — EXACT TELEMETRY")
print("=" * 70)

# 1. Video Properties
cap = cv2.VideoCapture(video_path)
orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
cap.release()

print(f"1. Original frame resolution: {orig_w}x{orig_h} (Portrait: W={orig_w}, H={orig_h})")
print(f"   FPS: {fps:.3f}, Total frames: {total_frames}")

# 2. Pipeline Defaults Check
detector = YOLODetector.get_instance()
print(f"2. Configured YOLO Model: {detector.model_name}")
print(f"3. Configured Default Confidence: {detector.confidence}")
print(f"4. Configured Default IoU: {detector.iou}")

# 3. Model Classes Check
model = detector._model
names = model.names
class_32_name = names.get(32, "UNKNOWN")
print(f"5. Class ID 32 Name in YOLO model: '{class_32_name}'")
print(f"   Is class 32 enabled in YOLO COCO list? {'YES' if 32 in names else 'NO'}")
print(f"   Is class 32 in PRIORITY_CLASSES? {class_32_name in PRIORITY_CLASSES}")

# Check imgsz calculation in pipeline
if max(orig_h, orig_w) >= 1920:
    pipeline_inference_imgsz = 832
    scale = pipeline_inference_imgsz / max(orig_h, orig_w)
    new_w, new_h = int(orig_w * scale), int(orig_h * scale)
else:
    pipeline_inference_imgsz = 640
    new_w, new_h = orig_w, orig_h

print(f"6. Pipeline Inference resolution/imgsz: {pipeline_inference_imgsz} (Resized to {new_w}x{new_h})")

# 4. Detailed Frame-by-Frame Trace at Pipeline Execution
device_str = "cuda:0" if torch.cuda.is_available() else "cpu"

print("\n" + "=" * 70)
print("CONFIDENCE SWEEPS & TRACE ON EVERY 5TH SAMPLED FRAME (Pipeline Default)")
print("=" * 70)

cap = cv2.VideoCapture(video_path)
raw_frame_idx = 0
processed = 0
sample_rate = 5
max_frames = 300

highest_conf_32 = 0.0
highest_conf_32_frame = -1
traces = []
sweep_counts = {0.40: 0, 0.30: 0, 0.20: 0.10, 0.10: 0}
sweep_counts = {0.40: 0, 0.30: 0, 0.20: 0, 0.10: 0}
raw_dets_all_classes = 0

all_detected_classes = set()

while processed < max_frames:
    ret = cap.grab()
    if not ret:
        break
    if raw_frame_idx % sample_rate != 0:
        raw_frame_idx += 1
        continue
    ret, raw_frame = cap.retrieve()
    if not ret or raw_frame is None:
        raw_frame_idx += 1
        continue

    frame_idx = raw_frame_idx
    raw_frame_idx += 1
    processed += 1

    h, w = raw_frame.shape[:2]
    scale = 832 / max(h, w)
    nw, nh = int(w * scale), int(h * scale)
    proc_frame = cv2.resize(raw_frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
    scale_back_x = w / nw
    scale_back_y = h / nh

    # Low threshold predict to inspect all raw boxes
    raw_res = model.predict(source=proc_frame, conf=0.01, imgsz=832, verbose=False, device=device_str)
    
    # Live pipeline track at conf=0.40
    track_res = model.track(source=proc_frame, persist=True, tracker="bytetrack.yaml", conf=0.40, imgsz=832, verbose=False, device=device_str)

    if raw_res[0].boxes is not None:
        for box in raw_res[0].boxes:
            c_id = int(box.cls[0].item())
            c_conf = float(box.conf[0].item())
            c_name = names.get(c_id, str(c_id))
            all_detected_classes.add(c_name)
            
            for th in [0.40, 0.30, 0.20, 0.10]:
                if c_id == 32 and c_conf >= th:
                    sweep_counts[th] += 1

            if c_id == 32:
                if c_conf > highest_conf_32:
                    highest_conf_32 = c_conf
                    highest_conf_32_frame = frame_idx
                
                xyxy = box.xyxy[0].tolist()
                bx1 = int(round(xyxy[0] * scale_back_x))
                by1 = int(round(xyxy[1] * scale_back_y))
                bx2 = int(round(xyxy[2] * scale_back_x))
                by2 = int(round(xyxy[3] * scale_back_y))
                bw = bx2 - bx1
                bh = by2 - by1
                barea = bw * bh
                passed_conf = c_conf >= 0.40
                
                tid = None
                if track_res[0].boxes is not None:
                    for tbox in track_res[0].boxes:
                        if int(tbox.cls[0].item()) == 32:
                            if tbox.id is not None:
                                try:
                                    tid = int(tbox.id[0].item())
                                except:
                                    tid = int(tbox.id.item())

                trace_entry = {
                    "frame": frame_idx,
                    "raw_confidence": round(c_conf, 4),
                    "bbox": (bx1, by1, bx2, by2),
                    "bbox_width": bw,
                    "bbox_height": bh,
                    "bbox_area": barea,
                    "passed_confidence": passed_conf,
                    "passed_filter": passed_conf,
                    "track_id": tid
                }
                traces.append(trace_entry)

cap.release()

print("All classes detected in raw video:", all_detected_classes)
print(f"Confidence sweep for class 32 (sports ball) across sampled frames:")
for th, count in sweep_counts.items():
    print(f"  Conf >= {th:.2f}: {count} detections")

print(f"\nHighest raw YOLO confidence for class 32 (sports ball): {highest_conf_32:.4f} (at Frame {highest_conf_32_frame})")
print(f"Total raw class 32 detections (conf >= 0.01): {len(traces)}")

print("\n" + "=" * 70)
print("[SPORTS_BALL_TRACE] LOGS")
print("=" * 70)
if len(traces) == 0:
    print("[SPORTS_BALL_TRACE] ZERO class 32 (sports ball) detections found across all frames even at conf >= 0.01!")
else:
    for t in traces:
        print(f"[SPORTS_BALL_TRACE] frame={t['frame']} raw_confidence={t['raw_confidence']:.4f} bbox={t['bbox']} bbox_width={t['bbox_width']} bbox_height={t['bbox_height']} bbox_area={t['bbox_area']} passed_confidence={t['passed_confidence']} passed_filter={t['passed_filter']} track_id={t['track_id']}")

# 5. Let's also test consecutive frames (sample_rate=1) and different image sizes (e.g. native/letterbox vs raw resize)
print("\n" + "=" * 70)
print("TESTING FULL CONSECUTIVE FRAMES (sample_rate=1, conf=0.01)")
print("=" * 70)

cap2 = cv2.VideoCapture(video_path)
full_traces = []
f_idx = 0
highest_full_conf = 0.0
highest_full_frame = -1
full_sweep = {0.40: 0, 0.30: 0, 0.20: 0, 0.10: 0, 0.05: 0, 0.01: 0}

while f_idx < 240:
    ret, raw_frame = cap2.read()
    if not ret or raw_frame is None:
        break
    
    h, w = raw_frame.shape[:2]
    scale = 832 / max(h, w)
    nw, nh = int(w * scale), int(h * scale)
    proc_frame = cv2.resize(raw_frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
    scale_back_x = w / nw
    scale_back_y = h / nh

    res = model.predict(source=proc_frame, conf=0.01, imgsz=832, verbose=False, device=device_str)
    if res[0].boxes is not None:
        for box in res[0].boxes:
            c_id = int(box.cls[0].item())
            c_conf = float(box.conf[0].item())
            if c_id == 32:
                for th in full_sweep.keys():
                    if c_conf >= th:
                        full_sweep[th] += 1
                if c_conf > highest_full_conf:
                    highest_full_conf = c_conf
                    highest_full_frame = f_idx
                
                xyxy = box.xyxy[0].tolist()
                bx1 = int(round(xyxy[0] * scale_back_x))
                by1 = int(round(xyxy[1] * scale_back_y))
                bx2 = int(round(xyxy[2] * scale_back_x))
                by2 = int(round(xyxy[3] * scale_back_y))
                bw = bx2 - bx1
                bh = by2 - by1
                barea = bw * bh
                
                full_traces.append({
                    "frame": f_idx,
                    "raw_confidence": round(c_conf, 4),
                    "bbox": (bx1, by1, bx2, by2),
                    "bbox_width": bw,
                    "bbox_height": bh,
                    "bbox_area": barea,
                    "passed_confidence": c_conf >= 0.40,
                    "passed_filter": c_conf >= 0.40,
                    "track_id": None
                })
    f_idx += 1
cap2.release()

print(f"Full Consecutive Frames (240 frames) results for class 32:")
for th, count in full_sweep.items():
    print(f"  Conf >= {th:.2f}: {count} detections")
print(f"Highest confidence across all 240 frames: {highest_full_conf:.4f} at Frame {highest_full_frame}")

if len(full_traces) > 0:
    print(f"\nTop 10 Detections across all 240 consecutive frames:")
    for t in sorted(full_traces, key=lambda x: x['raw_confidence'], reverse=True)[:10]:
        print(f"[SPORTS_BALL_TRACE] frame={t['frame']} raw_confidence={t['raw_confidence']:.4f} bbox={t['bbox']} bbox_width={t['bbox_width']} bbox_height={t['bbox_height']} bbox_area={t['bbox_area']} passed_confidence={t['passed_confidence']} passed_filter={t['passed_filter']} track_id={t['track_id']}")

