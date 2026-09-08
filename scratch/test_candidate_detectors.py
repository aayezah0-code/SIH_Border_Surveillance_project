import os
import sys
import math
import logging

logging.basicConfig(level=logging.WARNING)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
sys.path.insert(0, BACKEND_DIR)
sys.path.insert(0, BASE_DIR)

from ai_engine.modules.detection.yolo_detector import YOLODetector
from ai_engine.modules.behavior.suspicious.track_history import TrackHistoryBuffer, TrackObservation

class CandidateCrawlingDetector:
    """
    Robust Crawling Detector:
    1. Prone body posture:
       - Strongly prone: Aspect Ratio >= 1.10 (width > height, typical for horizontal body)
       - Moderately prone with standing baseline drop:
         If track has confirmed standing baseline (AR <= 0.55), height must drop to <= 65% of standing, AND AR >= 0.85
       - Hard rejection: Any frame with AR <= 0.65 is upright (CANNOT be crawling)
    2. Ground locomotion:
       - Average ground displacement speed between min_crawling_speed (0.015 h/s) and max_crawling_speed (0.65 h/s)
       - If speed exceeds 0.65 h/s, it is walking or running, NOT crawling
    3. Temporal persistence:
       - Must sustain prone locomotion for >= 0.8s
    """
    def __init__(
        self,
        min_crawling_duration_sec: float = 0.8,
        min_prone_aspect_ratio: float = 1.10,
        moderate_prone_aspect_ratio: float = 0.85,
        upright_aspect_ceiling: float = 0.65,
        max_relative_height: float = 0.65,
        min_horizontal_speed: float = 0.015,
        max_crawling_speed: float = 0.65,
        stop_duration_sec: float = 0.8,
    ):
        self.min_crawling_duration_sec = min_crawling_duration_sec
        self.min_prone_aspect_ratio = min_prone_aspect_ratio
        self.moderate_prone_aspect_ratio = moderate_prone_aspect_ratio
        self.upright_aspect_ceiling = upright_aspect_ceiling
        self.max_relative_height = max_relative_height
        self.min_horizontal_speed = min_horizontal_speed
        self.max_crawling_speed = max_crawling_speed
        self.stop_duration_sec = stop_duration_sec
        self._states = {}

    def process_observation(self, source_id: str, obs: TrackObservation, history_buffer: TrackHistoryBuffer):
        if obs is None or obs.class_name != "person" or obs.track_id is None:
            return None
        
        tid = obs.track_id
        if source_id not in self._states:
            self._states[source_id] = {}
        if tid not in self._states[source_id]:
            self._states[source_id][tid] = {
                "state": "NOT_CRAWLING",
                "crawl_start_ts": None,
                "crawl_start_point": None,
                "upright_start_ts": None,
                "standing_h": None,
                "last_confirmed_ts": None,
            }
        st = self._states[source_id][tid]
        hist = history_buffer.get_history(source_id, tid)
        if len(hist) < 3:
            return None

        ar = obs.aspect_ratio
        h = float(obs.height)

        # Baseline update ONLY from clearly upright frames
        if ar <= 0.55 and h > 0:
            if st["standing_h"] is None or h > st["standing_h"]:
                st["standing_h"] = h

        # 1. Posture check
        is_strongly_prone = (ar >= self.min_prone_aspect_ratio)
        is_dropped_prone = False
        if st["standing_h"] is not None and st["standing_h"] > 0:
            rel_h = h / st["standing_h"]
            if rel_h <= self.max_relative_height and ar >= self.moderate_prone_aspect_ratio:
                is_dropped_prone = True

        # Hard rejection: upright AR is NEVER prone
        is_prone_posture = (is_strongly_prone or is_dropped_prone) and (ar > self.upright_aspect_ceiling)

        baseline_h = st["standing_h"] if st["standing_h"] else h

        if is_prone_posture:
            st["upright_start_ts"] = None
            if st["crawl_start_ts"] is None or st["crawl_start_point"] is None:
                st["crawl_start_ts"] = obs.timestamp_sec
                st["crawl_start_point"] = obs.bottom_center

            elapsed_crawl = obs.timestamp_sec - st["crawl_start_ts"]
            
            # Ground displacement
            total_dx = obs.bottom_center[0] - st["crawl_start_point"][0]
            total_dy = obs.bottom_center[1] - st["crawl_start_point"][1]
            total_dist = math.sqrt(total_dx*total_dx + total_dy*total_dy)
            
            avg_speed = (total_dist / elapsed_crawl) / baseline_h if elapsed_crawl > 0.05 else 0.0

            # Locomotion check: must be in crawling window (reject stationary or fast running)
            has_valid_locomotion = (self.min_horizontal_speed <= avg_speed <= self.max_crawling_speed)

            if (
                st["state"] == "NOT_CRAWLING"
                and elapsed_crawl >= self.min_crawling_duration_sec
                and has_valid_locomotion
            ):
                st["state"] = "CRAWLING_CONFIRMED"
                st["last_confirmed_ts"] = obs.timestamp_sec
                rel_h = h / baseline_h
                return {
                    "track_id": tid,
                    "source_id": source_id,
                    "timestamp_sec": obs.timestamp_sec,
                    "frame_index": obs.frame_index,
                    "aspect_ratio": round(ar, 3),
                    "relative_height": round(rel_h, 3),
                    "horizontal_speed": round(avg_speed, 3),
                    "duration_sec": round(elapsed_crawl, 3),
                    "confidence": 0.95,
                    "activity": "CRAWLING",
                }
        else:
            st["crawl_start_ts"] = None
            st["crawl_start_point"] = None
            if st["upright_start_ts"] is None:
                st["upright_start_ts"] = obs.timestamp_sec
            if st["state"] == "CRAWLING_CONFIRMED":
                if (obs.timestamp_sec - st["upright_start_ts"]) >= self.stop_duration_sec:
                    st["state"] = "NOT_CRAWLING"
                    st["upright_start_ts"] = None
        return None


