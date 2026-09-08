import os
import sys
import math
import cv2
import logging

logging.basicConfig(level=logging.WARNING)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
sys.path.insert(0, BACKEND_DIR)
sys.path.insert(0, BASE_DIR)

from ai_engine.modules.detection.yolo_detector import YOLODetector
from ai_engine.modules.behavior.suspicious.track_history import TrackHistoryBuffer
from ai_engine.modules.behavior.suspicious.running_detector import RunningDetector
from ai_engine.modules.behavior.suspicious.crawling_detector import CrawlingDetector
from ai_engine.modules.behavior.suspicious.throwing_detector import ThrowingDetector
from ai_engine.modules.behavior.suspicious.suspicious_engine import SuspiciousActivityEngine

def analyze_video(video_path: str, source_id: str):
    print("\n" + "=" * 80)
    print(f"ANALYZING VIDEO: {os.path.basename(video_path)} (path: {video_path})")
    print("=" * 80)

    if not os.path.exists(video_path):
        print(f"File not found: {video_path}")
        return

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration_sec = total_frames / fps if fps > 0 else 0.0
    cap.release()

    print(f"Resolution: {width}x{height}, FPS: {fps:.2f}, Total Frames: {total_frames}, Duration: {duration_sec:.2f}s")

    detector = YOLODetector.get_instance()
    history_buffer = TrackHistoryBuffer(max_history=120)
    running_det = RunningDetector()
    crawling_det = CrawlingDetector()
    throwing_det = ThrowingDetector()
    engine = SuspiciousActivityEngine(
        history_buffer=history_buffer,
        running_detector=running_det,
        crawling_detector=crawling_det,
        throwing_detector=throwing_det,
    )

    confirmed_events = []
    frame_count = 0
    person_tracks_seen = set()

    def on_frame(frame_data):
        nonlocal frame_count
        frame_count += 1
        raw_frame_idx = frame_data.frame_index
        timestamp_sec = frame_data.timestamp_sec
        tracked_dets = frame_data.detections

        for det in tracked_dets:
            if det.track_id is not None and det.class_name == "person":
                person_tracks_seen.add(det.track_id)

                # Collect detailed telemetry for every person frame
                hist = history_buffer.get_history(source_id, det.track_id)
                tstate_c = crawling_det._get_track_state(source_id, det.track_id)
                tstate_r = running_det._get_track_state(source_id, det.track_id)

                w = det.x2 - det.x1
                h = det.y2 - det.y1
                ar = w / h if h > 0 else 0.0
                area = w * h

                # Representative height & baselines
                baseline_h = tstate_c.standing_height_baseline or float(h)
                baseline_area = tstate_c.standing_area_baseline or float(area)
                rel_h = h / baseline_h if baseline_h > 0 else 1.0
                area_ratio = area / baseline_area if baseline_area > 0 else 1.0

                # Kinematics from history
                if len(hist) >= 2:
                    p_prev = hist[-1].bottom_center
                    p_curr = ( (det.x1+det.x2)/2.0, det.y2 )
                    dt = timestamp_sec - hist[-1].timestamp_sec
                    dx = p_curr[0] - p_prev[0]
                    dy = p_curr[1] - p_prev[1]
                    dist_px = math.sqrt(dx*dx + dy*dy)
                    vx = (dx / dt) / baseline_h if (dt > 0 and baseline_h > 0) else 0.0
                    vy = (dy / dt) / baseline_h if (dt > 0 and baseline_h > 0) else 0.0
                    v_norm = (dist_px / dt) / baseline_h if (dt > 0 and baseline_h > 0) else 0.0
                else:
                    vx, vy, v_norm = 0.0, 0.0, 0.0

                # Crawling signals evaluation
                sig_a = (crawling_det.min_aspect_ratio <= ar <= crawling_det.max_aspect_ratio) or (
                    tstate_c.standing_aspect_baseline is not None and ar >= tstate_c.standing_aspect_baseline * crawling_det.aspect_ratio_change_multiplier
                )
                sig_b = (rel_h <= crawling_det.max_relative_height) if baseline_h > 0 else False
                sig_c = (area_ratio <= crawling_det.max_area_ratio) if baseline_area > 0 else False
                active_signals = int(sig_a) + int(sig_b) + int(sig_c)

                # Elapsed times
                crawl_elapsed = (timestamp_sec - tstate_c.crawl_start_ts) if tstate_c.crawl_start_ts else 0.0
                run_elapsed = (timestamp_sec - tstate_r.run_start_ts) if tstate_r.run_start_ts else 0.0

                # Smoothed speed in running detector
                win_samples = list(tstate_r.velocity_samples)
                smoothed_v_norm = sum(s.v_norm for s in win_samples[-3:]) / float(len(win_samples[-3:])) if win_samples else 0.0

                # Print telemetry for person track
                print(
                    f"[TELEMETRY] F#{raw_frame_idx:03d} T={timestamp_sec:.2f}s | Trk#{det.track_id} | "
                    f"bbox=[{det.x1},{det.y1},{det.x2},{det.y2}] w={w} h={h} AR={ar:.2f} | "
                    f"baseH={baseline_h:.0f} relH={rel_h:.2f} areaR={area_ratio:.2f} | "
                    f"vNorm={v_norm:.2f} (smth={smoothed_v_norm:.2f}) vx={vx:.2f} vy={vy:.2f} | "
                    f"crawlSig={active_signals}/3 (A:{int(sig_a)},B:{int(sig_b)},C:{int(sig_c)}) crawlT={crawl_elapsed:.2f}s | "
                    f"runT={run_elapsed:.2f}s | crawlState={tstate_c.state} runState={tstate_r.state}"
                )

        # Process frame through engine
        events = engine.process_frame(
            source_id=source_id,
            frame_data=frame_data,
            timestamp_sec=timestamp_sec,
            frame_index=raw_frame_idx,
        )
        for ev in events:
            confirmed_events.append(ev)
            print(f"*** EVENT CONFIRMED: {ev.activity} on Track #{ev.track_id} at {ev.timestamp_sec:.2f}s (Frame #{ev.frame_index}) Conf={ev.confidence:.2f} Score={ev.score:.2f} Meta={ev.metadata}")

    detector.process_video(
        video_path=video_path,
        max_frames=600,
        sample_rate=1, # process every frame for accurate telemetry
        on_frame_processed=on_frame,
    )

    print("\n--- SUMMARY FOR VIDEO:", os.path.basename(video_path), "---")
    print(f"Total Frames Processed: {frame_count}")
    print(f"Person Tracks Seen: {sorted(list(person_tracks_seen))}")
    print(f"Confirmed Events ({len(confirmed_events)}):")
    for ev in confirmed_events:
        print(f"  -> Activity: {ev.activity}, Track: {ev.track_id}, Time: {ev.timestamp_sec:.2f}s, Conf: {ev.confidence:.2f}, Metadata: {ev.metadata}")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    videos = [
        ("C:/Users/HP/Downloads/running.mp4", "vid_running_orig"),
        ("C:/Users/HP/Downloads/running_test.mp4", "vid_running_test"),
        ("C:/Users/HP/Downloads/running test2.mp4", "vid_running_test2"),
        ("C:/Users/HP/Downloads/crawling.mp4", "vid_crawling_orig"),
        ("C:/Users/HP/Downloads/Thowing.mp4", "vid_throwing_orig"),
    ]
    for vpath, sid in videos:
        if os.path.exists(vpath):
            analyze_video(vpath, sid)
