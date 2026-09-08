import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.services.detection_service import run_detection_on_video
from app.api.detection_router import handle_frame_processed, suspicious_engine
from ai_engine.modules.tracking.tracker_registry import tracker_registry

def test_video(filename, expected_act, label):
    source_id = Path(filename).stem
    tracker_registry.prepare_for_source(source_id)
    suspicious_engine.clear_source(source_id)
    
    collected_events = []
    def on_frame(fd):
        evs = handle_frame_processed(fd, source_id=source_id)
        if evs:
            for ev in evs:
                collected_events.append(ev)

    run_detection_on_video(
        filename=filename,
        max_frames=60,
        sample_rate=5,
        confidence=0.35,
        on_frame_processed=on_frame,
        source_id=source_id,
    )

    activities = [e.activity for e in collected_events]
    has_expected = expected_act in activities
    print(f"[{label}] Expected: {expected_act} | Emitted: {activities} | Success: {has_expected}")
    return has_expected, activities

if __name__ == "__main__":
    print("=== GOLDEN BASELINE NON-REGRESSION VERIFICATION ===")
    
    # Running test 1
    s1, a1 = test_video("f631aed7-39cb-498d-abfa-b3e3aaa3e595.mp4", "RUNNING", "running.mp4 (Known)")
    # Running test 2
    s2, a2 = test_video("3c328e96-4b11-4bb3-b78c-c588eac26b9a.mp4", "RUNNING", "running_test.mp4 (New 1)")
    # Running test 3
    s3, a3 = test_video("2bb13eb0-a0d0-4fc6-a60c-ef4117893b7f.mp4", "RUNNING", "running test2.mp4 (New 2)")
    # Crawling test 1
    s4, a4 = test_video("1878f2eb-ca3f-4083-ba22-1b0008918f02.mp4", "CRAWLING", "crawling.mp4 (Known)")

    assert s1 and s2 and s3, "Running regression failed!"
    assert s4, "Crawling regression failed!"
    # Mutual exclusion check
    assert "CRAWLING" not in a1 and "CRAWLING" not in a2 and "CRAWLING" not in a3, "False CRAWLING on runner!"
    assert "RUNNING" not in a4, "False RUNNING on crawler!"
    print("\nALL GOLDEN BASELINE NON-REGRESSION TESTS PASSED!")
