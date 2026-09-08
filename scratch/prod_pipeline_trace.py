"""
Production Pipeline Trace
=========================
Replicates the EXACT detection_router.py code path for uploaded videos
and traces whether suspicious activity events fire.
"""
import os, sys, logging

logging.basicConfig(level=logging.WARNING, format='%(levelname)s:%(name)s:%(message)s')
logging.getLogger('ai_engine.modules.behavior.suspicious').setLevel(logging.INFO)

BASE_DIR = r'C:\Users\HP\Desktop\SIH_Border_Surveillance_project'
BACKEND_DIR = os.path.join(BASE_DIR, 'backend')
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, BACKEND_DIR)

# ── Replicate module-level detection_router setup ──────────────────────────
from ai_engine.modules.behavior.suspicious import SuspiciousActivityEngine
suspicious_engine = SuspiciousActivityEngine()

from ai_engine.modules.tracking.tracker_registry import tracker_registry
from ai_engine.modules.behavior.virtual_fence import fence_registry
from app.services.detection_service import run_detection_on_video

RUNNING_SRC = '4bee2e49-e24f-4ce4-88bd-25616ac06c0f'
CRAWLING_SRC = 'd7a2bb15-aea4-4799-ab2b-1cb1cc2f817d'

def test_source(source_id, label):
    filename = source_id + '.mp4'
    print(f"\n{'='*70}")
    print(f"TEST: {label}")
    print(f"source_id={source_id}")
    print(f"{'='*70}")

    # Exact replicas of lines 676-680 in detection_router
    tracker_registry.prepare_for_source(source_id)
    fence_registry.prepare_for_source(source_id)
    suspicious_engine.clear_source(source_id)

    confirmed_events = []
    frame_count = [0]

    def handle_frame(frame_data):
        frame_count[0] += 1
        try:
            active_tids = {d.track_id for d in frame_data.detections if d.track_id is not None}
            suspicious_engine.cleanup(
                source_id=source_id,
                active_track_ids=active_tids,
                current_timestamp_sec=getattr(frame_data, 'timestamp_sec', 0.0),
                max_stale_seconds=3.0,
            )
            susp_events = suspicious_engine.process_frame(
                source_id=source_id,
                frame_data=frame_data,
                timestamp_sec=getattr(frame_data, 'timestamp_sec', 0.0),
                frame_index=getattr(frame_data, 'frame_index', 0),
            )
            for ev in susp_events:
                msg = f"!!! {ev.activity} track={ev.track_id} ts={ev.timestamp_sec:.2f}s meta={dict(ev.metadata)}"
                print(msg)
                confirmed_events.append(msg)
        except Exception as e:
            import traceback
            print(f"[ENGINE ERROR] {e}")
            traceback.print_exc()

        # Per-person telemetry
        for det in frame_data.detections:
            if det.class_name == 'person' and det.track_id is not None:
                hist = suspicious_engine.history_buffer.get_history(source_id, det.track_id)
                r_state = suspicious_engine.running_detector._states.get(source_id, {}).get(det.track_id)
                c_state = suspicious_engine.crawling_detector._states.get(source_id, {}).get(det.track_id)
                r_st = r_state.state if r_state else 'NONE'
                r_con = r_state.consecutive_running if r_state else 0
                r_vhist = list(r_state.velocity_history_norm) if r_state else []
                c_st = c_state.state if c_state else 'NONE'
                c_ar = 0.0
                if hist:
                    obs = hist[-1]
                    c_ar = obs.aspect_ratio
                print(
                    f"  [F{frame_data.frame_index:04d}] ts={frame_data.timestamp_sec:.3f} t={det.track_id} "
                    f"h={det.y2-det.y1}px hist={len(hist)} "
                    f"run_state={r_st} consec={r_con} v_hist={[round(v,3) for v in r_vhist]} "
                    f"crawl_state={c_st} ar={c_ar:.3f}"
                )

    try:
        results = run_detection_on_video(
            filename=filename,
            max_frames=300,
            sample_rate=5,
            confidence=0.35,
            on_frame_processed=handle_frame,
        )
    except Exception as e:
        print(f"DETECTION ERROR: {e}")
        return

    # Exact replica of line 777
    suspicious_engine.clear_source(source_id)

    print(f"\n--- SUMMARY: {label} ---")
    print(f"  frames_processed = {results['frames_processed']}")
    print(f"  callbacks fired  = {frame_count[0]}")
    print(f"  total_detections = {results['total_detections']}")
    print(f"  unique_classes   = {results['unique_classes']}")
    print(f"  confirmed_events = {confirmed_events}")


if __name__ == '__main__':
    test_source(RUNNING_SRC, 'RUNNING VIDEO')
    test_source(CRAWLING_SRC, 'CRAWLING VIDEO')
    print("\nDONE")
