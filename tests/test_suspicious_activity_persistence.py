"""
Automated Verification Suite for Suspicious Activity Backend Persistence Integration
===================================================================================
Covers all 14 required test cases for Step 6A:
  1. RUNNING event is persisted to threat_alerts and detection_events.
  2. CRAWLING event is persisted to threat_alerts and detection_events.
  3. THROWING event is persisted to threat_alerts and detection_events.
  4. source_id is persisted correctly in both tables.
  5. person track_id is persisted correctly in both tables.
  6. THROWING object_track_id is preserved in extra_metadata and description.
  7. timestamp_sec is preserved correctly.
  8. confidence / score is preserved where supported.
  9. subtype is distinguishable (RUNNING, CRAWLING, THROWING).
  10. duplicate event does not create unintended duplicate persistence.
  11. DB failure does not crash surveillance processing or frame callback.
  12. malformed / incomplete event is handled safely without crashing.
  13. existing unrelated event persistence (intrusions, standard detections) still works.
  14. existing database startup / schema behavior remains intact.
"""

import json
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Bootstrap paths
ROOT = Path(__file__).resolve().parent.parent if Path(__file__).resolve().parent.name == "tests" else Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from app.db.database import get_db_context, init_db
from app.db.models import DetectionEventModel, ThreatAlertModel, IntrusionEventModel
from app.services.db_service import db_service
from ai_engine.modules.behavior.suspicious import (
    SuspiciousActivityEngine,
    SuspiciousActivityEvent,
)
from ai_engine.modules.behavior.suspicious.suspicious_engine import (
    ACTIVITY_RUNNING,
    ACTIVITY_CRAWLING,
    ACTIVITY_THROWING,
)
from ai_engine.modules.detection.yolo_detector import FrameDetections, DetectionResult