class CandidateRunningDetector:
    """
    Robust Running Detector:
    1. Kinematics calculation:
       - Uses representative body height from recent history
       - Computes instantaneous normalized speed in body-heights/sec
       - Smooths velocity with EMA (alpha=0.35) or rolling window to handle running stride oscillation
    2. Running threshold:
       - Threshold: 0.65 body-heights/sec (biomechanically separates fast walking 0.3-0.5 from running > 0.65)
       - Adaptive multiplier: 2.0x of verified walking baseline (if baseline is available from slow locomotion < 0.4 h/s)
    3. Temporal persistence:
       - Requires >= 0.30s of sustained running speed (FPS-invariant based on timestamp_sec)
    4. One event per running episode with hysteresis reset when stopped/slow for 0.5s.
    """
    def __init__(
        self,
        running_threshold: float = 0.65,          # body-heights/sec
        min_running_duration_sec: float = 0.30,   # media duration (FPS-invariant)
        velocity_window_sec: float = 0.5,
        walk_speed_ceiling: float = 0.45,         # max speed that can be considered walking baseline
        adaptive_run_multiplier: float = 2.0,
        stop_threshold: float = 0.35,
        stop_duration_sec: float = 0.5,
    ):
        self.running_threshold = running_threshold
        self.min_running_duration_sec = min_running_duration_sec
        self.velocity_window_sec = velocity_window_sec
        self.walk_speed_ceiling = walk_speed_ceiling
        self.adaptive_run_multiplier = adaptive_run_multiplier
        self.stop_threshold = stop_threshold
        self.stop_duration_sec = stop_duration_sec
        self._states = {}

    def process_observation(self, source_id: str, obs: TrackObservation, history_buffer: TrackHistoryBuffer):
        if obs is None or obs.class_name != "person" or obs.track_id is None:
            return None

        tid = obs.track_id
        if source_id not in self._states:
            self._states[source_id] = {}
        if tid not in self._states[source_id]:
            self._states[source_id][tid] = {
                "state": "NOT_RUNNING",
                "run_start_ts": None,
                "slow_start_ts": None,
                "smoothed_v": 0.0,
                "walk_samples": [],
                "walk_baseline": None,
            }
        st = self._states[source_id][tid]
        hist = history_buffer.get_history(source_id, tid)
        if len(hist) < 3:
            return None

        prev = hist[-2]
        dt = obs.timestamp_sec - prev.timestamp_sec
        if dt <= 0 or dt > 1.5:
            st["run_start_ts"] = None
            return None

        recent_h = [h.height for h in hist[-6:] if h.height > 0]
        rep_h = sum(recent_h) / len(recent_h) if recent_h else float(obs.height)
        if rep_h <= 0:
            return None

        p_prev = prev.bottom_center
        p_curr = obs.bottom_center
        dx = p_curr[0] - p_prev[0]
        dy = p_curr[1] - p_prev[1]
        dist_px = math.sqrt(dx*dx + dy*dy)
        inst_v_norm = (dist_px / dt) / rep_h

        # EMA smoothing for stride oscillation resistance
        # alpha = 0.40 provides fast response with stride smoothing
        if st["smoothed_v"] == 0.0:
            st["smoothed_v"] = inst_v_norm
        else:
            st["smoothed_v"] = 0.40 * inst_v_norm + 0.60 * st["smoothed_v"]

        smoothed_v = st["smoothed_v"]
        curr_ts = obs.timestamp_sec

        # Baseline updating: ONLY update from slow speeds <= walk_speed_ceiling
        if inst_v_norm <= self.walk_speed_ceiling and st["state"] == "NOT_RUNNING":
            st["walk_samples"].append((curr_ts, inst_v_norm))
            w_cutoff = curr_ts - 2.0
            st["walk_samples"] = [s for s in st["walk_samples"] if s[0] >= w_cutoff]
            if len(st["walk_samples"]) >= 4:
                st["walk_baseline"] = sum(s[1] for s in st["walk_samples"]) / len(st["walk_samples"])

        # Running Classification:
        is_running_speed = False
        if st["walk_baseline"] is not None:
            adaptive_target = max(self.running_threshold, st["walk_baseline"] * self.adaptive_run_multiplier)
            is_running_speed = (smoothed_v >= adaptive_target)
        else:
            is_running_speed = (smoothed_v >= self.running_threshold)

        if is_running_speed:
            st["slow_start_ts"] = None
            if st["run_start_ts"] is None:
                st["run_start_ts"] = prev.timestamp_sec

            elapsed_run = curr_ts - st["run_start_ts"]
            if st["state"] == "NOT_RUNNING" and elapsed_run >= self.min_running_duration_sec:
                st["state"] = "RUNNING_CONFIRMED"
                return {
                    "track_id": tid,
                    "source_id": source_id,
                    "timestamp_sec": curr_ts,
                    "frame_index": obs.frame_index,
                    "normalized_speed": round(smoothed_v, 3),
                    "duration_sec": round(elapsed_run, 3),
                    "confidence": 0.95,
                    "activity": "RUNNING",
                }
        else:
            if smoothed_v < self.stop_threshold:
                if st["slow_start_ts"] is None:
                    st["slow_start_ts"] = curr_ts
                if st["state"] == "RUNNING_CONFIRMED":
                    if (curr_ts - st["slow_start_ts"]) >= self.stop_duration_sec:
                        st["state"] = "NOT_RUNNING"
                        st["run_start_ts"] = None
                        st["slow_start_ts"] = None
            else:
                if st["state"] == "NOT_RUNNING":
                    st["run_start_ts"] = None
        return None

