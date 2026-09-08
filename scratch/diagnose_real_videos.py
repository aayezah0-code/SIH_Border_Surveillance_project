import os
import sys
import math
import logging

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
AI_ENGINE_DIR = os.path.join(BASE_DIR, "ai_engine")
sys.path.insert(0, BACKEND_DIR)
sys.path.insert(0, BASE_DIR)

from ai_engine.modules.detection.yolo_detector import YOLODetector
from ai_engine.modules.behavior.suspicious.track_history import TrackHistoryBuffer
from ai_engine.modules.behavior.suspicious.running_detector import RunningDetector
from ai_engine.modules.behavior.suspicious.crawling_detector import CrawlingDetector
from ai_engine.modules.behavior.suspicious.throwing_detector import ThrowingDetector
from ai_engine.modules.behavior.suspicious.suspicious_engine import SuspiciousActivityEngine

def trace_video(video_path: str, source_id: str, label: str):
    print("=" * 80)
    print(f"TRACING VIDEO: {label} ({os.path.basename(video_path)})")
    print("=" * 80)

    if not os.path.exists(video_path):
        print(f"ERROR: Video path not found: {video_path}")
        return

    detector = YOLODetector.get_instance()
    history_buffer = TrackHistoryBuffer(max_history=30)
    running_detector = RunningDetector()
    crawling_detector = CrawlingDetector()
    throwing_detector = ThrowingDetector()
    engine = SuspiciousActivityEngine(
        history_buffer=history_buffer,
        running_detector=running_detector,
        crawling_detector=crawling_detector,
        throwing_detector=throwing_detector,
    )

    detected_classes_summary = {}
    confirmed_events_list = []

    def on_frame(frame_data):
        raw_frame_idx = frame_data.frame_index
        timestamp_sec = frame_data.timestamp_sec
        tracked_dets = frame_data.detections

        for d in tracked_dets:
            cls_n = d.class_name
            detected_classes_summary[cls_n] = detected_classes_summary.get(cls_n, 0) + 1

        # Log [SUSPICIOUS_DEBUG] for every tracked detection
        for det in tracked_dets:
            if det.track_id is not None:
                h_len = len(history_buffer.get_history(source_id, det.track_id))
                cx = (det.x1 + det.x2) / 2.0
                cy = (det.y1 + det.y2) / 2.0
                w = det.x2 - det.x1
                h = det.y2 - det.y1
                ar = (w / h) if h > 0 else 0.0
                print(
                    f"[SUSPICIOUS_DEBUG] source={source_id} track_id={det.track_id} "
                    f"cls={det.class_name} frame={raw_frame_idx} ts={timestamp_sec:.3f} "
                    f"bbox=({det.x1},{det.y1},{det.x2},{det.y2}) (w={w},h={h},ar={ar:.2f}) "
                    f"center=({cx:.1f},{cy:.1f}) conf={det.confidence:.2f} hist_before={h_len}"
                )

        # Process frame in engine
        active_tids = {d.track_id for d in tracked_dets if d.track_id is not None}
        engine.cleanup(
            source_id=source_id,
            active_track_ids=active_tids,
            current_timestamp_sec=timestamp_sec,
            max_stale_seconds=3.0,
        )
        events = engine.process_frame(
            source_id=source_id,
            frame_data=frame_data,
            timestamp_sec=timestamp_sec,
            frame_index=raw_frame_idx,
        )

        # Log [RUNNING_DEBUG] and [CRAWLING_DEBUG] for persons
        for det in tracked_dets:
            if det.track_id is None:
                continue

            if det.class_name == "person":
                hist = history_buffer.get_history(source_id, det.track_id)
                h_len = len(hist)

                # Running debug
                r_state = running_detector._get_track_state(source_id, det.track_id)
                v_norm = (
                    r_state.velocity_history_norm[-1]
                    if r_state.velocity_history_norm
                    else 0.0
                )
                smoothed_v = (
                    sum(r_state.velocity_history_norm) / len(r_state.velocity_history_norm)
                    if r_state.velocity_history_norm
                    else 0.0
                )
                r_detected = r_state.state == "RUNNING_CONFIRMED"
                r_reason = (
                    f"state={r_state.state}, consec={r_state.consecutive_running}/{running_detector.min_consecutive_frames}, "
                    f"smoothed_v={smoothed_v:.2f}, latest_inst_v={v_norm:.2f}, thresh={running_detector.running_threshold}"
                )
                print(
                    f"[RUNNING_DEBUG] track_id={det.track_id} hist_len={h_len} "
                    f"norm_vel={smoothed_v:.2f} qual_obs={r_state.consecutive_running} "
                    f"conf_count={running_detector.min_consecutive_frames} detected={r_detected} reason='{r_reason}'"
                )

                # Crawling debug
                c_state = crawling_detector._get_track_state(source_id, det.track_id)
                cur_obs = hist[-1] if hist else None
                if cur_obs:
                    ar = cur_obs.aspect_ratio
                    baseline = c_state.standing_height_baseline or cur_obs.height
                    rel_h = cur_obs.height / baseline if baseline > 0 else 1.0
                    elapsed_c = (
                        (timestamp_sec - c_state.crawl_start_ts)
                        if c_state.crawl_start_ts
                        else 0.0
                    )
                    c_detected = c_state.state == "CRAWLING_CONFIRMED"
                    c_reason = (
                        f"state={c_state.state}, ar={ar:.2f} (min={crawling_detector.min_aspect_ratio}), "
                        f"rel_h={rel_h:.2f} (max={crawling_detector.max_relative_height}), "
                        f"elapsed={elapsed_c:.2f}s (min={crawling_detector.min_crawling_duration_sec}s), "
                        f"baseline_h={baseline}"
                    )
                    print(
                        f"[CRAWLING_DEBUG] track_id={det.track_id} hist_len={h_len} "
                        f"ar={ar:.2f} rel_h={rel_h:.2f} horiz_v=-- "
                        f"persist_sec={elapsed_c:.2f} detected={c_detected} reason='{c_reason}'"
                    )

        # Log [THROWING_DEBUG]
        person_tracks = [d.track_id for d in tracked_dets if d.class_name == "person" and d.track_id is not None]
        obj_tracks = [d for d in tracked_dets if d.class_name != "person" and d.track_id is not None]
        for p_tid in person_tracks:
            for obj_d in obj_tracks:
                pair_key = (p_tid, obj_d.track_id)
                cand = throwing_detector._candidates.get(source_id, {}).get(pair_key)
                p_hist = history_buffer.get_history(source_id, p_tid)
                o_hist = history_buffer.get_history(source_id, obj_d.track_id)
                c_state = cand.state if cand else "NONE"
                q_count = cand.qualifying_count if cand else 0
                th_detected = cand.state == "THROW_CONFIRMED" if cand else False
                th_reason = f"cand_state={c_state}, qual_count={q_count}"
                print(
                    f"[THROWING_DEBUG] p_track={p_tid} obj_track={obj_d.track_id} "
                    f"p_hist={len(p_hist)} o_hist={len(o_hist)} obj_cls={obj_d.class_name} "
                    f"speed=-- dist=-- sep_growth=-- traj_score=-- "
                    f"conf_count={q_count} detected={th_detected} reason='{th_reason}'"
                )

        if events:
            for ev in events:
                msg = f"!!! CONFIRMED EVENT: {ev.activity} for track={ev.track_id} at {ev.timestamp_sec:.2f}s, metadata={ev.metadata}"
                print(msg)
                confirmed_events_list.append(msg)

    detector.process_video(
        video_path=video_path,
        max_frames=300,
        sample_rate=5,
        confidence=0.35,
        on_frame_processed=on_frame,
    )

    print("-" * 80)
    print(f"Summary for {label}: classes detected: {detected_classes_summary}")
    print(f"Confirmed events for {label}: {confirmed_events_list}")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    uploads = "backend/uploads"
    running_file = os.path.join(uploads, "4bee2e49-e24f-4ce4-88bd-25616ac06c0f.mp4")
    crawling_file = os.path.join(uploads, "d7a2bb15-aea4-4799-ab2b-1cb1cc2f817d.mp4")
    throwing_file = os.path.join(uploads, "16ad194b-5764-4157-ace1-3e2e225df2fe.mp4")

    trace_video(running_file, "running_test_src", "RUNNING VIDEO")
    trace_video(crawling_file, "crawling_test_src", "CRAWLING VIDEO")
    trace_video(throwing_file, "throwing_test_src", "THROWING VIDEO")