class TestSuspiciousActivityPersistence(unittest.TestCase):
    """Test suite verifying backend database persistence for SuspiciousActivityEvent."""

    @classmethod
    def setUpClass(cls):
        """Ensure database tables are initialized before tests."""
        init_db()

    def _wait_for_db(self, delay: float = 0.5):
        """Wait briefly for the background DB worker to process tasks."""
        time.sleep(delay)

    def test_1_running_persisted(self):
        """Test 1: RUNNING event is persisted to threat_alerts and detection_events."""
        source_id = f"test_cam_run_{int(time.time() * 1000) % 100000}"
        event = SuspiciousActivityEvent(
            activity=ACTIVITY_RUNNING,
            source_id=source_id,
            track_id=101,
            timestamp_sec=5.25,
            confidence=0.92,
            score=0.95,
            metadata={"normalized_speed": 2.4, "body_height_px": 180.0},
        )

        res = db_service.enqueue_suspicious_activity(event=event)
        self.assertIsNotNone(res)
        alert_id, event_id = res
        self._wait_for_db()

        with get_db_context() as db:
            alt = db.query(ThreatAlertModel).filter_by(alert_id=alert_id).first()
            self.assertIsNotNone(alt, "ThreatAlertModel record not found for RUNNING")
            self.assertEqual(alt.alert_type, "SUSPICIOUS ACTIVITY — RUNNING")
            self.assertEqual(alt.threat_level, "HIGH")
            self.assertEqual(alt.severity, "High")

            evt = db.query(DetectionEventModel).filter_by(event_id=event_id).first()
            self.assertIsNotNone(evt, "DetectionEventModel record not found for RUNNING")
            self.assertEqual(evt.event_type, "SUSPICIOUS_ACTIVITY")
            self.assertEqual(evt.threat_level, "HIGH")
            self.assertIn("RUNNING", evt.description)

    def test_2_crawling_persisted(self):
        """Test 2: CRAWLING event is persisted to threat_alerts and detection_events."""
        source_id = f"test_cam_crawl_{int(time.time() * 1000) % 100000}"
        event = SuspiciousActivityEvent(
            activity=ACTIVITY_CRAWLING,
            source_id=source_id,
            track_id=102,
            timestamp_sec=8.40,
            confidence=0.88,
            score=0.90,
            metadata={"aspect_ratio": 1.45, "relative_height": 0.42},
        )

        res = db_service.enqueue_suspicious_activity(event=event)
        self.assertIsNotNone(res)
        alert_id, event_id = res
        self._wait_for_db()

        with get_db_context() as db:
            alt = db.query(ThreatAlertModel).filter_by(alert_id=alert_id).first()
            self.assertIsNotNone(alt)
            self.assertEqual(alt.alert_type, "SUSPICIOUS ACTIVITY — CRAWLING")
            self.assertEqual(alt.threat_level, "CRITICAL")
            self.assertEqual(alt.severity, "Critical")

            evt = db.query(DetectionEventModel).filter_by(event_id=event_id).first()
            self.assertIsNotNone(evt)
            self.assertEqual(evt.event_type, "SUSPICIOUS_ACTIVITY")
            self.assertEqual(evt.threat_level, "CRITICAL")
            self.assertIn("CRAWLING", evt.description)

    def test_3_throwing_persisted(self):
        """Test 3: THROWING event is persisted to threat_alerts and detection_events."""
        source_id = f"test_cam_throw_{int(time.time() * 1000) % 100000}"
        event = SuspiciousActivityEvent(
            activity=ACTIVITY_THROWING,
            source_id=source_id,
            track_id=103,
            object_track_id=205,
            timestamp_sec=12.10,
            confidence=0.94,
            score=0.98,
            metadata={"launch_speed": 3.2, "object_class": "backpack"},
        )

        res = db_service.enqueue_suspicious_activity(event=event)
        self.assertIsNotNone(res)
        alert_id, event_id = res
        self._wait_for_db()

        with get_db_context() as db:
            alt = db.query(ThreatAlertModel).filter_by(alert_id=alert_id).first()
            self.assertIsNotNone(alt)
            self.assertEqual(alt.alert_type, "SUSPICIOUS ACTIVITY — THROWING")
            self.assertEqual(alt.threat_level, "CRITICAL")
            self.assertEqual(alt.severity, "Critical")

            evt = db.query(DetectionEventModel).filter_by(event_id=event_id).first()
            self.assertIsNotNone(evt)
            self.assertEqual(evt.event_type, "SUSPICIOUS_ACTIVITY")
            self.assertIn("205", evt.description)

    def test_4_source_id_preserved(self):
        """Test 4: source_id is persisted correctly in both tables."""
        source_id = f"sector_7_cam_alpha_{int(time.time() * 1000) % 100000}"
        event = SuspiciousActivityEvent(
            activity=ACTIVITY_RUNNING,
            source_id=source_id,
            track_id=104,
            timestamp_sec=2.0,
            confidence=0.90,
            metadata={},
        )
        alert_id, event_id = db_service.enqueue_suspicious_activity(event=event)
        self._wait_for_db()

        with get_db_context() as db:
            alt = db.query(ThreatAlertModel).filter_by(alert_id=alert_id).first()
            evt = db.query(DetectionEventModel).filter_by(event_id=event_id).first()
            self.assertEqual(alt.source_id, source_id)
            self.assertEqual(evt.source_id, source_id)

    def test_5_track_id_preserved(self):
        """Test 5: person track_id is persisted correctly in both tables."""
        source_id = f"test_cam_tid_{int(time.time() * 1000) % 100000}"
        target_track_id = 777
        event = SuspiciousActivityEvent(
            activity=ACTIVITY_CRAWLING,
            source_id=source_id,
            track_id=target_track_id,
            timestamp_sec=3.5,
            confidence=0.85,
            metadata={},
        )
        alert_id, event_id = db_service.enqueue_suspicious_activity(event=event)
        self._wait_for_db()

        with get_db_context() as db:
            alt = db.query(ThreatAlertModel).filter_by(alert_id=alert_id).first()
            evt = db.query(DetectionEventModel).filter_by(event_id=event_id).first()
            self.assertEqual(alt.track_id, target_track_id)
            self.assertEqual(evt.track_id, target_track_id)

    def test_6_throwing_object_track_id_preserved(self):
        """Test 6: THROWING object_track_id is preserved in extra_metadata and description."""
        source_id = f"test_cam_obj_{int(time.time() * 1000) % 100000}"
        event = SuspiciousActivityEvent(
            activity=ACTIVITY_THROWING,
            source_id=source_id,
            track_id=50,
            object_track_id=99,
            timestamp_sec=4.0,
            confidence=0.91,
            metadata={"object_class": "bottle"},
        )
        alert_id, event_id = db_service.enqueue_suspicious_activity(event=event)
        self._wait_for_db()

        with get_db_context() as db:
            evt = db.query(DetectionEventModel).filter_by(event_id=event_id).first()
            self.assertIsNotNone(evt)
            self.assertIn("OBJECT #99", evt.description)
            self.assertIsNotNone(evt.extra_metadata)
            meta = json.loads(evt.extra_metadata)
            self.assertEqual(meta["object_track_id"], 99)
            self.assertEqual(meta["activity_subtype"], "THROWING")

    def test_7_timestamp_preserved(self):
        """Test 7: timestamp_sec is preserved correctly in DetectionEventModel."""
        source_id = f"test_cam_ts_{int(time.time() * 1000) % 100000}"
        t_sec = 42.125
        event = SuspiciousActivityEvent(
            activity=ACTIVITY_RUNNING,
            source_id=source_id,
            track_id=12,
            timestamp_sec=t_sec,
            confidence=0.88,
            metadata={},
        )
        _, event_id = db_service.enqueue_suspicious_activity(event=event)
        self._wait_for_db()

        with get_db_context() as db:
            evt = db.query(DetectionEventModel).filter_by(event_id=event_id).first()
            self.assertAlmostEqual(evt.timestamp_sec, t_sec, places=2)

    def test_8_confidence_score_preserved(self):
        """Test 8: confidence and score are preserved where supported."""
        source_id = f"test_cam_conf_{int(time.time() * 1000) % 100000}"
        event = SuspiciousActivityEvent(
            activity=ACTIVITY_CRAWLING,
            source_id=source_id,
            track_id=14,
            timestamp_sec=6.0,
            confidence=0.8765,
            score=0.9321,
            metadata={"speed": 0.5},
        )
        alert_id, event_id = db_service.enqueue_suspicious_activity(event=event)
        self._wait_for_db()

        with get_db_context() as db:
            alt = db.query(ThreatAlertModel).filter_by(alert_id=alert_id).first()
            evt = db.query(DetectionEventModel).filter_by(event_id=event_id).first()
            self.assertAlmostEqual(alt.confidence, 0.8765, places=3)
            self.assertEqual(alt.confidence_pct, 88)
            self.assertAlmostEqual(evt.confidence, 0.8765, places=3)
            meta = json.loads(evt.extra_metadata)
            self.assertAlmostEqual(meta["score"], 0.9321, places=3)

    def test_9_subtype_distinguishable(self):
        """Test 9: subtype is distinguishable (RUNNING, CRAWLING, THROWING) in queries."""
        source_id = f"test_cam_subtypes_{int(time.time() * 1000) % 100000}"
        for act in (ACTIVITY_RUNNING, ACTIVITY_CRAWLING, ACTIVITY_THROWING):
            ev = SuspiciousActivityEvent(
                activity=act,
                source_id=source_id,
                track_id=20,
                timestamp_sec=1.0,
                confidence=0.85,
                metadata={},
            )
            db_service.enqueue_suspicious_activity(event=ev)

        self._wait_for_db(0.8)

        with get_db_context() as db:
            alerts = db.query(ThreatAlertModel).filter_by(source_id=source_id).all()
            alert_types = {a.alert_type for a in alerts}
            self.assertIn("SUSPICIOUS ACTIVITY — RUNNING", alert_types)
            self.assertIn("SUSPICIOUS ACTIVITY — CRAWLING", alert_types)
            self.assertIn("SUSPICIOUS ACTIVITY — THROWING", alert_types)

            events = db.query(DetectionEventModel).filter_by(source_id=source_id).all()
            subtypes = {json.loads(e.extra_metadata)["activity_subtype"] for e in events}
            self.assertIn("RUNNING", subtypes)
            self.assertIn("CRAWLING", subtypes)
            self.assertIn("THROWING", subtypes)

    def test_10_duplicate_event_does_not_create_unintended_duplicate_persistence(self):
        """Test 10: continuous frames of the same activity episode produce only one persistence call."""
        engine = SuspiciousActivityEngine()
        source_id = f"test_cam_dedup_{int(time.time() * 1000) % 100000}"

        persisted_events = []
        mock_enqueue = MagicMock(side_effect=lambda **kw: persisted_events.append(kw) or ("alt_mock", "evt_mock"))

        # Simulate 10 frames of a running person with steady high speed (120 px/s = 2.4 body_heights/s)
        with patch.object(db_service, "enqueue_suspicious_activity", mock_enqueue):
            for i in range(10):
                t = i * 0.1
                x_pos = 100 + int(i * 12)
                det = DetectionResult(
                    track_id=1,
                    class_id=0,
                    class_name="person",
                    confidence=0.85,
                    x1=x_pos,
                    y1=100,
                    x2=x_pos + 30,
                    y2=150,
                )
                fd = FrameDetections(
                    frame_index=i,
                    timestamp_sec=t,
                    detections=[det],
                    frame_width=640,
                    frame_height=480,
                )
                susp_events = engine.process_frame(source_id, fd, t, i)
                for s_ev in susp_events:
                    db_service.enqueue_suspicious_activity(event=s_ev)

        # The engine confirms once on qualification and deduplicates continuous frames
        self.assertEqual(len(persisted_events), 1, f"Expected exactly 1 persistence call, got {len(persisted_events)}")

    def test_11_db_failure_does_not_crash_surveillance_processing(self):
        """Test 11: DB failure does not crash surveillance processing or frame callback."""
        source_id = f"test_cam_fail_{int(time.time() * 1000) % 100000}"
        event = SuspiciousActivityEvent(
            activity=ACTIVITY_RUNNING,
            source_id=source_id,
            track_id=5,
            timestamp_sec=1.0,
            confidence=0.9,
            metadata={},
        )

        # Simulate catastrophic exception inside enqueue
        with patch.object(db_service, "enqueue_threat_alert", side_effect=RuntimeError("Simulated DB disk failure")):
            res = db_service.enqueue_suspicious_activity(event=event)
            # Must return None safely without propagating exception
            self.assertIsNone(res)

        # Subsequent processing must continue unaffected
        res2 = db_service.enqueue_suspicious_activity(event=event)
        self.assertIsNotNone(res2)

    def test_12_malformed_incomplete_event_handled_safely(self):
        """Test 12: malformed/incomplete event is handled safely without crashing."""
        # None source_id
        res1 = db_service.enqueue_suspicious_activity(source_id=None, activity="RUNNING", track_id=1)
        self.assertIsNone(res1)

        # None track_id
        res2 = db_service.enqueue_suspicious_activity(source_id="cam_01", activity="RUNNING", track_id=None)
        self.assertIsNone(res2)

        # Empty activity
        res3 = db_service.enqueue_suspicious_activity(source_id="cam_01", activity="", track_id=1)
        self.assertIsNone(res3)

        # Empty event object
        res4 = db_service.enqueue_suspicious_activity(event=object())
        self.assertIsNone(res4)

    def test_13_existing_unrelated_event_persistence_still_works(self):
        """Test 13: existing unrelated event persistence (standard detections, intrusions) still works."""
        source_id = f"test_cam_unrelated_{int(time.time() * 1000) % 100000}"

        # Standard detection event
        evt_id = db_service.enqueue_detection_event(
            source_id=source_id,
            event_type="Person Movement Detected",
            track_id=10,
            confidence=0.85,
            timestamp_sec=3.0,
        )
        self.assertIsNotNone(evt_id)

        # Standard intrusion event
        intr_id = db_service.enqueue_intrusion_event(
            source_id=source_id,
            event_type="zone_intrusion",
            track_id=10,
            severity="Critical",
        )
        self.assertIsNotNone(intr_id)

        self._wait_for_db()

        with get_db_context() as db:
            evt = db.query(DetectionEventModel).filter_by(event_id=evt_id).first()
            self.assertIsNotNone(evt)
            self.assertEqual(evt.event_type, "Person Movement Detected")

            intr = db.query(IntrusionEventModel).filter_by(intrusion_id=intr_id).first()
            self.assertIsNotNone(intr)
            self.assertEqual(intr.event_type, "zone_intrusion")

    def test_14_existing_database_startup_schema_behavior_still_works(self):
        """Test 14: existing database startup and schema behavior remains intact."""
        # Re-running init_db should be idempotent
        init_db()
        with get_db_context() as db:
            # Query all major tables
            alerts_count = db.query(ThreatAlertModel).count()
            events_count = db.query(DetectionEventModel).count()
            self.assertGreaterEqual(alerts_count, 0)
            self.assertGreaterEqual(events_count, 0)


def run_all_tests():
    print("==================================================")
    print("RUNNING SUSPICIOUS ACTIVITY PERSISTENCE TESTS")
    print("==================================================")
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSuspiciousActivityPersistence)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    print("==================================================")
    print(f"RESULTS: {result.testsRun} run, {len(result.failures)} failures, {len(result.errors)} errors")
    print("==================================================")
    if not result.wasSuccessful():
        raise RuntimeError("Persistence tests failed!")
    return result.testsRun


if __name__ == "__main__":
    run_all_tests()
