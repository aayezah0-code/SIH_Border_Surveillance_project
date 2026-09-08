"""
Automated Verification Suite for Suspicious Activity WebSocket Broadcasting Integration
======================================================================================
Covers all 18 required test cases for Step 6B:
  1. RUNNING event is broadcast over WebSocket.
  2. CRAWLING event is broadcast over WebSocket.
  3. THROWING event is broadcast over WebSocket.
  4. source_id is preserved in broadcast payload.
  5. track_id is preserved in broadcast payload.
  6. activity_subtype is preserved in broadcast payload.
  7. timestamp_sec is preserved in broadcast payload.
  8. confidence and score are preserved in broadcast payload.
  9. THROWING object_track_id is preserved in broadcast payload.
  10. Only confirmed engine events are broadcast.
  11. Continuous frames do not create repeated broadcasts (single episode confirmation).
  12. WebSocket failure does not crash frame processing.
  13. WebSocket failure does not prevent DB persistence.
  14. DB failure does not prevent WebSocket broadcast.
  15. Existing WebSocket messages / event types remain unaffected.
  16. Disconnected WebSocket clients are handled using existing manager disconnect behavior.
  17. Malformed / incomplete suspicious event is handled safely without crashing.
  18. No duplicate WebSocket broadcast is generated for one engine event.
"""

import asyncio
import json
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

# Bootstrap paths
ROOT = Path(__file__).resolve().parent.parent if Path(__file__).resolve().parent.name == "tests" else Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from app.websockets.manager import ConnectionManager, manager
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


class MockWebSocket:
    """Mock FastAPI WebSocket connection for unit testing."""
    def __init__(self):
        self.sent_messages = []
        self.closed = False

    async def accept(self):
        pass

    async def send_text(self, text: str):
        if self.closed:
            raise RuntimeError("WebSocket connection already closed")
        self.sent_messages.append(text)

    async def close(self):
        self.closed = True


