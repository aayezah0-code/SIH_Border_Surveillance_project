import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[4] / "SIH_Border_Surveillance_project"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from ai_engine.modules.behavior.virtual_fence import fence_registry
from ai_engine.modules.recognition.face_worker import face_worker

def test_loitering_suite():
    print("=== STARTING LOITERING TEST SUITE ===")
    source_id = "test_cam_01"
    
    # 1. Setup zone with 10.0s loitering duration
    polygon_points = [(0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)]
    fence_registry.set_fence(source_id, "zone", polygon_points, loitering_duration=10.0)
    
    # Check initial fence config
    config = fence_registry.get_fence(source_id)
    assert config is not None
    assert config.type == "zone"
    assert config.loitering_duration == 10.0
    print("[PASS] Setup zone with 10s loitering threshold passed.")
    
    # Test F: Existing restricted-zone intrusion still works immediately
    # Track 101 enters zone (normalized bbox: [0.3, 0.3, 0.5, 0.7])
    intrusion_ev = fence_registry.check_intrusion(
        source_id=source_id,
        track_id=101,
        bbox_norm=(0.3, 0.3, 0.5, 0.7),
        frame_width=1000,
        frame_height=1000
    )
    assert intrusion_ev == "zone_intrusion", f"Expected zone_intrusion, got {intrusion_ev}"
    print("[PASS] Test F: Immediate Restricted Zone Intrusion alert works as before.")
    
    # Set Track 101 as UNKNOWN_PERSON in face_worker
    face_worker._track_identities[(source_id, 101)] = {
        "source_id": source_id,
        "track_id": 101,
        "status": "UNKNOWN_PERSON",
        "name": "Unknown Person",
        "role": "Unrecognized Subject",
        "confidence": 0.35,
    }
    
    # Test A: Unknown person < threshold -> no loitering alert
    res_2s = fence_registry.check_loitering(source_id, 101, current_timestamp_sec=2.0, is_person=True)
    assert res_2s is None, f"Expected None at 2s, got {res_2s}"
    res_8s = fence_registry.check_loitering(source_id, 101, current_timestamp_sec=8.0, is_person=True)
    assert res_8s is None, f"Expected None at 8s (elapsed 6s < 10s), got {res_8s}"
    print("[PASS] Test A: Unknown person < threshold (elapsed 6s < 10s) generates NO alert.")
    
    # Test B: Unknown person >= threshold -> exactly ONE loitering alert
    res_12s = fence_registry.check_loitering(source_id, 101, current_timestamp_sec=12.5, is_person=True)
    assert res_12s is not None, "Expected loitering alert at 12.5s (elapsed 10.5s >= 10s)"
    assert res_12s["threshold"] == 10.0
    assert res_12s["duration"] >= 10.0
    print(f"[PASS] Test B1: Loitering alert triggered at {res_12s['duration']}s dwell time.")
    
    # Check that subsequent frames do NOT re-alert (single alert per continuous stay)
    res_13s = fence_registry.check_loitering(source_id, 101, current_timestamp_sec=13.0, is_person=True)
    assert res_13s is None, "Expected deduplication (no duplicate alert in same stay)"
    res_20s = fence_registry.check_loitering(source_id, 101, current_timestamp_sec=20.0, is_person=True)
    assert res_20s is None, "Expected deduplication at 20s"
    print("[PASS] Test B2: Exactly ONE alert generated for continuous stay (no duplicates).")
    
    # Test C: Known person inside zone for longer than threshold -> NO loitering alert (exempt)
    # Track 202 enters zone
    fence_registry.check_intrusion(source_id, 202, (0.4, 0.4, 0.6, 0.8), 1000, 1000)
    face_worker._track_identities[(source_id, 202)] = {
        "source_id": source_id,
        "track_id": 202,
        "status": "KNOWN_PERSON",
        "name": "Capt. Sharma",
        "role": "Army Personnel",
        "confidence": 0.92,
    }
    # Check at 0s, 10s, 30s, 100s
    res_c0 = fence_registry.check_loitering(source_id, 202, current_timestamp_sec=1.0, is_person=True)
    res_c10 = fence_registry.check_loitering(source_id, 202, current_timestamp_sec=15.0, is_person=True)
    res_c30 = fence_registry.check_loitering(source_id, 202, current_timestamp_sec=45.0, is_person=True)
    assert res_c0 is None and res_c10 is None and res_c30 is None
    print("[PASS] Test C: KNOWN_PERSON (Authorized military) inside zone for 45s is 100% EXEMPT (0 alerts).")
    
    # Test D: Unknown person exits before threshold and re-enters -> timer resets
    # Track 303 enters at t=50.0
    fence_registry.check_intrusion(source_id, 303, (0.3, 0.3, 0.5, 0.7), 1000, 1000)
    face_worker._track_identities[(source_id, 303)] = {
        "source_id": source_id,
        "track_id": 303,
        "status": "UNKNOWN_PERSON",
        "name": "Unknown Person",
    }
    fence_registry.check_loitering(source_id, 303, current_timestamp_sec=50.0, is_person=True)
    # At t=56.0 (elapsed 6s < 10s), target exits the zone (bbox moved to 0.05, 0.05)
    fence_registry.check_intrusion(source_id, 303, (0.01, 0.01, 0.05, 0.05), 1000, 1000)
    fence_registry.cleanup_exited_tracks(source_id, {101, 202})  # 303 exited
    
    # Now Track 303 re-enters at t=85.0
    fence_registry.check_intrusion(source_id, 303, (0.3, 0.3, 0.5, 0.7), 1000, 1000)
    res_re_85 = fence_registry.check_loitering(source_id, 303, current_timestamp_sec=85.0, is_person=True)
    assert res_re_85 is None, "Expected None at 85s (fresh re-entry start)"
    res_re_90 = fence_registry.check_loitering(source_id, 303, current_timestamp_sec=90.0, is_person=True)
    assert res_re_90 is None, "Expected None at 90s (elapsed 5s < 10s)"
    res_re_96 = fence_registry.check_loitering(source_id, 303, current_timestamp_sec=96.0, is_person=True)
    assert res_re_96 is not None, "Expected alert at 96s (elapsed 11s from re-entry >= 10s)"
    assert res_re_96["duration"] == 11.0
    print("[PASS] Test D: Unknown person exit resets timer; re-entry starts fresh from 0s and alerts properly.")
    
    # Test E: Loitering Off -> no loitering alert
    source_id_off = "cam_off"
    fence_registry.set_fence(source_id_off, "zone", polygon_points, loitering_duration=None)
    fence_registry.check_intrusion(source_id_off, 404, (0.3, 0.3, 0.5, 0.7), 1000, 1000)
    res_off = fence_registry.check_loitering(source_id_off, 404, current_timestamp_sec=500.0, is_person=True)
    assert res_off is None
    print("[PASS] Test E: Loitering Off / Disabled produces 0 loitering alerts even after 500s.")
    
    print("\n=== ALL LOITERING TESTS PASSED PERFECTLY ===")

if __name__ == "__main__":
    test_loitering_suite()
