import sys
import os
from pathlib import Path
import json

# Setup paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

import cv2
import numpy as np
from ai_engine.modules.detection.yolo_detector import YOLODetector
from ai_engine.modules.behavior.suspicious.track_history import TrackHistoryBuffer
from ai_engine.modules.behavior.suspicious.throwing_detector import ThrowingDetector
from ai_engine.modules.behavior.suspicious.suspicious_engine import SuspiciousActivityEngine

def trace_video(video_path: str, label: str):
    print("=" * 80)
    print(f"TRACING THROWING PIPELINE FOR: {label} ({video_path})")
    print("=" * 80)

    if not os.path.exists(video_path):
        print(f"ERROR: Video file {video_path} does not exist.")
        return

    detector = YOLODetector()
    detector._load_model()
    
    # Process video with sample_rate=1 (every frame) and default sample_rate=5 to see differences
    for s_rate in [1, 5]:
        print(f"\n--- TESTING WITH SAMPLE_RATE = {s_rate} ---")
        history = TrackHistoryBuffer(max_history=50)
        throwing_detector = ThrowingDetector()
        engine = SuspiciousActivityEngine(
            history_buffer=history,
            throwing_detector=throwing_detector,
        )

        detector._reset_tracker()
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"Video props: {w}x{h}, {total_frames} frames, {fps:.1f} fps, duration={total_frames/fps:.2f}s")

        frame_idx = 0
        processed_count = 0
        
        person_detections = []
        object_detections = []
        candidates_seen = []
        confirmed_events = []

        while True:
            ret = cap.grab()
            if not ret:
                break
            if frame_idx % s_rate != 0:
                frame_idx += 1
                continue
            ret, frame = cap.retrieve()
            if not ret or frame is None:
                frame_idx += 1
                continue

            ts = frame_idx / fps
            raw_idx = frame_idx
            frame_idx += 1
            processed_count += 1

            # Run detection + tracking
            # Follow yolo_detector's resolution handling
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
                conf=0.25, # Check at low conf to see all YOLO detections
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

            # Log frame detections
            frame_persons = [d for d in dets if d.class_name == "person"]
            frame_objects = [d for d in dets if d.class_name != "person"]

            if frame_persons:
                person_detections.append((raw_idx, ts, [(p.track_id, p.confidence, p.x1, p.y1, p.x2, p.y2) for p in frame_persons]))
            if frame_objects:
                object_detections.append((raw_idx, ts, [(o.track_id, o.class_name, o.confidence, (o.x2-o.x1)*(o.y2-o.y1), o.x1, o.y1, o.x2, o.y2) for o in frame_objects]))

            # Feed engine
            from ai_engine.modules.detection.yolo_detector import FrameDetections
            fd = FrameDetections(
                frame_index=raw_idx,
                timestamp_sec=ts,
                detections=dets,
                frame_width=w,
                frame_height=h,
            )
            evs = engine.process_frame("test_source", fd, timestamp_sec=ts, frame_index=raw_idx)
            if evs:
                for ev in evs:
                    confirmed_events.append((raw_idx, ts, ev))

            # Inspect internal candidate state
            with throwing_detector._lock:
                cands = throwing_detector._candidates.get("test_source", {})
                for pair, cand in cands.items():
                    candidates_seen.append((raw_idx, ts, pair, cand.state, cand.qualifying_count, cand.release_dist_norm, cand.prev_dist_norm))

        cap.release()

        print(f"\n--- RESULTS SUMMARY (sample_rate={s_rate}) ---")
        print(f"Processed frames: {processed_count}")
        print(f"Frames with PERSON detections: {len(person_detections)}")
        print(f"Unique person tracks: {set(p[0] for _, _, plist in person_detections for p in plist)}")
        print(f"Frames with NON-PERSON detections: {len(object_detections)}")
        
        all_objs = {}
        for f_idx, ts, olist in object_detections:
            for o in olist:
                tid, cname, conf, area, x1, y1, x2, y2 = o
                if tid not in all_objs:
                    all_objs[tid] = {"class": cname, "frames": [], "confs": [], "areas": [], "bboxes": []}
                all_objs[tid]["frames"].append(f_idx)
                all_objs[tid]["confs"].append(conf)
                all_objs[tid]["areas"].append(area)
                all_objs[tid]["bboxes"].append((x1, y1, x2, y2))

        print(f"\nDetected Objects Breakdown ({len(all_objs)} tracks):")
        for tid, data in all_objs.items():
            print(f"  Track ID {tid}: Class='{data['class']}', Frames={len(data['frames'])} (first={data['frames'][0]}, last={data['frames'][-1]}), AvgConf={np.mean(data['confs']):.3f}, MaxConf={np.max(data['confs']):.3f}, AvgArea={np.mean(data['areas']):.1f}px")

        print(f"\nCandidates recorded in detector: {len(candidates_seen)}")
        unique_cand_states = set((c[2], c[3]) for c in candidates_seen)
        for pair, state in unique_cand_states:
            print(f"  Pair {pair}: State reached -> {state}")

        print(f"\nConfirmed Throwing Events: {len(confirmed_events)}")
        for f_idx, ts, ev in confirmed_events:
            print(f"  [EVENT] Frame {f_idx} (t={ts:.2f}s): Person #{ev.track_id} -> Object #{ev.object_track_id} ({ev.metadata.get('object_class')}), meta={ev.metadata}")


if __name__ == "__main__":
    v1 = "backend/uploads/16ad194b-5764-4157-ace1-3e2e225df2fe.mp4" # throwing.mp4
    v2 = "backend/uploads/849705c0-d52f-439d-90ec-ddebb44ed905.mp4" # Thowing.mp4
    trace_video(v1, "throwing.mp4 (16ad194b)")
    trace_video(v2, "Thowing.mp4 (849705c0)")
