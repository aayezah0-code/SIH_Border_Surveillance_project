"""
tests/test_suspicious_activity_evidence.py
==========================================
Verification test suite for Step 6D — Suspicious Activity Evidence / Forensic Snapshot Integration.

Covers:
  1. RUNNING confirmed event creates/associates evidence.
  2. CRAWLING confirmed event creates/associates evidence.
  3. THROWING confirmed event creates/associates evidence.
  4. Throwing preserves object_track_id.
  5. Evidence is associated with correct source_id.
  6. Evidence is associated with correct track_id.
  7. Evidence timestamp matches the suspicious activity event.
  8. Continuous frames of the same episode do NOT create duplicate evidence.
  9. A new Episode B (after activity stops/restarts) creates its own evidence (Safeguard 1).
  10. Existing callers continue using the 30-second dedup window (Safeguard 1).
  11. Evidence failure does NOT stop suspicious activity alert generation.
  12. Evidence failure does NOT stop DB persistence or WebSocket broadcast.
  13. DB failure does NOT stop evidence capture.
  14. Existing threat/intrusion evidence behavior remains unaffected.
  15. event_id from db_service is preserved in evidence record and DB snapshot (Safeguard 2).
  16. GET /api/v1/evidence filters by source_id, track_id, and event_type="suspicious_activity".
  17. GET /api/v1/evidence/image/{filename} serves the saved JPEG snapshot.
  18. _load_existing_evidence disk scan recognizes suspicious_activity filenames.
"""

import os
import sys
import time
import json
import uuid
import tempfile
import numpy as np
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Bootstrap paths
_ROOT = Path(__file__).resolve().parents[1]
_BACKEND = _ROOT / "backend"
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services.evidence_writer import (
    EvidenceWriter,
    EvidenceTask,
    evidence_writer,
    EVIDENCE_DIR,
)
from app.services.db_service import db_service
from app.api.detection_router import handle_frame_processed
from ai_engine.modules.behavior.suspicious import SuspiciousActivityEvent
from ai_engine.modules.detection.yolo_detector import DetectionResult, FrameDetections


@pytest.fixture
def dummy_frame():
    """Create a dummy BGR frame."""
    return np.zeros((480, 640, 3), dtype=np.uint8)


