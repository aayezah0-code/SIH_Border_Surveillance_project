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
from ai_engine.modules.behavior.suspicious.track_history import TrackHistoryBuffer, TrackObservation

# Let's prototype the refined detector logic
class RefinedCrawlingDetector:
    def __init__(
        self,
        min_crawling_duration_sec: float = 0.8,
        min_prone_aspect_ratio: float = 1.15,      # Strongly prone AR
        moderate_prone_aspect_ratio: float = 0.85, # Moderate prone AR (requires standing drop)
        upright_aspect_ceiling: float = 0.65,      # Above this is upright/vertical (CANNOT be crawling)
        max_relative_height: float = 0.65,         # Body height must drop to <= 65% of standing
        min_horizontal_speed: float = 0.02,        # Ground locomotion floor (h/s)
        max_crawling_speed: float = 0.75,          # Ground locomotion ceiling (h/s) - above this is running/walking
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
                "consecutive_prone_time": 0.0,
            }
        st = self._states[source_id][tid]
        hist = history_buffer.get_history(source_id, tid)
        if len(hist) < 3:
            return None

        # Standing baseline update: ONLY from clearly upright frames (AR <= 0.55)
        ar = obs.aspect_ratio
        h = float(obs.height)
        w = float(obs.width)

        if ar <= 0.55 and h > 0:
            if st["standing_h"] is None or h > st["standing_h"]:
                st["standing_h"] = h

        # Evaluate Prone Posture:
        # Case 1: Strongly prone by aspect ratio (e.g. AR >= 1.15, person enters already crawling or lying flat)
        is_strongly_prone = (ar >= self.min_prone_aspect_ratio)
        
        # Case 2: Dropped from confirmed standing baseline AND has non-upright aspect ratio
        # Must have a real standing baseline, height dropped significantly (<= 0.65), AND AR >= 0.85
        # (Reject running person whose stride temporarily shrinks bbox height but remains AR < 0.65)
        is_dropped_prone = False
        if st["standing_h"] is not None and st["standing_h"] > 0:
            rel_h = h / st["standing_h"]
            if rel_h <= self.max_relative_height and ar >= self.moderate_prone_aspect_ratio:
                is_dropped_prone = True

        # STRICT REJECTION: An upright aspect ratio (AR <= upright_aspect_ceiling, e.g. <= 0.65) is NEVER prone
        is_prone_posture = (is_strongly_prone or is_dropped_prone) and (ar > self.upright_aspect_ceiling)

        baseline_h = st["standing_h"] if st["standing_h"] else h

        # Kinematics check (velocity)
        prev = hist[-2]
        dt = obs.timestamp_sec - prev.timestamp_sec
        if dt > 0 and baseline_h > 0:
            dx = obs.bottom_center[0] - prev.bottom_center[0]
            dy = obs.bottom_center[1] - prev.bottom_center[1]
            inst_speed = (math.sqrt(dx*dx + dy*dy) / dt) / baseline_h
        else:
            inst_speed = 0.0

        if is_prone_posture:
            st["upright_start_ts"] = None
            if st["crawl_start_ts"] is None or st["crawl_start_point"] is None:
                st["crawl_start_ts"] = obs.timestamp_sec
                st["crawl_start_point"] = obs.bottom_center

            elapsed_crawl = obs.timestamp_sec - st["crawl_start_ts"]
            
            # Ground displacement from start
            total_dx = obs.bottom_center[0] - st["crawl_start_point"][0]
            total_dy = obs.bottom_center[1] - st["crawl_start_point"][1]
            total_dist = math.sqrt(total_dx*total_dx + total_dy*total_dy)
            
            if elapsed_crawl > 0.05:
                avg_speed = (total_dist / elapsed_crawl) / baseline_h
            else:
                avg_speed = 0.0

            # Locomotion condition: must be in crawling speed range [min_speed, max_crawling_speed]
            # If speed > max_crawling_speed (e.g. 0.75 h/s), it is fast movement/running, NOT crawling!
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


class RefinedRunningDetector:
    def __init__(
        self,
        running_threshold: float = 0.75,          # body-heights/sec (realistic running threshold)
        min_running_duration_sec: float = 0.35,   # media duration (FPS-invariant)
        velocity_window_sec: float = 0.4,
        walk_speed_ceiling: float = 0.55,         # max speed that can be considered walking baseline
        adaptive_run_multiplier: float = 2.0,
        stop_threshold: float = 0.4,
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
                "samples": [],   # (ts, v_norm)
                "walk_samples": [],
                "walk_baseline": None,
            }
        st = self._states[source_id][tid]
        hist = history_buffer.get_history(source_id, tid)
        if len(hist) < 3:
            return None

        prev = hist[-2]
        dt = obs.timestamp_sec - prev.timestamp_sec
        if dt <= 0:
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

        curr_ts = obs.timestamp_sec
        st["samples"].append((curr_ts, inst_v_norm))
        # Keep window
        cutoff = curr_ts - self.velocity_window_sec
        st["samples"] = [s for s in st["samples"] if s[0] >= cutoff]

        if not st["samples"]:
            return None

        # Smoothed velocity (median or average over short recent window for noise resistance)
        recent_s = st["samples"][-min(len(st["samples"]), 4):]
        smoothed_v = sum(s[1] for s in recent_s) / len(recent_s)

        # Baseline updating: ONLY update from speeds <= walk_speed_ceiling (prevents running from poisoning baseline)
        if inst_v_norm <= self.walk_speed_ceiling and st["state"] == "NOT_RUNNING":
            st["walk_samples"].append((curr_ts, inst_v_norm))
            w_cutoff = curr_ts - 2.0
            st["walk_samples"] = [s for s in st["walk_samples"] if s[0] >= w_cutoff]
            if len(st["walk_samples"]) >= 3:
                st["walk_baseline"] = sum(s[1] for s in st["walk_samples"]) / len(st["walk_samples"])

        # Running Classification:
        # 1. If we have a reliable walk baseline: speed > baseline * multiplier AND speed >= 0.70
        # 2. If no walk baseline: speed >= running_threshold (0.75)
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
        print(f"TESTING REFINED DETECTORS ON: {os.path.basename(vpath)}")
        print("=" * 80)

        history_buffer = TrackHistoryBuffer(max_history=120)
        crawling_det = RefinedCrawlingDetector()
        running_det = RefinedRunningDetector()

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
                            print(f"  >>> CONFIRMED RUNNING: Track #{r_res['track_id']} at {r_res['timestamp_sec']:.2f}s (Speed={r_res['normalized_speed']:.2f} h/s)")
                        
                        # Process crawling
                        c_res = crawling_det.process_observation(sid, obs, history_buffer)
                        if c_res:
                            confirmed_events.append(c_res)
                            print(f"  >>> CONFIRMED CRAWLING: Track #{c_res['track_id']} at {c_res['timestamp_sec']:.2f}s (AR={c_res['aspect_ratio']:.2f}, Speed={c_res['horizontal_speed']:.2f} h/s)")

        detector.process_video(vpath, max_frames=600, sample_rate=1, on_frame_processed=on_frame)
        print(f"Result for {os.path.basename(vpath)}: {len(confirmed_events)} events -> {[e['activity'] for e in confirmed_events]}")

if __name__ == "__main__":
    test_on_all_videos()
