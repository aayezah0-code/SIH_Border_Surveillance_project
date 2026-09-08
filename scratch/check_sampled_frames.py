import os
import sys
sys.path.insert(0, os.path.abspath("."))

import cv2
import torch
from ai_engine.modules.detection.yolo_detector import YOLODetector

video_path = r"C:\Users\HP\Downloads\7939015-uhd_2160_3840_24fps.mp4"
detector = YOLODetector.get_instance()

cap = cv2.VideoCapture(video_path)
raw_frame_idx = 0
processed = 0
sample_rate = 5

while processed < 60:
    ret = cap.grab()
    if not ret:
        break
    if raw_frame_idx % sample_rate != 0:
        raw_frame_idx += 1
        continue
    ret, raw_frame = cap.retrieve()
    if not ret:
        raw_frame_idx += 1
        continue

    frame_idx = raw_frame_idx
    raw_frame_idx += 1
    processed += 1

    h, w = raw_frame.shape[:2]
    scale = 832 / max(h, w)
    nw, nh = int(w * scale), int(h * scale)
    proc_frame = cv2.resize(raw_frame, (nw, nh), interpolation=cv2.INTER_LINEAR)

    # Let's run track with conf=0.40 on det_frame
    from ai_engine.modules.enhancement.low_light_enhancer import low_light_enhancer
    det_frame, was_enhanced, _, eff_conf = low_light_enhancer.enhance_if_needed(
        proc_frame, base_conf=0.40, low_light_conf=0.30
    )

    results = detector._model.track(
        source=det_frame,
        persist=True,
        tracker="bytetrack.yaml",
        conf=eff_conf,
        imgsz=832,
        verbose=False,
    )

    dets = detector._parse_results(results)
    non_person = [d for d in dets if d.class_name != "person"]
    print(f"Sampled Frame {frame_idx:3d} (processed #{processed}): was_enhanced={was_enhanced}, eff_conf={eff_conf}, non_person={[(d.class_name, d.confidence, d.track_id) for d in non_person]}")

cap.release()
