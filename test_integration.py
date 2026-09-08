import sys
import time
from pathlib import Path

# Add paths
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from ai_engine.modules.behavior.virtual_fence import fence_registry
from ai_engine.modules.recognition.face_worker import face_worker

def test_full_runtime_pipeline():
    print("=== RUNNING FULL RUNTIME INTEGRATION TEST ===")
    source_id = "sector_4_alpha"
    
    # 1. User configures a 10-second loitering zone on Sector 4 - Alpha
    zone_pts = [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)]
    fence_registry.set_fence(source_id, "zone", zone_pts, loitering_duration=10.0)
    
    cfg = fence_registry.get_fence(source_id)
    assert cfg.loitering_duration == 10.0
    print("[PASS] 1. Configured 10s loitering zone for Sector 4 - Alpha.")
    
    # 2. Frame 0: Unknown Person Track #5 enters restricted zone at t=0.0s
    bbox_in = (0.3, 0.3, 0.5, 0.7) # inside zone
    intrusion_event = fence_registry.check_intrusion(source_id, 5, bbox_in, 1920, 1080)
    assert intrusion_event == "zone_intrusion"
    print("[PASS] 2. Immediate Restricted Zone Intrusion (ZONE ENTRY) alert triggered at t=0.0s.")
    
    # Check loitering at t=0.0s (face recognition pending)
    loiter_t0 = fence_registry.check_loitering(source_id, 5, current_timestamp_sec=0.0, is_person=True)
    assert loiter_t0 is None, "Loitering alert must NOT fire at entry (t=0.0s)"
    print("[PASS] 3. Loitering alert did not fire prematurely at entry.")
    
    # 3. Frame at t=5.0s: Person remains inside zone, face recognized as UNKNOWN_PERSON
    face_worker._track_identities[(source_id, 5)] = {
        "status": "UNKNOWN_PERSON",
        "name": "Unknown Person",
        "role": "Unrecognized Subject",
        "confidence": 0.42
    }
    # Check intrusion at t=5.0s (should NOT re-fire intrusion alert)
    intrusion_t5 = fence_registry.check_intrusion(source_id, 5, bbox_in, 1920, 1080)
    assert intrusion_t5 is None, "Duplicate intrusion alert prevented"
    
    # Check loitering at t=5.0s (elapsed 5.0s < 10.0s threshold)
    loiter_t5 = fence_registry.check_loitering(source_id, 5, current_timestamp_sec=5.0, is_person=True)
    assert loiter_t5 is None, "Loitering must NOT fire before 10.0s"
    print("[PASS] 4. t=5.0s: Target still inside, elapsed 5.0s < 10.0s -> 0 alerts.")
    
    # 4. Simulate a dropped detection at t=7.0s (cleanup_exited_tracks runs)
    fence_registry.cleanup_exited_tracks(source_id, set(), current_timestamp_sec=7.0)
    # Ensure dwell timer wasn't wiped by transient 1-frame drop
    assert 5 in fence_registry._zone_dwell_start[source_id]
    print("[PASS] 5. Transient tracking flicker at t=7.0s did not wipe accumulated dwell timer.")
    
    # 5. Frame at t=10.5s: Person still inside zone -> EXCEEDS 10.0s threshold!
    loiter_t10 = fence_registry.check_loitering(source_id, 5, current_timestamp_sec=10.5, is_person=True)
    assert loiter_t10 is not None, "Loitering alert MUST fire at t=10.5s (elapsed 10.5s >= 10.0s)"
    assert loiter_t10["duration"] == 10.5
    assert loiter_t10["threshold"] == 10.0
    print(f"[PASS] 6. [ALERT] LOITERING DETECTED triggered at elapsed={loiter_t10['duration']}s (Threshold: {loiter_t10['threshold']}s).")
    
    # 6. Subsequent frames at t=12.0s, 15.0s, 20.0s -> MUST NOT DUPLICATE ALERTS
    loiter_t12 = fence_registry.check_loitering(source_id, 5, current_timestamp_sec=12.0, is_person=True)
    loiter_t15 = fence_registry.check_loitering(source_id, 5, current_timestamp_sec=15.0, is_person=True)
    loiter_t20 = fence_registry.check_loitering(source_id, 5, current_timestamp_sec=20.0, is_person=True)
    assert loiter_t12 is None and loiter_t15 is None and loiter_t20 is None
    print("[PASS] 7. Subsequent frames at t=12s, 15s, 20s generated ZERO duplicate alerts.")
    
    # 7. Person exits zone at t=25.0s
    bbox_out = (0.05, 0.05, 0.1, 0.1) # outside
    fence_registry.check_intrusion(source_id, 5, bbox_out, 1920, 1080)
    fence_registry.cleanup_exited_tracks(source_id, {5}, current_timestamp_sec=25.0)
    assert 5 not in fence_registry._zone_dwell_start[source_id]
    print("[PASS] 8. Target exit at t=25.0s cleanly reset dwell timer.")
    
    # 8. Person re-enters at t=40.0s (first check_loitering at t=45.0s -> dwell_start = 45.0s)
    fence_registry.check_intrusion(source_id, 5, bbox_in, 1920, 1080)
    loiter_re_45 = fence_registry.check_loitering(source_id, 5, current_timestamp_sec=45.0, is_person=True)
    assert loiter_re_45 is None, "Re-entry at t=45s: elapsed 0.0s < 10.0s -> no alert"
    loiter_re_50 = fence_registry.check_loitering(source_id, 5, current_timestamp_sec=50.0, is_person=True)
    assert loiter_re_50 is None, "Re-entry at t=45s: elapsed 5.0s < 10.0s -> no alert"
    loiter_re_56 = fence_registry.check_loitering(source_id, 5, current_timestamp_sec=56.0, is_person=True)
    assert loiter_re_56 is not None, "Re-entry at t=45s: elapsed 11.0s >= 10.0s -> NEW alert fired"
    print(f"[PASS] 9. Re-entry started fresh timer at 45.0s and fired new alert at t=56.0s (elapsed={loiter_re_56['duration']}s).")
    
    # 9. Test KNOWN_PERSON (military authorized personnel)
    fence_registry.check_intrusion(source_id, 99, bbox_in, 1920, 1080)
    face_worker._track_identities[(source_id, 99)] = {
        "status": "KNOWN_PERSON",
        "name": "Major Rajan",
        "role": "Border Security Force",
        "confidence": 0.95
    }
    loiter_known_60 = fence_registry.check_loitering(source_id, 99, current_timestamp_sec=60.0, is_person=True)
    loiter_known_100 = fence_registry.check_loitering(source_id, 99, current_timestamp_sec=100.0, is_person=True)
    assert loiter_known_60 is None and loiter_known_100 is None
    print("[PASS] 10. KNOWN_PERSON (Authorized military) remained inside for 60+ seconds with 0 alerts (100% EXEMPT).")
    
    print("\n=== COMPLETE RUNTIME INTEGRATION TEST PASSED ===")

if __name__ == "__main__":
    test_full_runtime_pipeline()
