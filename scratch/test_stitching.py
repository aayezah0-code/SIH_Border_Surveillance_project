import os
import sys
sys.path.insert(0, os.path.abspath("."))

import cv2
import math
from collections import deque
from typing import Dict, List, Optional, Set, Tuple
from ai_engine.modules.detection.yolo_detector import YOLODetector
from ai_engine.modules.behavior.suspicious.track_history import TrackHistoryBuffer, TrackObservation
from ai_engine.modules.behavior.suspicious.throwing_detector import (
    ThrowingDetector,
    _ThrowCandidateState,
    ThrowingDetection,
    DEFAULT_ALLOWED_OBJECT_CLASSES,
    FORBIDDEN_CLASSES
)

video_path = r"C:\Users\HP\Downloads\7939015-uhd_2160_3840_24fps.mp4"

detector = YOLODetector.get_instance()
print("Running process_video with sample_rate=5 (standard upload)...")
frame_results = detector.process_video(video_path, max_frames=300, sample_rate=5, confidence=0.40)
print(f"Processed {len(frame_results)} frames.")

# Let's see the detections per frame
for fr in frame_results:
    balls = [d for d in fr.detections if d.class_name == "sports ball"]
    if balls:
        print(f"Frame {fr.frame_index:3d} (t={fr.timestamp_sec:.2f}s): {[ (d.class_name, d.track_id, d.confidence, d.bbox) for d in balls ]}")