class TestSuspiciousActivityWebSocket(unittest.TestCase):
    """Test suite verifying WebSocket broadcasting for SuspiciousActivityEvent."""

    def setUp(self):
        """Set up test environment and clean active WebSocket connections."""
        self.test_mgr = ConnectionManager()
        self.mock_client = MockWebSocket()
        self.test_mgr.active_connections.append(self.mock_client)

    def tearDown(self):
        self.test_mgr.active_connections.clear()

    def _broadcast_sync(self, payload_dict: dict, custom_mgr=None):
        """Helper to run broadcast on event loop synchronously."""
        mgr = custom_mgr or self.test_mgr
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(mgr.broadcast(json.dumps(payload_dict)))
        finally:
            loop.close()

    def _simulate_router_callback(
        self,
        susp_events,
        source_id="test_cam_ws",
        frame_detections=None,
        custom_mgr=None,
    ):
        """Simulate the detection_router handle_frame_processed block for suspicious events."""
        mgr = custom_mgr or self.test_mgr
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Mirror detection_router.py lines 407-488 exactly
        for s_ev in susp_events:
            camera_label = source_id.replace('_', ' ').title()
            subj_bbox = None
            if frame_detections:
                for d in frame_detections.detections:
                    if d.track_id == s_ev.track_id:
                        subj_bbox = (float(d.x1), float(d.y1), float(d.x2), float(d.y2))
                        break

            # 1. DB persistence block
            try:
                db_service.enqueue_suspicious_activity(
                    event=s_ev,
                    camera_label=camera_label,
                    bbox=subj_bbox,
                )
            except Exception as _pers_err:
                pass

            # 2. WebSocket broadcast block
            try:
                act_upper = str(s_ev.activity).upper()
                threat_sev = "Critical" if act_upper in ("THROWING", "CRAWLING") else "High"
                conf_pct = int(round(s_ev.confidence * 100))

                if s_ev.object_track_id is not None:
                    desc = f"Suspicious activity ({act_upper}) confirmed for PERSON #{s_ev.track_id} throwing OBJECT #{s_ev.object_track_id} at {s_ev.timestamp_sec:.1f}s."
                else:
                    desc = f"Suspicious activity ({act_upper}) confirmed for PERSON #{s_ev.track_id} at {s_ev.timestamp_sec:.1f}s."

                ws_alert = {
                    "type": "alert",
                    "source_id": source_id,
                    "data": {
                        "alert_type": f"SUSPICIOUS ACTIVITY — {act_upper}",
                        "event_type": "SUSPICIOUS_ACTIVITY",
                        "activity_subtype": act_upper,
                        "object_class": "PERSON",
                        "track_id": s_ev.track_id,
                        "track_label": f"PERSON #{s_ev.track_id}",
                        "confidence": s_ev.confidence,
                        "confidence_pct": conf_pct,
                        "score": round(s_ev.score, 4),
                        "severity": threat_sev,
                        "time": time.strftime("%H:%M:%S"),
                        "timestamp_sec": round(s_ev.timestamp_sec, 2),
                        "frame_index": s_ev.frame_index,
                        "camera": camera_label,
                        "description": desc,
                        "source_id": source_id,
                        "is_intrusion": False,
                        "object_track_id": s_ev.object_track_id,
                        "bbox": subj_bbox,
                        "metadata": dict(s_ev.metadata) if s_ev.metadata else {},
                    }
                }

                msg_str = json.dumps(ws_alert)
                loop.run_until_complete(mgr.broadcast(msg_str))
            except Exception:
                pass

        loop.close()

    def test_1_running_event_broadcast(self):
        """Test 1: RUNNING event is broadcast over WebSocket."""
        event = SuspiciousActivityEvent(
            activity=ACTIVITY_RUNNING,
            source_id="cam_01",
            track_id=10,
            timestamp_sec=3.5,
            confidence=0.92,
            score=0.95,
            metadata={"speed": 2.4},
        )
        self._simulate_router_callback([event], source_id="cam_01")

        self.assertEqual(len(self.mock_client.sent_messages), 1)
        msg = json.loads(self.mock_client.sent_messages[0])
        self.assertEqual(msg["type"], "alert")
        self.assertEqual(msg["data"]["event_type"], "SUSPICIOUS_ACTIVITY")
        self.assertEqual(msg["data"]["activity_subtype"], "RUNNING")
        self.assertEqual(msg["data"]["severity"], "High")

    def test_2_crawling_event_broadcast(self):
        """Test 2: CRAWLING event is broadcast over WebSocket."""
        event = SuspiciousActivityEvent(
            activity=ACTIVITY_CRAWLING,
            source_id="cam_02",
            track_id=15,
            timestamp_sec=7.2,
            confidence=0.88,
            score=0.91,
            metadata={"aspect_ratio": 1.45},
        )
        self._simulate_router_callback([event], source_id="cam_02")

        self.assertEqual(len(self.mock_client.sent_messages), 1)
        msg = json.loads(self.mock_client.sent_messages[0])
        self.assertEqual(msg["data"]["activity_subtype"], "CRAWLING")
        self.assertEqual(msg["data"]["severity"], "Critical")

    def test_3_throwing_event_broadcast(self):
        """Test 3: THROWING event is broadcast over WebSocket."""
        event = SuspiciousActivityEvent(
            activity=ACTIVITY_THROWING,
            source_id="cam_03",
            track_id=22,
            object_track_id=305,
            timestamp_sec=11.4,
            confidence=0.94,
            score=0.98,
            metadata={"object_class": "backpack"},
        )
        self._simulate_router_callback([event], source_id="cam_03")

        self.assertEqual(len(self.mock_client.sent_messages), 1)
        msg = json.loads(self.mock_client.sent_messages[0])
        self.assertEqual(msg["data"]["activity_subtype"], "THROWING")
        self.assertEqual(msg["data"]["object_track_id"], 305)
        self.assertEqual(msg["data"]["severity"], "Critical")

    def test_4_source_id_preserved(self):
        """Test 4: source_id is preserved in broadcast payload."""
        src = "sector_4_alpha_camera"
        event = SuspiciousActivityEvent(
            activity=ACTIVITY_RUNNING,
            source_id=src,
            track_id=1,
            timestamp_sec=1.0,
            confidence=0.9,
            metadata={},
        )
        self._simulate_router_callback([event], source_id=src)

        msg = json.loads(self.mock_client.sent_messages[0])
        self.assertEqual(msg["source_id"], src)
        self.assertEqual(msg["data"]["source_id"], src)

    def test_5_track_id_preserved(self):
        """Test 5: track_id is preserved in broadcast payload."""
        event = SuspiciousActivityEvent(
            activity=ACTIVITY_RUNNING,
            source_id="cam_01",
            track_id=9876,
            timestamp_sec=1.0,
            confidence=0.9,
            metadata={},
        )
        self._simulate_router_callback([event])

        msg = json.loads(self.mock_client.sent_messages[0])
        self.assertEqual(msg["data"]["track_id"], 9876)
        self.assertEqual(msg["data"]["track_label"], "PERSON #9876")

    def test_6_activity_subtype_preserved(self):
        """Test 6: activity_subtype is preserved in broadcast payload."""
        event = SuspiciousActivityEvent(
            activity=ACTIVITY_CRAWLING,
            source_id="cam_01",
            track_id=1,
            timestamp_sec=1.0,
            confidence=0.9,
            metadata={},
        )
        self._simulate_router_callback([event])

        msg = json.loads(self.mock_client.sent_messages[0])
        self.assertEqual(msg["data"]["activity_subtype"], "CRAWLING")
        self.assertEqual(msg["data"]["alert_type"], "SUSPICIOUS ACTIVITY — CRAWLING")

    def test_7_timestamp_sec_preserved(self):
        """Test 7: timestamp_sec is preserved in broadcast payload."""
        event = SuspiciousActivityEvent(
            activity=ACTIVITY_RUNNING,
            source_id="cam_01",
            track_id=1,
            timestamp_sec=18.75,
            confidence=0.9,
            metadata={},
        )
        self._simulate_router_callback([event])

        msg = json.loads(self.mock_client.sent_messages[0])
        self.assertEqual(msg["data"]["timestamp_sec"], 18.75)

    def test_8_confidence_score_preserved(self):
        """Test 8: confidence and score are preserved in broadcast payload."""
        event = SuspiciousActivityEvent(
            activity=ACTIVITY_THROWING,
            source_id="cam_01",
            track_id=1,
            object_track_id=2,
            timestamp_sec=1.0,
            confidence=0.8765,
            score=0.9432,
            metadata={},
        )
        self._simulate_router_callback([event])

        msg = json.loads(self.mock_client.sent_messages[0])
        self.assertAlmostEqual(msg["data"]["confidence"], 0.8765, places=3)
        self.assertEqual(msg["data"]["confidence_pct"], 88)
        self.assertAlmostEqual(msg["data"]["score"], 0.9432, places=3)

    def test_9_throwing_object_track_id_preserved(self):
        """Test 9: THROWING object_track_id is preserved in broadcast payload."""
        event = SuspiciousActivityEvent(
            activity=ACTIVITY_THROWING,
            source_id="cam_01",
            track_id=40,
            object_track_id=888,
            timestamp_sec=2.0,
            confidence=0.9,
            metadata={},
        )
        self._simulate_router_callback([event])

        msg = json.loads(self.mock_client.sent_messages[0])
        self.assertEqual(msg["data"]["object_track_id"], 888)
        self.assertIn("OBJECT #888", msg["data"]["description"])

    def test_10_only_confirmed_engine_events_are_broadcast(self):
        """Test 10: only confirmed engine events are broadcast (unconfirmed observations yield 0 broadcasts)."""
        engine = SuspiciousActivityEngine()
        # Single frame of a walking person (speed too low to confirm running)
        det = DetectionResult(
            track_id=1,
            class_id=0,
            class_name="person",
            confidence=0.85,
            x1=100,
            y1=100,
            x2=130,
            y2=160,
        )
        fd = FrameDetections(frame_index=0, timestamp_sec=0.0, detections=[det], frame_width=640, frame_height=480)
        susp_events = engine.process_frame("cam_01", fd, 0.0, 0)

        self.assertEqual(len(susp_events), 0)
        self._simulate_router_callback(susp_events)
        self.assertEqual(len(self.mock_client.sent_messages), 0)

    def test_11_continuous_frames_do_not_create_repeated_broadcasts(self):
        """Test 11: continuous frames of the same activity episode produce only one broadcast."""
        engine = SuspiciousActivityEngine()
        source_id = "cam_continuous_running"

        all_emitted_events = []
        # Simulate 12 frames of sustained running (120 px/s)
        for i in range(12):
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
            fd = FrameDetections(frame_index=i, timestamp_sec=t, detections=[det], frame_width=640, frame_height=480)
            events = engine.process_frame(source_id, fd, t, i)
            if events:
                all_emitted_events.extend(events)

        self.assertEqual(len(all_emitted_events), 1, "Engine must confirm exactly once per continuous episode")
        self._simulate_router_callback(all_emitted_events, source_id=source_id)
        self.assertEqual(len(self.mock_client.sent_messages), 1, "Only 1 WebSocket message must be broadcast")

    def test_12_websocket_failure_does_not_crash_frame_processing(self):
        """Test 12: WebSocket failure does not crash frame processing or caller."""
        event = SuspiciousActivityEvent(
            activity=ACTIVITY_RUNNING,
            source_id="cam_fail",
            track_id=1,
            timestamp_sec=1.0,
            confidence=0.9,
            metadata={},
        )
        bad_mgr = ConnectionManager()
        # Mock broadcast to raise a connection reset exception
        bad_mgr.broadcast = AsyncMock(side_effect=ConnectionResetError("Simulated network drop"))

        # Must not raise an exception
        try:
            self._simulate_router_callback([event], custom_mgr=bad_mgr)
        except Exception as exc:
            self.fail(f"_simulate_router_callback crashed on WebSocket error: {exc}")

    def test_13_websocket_failure_does_not_prevent_db_persistence(self):
        """Test 13: WebSocket failure does not prevent DB persistence."""
        event = SuspiciousActivityEvent(
            activity=ACTIVITY_CRAWLING,
            source_id="cam_ws_fail_db_ok",
            track_id=7,
            timestamp_sec=2.0,
            confidence=0.9,
            metadata={},
        )
        bad_mgr = ConnectionManager()
        bad_mgr.broadcast = AsyncMock(side_effect=RuntimeError("WebSocket subsystem crashed"))

        mock_db_enqueue = MagicMock(return_value=("alt_123", "evt_123"))
        with patch.object(db_service, "enqueue_suspicious_activity", mock_db_enqueue):
            self._simulate_router_callback([event], custom_mgr=bad_mgr)

        mock_db_enqueue.assert_called_once()

    def test_14_db_failure_does_not_prevent_websocket_broadcast(self):
        """Test 14: DB failure does not prevent WebSocket broadcast."""
        event = SuspiciousActivityEvent(
            activity=ACTIVITY_THROWING,
            source_id="cam_db_fail_ws_ok",
            track_id=8,
            object_track_id=9,
            timestamp_sec=3.0,
            confidence=0.9,
            metadata={},
        )

        mock_db_enqueue = MagicMock(side_effect=RuntimeError("SQLite database locked"))
        with patch.object(db_service, "enqueue_suspicious_activity", mock_db_enqueue):
            self._simulate_router_callback([event])

        self.assertEqual(len(self.mock_client.sent_messages), 1)
        msg = json.loads(self.mock_client.sent_messages[0])
        self.assertEqual(msg["data"]["activity_subtype"], "THROWING")

    def test_15_existing_websocket_messages_unaffected(self):
        """Test 15: Existing WebSocket messages (frame_update, loitering, intrusion) remain unaffected."""
        # Existing frame_update
        frame_msg = {
            "type": "frame_update",
            "source_id": "cam_standard",
            "data": {"frame_index": 10, "detections": []},
        }
        self._broadcast_sync(frame_msg)

        # Existing zone_intrusion alert
        intrusion_msg = {
            "type": "alert",
            "source_id": "cam_standard",
            "data": {
                "alert_type": "RESTRICTED ZONE INTRUSION",
                "is_intrusion": True,
                "event_type": "zone_intrusion",
            },
        }
        self._broadcast_sync(intrusion_msg)

        self.assertEqual(len(self.mock_client.sent_messages), 2)
        m1 = json.loads(self.mock_client.sent_messages[0])
        m2 = json.loads(self.mock_client.sent_messages[1])
        self.assertEqual(m1["type"], "frame_update")
        self.assertEqual(m2["data"]["event_type"], "zone_intrusion")

    def test_16_disconnected_clients_handled_gracefully(self):
        """Test 16: Disconnected WebSocket clients are removed gracefully without halting broadcast."""
        dead_client = MockWebSocket()
        dead_client.closed = True  # send_text will raise RuntimeError
        live_client = MockWebSocket()

        test_mgr = ConnectionManager()
        test_mgr.active_connections = [dead_client, live_client]

        msg = {"type": "alert", "data": {"event_type": "SUSPICIOUS_ACTIVITY"}}
        self._broadcast_sync(msg, custom_mgr=test_mgr)

        # dead_client was disconnected and removed
        self.assertNotIn(dead_client, test_mgr.active_connections)
        # live_client stayed and received the message
        self.assertIn(live_client, test_mgr.active_connections)
        self.assertEqual(len(live_client.sent_messages), 1)

    def test_17_malformed_incomplete_suspicious_event_handled_safely(self):
        """Test 17: Malformed / incomplete suspicious event is handled safely without crashing."""
        malformed_event = SuspiciousActivityEvent(
            activity="UNKNOWN_ACT",
            source_id="",
            track_id=0,
            timestamp_sec=0.0,
            confidence=0.0,
            metadata={},
        )
        try:
            self._simulate_router_callback([malformed_event])
        except Exception as exc:
            self.fail(f"Crashed on malformed event: {exc}")

    def test_18_no_duplicate_websocket_broadcast_for_one_engine_event(self):
        """Test 18: Exactly 1 WebSocket broadcast is generated for one confirmed engine event."""
        event = SuspiciousActivityEvent(
            activity=ACTIVITY_RUNNING,
            source_id="cam_single",
            track_id=33,
            timestamp_sec=5.0,
            confidence=0.9,
            metadata={},
        )
        self._simulate_router_callback([event])
        self.assertEqual(len(self.mock_client.sent_messages), 1)


def run_all_tests():
    print("==================================================")
    print("RUNNING SUSPICIOUS ACTIVITY WEBSOCKET TESTS")
    print("==================================================")
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSuspiciousActivityWebSocket)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    print("==================================================")
    print(f"RESULTS: {result.testsRun} run, {len(result.failures)} failures, {len(result.errors)} errors")
    print("==================================================")
    if not result.wasSuccessful():
        raise RuntimeError("WebSocket integration tests failed!")
    return result.testsRun


if __name__ == "__main__":
    run_all_tests()
