import os
import sys
sys.path.insert(0, os.path.abspath("."))

import cv2
import math
from collections import deque
from typing import Dict, List, Optional, Set, Tuple

from ai_engine.modules.detection.yolo_detector import YOLODetector, DetectionResult
from ai_engine.modules.behavior.suspicious.track_history import TrackHistoryBuffer, TrackObservation
from ai_engine.modules.behavior.suspicious.throwing_detector import (
    ThrowingDetector,
    _ThrowCandidateState,
    ThrowingDetection,
    DEFAULT_ALLOWED_OBJECT_CLASSES,
    FORBIDDEN_CLASSES
)
from ai_engine.modules.behavior.suspicious.suspicious_engine import SuspiciousActivityEngine

# Let's test the complete pipeline on the failing video 7939015
video_path = r"C:\Users\HP\Downloads\7939015-uhd_2160_3840_24fps.mp4"

detector = YOLODetector.get_instance()
model = detector._model

# Run process_video logic with predict + fallback tracker to ensure all detections are retained
cap = cv2.VideoCapture(video_path)
fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
sample_rate = 5
f = 0
processed = 0

tracker = detector._fallback_tracker
tracker.reset()

engine = SuspiciousActivityEngine()
source_id = "test_7939015"
engine.clear_source(source_id)

collected_events = []
frame_detections_list = []

while True:
    ret, frame = cap.read()
    if not ret:
        break
    if f % sample_rate == 0:
        h, w = frame.shape[:2]
        scale = 832 / max(h, w)
        nw, nh = int(w * scale), int(h * scale)
        proc_frame = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
        scale_back_x = w / nw
        scale_back_y = h / nh
        
        # Predict at conf=0.40
        res = model.predict(source=proc_frame, conf=0.40, imgsz=832, verbose=False)
        raw_dets = detector._parse_results(res)
        
        # Rescale bboxes back to orig frame
        for d in raw_dets:
            d.x1 = int(round(d.x1 * scale_back_x))
            d.y1 = int(round(d.y1 * scale_back_y))
            d.x2 = int(round(d.x2 * scale_back_x))
            d.y2 = int(round(d.y2 * scale_back_y))
        
        tracked_dets = tracker.update(raw_dets)
        
        from ai_engine.modules.detection.yolo_detector import FrameDetections
        fr = FrameDetections(
            frame_index=f,
            timestamp_sec=f / fps,
            detections=tracked_dets,
            frame_width=w,
            frame_height=h
        )
        frame_detections_list.append(fr)
    f += 1
cap.release()

print(f"Total sampled frames: {len(frame_detections_list)}")

# Now let's run through ThrowingDetector with stitching
# Let's inspect the detections of sports ball across frames
for fr in frame_detections_list:
    sb = [d for d in fr.detections if d.class_name == "sports ball"]
    if sb:
        print(f"Frame {fr.frame_index:3d} (t={fr.timestamp_sec:.2f}s): {[ (d.class_name, d.track_id, d.confidence, d.bbox) for d in sb ]}")