def test_on_all_videos():
    videos = [
        ("C:/Users/HP/Downloads/running.mp4", "vid_running_orig"),
        ("C:/Users/HP/Downloads/running_test.mp4", "vid_running_test"),
        ("C:/Users/HP/Downloads/running test2.mp4", "vid_running_test2"),
        ("C:/Users/HP/Downloads/crawling.mp4", "vid_crawling_orig"),
        ("C:/Users/HP/Downloads/Thowing.mp4", "vid_throwing_orig"),
    ]
    detector = YOLODetector.get_instance()
    for vpath, sid in videos:
        if not os.path.exists(vpath):
            continue
        print("\n" + "=" * 80)
        print(f"TESTING CANDIDATE DETECTORS ON: {os.path.basename(vpath)}")
        print("=" * 80)

        history_buffer = TrackHistoryBuffer(max_history=120)
        crawling_det = CandidateCrawlingDetector()
        running_det = CandidateRunningDetector()

        confirmed_events = []

        def on_frame(frame_data):
            for det in frame_data.detections:
                if det.track_id is not None and det.class_name == "person":
                    obs = history_buffer.update(sid, det, frame_data.timestamp_sec, frame_data.frame_index)
                    if obs:
                        # Process running
                        r_res = running_det.process_observation(sid, obs, history_buffer)
                        if r_res:
                            confirmed_events.append(r_res)
                            print(f"  >>> CONFIRMED RUNNING: Track #{r_res['track_id']} at {r_res['timestamp_sec']:.2f}s (Speed={r_res['normalized_speed']:.2f} h/s, dur={r_res['duration_sec']:.2f}s)")
                        
                        # Process crawling
                        c_res = crawling_det.process_observation(sid, obs, history_buffer)
                        if c_res:
                            confirmed_events.append(c_res)
                            print(f"  >>> CONFIRMED CRAWLING: Track #{c_res['track_id']} at {c_res['timestamp_sec']:.2f}s (AR={c_res['aspect_ratio']:.2f}, Speed={c_res['horizontal_speed']:.2f} h/s)")

        detector.process_video(vpath, max_frames=600, sample_rate=1, on_frame_processed=on_frame)
        print(f"FINAL RESULT for {os.path.basename(vpath)}: {len(confirmed_events)} events -> {[e['activity'] for e in confirmed_events]}")

if __name__ == "__main__":
    test_on_all_videos()
