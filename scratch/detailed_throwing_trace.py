import sys
import os
from pathlib import Path
import math

sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

import cv2
import numpy as np
from ai_engine.modules.detection.yolo_detector import YOLODetector
from ai_engine.modules.behavior.suspicious.track_history import TrackHistoryBuffer
from ai_engine.modules.behavior.suspicious.throwing_detector import (
    ThrowingDetector,
    DEFAULT_ALLOWED_OBJECT_CLASSES,
    FORBIDDEN_CLASSES
)
from ai_engine.modules.behavior.suspicious.suspicious_engine import SuspiciousActivityEngine

def trace_throwing_deep(video_path: str, video_title: str):
    print(f"\n{'#'*80}", flush=True)
    print(f"# DEEP TRACE: {video_title}", flush=True)
    print(f"# File: {video_path}", flush=True)
    print(f"{'#'*80}\n", flush=True)

    if not os.path.exists(video_path):
        print(f"File not found: {video_path}", flush=True)
        return

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Video Info: {width}x{height}, {fps:.1f} FPS, {total_frames} frames, {total_frames/fps:.2f}s", flush=True)
    cap.release()

    detector = YOLODetector()
    detector._load_model()

    # We test both sample_rate=1 (every frame) and sample_rate=5 (backend default)
    for sample_rate in [1, 5]:
        print(f"\n=======================================================", flush=True)
        print(f"=== TESTING SAMPLE_RATE = {sample_rate} ===", flush=True)
        print(f"=======================================================", flush=True)

        history = TrackHistoryBuffer(max_history=50)
        throwing_detector = ThrowingDetector()
        engine = SuspiciousActivityEngine(
            history_buffer=history,
            throwing_detector=throwing_detector,
        )

        detector._reset_tracker()
        cap = cv2.VideoCapture(video_path)

        frame_idx = 0
        processed_idx = 0
        detected_person_frames = 0
        detected_object_frames = 0
        person_track_ids = set()
        object_track_ids = set()
        object_classes_seen = set()

        confirmed_throws = []

        while True:
            ret = cap.grab()
            if not ret:
                break
            if frame_idx % sample_rate != 0:
                frame_idx += 1
                continue
            ret, frame = cap.retrieve()
            if not ret or frame is None:
                frame_idx += 1
                continue

            current_f_idx = frame_idx
            ts = current_f_idx / fps
            frame_idx += 1
            processed_idx += 1

            # Run detection using yolo_detector's exact logic
            orig_h, orig_w = frame.shape[:2]
            if max(orig_h, orig_w) >= 1920:
                inference_imgsz = 832
                scale = inference_imgsz / max(orig_h, orig_w)
                new_w, new_h = int(orig_w * scale), int(orig_h * scale)
                proc_frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
                scale_back_x = orig_w / new_w
                scale_back_y = orig_h / new_h
            else:
                inference_imgsz = 640
                proc_frame = frame
                scale_back_x = 1.0
                scale_back_y = 1.0

            results = detector._model.track(
                source=proc_frame,
                persist=True,
                tracker="bytetrack.yaml",
                conf=0.25, # Check broad confidence to see what YOLO outputs
                iou=0.45,
                imgsz=inference_imgsz,
                verbose=False,
            )
            dets = detector._parse_results(results)
            dets = detector._fallback_tracker.update(dets)
            if scale_back_x != 1.0 or scale_back_y != 1.0:
                for d in dets:
                    d.x1 = int(round(d.x1 * scale_back_x))
                    d.y1 = int(round(d.y1 * scale_back_y))
                    d.x2 = int(round(d.x2 * scale_back_x))
                    d.y2 = int(round(d.y2 * scale_back_y))

            persons = [d for d in dets if d.class_name == "person"]
            objects = [d for d in dets if d.class_name != "person"]

            if persons:
                detected_person_frames += 1
                for p in persons:
                    person_track_ids.add(p.track_id)
            if objects:
                detected_object_frames += 1
                for o in objects:
                    object_track_ids.add(o.track_id)
                    object_classes_seen.add(o.class_name)

            # Check manual pairing & telemetry before engine call
            from ai_engine.modules.detection.yolo_detector import FrameDetections
            fd = FrameDetections(
                frame_index=current_f_idx,
                timestamp_sec=ts,
                detections=dets,
                frame_width=orig_w,
                frame_height=orig_h,
            )

            # Detailed per-frame log when any object is present
            if objects:
                print(f"[Frame {current_f_idx:04d} | t={ts:.2f}s] Persons: {[p.track_id for p in persons]}, Objects: {[(o.track_id, o.class_name, round(o.confidence,2), (o.x1, o.y1, o.x2, o.y2)) for o in objects]}", flush=True)
                for p in persons:
                    for o in objects:
                        # Log distance, candidate state, speeds
                        p_h = p.y2 - p.y1
                        if p_h > 0:
                            p_cx, p_cy = (p.x1 + p.x2)/2.0, (p.y1 + p.y2)/2.0
                            o_cx, o_cy = (o.x1 + o.x2)/2.0, (o.y1 + o.y2)/2.0
                            dist_px = math.sqrt((o_cx - p_cx)**2 + (o_cy - p_cy)**2)
                            dist_h = dist_px / p_h
                            cand_state = throwing_detector.get_candidate_state("source_1", p.track_id, o.track_id)
                            print(f"   -> Pair (P#{p.track_id}, O#{o.track_id} {o.class_name}): dist={dist_h:.2f} body heights, current_cand_state={cand_state}", flush=True)

            evs = engine.process_frame("source_1", fd, timestamp_sec=ts, frame_index=current_f_idx)
            if evs:
                for ev in evs:
                    if ev.activity == "THROWING":
                        confirmed_throws.append((current_f_idx, ts, ev))
                        print(f"   🚨 [CONFIRMED THROW EVENT] Frame {current_f_idx} (t={ts:.2f}s): Person #{ev.track_id} -> Object #{ev.object_track_id} ({ev.metadata.get('object_class')}), speed={ev.metadata.get('object_speed_normalized')} h/s, sep={ev.metadata.get('separation')}, consistency={ev.metadata.get('trajectory_consistency')}", flush=True)

        cap.release()

        print(f"\n--- SUMMARY for {video_title} (sample_rate={sample_rate}) ---", flush=True)
        print(f"Total processed frames: {processed_idx}", flush=True)
        print(f"Frames with Person: {detected_person_frames} / {processed_idx}", flush=True)
        print(f"Person Track IDs: {person_track_ids}", flush=True)
        print(f"Frames with Object: {detected_object_frames} / {processed_idx}", flush=True)
        print(f"Object Classes Seen: {object_classes_seen}", flush=True)
        print(f"Object Track IDs: {object_track_ids}", flush=True)
        print(f"Total Confirmed THROWING Events: {len(confirmed_throws)}", flush=True)
        for cf in confirmed_throws:
            print(f"   * Frame {cf[0]} @ {cf[1]:.2f}s: Person #{cf[2].track_id}, Object #{cf[2].object_track_id}, metadata={cf[2].metadata}", flush=True)

if __name__ == "__main__":
    v1 = "backend/uploads/16ad194b-5764-4157-ace1-3e2e225df2fe.mp4" # throwing.mp4
    v2 = "backend/uploads/849705c0-d52f-439d-90ec-ddebb44ed905.mp4" # Thowing.mp4
    trace_throwing_deep(v2, "Thowing.mp4 (849705c0, 2.8MB, 10s)")
    trace_throwing_deep(v1, "throwing.mp4 (16ad194b, 24MB, 10s)")