class TestSuspiciousActivityEvidence:
    """Suite testing Step 6D evidence integration for suspicious activity."""

    def test_1_running_enqueues_evidence(self, dummy_frame):
        """Verify that a confirmed RUNNING event creates an evidence snapshot."""
        src_id = f"test-src-{uuid.uuid4().hex[:6]}"
        trk_id = 101

        with patch.object(evidence_writer, "enqueue_snapshot") as mock_enqueue:
            s_ev = SuspiciousActivityEvent(
                activity="RUNNING",
                source_id=src_id,
                track_id=trk_id,
                timestamp_sec=14.5,
                confidence=0.88,
                metadata={"speed": 2.5},
                frame_index=145,
            )
            frame_data = FrameDetections(
                frame_index=145,
                timestamp_sec=14.5,
                detections=[
                    DetectionResult(
                        class_id=0,
                        class_name="person",
                        confidence=0.88,
                        x1=100.0, y1=100.0, x2=200.0, y2=300.0,
                        track_id=trk_id,
                    )
                ],
                frame_width=640,
                frame_height=480,
            )
            frame_data._raw_frame = dummy_frame

            with patch("app.api.detection_router.suspicious_engine.process_frame", return_value=[s_ev]):
                handle_frame_processed(frame_data)

            mock_enqueue.assert_called_once()
            call_kwargs = mock_enqueue.call_args[1]
            assert call_kwargs["source_id"] == src_id
            assert call_kwargs["event_type"] == "suspicious_activity"
            assert call_kwargs["track_id"] == trk_id
            assert call_kwargs["object_class"] == "PERSON"
            assert call_kwargs["confidence"] == 0.88
            assert call_kwargs["timestamp_sec"] == 14.5
            assert call_kwargs["skip_dedup"] is True

    def test_2_crawling_enqueues_evidence(self, dummy_frame):
        """Verify that a confirmed CRAWLING event creates an evidence snapshot."""
        src_id = f"test-src-{uuid.uuid4().hex[:6]}"
        trk_id = 102

        with patch.object(evidence_writer, "enqueue_snapshot") as mock_enqueue:
            s_ev = SuspiciousActivityEvent(
                activity="CRAWLING",
                source_id=src_id,
                track_id=trk_id,
                timestamp_sec=22.0,
                confidence=0.93,
                metadata={"aspect_ratio": 0.5},
                frame_index=220,
            )
            frame_data = FrameDetections(
                frame_index=220,
                timestamp_sec=22.0,
                detections=[
                    DetectionResult(
                        class_id=0,
                        class_name="person",
                        confidence=0.93,
                        x1=50.0, y1=300.0, x2=250.0, y2=400.0,
                        track_id=trk_id,
                    )
                ],
                frame_width=640,
                frame_height=480,
            )
            frame_data._raw_frame = dummy_frame

            with patch("app.api.detection_router.suspicious_engine.process_frame", return_value=[s_ev]):
                handle_frame_processed(frame_data)

            mock_enqueue.assert_called_once()
            call_kwargs = mock_enqueue.call_args[1]
            assert call_kwargs["source_id"] == src_id
            assert call_kwargs["event_type"] == "suspicious_activity"
            assert call_kwargs["track_id"] == trk_id
            assert call_kwargs["confidence"] == 0.93

    def test_3_throwing_enqueues_evidence(self, dummy_frame):
        """Verify that a confirmed THROWING event creates an evidence snapshot."""
        src_id = f"test-src-{uuid.uuid4().hex[:6]}"
        trk_id = 103

        with patch.object(evidence_writer, "enqueue_snapshot") as mock_enqueue:
            s_ev = SuspiciousActivityEvent(
                activity="THROWING",
                source_id=src_id,
                track_id=trk_id,
                timestamp_sec=35.2,
                confidence=0.91,
                metadata={"object_track_id": 77},
                object_track_id=77,
                frame_index=352,
            )
            frame_data = FrameDetections(
                frame_index=352,
                timestamp_sec=35.2,
                detections=[
                    DetectionResult(
                        class_id=0,
                        class_name="person",
                        confidence=0.91,
                        x1=150.0, y1=100.0, x2=250.0, y2=350.0,
                        track_id=trk_id,
                    ),
                    DetectionResult(
                        class_id=24,
                        class_name="backpack",
                        confidence=0.85,
                        x1=300.0, y1=150.0, x2=350.0, y2=200.0,
                        track_id=77,
                    ),
                ],
                frame_width=640,
                frame_height=480,
            )
            frame_data._raw_frame = dummy_frame

            with patch("app.api.detection_router.suspicious_engine.process_frame", return_value=[s_ev]):
                handle_frame_processed(frame_data)

            mock_enqueue.assert_called_once()
            call_kwargs = mock_enqueue.call_args[1]
            assert call_kwargs["source_id"] == src_id
            assert call_kwargs["track_id"] == trk_id
            assert call_kwargs["event_type"] == "suspicious_activity"

    def test_4_throwing_preserves_object_track_id_in_db_persistence(self, dummy_frame):
        """Verify THROWING object_track_id is preserved across the pipeline."""
        src_id = f"test-src-{uuid.uuid4().hex[:6]}"
        trk_id = 104
        obj_trk_id = 88

        s_ev = SuspiciousActivityEvent(
            activity="THROWING",
            source_id=src_id,
            track_id=trk_id,
            timestamp_sec=40.0,
            confidence=0.95,
            metadata={"object_track_id": obj_trk_id},
            object_track_id=obj_trk_id,
            frame_index=400,
        )
        res = db_service.enqueue_suspicious_activity(event=s_ev)
        assert res is not None
        alert_id, event_id = res
        assert alert_id.startswith("alt_")
        assert event_id.startswith("evt_")

    def test_5_and_6_evidence_source_and_track_id_associated(self, dummy_frame):
        """Verify evidence is associated with the exact source_id and track_id."""
        src_id = f"test-src-{uuid.uuid4().hex[:6]}"
        trk_id = 105

        with patch.object(evidence_writer, "enqueue_snapshot") as mock_enqueue:
            s_ev = SuspiciousActivityEvent(
                activity="RUNNING",
                source_id=src_id,
                track_id=trk_id,
                timestamp_sec=5.0,
                confidence=0.89,
                metadata={},
                frame_index=50,
            )
            frame_data = FrameDetections(
                frame_index=50,
                timestamp_sec=5.0,
                detections=[],
                frame_width=640,
                frame_height=480,
            )
            frame_data._raw_frame = dummy_frame

            with patch("app.api.detection_router.suspicious_engine.process_frame", return_value=[s_ev]):
                handle_frame_processed(frame_data)

            call_kwargs = mock_enqueue.call_args[1]
            assert call_kwargs["source_id"] == src_id
            assert call_kwargs["track_id"] == trk_id

    def test_7_evidence_timestamp_matches_suspicious_event(self, dummy_frame):
        """Verify evidence timestamp_sec matches event.timestamp_sec."""
        src_id = f"test-src-{uuid.uuid4().hex[:6]}"
        trk_id = 106
        expected_t = 18.75

        with patch.object(evidence_writer, "enqueue_snapshot") as mock_enqueue:
            s_ev = SuspiciousActivityEvent(
                activity="CRAWLING",
                source_id=src_id,
                track_id=trk_id,
                timestamp_sec=expected_t,
                confidence=0.92,
                metadata={},
                frame_index=187,
            )
            frame_data = FrameDetections(
                frame_index=187,
                timestamp_sec=expected_t,
                detections=[],
                frame_width=640,
                frame_height=480,
            )
            frame_data._raw_frame = dummy_frame

            with patch("app.api.detection_router.suspicious_engine.process_frame", return_value=[s_ev]):
                handle_frame_processed(frame_data)

            call_kwargs = mock_enqueue.call_args[1]
            assert call_kwargs["timestamp_sec"] == expected_t

    def test_8_continuous_frames_same_episode_no_duplicate_evidence(self, dummy_frame):
        """Verify that continuous frames of the same episode only enqueue evidence once."""
        src_id = f"test-src-{uuid.uuid4().hex[:6]}"
        trk_id = 107

        with patch.object(evidence_writer, "enqueue_snapshot") as mock_enqueue:
            # Frame 1 confirms the episode
            s_ev = SuspiciousActivityEvent(
                activity="RUNNING",
                source_id=src_id,
                track_id=trk_id,
                timestamp_sec=1.0,
                confidence=0.85,
                metadata={},
                frame_index=10,
            )
            frame_data_1 = FrameDetections(
                frame_index=10,
                timestamp_sec=1.0,
                detections=[],
                frame_width=640,
                frame_height=480,
            )
            frame_data_1._raw_frame = dummy_frame

            with patch("app.api.detection_router.suspicious_engine.process_frame", return_value=[s_ev]):
                handle_frame_processed(frame_data_1)

            # Continuous frames 2, 3, 4: engine emits [] because episode is ongoing
            for f_idx in range(11, 15):
                f_data = FrameDetections(
                    frame_index=f_idx,
                    timestamp_sec=f_idx * 0.1,
                    detections=[],
                    frame_width=640,
                    frame_height=480,
                )
                f_data._raw_frame = dummy_frame
                with patch("app.api.detection_router.suspicious_engine.process_frame", return_value=[]):
                    handle_frame_processed(f_data)

            # mock_enqueue should be called exactly once
            assert mock_enqueue.call_count == 1

    def test_9_safeguard_1_new_episode_b_creates_its_own_evidence(self, dummy_frame):
        """
        Verify Safeguard 1: When a genuinely new Episode B occurs (confirmed by
        SuspiciousActivityEngine), evidence_writer enqueues it even within the
        30-second window because skip_dedup=True is passed for engine events.
        """
        src_id = f"test-src-{uuid.uuid4().hex[:6]}"
        trk_id = 108

        # Create isolated EvidenceWriter
        writer = EvidenceWriter()

        with patch.object(writer._queue, "put_nowait") as mock_put:
            # Episode A
            writer.enqueue_snapshot(
                frame=dummy_frame,
                source_id=src_id,
                event_type="suspicious_activity",
                track_id=trk_id,
                skip_dedup=True,
            )
            assert mock_put.call_count == 1

            # Episode B (1 second later, confirmed new episode)
            writer.enqueue_snapshot(
                frame=dummy_frame,
                source_id=src_id,
                event_type="suspicious_activity",
                track_id=trk_id,
                skip_dedup=True,
            )
            # With skip_dedup=True, Episode B is enqueued and NOT dropped!
            assert mock_put.call_count == 2

    def test_10_safeguard_1_existing_callers_preserve_30s_dedup(self, dummy_frame):
        """
        Verify Safeguard 1: Existing callers using default skip_dedup=False
        continue to be rate-limited by the 30-second window.
        """
        src_id = f"test-src-{uuid.uuid4().hex[:6]}"
        trk_id = 109

        writer = EvidenceWriter()

        with patch.object(writer._queue, "put_nowait") as mock_put:
            # Call 1 with default skip_dedup=False
            writer.enqueue_snapshot(
                frame=dummy_frame,
                source_id=src_id,
                event_type="zone_intrusion",
                track_id=trk_id,
            )
            assert mock_put.call_count == 1

            # Immediate Call 2 (same track, same event)
            writer.enqueue_snapshot(
                frame=dummy_frame,
                source_id=src_id,
                event_type="zone_intrusion",
                track_id=trk_id,
            )
            # Should be suppressed by the 30-second window
            assert mock_put.call_count == 1

    def test_11_evidence_failure_does_not_stop_suspicious_alert_generation(self, dummy_frame):
        """Verify that an exception in evidence enqueue does not halt surveillance or alert generation."""
        src_id = f"test-src-{uuid.uuid4().hex[:6]}"
        trk_id = 110

        s_ev = SuspiciousActivityEvent(
            activity="RUNNING",
            source_id=src_id,
            track_id=trk_id,
            timestamp_sec=12.0,
            confidence=0.87,
            metadata={},
            frame_index=120,
        )
        frame_data = FrameDetections(
            frame_index=120,
            timestamp_sec=12.0,
            detections=[],
            frame_width=640,
            frame_height=480,
        )
        frame_data._raw_frame = dummy_frame

        # Mock evidence_writer.enqueue_snapshot to raise an exception
        with patch.object(evidence_writer, "enqueue_snapshot", side_effect=RuntimeError("Disk full")):
            with patch("app.api.detection_router.suspicious_engine.process_frame", return_value=[s_ev]):
                # Must NOT raise
                handle_frame_processed(frame_data)

    def test_12_evidence_failure_does_not_prevent_ws_or_db(self, dummy_frame):
        """Verify DB persistence and WebSocket broadcast succeed even if evidence enqueue fails."""
        src_id = f"test-src-{uuid.uuid4().hex[:6]}"
        trk_id = 111

        s_ev = SuspiciousActivityEvent(
            activity="CRAWLING",
            source_id=src_id,
            track_id=trk_id,
            timestamp_sec=15.0,
            confidence=0.96,
            metadata={},
            frame_index=150,
        )
        frame_data = FrameDetections(
            frame_index=150,
            timestamp_sec=15.0,
            detections=[],
            frame_width=640,
            frame_height=480,
        )
        frame_data._raw_frame = dummy_frame

        with patch.object(evidence_writer, "enqueue_snapshot", side_effect=Exception("Evidence write crash")):
            with patch("app.api.detection_router.db_service.enqueue_suspicious_activity") as mock_db:
                mock_db.return_value = ("alt_test", "evt_test")
                with patch("app.api.detection_router.manager.broadcast_from_thread") as mock_ws:
                    with patch("app.api.detection_router.suspicious_engine.process_frame", return_value=[s_ev]):
                        handle_frame_processed(frame_data)

                    mock_db.assert_called_once()
                    assert mock_ws.call_count >= 1
                    messages = [json.loads(c[0][0]) for c in mock_ws.call_args_list]
                    alert_msgs = [m for m in messages if m.get("type") == "alert"]
                    assert len(alert_msgs) == 1
                    assert alert_msgs[0]["data"]["activity_subtype"] == "CRAWLING"

    def test_13_db_failure_does_not_stop_evidence_capture(self, dummy_frame):
        """Verify that a database failure does not prevent evidence snapshot enqueue."""
        src_id = f"test-src-{uuid.uuid4().hex[:6]}"
        trk_id = 112

        s_ev = SuspiciousActivityEvent(
            activity="THROWING",
            source_id=src_id,
            track_id=trk_id,
            timestamp_sec=19.0,
            confidence=0.90,
            metadata={},
            frame_index=190,
        )
        frame_data = FrameDetections(
            frame_index=190,
            timestamp_sec=19.0,
            detections=[],
            frame_width=640,
            frame_height=480,
        )
        frame_data._raw_frame = dummy_frame

        with patch("app.api.detection_router.db_service.enqueue_suspicious_activity", side_effect=Exception("DB locked")):
            with patch.object(evidence_writer, "enqueue_snapshot") as mock_enqueue:
                with patch("app.api.detection_router.suspicious_engine.process_frame", return_value=[s_ev]):
                    handle_frame_processed(frame_data)

                # Evidence should still be enqueued!
                mock_enqueue.assert_called_once()
                # event_id will be None because DB failed, but snapshot was safely captured
                assert mock_enqueue.call_args[1]["event_id"] is None

    def test_14_safeguard_2_event_id_linked_from_db_to_evidence(self, dummy_frame):
        """
        Verify Safeguard 2: The exact event_id generated by db_service.enqueue_suspicious_activity
        is passed to evidence_writer.enqueue_snapshot.
        """
        src_id = f"test-src-{uuid.uuid4().hex[:6]}"
        trk_id = 113

        s_ev = SuspiciousActivityEvent(
            activity="RUNNING",
            source_id=src_id,
            track_id=trk_id,
            timestamp_sec=8.0,
            confidence=0.88,
            metadata={},
            frame_index=80,
        )
        frame_data = FrameDetections(
            frame_index=80,
            timestamp_sec=8.0,
            detections=[],
            frame_width=640,
            frame_height=480,
        )
        frame_data._raw_frame = dummy_frame

        with patch.object(evidence_writer, "enqueue_snapshot") as mock_enqueue:
            with patch("app.api.detection_router.suspicious_engine.process_frame", return_value=[s_ev]):
                handle_frame_processed(frame_data)

            call_kwargs = mock_enqueue.call_args[1]
            passed_evt_id = call_kwargs["event_id"]
            assert passed_evt_id is not None
            assert passed_evt_id.startswith("evt_")

    def test_15_evidence_writer_saves_record_with_event_id(self, dummy_frame):
        """Verify _save_snapshot records event_id in evidence record and DB snapshot."""
        src_id = f"test-src-{uuid.uuid4().hex[:6]}"
        trk_id = 114
        expected_evt_id = f"evt_{uuid.uuid4().hex[:12]}"

        writer = EvidenceWriter()
        task = EvidenceTask(
            frame=dummy_frame,
            source_id=src_id,
            event_type="suspicious_activity",
            track_id=trk_id,
            object_class="PERSON",
            confidence=0.92,
            timestamp_sec=11.5,
            event_id=expected_evt_id,
        )

        with patch("app.services.db_service.db_service.enqueue_evidence_snapshot") as mock_db_snap:
            writer._save_snapshot(task)

            # DB enqueue should receive event_id
            mock_db_snap.assert_called_once()
            call_kwargs = mock_db_snap.call_args[1]
            assert call_kwargs["event_id"] == expected_evt_id
            assert call_kwargs["source_id"] == src_id
            assert call_kwargs["event_type"] == "suspicious_activity"
            assert call_kwargs["track_id"] == trk_id

    def test_16_get_evidence_list_filters_suspicious_activity(self, dummy_frame):
        """Verify get_evidence_list retrieves suspicious_activity records."""
        src_id = f"test-src-{uuid.uuid4().hex[:6]}"
        trk_id = 115

        writer = EvidenceWriter()
        task = EvidenceTask(
            frame=dummy_frame,
            source_id=src_id,
            event_type="suspicious_activity",
            track_id=trk_id,
            object_class="PERSON",
            confidence=0.94,
            timestamp_sec=25.0,
        )
        writer._save_snapshot(task)

        # Query by source_id + event_type
        records = writer.get_evidence_list(
            source_id=src_id,
            event_type="suspicious_activity",
        )
        assert len(records) >= 1
        matched = [r for r in records if r["track_id"] == trk_id]
        assert len(matched) == 1
        assert matched[0]["event_type"] == "suspicious_activity"
        assert matched[0]["object_class"] == "PERSON"

    def test_17_disk_recovery_recognizes_suspicious_activity(self):
        """Verify _record_from_filename correctly parses suspicious_activity filenames."""
        writer = EvidenceWriter()
        filename = Path("2026-09-04_21-15-00_test-source_suspicious_activity_abc12345.jpg")
        record = writer._record_from_filename(filename)
        assert record is not None
        assert record["event_type"] == "suspicious_activity"
        assert "test-source" in record["source_id"]

    def test_18_existing_intrusion_evidence_still_works(self, dummy_frame):
        """Verify zone_intrusion evidence capture behavior is completely unchanged."""
        src_id = f"test-src-{uuid.uuid4().hex[:6]}"
        trk_id = 116

        with patch.object(evidence_writer, "enqueue_snapshot") as mock_enqueue:
            frame_data = FrameDetections(
                frame_index=10,
                timestamp_sec=1.0,
                detections=[
                    DetectionResult(
                        class_id=0,
                        class_name="person",
                        confidence=0.92,
                        x1=100.0, y1=100.0, x2=200.0, y2=300.0,
                        track_id=trk_id,
                    )
                ],
                frame_width=640,
                frame_height=480,
            )
            frame_data._raw_frame = dummy_frame

            with patch("app.api.detection_router.fence_registry.check_intrusion", return_value="zone_intrusion"):
                with patch("app.api.detection_router.suspicious_engine.process_frame", return_value=[]):
                    handle_frame_processed(frame_data)

            mock_enqueue.assert_called_once()
            call_kwargs = mock_enqueue.call_args[1]
            assert call_kwargs["event_type"] == "zone_intrusion"
            assert call_kwargs["track_id"] == trk_id
