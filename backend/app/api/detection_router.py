"""
Detection API Router — Phase 4 + Phase 6 (ByteTrack)
------------------------------------------------------
Endpoints:
  GET  /api/v1/detection/status
       — Reports whether the YOLO model is loaded and ready.

  POST /api/v1/detection/analyze/{source_id}
       — Runs YOLO + ByteTrack tracking on the uploaded video for the given source.
         Returns per-frame detection results with persistent track IDs.

  GET  /api/v1/detection/results/{source_id}
       — Returns cached results for a previously analysed source.
         (Cache is in-memory; future phases will persist to DB.)
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, HTTPException, status

from app.services.video_service import get_source
from app.services.detection_service import (
    run_detection_on_video,
    run_detection_on_stream,
    detector_status,
)
import threading
import json
from datetime import datetime
from app.websockets.manager import manager

# Evidence capture service (non-blocking background writer)
from app.services.evidence_writer import evidence_writer

# Phase 6: per-source tracker deduplication registry
from ai_engine.modules.tracking.tracker_registry import tracker_registry

# Phase 7: virtual fence intrusion registry
from ai_engine.modules.behavior.virtual_fence import fence_registry

# Persistence service (non-blocking async queue)
from app.services.db_service import db_service

# Phase 10: Unified Suspicious Activity Engine
from ai_engine.modules.behavior.suspicious import (
    SuspiciousActivityEngine,
    SuspiciousActivityEvent,
)

logger = logging.getLogger(__name__)

# Thread-pool for running blocking YOLO inference without blocking the event loop
_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="yolo_worker")

# Module-level persistent suspicious activity engine instance
suspicious_engine = SuspiciousActivityEngine()

router = APIRouter(prefix="/api/v1/detection", tags=["Object Detection"])

# ── In-memory results cache  (source_id → results dict) ──────────────────────
# Phase 5+ will move this to a proper database.
_results_cache: dict[str, dict] = {}

# In-flight video analyses tracking (source_id -> asyncio.Task)
_active_video_analyses: dict[str, asyncio.Task] = {}

# Dictionary to hold threading.Event objects to stop RTSP processing loops
_rtsp_stop_events: dict[str, threading.Event] = {}
_rtsp_running_sources: set[str] = set()
_rtsp_futures: dict[str, asyncio.Future] = {}

async def stop_rtsp_detection(source_id: str):
    """Stop the continuous RTSP YOLO detection worker for a given source."""
    if source_id in _rtsp_stop_events:
        _rtsp_stop_events[source_id].set()
        _rtsp_stop_events.pop(source_id, None)
    
    # Phase 7 Fix: Properly await the future to release YOLO/tracker instance
    if source_id in _rtsp_futures:
        future = _rtsp_futures.pop(source_id)
        try:
            # Wait up to 3 seconds for the worker to finish the current frame
            await asyncio.wait_for(future, timeout=3.0)
        except asyncio.TimeoutError:
            logger.warning(f"RTSP worker for {source_id} timed out. Cancelling.")
            future.cancel()
        except Exception as e:
            logger.error(f"Error while waiting for RTSP worker {source_id} to stop: {e}")

    _rtsp_running_sources.discard(source_id)
    suspicious_engine.clear_source(source_id)
    logger.info("Stopped RTSP detection worker for source '%s'", source_id)


# ---------------------------------------------------------------------------
# GET /status
# ---------------------------------------------------------------------------

@router.get("/status")
def get_detector_status():
    """Return YOLO detector readiness and configuration."""
    return detector_status()


# ---------------------------------------------------------------------------
# POST /analyze/{source_id}
# ---------------------------------------------------------------------------



def handle_frame_processed(
    frame_data,
    source_id: str = "default_source",
    source = None,
    loop = None,
):
    """
    Called after each sampled frame is processed.
    Emits ONE WebSocket alert per unique tracked object (by track_id) to avoid
    flooding the Threat Alerts panel with the same object every frame.
    """
    susp_events = []
    try:
        # ── Phase 7: Virtual Fence Intrusion Check ────────────────────────
        for det in frame_data.detections:
            effective_track_id = det.track_id if det.track_id is not None else hash(f"{det.class_name}_{det.x1}_{det.y1}")
            
            if getattr(frame_data, 'frame_width', 0) > 0 and getattr(frame_data, 'frame_height', 0) > 0:
                nx1 = det.x1 / frame_data.frame_width
                ny1 = det.y1 / frame_data.frame_height
                nx2 = det.x2 / frame_data.frame_width
                ny2 = det.y2 / frame_data.frame_height
                
                event_type = fence_registry.check_intrusion(
                    source_id=source_id,
                    track_id=effective_track_id,
                    bbox_norm=(nx1, ny1, nx2, ny2),
                    frame_width=frame_data.frame_width,
                    frame_height=frame_data.frame_height
                )
                
                if event_type:
                    logger.info("[INTRUSION ALERT] Source '%s' (%s #%s): %s", source_id, det.class_name, det.track_id, event_type)
                    alert_title = "RESTRICTED ZONE INTRUSION" if event_type == 'zone_intrusion' else "LINE CROSSING"
                    event_msg = "entered Restricted Zone" if event_type == 'zone_intrusion' else "crossed Virtual Fence"
                    
                    obj_class = det.class_name.upper()
                    conf_pct = int(round(det.confidence * 100))
                    track_label = f"{obj_class} #{det.track_id}" if det.track_id is not None else obj_class
                    
                    description = f"{track_label} {event_msg} ({conf_pct}%) at {frame_data.timestamp_sec:.1f}s."
                    
                    camera_label = getattr(source, "location", "") or getattr(source, "original_name", "") or source_id.replace('_', ' ').title()
                    
                    # ── Evidence Snapshot (non-blocking) ─────────────────
                    try:
                        raw_frame = getattr(frame_data, '_raw_frame', None)
                        if raw_frame is not None:
                            evidence_writer.enqueue_snapshot(
                                frame=raw_frame,
                                source_id=source_id,
                                event_type=event_type,
                                track_id=det.track_id,
                                object_class=obj_class,
                                confidence=det.confidence,
                                timestamp_sec=frame_data.timestamp_sec,
                            )
                    except Exception as _ev_err:
                        logger.error("[Evidence] Snapshot enqueue failed (intrusion): %s", _ev_err)
                    
                    alert = {
                        "type": "alert",
                        "source_id": source_id,
                        "data": {
                            "alert_type": alert_title,
                            "is_intrusion": True,
                            "event_type": event_type,
                            "object_class": obj_class,
                            "track_id": det.track_id,
                            "track_label": track_label,
                            "confidence": det.confidence,
                            "confidence_pct": conf_pct,
                            "severity": "Critical",
                            "time": datetime.now().strftime("%H:%M:%S"),
                            "camera": camera_label,
                            "description": description,
                            "source_id": source_id,
                        }
                    }
                    asyncio.run_coroutine_threadsafe(
                        manager.broadcast(json.dumps(alert)),
                        loop
                    )

                    # ── Database persistence (non-blocking async queue) ───
                    try:
                        db_service.enqueue_intrusion_event(
                            source_id=source_id,
                            event_type=event_type,
                            track_id=det.track_id,
                            object_class=obj_class,
                            severity="Critical",
                            description=description,
                            timestamp_sec=frame_data.timestamp_sec,
                        )
                        db_service.enqueue_threat_alert(
                            source_id=source_id,
                            alert_type=alert_title,
                            threat_level="CRITICAL",
                            severity="Critical",
                            track_id=det.track_id,
                            object_class=obj_class,
                            confidence=det.confidence,
                            is_intrusion=True,
                            event_type=event_type,
                            camera_label=camera_label,
                            description=description,
                        )
                        db_service.enqueue_detection_event(
                            source_id=source_id,
                            event_type=alert_title,
                            object_class=obj_class,
                            track_id=det.track_id,
                            confidence=det.confidence,
                            timestamp_sec=frame_data.timestamp_sec,
                            threat_level="CRITICAL",
                            severity="Critical",
                            description=description,
                            bbox=(det.x1, det.y1, det.x2, det.y2),
                        )
                    except Exception as _dbe:
                        logger.error("[Database] Intrusion persistence error: %s", _dbe)

                # ── Phase 9: Loitering Detection Check for UNKNOWN PERSON ──────
                is_person = det.class_name.lower() == 'person'
                loiter_info = fence_registry.check_loitering(
                    source_id=source_id,
                    track_id=effective_track_id,
                    current_timestamp_sec=frame_data.timestamp_sec,
                    is_person=is_person,
                )
                
                if loiter_info:
                    logger.info("[LOITERING ALERT] Source '%s' (Person #%s): Loitering detected (duration=%.1fs, threshold=%.1fs)",
                                source_id, det.track_id, loiter_info['duration'], loiter_info['threshold'])
                    obj_class = "PERSON"
                    conf_pct = int(round(det.confidence * 100))
                    track_label = f"UNKNOWN PERSON #{det.track_id}" if det.track_id is not None else "UNKNOWN PERSON"
                    thresh_val = loiter_info['threshold']
                    thresh_str = f"{int(thresh_val)}s" if thresh_val < 60 else (f"{int(thresh_val // 60)}m" if thresh_val % 60 == 0 else f"{thresh_val/60:.1f}m")
                    
                    description = f"🚨 {track_label} loitering in Restricted Zone for {loiter_info['duration']:.1f}s (Threshold: {thresh_str})."
                    camera_label = getattr(source, "location", "") or getattr(source, "original_name", "") or source_id.replace('_', ' ').title()
                    
                    # Forensic evidence snapshot
                    try:
                        raw_frame = getattr(frame_data, '_raw_frame', None)
                        if raw_frame is not None:
                            evidence_writer.enqueue_snapshot(
                                frame=raw_frame,
                                source_id=source_id,
                                event_type="loitering",
                                track_id=det.track_id,
                                object_class=obj_class,
                                confidence=det.confidence,
                                timestamp_sec=frame_data.timestamp_sec,
                            )
                    except Exception as _ev_err:
                        logger.error("[Evidence] Snapshot enqueue failed (loitering): %s", _ev_err)
                        
                    loiter_alert = {
                        "type": "alert",
                        "source_id": source_id,
                        "data": {
                            "alert_type": "LOITERING DETECTED",
                            "is_intrusion": True,
                            "event_type": "loitering",
                            "object_class": obj_class,
                            "track_id": det.track_id,
                            "track_label": track_label,
                            "confidence": det.confidence,
                            "confidence_pct": conf_pct,
                            "duration_sec": loiter_info['duration'],
                            "threshold_sec": loiter_info['threshold'],
                            "severity": "Critical",
                            "time": datetime.now().strftime("%H:%M:%S"),
                            "camera": camera_label,
                            "description": description,
                            "source_id": source_id,
                        }
                    }
                    asyncio.run_coroutine_threadsafe(
                        manager.broadcast(json.dumps(loiter_alert)),
                        loop
                    )

                    # ── Database persistence for loitering ────────────────
                    try:
                        db_service.enqueue_intrusion_event(
                            source_id=source_id,
                            event_type="loitering",
                            track_id=det.track_id,
                            object_class=obj_class,
                            duration_sec=loiter_info['duration'],
                            threshold_sec=loiter_info['threshold'],
                            severity="Critical",
                            description=description,
                            timestamp_sec=frame_data.timestamp_sec,
                        )
                        db_service.enqueue_threat_alert(
                            source_id=source_id,
                            alert_type="LOITERING DETECTED",
                            threat_level="CRITICAL",
                            severity="Critical",
                            track_id=det.track_id,
                            object_class=obj_class,
                            confidence=det.confidence,
                            is_intrusion=True,
                            event_type="loitering",
                            camera_label=camera_label,
                            description=description,
                        )
                        db_service.enqueue_detection_event(
                            source_id=source_id,
                            event_type="LOITERING DETECTED",
                            object_class=obj_class,
                            track_id=det.track_id,
                            confidence=det.confidence,
                            timestamp_sec=frame_data.timestamp_sec,
                            threat_level="CRITICAL",
                            severity="Critical",
                            description=description,
                            bbox=(det.x1, det.y1, det.x2, det.y2),
                        )
                    except Exception as _dbe:
                        logger.error("[Database] Loitering persistence error: %s", _dbe)

        # Clean up exited / disappeared tracks from loitering timers
        current_frame_track_ids = {
            (d.track_id if d.track_id is not None else hash(f"{d.class_name}_{d.x1}_{d.y1}"))
            for d in frame_data.detections
        }
        fence_registry.cleanup_exited_tracks(source_id, current_frame_track_ids, getattr(frame_data, 'timestamp_sec', 0.0))

        # ── Phase 10: Suspicious Activity Detection Engine (Additive Integration) ──
        try:
            active_tids = {d.track_id for d in frame_data.detections if d.track_id is not None}
            suspicious_engine.cleanup(
                source_id=source_id,
                active_track_ids=active_tids,
                current_timestamp_sec=getattr(frame_data, "timestamp_sec", 0.0),
                max_stale_seconds=3.0,
            )
            susp_events = suspicious_engine.process_frame(
                source_id=source_id,
                frame_data=frame_data,
                timestamp_sec=getattr(frame_data, "timestamp_sec", 0.0),
                frame_index=getattr(frame_data, "frame_index", 0),
            )
            for s_ev in susp_events:
                if s_ev.object_track_id is not None:
                    logger.info(
                        "[SUSPICIOUS_ACTIVITY][CONFIRMED] source=%s activity=%s track=%d object_track=%d timestamp=%.2f",
                        s_ev.source_id,
                        s_ev.activity,
                        s_ev.track_id,
                        s_ev.object_track_id,
                        s_ev.timestamp_sec,
                    )
                else:
                    logger.info(
                        "[SUSPICIOUS_ACTIVITY][CONFIRMED] source=%s activity=%s track=%d timestamp=%.2f",
                        s_ev.source_id,
                        s_ev.activity,
                        s_ev.track_id,
                        s_ev.timestamp_sec,
                    )

                # ── Database persistence (Threat Alert & Event Audit Log) ──
                persisted_event_id = None
                try:
                    camera_label = getattr(source, "location", "") or getattr(source, "original_name", "") or (getattr(s_ev, "source_id", None) or source_id).replace('_', ' ').title()
                    subj_bbox = None
                    for d in frame_data.detections:
                        if d.track_id == s_ev.track_id:
                            subj_bbox = (float(d.x1), float(d.y1), float(d.x2), float(d.y2))
                            break

                    res = db_service.enqueue_suspicious_activity(
                        event=s_ev,
                        camera_label=camera_label,
                        bbox=subj_bbox,
                    )
                    if res is not None:
                        persisted_event_id = res[1]
                        logger.info(
                            "[SUSPICIOUS_PERSISTENCE][SUCCESS] source=%s activity=%s track=%d alert_id=%s event_id=%s",
                            source_id,
                            s_ev.activity,
                            s_ev.track_id,
                            res[0],
                            res[1],
                        )
                except Exception as _pers_err:
                    logger.error(
                        "[SUSPICIOUS_PERSISTENCE][ERROR] Failed to persist suspicious event for source '%s' track %d: %s",
                        source_id,
                        s_ev.track_id,
                        _pers_err,
                    )

                # ── Evidence Snapshot (Step 6D — independent failure isolation) ──
                try:
                    raw_frame = getattr(frame_data, '_raw_frame', None)
                    if raw_frame is not None:
                        ev_source = getattr(s_ev, "source_id", None) or source_id
                        evidence_writer.enqueue_snapshot(
                            frame=raw_frame,
                            source_id=ev_source,
                            event_type="suspicious_activity",
                            track_id=s_ev.track_id,
                            object_class="PERSON",
                            confidence=s_ev.confidence,
                            timestamp_sec=s_ev.timestamp_sec,
                            event_id=persisted_event_id,
                            skip_dedup=True,
                        )
                        logger.info(
                            "[SUSPICIOUS_EVIDENCE][ENQUEUED] source=%s activity=%s track=%d time=%.2fs event_id=%s",
                            ev_source,
                            s_ev.activity,
                            s_ev.track_id,
                            s_ev.timestamp_sec,
                            persisted_event_id,
                        )
                except Exception as _ev_err:
                    logger.error(
                        "[Evidence] Snapshot enqueue failed for suspicious event source='%s' track=%d: %s",
                        source_id,
                        s_ev.track_id,
                        _ev_err,
                    )

                # ── WebSocket broadcast (Step 6B — independent failure isolation) ──
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
                            "time": datetime.now().strftime("%H:%M:%S"),
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
                    if loop is not None and loop.is_running():
                        asyncio.run_coroutine_threadsafe(
                            manager.broadcast(msg_str),
                            loop
                        )
                    else:
                        manager.broadcast_from_thread(msg_str)

                    logger.info(
                        "[SUSPICIOUS_WS][SUCCESS] source=%s activity=%s track=%d",
                        source_id,
                        act_upper,
                        s_ev.track_id,
                    )
                except Exception as _ws_err:
                    logger.error(
                        "[SUSPICIOUS_WS][ERROR] Failed to broadcast suspicious event for source '%s' track %d: %s",
                        source_id,
                        s_ev.track_id,
                        _ws_err,
                    )
        except Exception as _susp_err:
            logger.error("[SUSPICIOUS_ENGINE][INTEGRATION_ERROR] Source '%s': %s", source_id, _susp_err, exc_info=False)

        priority_dets = [d for d in frame_data.detections if d.is_priority]
        
        # ── Send live frame updates for RTSP streams and video file analysis ─
        frame_update = {
            "type": "frame_update",
            "source_id": source_id,
            "data": frame_data.to_dict()
        }
        if loop is not None and loop.is_running():
            asyncio.run_coroutine_threadsafe(
                manager.broadcast(json.dumps(frame_update)),
                loop
            )
        else:
            manager.broadcast_from_thread(json.dumps(frame_update))

        if not priority_dets:
            return susp_events

        # ── Alert deduplication via TrackerRegistry ─────────────────────────
        new_priority_dets = []
        for det in priority_dets:
            if det.track_id is not None:
                # We have a persistent track ID — deduplicate across ALL frames
                dedup_key = det.track_id
                if tracker_registry.is_track_seen(source_id, dedup_key):
                    continue
                tracker_registry.mark_track_seen(source_id, dedup_key)
                new_priority_dets.append(det)
            else:
                new_priority_dets.append(det)

        if not new_priority_dets:
            return susp_events

        # Pick highest confidence priority detection as primary identifier
        top_det = max(new_priority_dets, key=lambda d: d.confidence)
        obj_class = top_det.class_name.upper()
        conf_pct = int(round(top_det.confidence * 100))

        track_id   = top_det.track_id
        track_label = f"{obj_class} #{track_id}" if track_id is not None else obj_class

        # ── Evidence Snapshot for priority (unknown-person / unrecognized) alerts ──
        # Capture only for PERSON class since KNOWN_PERSON will be updated via face_recognition
        try:
            raw_frame = getattr(frame_data, '_raw_frame', None)
            if raw_frame is not None and obj_class == 'PERSON':
                evidence_writer.enqueue_snapshot(
                    frame=raw_frame,
                    source_id=source_id,
                    event_type='priority_person_alert',
                    track_id=track_id,
                    object_class=obj_class,
                    confidence=top_det.confidence,
                    timestamp_sec=frame_data.timestamp_sec,
                )
        except Exception as _ev_err:
            logger.error("[Evidence] Snapshot enqueue failed (priority alert): %s", _ev_err)

        if len(new_priority_dets) == 1:
            description = (
                f"{track_label} detected ({conf_pct}% confidence) at "
                f"{frame_data.timestamp_sec:.1f}s."
            )
        else:
            other_parts = [
                (
                    f"{d.class_name.upper()} #{d.track_id} ({int(round(d.confidence * 100))}%)"
                    if d.track_id is not None
                    else f"{d.class_name.upper()} ({int(round(d.confidence * 100))}%)"
                )
                for d in new_priority_dets if d != top_det
            ][:2]
            description = (
                f"{track_label} ({conf_pct}%) + "
                f"{', '.join(other_parts)} at {frame_data.timestamp_sec:.1f}s."
            )

        camera_label = getattr(source, "location", "") or getattr(source, "original_name", "") or source_id.replace('_', ' ').title()

        # Emit a real-time event for the dashboard
        alert = {
            "type": "alert",
            "source_id": source_id,
            "data": {
                "alert_type": f"Priority Object Detected — {track_label}",
                "object_class": obj_class,
                "track_id":     track_id,
                "track_label":  track_label,
                "confidence":   top_det.confidence,
                "confidence_pct": conf_pct,
                "severity":  "Critical",
                "time":      datetime.now().strftime("%H:%M:%S"),
                "camera":    camera_label,
                "description": description,
                "source_id": source_id,
            }
        }
        if loop is not None and loop.is_running():
            asyncio.run_coroutine_threadsafe(
                manager.broadcast(json.dumps(alert)),
                loop
            )
        else:
            manager.broadcast_from_thread(json.dumps(alert))

        # ── Database persistence for priority object detection ────────────
        try:
            db_service.enqueue_threat_alert(
                source_id=source_id,
                alert_type=f"Priority Object Detected — {track_label}",
                threat_level="HIGH",
                severity="Critical",
                track_id=track_id,
                object_class=obj_class,
                confidence=top_det.confidence,
                camera_label=camera_label,
                description=description,
            )
            db_service.enqueue_detection_event(
                source_id=source_id,
                event_type="Priority Perimeter Breach" if obj_class == "PERSON" else f"{obj_class} Detected",
                object_class=obj_class,
                track_id=track_id,
                confidence=top_det.confidence,
                timestamp_sec=frame_data.timestamp_sec,
                threat_level="HIGH",
                severity="Critical",
                description=description,
                bbox=(top_det.x1, top_det.y1, top_det.x2, top_det.y2),
            )
        except Exception as _dbe:
            logger.error("[Database] Priority detection persistence error: %s", _dbe)

    except Exception as e:
        logger.error("Error in event processing for stream %s: %s", source_id, e, exc_info=True)

    return susp_events



@router.post("/analyze/{source_id}", status_code=status.HTTP_200_OK)
async def analyze_source(
    source_id: str,
    max_frames: int = 300,
    sample_rate: int = 5,
    confidence: float = 0.40,
):
    """
    Run object detection on the video file associated with the given source_id.
    Trigger YOLO object detection on a registered video source.
    """
    source = get_source(source_id)
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source '{source_id}' not found.",
        )

    filename = getattr(source, "name", source_id)
    is_rtsp = getattr(source, "source_type", None) == "RTSP"

    if not is_rtsp and source_id in _active_video_analyses:
        logger.info("[ANALYZE] Analysis already running for source '%s', attaching to existing in-flight task.", source_id)
        return await asyncio.shield(_active_video_analyses[source_id])

    loop = asyncio.get_running_loop()

    # Phase 6: Reset tracker state for this source so re-analysis always gets fresh IDs
    tracker_registry.prepare_for_source(source_id)
    # Phase 7: Reset virtual fence state for this source
    fence_registry.prepare_for_source(source_id)
    # Phase 10: Reset suspicious engine state for this source
    suspicious_engine.clear_source(source_id)

    collected_suspicious_events = []

    def on_frame_processed_callback(fd):
        evs = handle_frame_processed(
            frame_data=fd,
            source_id=source_id,
            source=source,
            loop=loop,
        )
        if evs:
            collected_suspicious_events.extend(evs)

    try:
        if getattr(source, "source_type", None) == "RTSP":
            # If already running continuously for this source, do not restart
            if source_id in _rtsp_running_sources and source_id in _rtsp_stop_events and not _rtsp_stop_events[source_id].is_set():
                future = _rtsp_futures.get(source_id)
                if future and not future.done():
                    logger.info("[RTSP_ANALYZE_TRACE] RTSP detection already running for source '%s'", source_id)
                    return {
                        "source_id":          source_id,
                        "status":             "processing_stream",
                        "frames_processed":   0,
                        "total_detections":   0,
                        "unique_classes":     [],
                        "frame_results":      [],
                        "suspicious_events":  [],
                    }
                else:
                    logger.info("[RTSP_ANALYZE_TRACE] Previous RTSP detection worker completed/failed for '%s', restarting...", source_id)
                    _rtsp_running_sources.discard(source_id)

            if source_id in _rtsp_stop_events:
                await stop_rtsp_detection(source_id)
            stop_event = threading.Event()
            _rtsp_stop_events[source_id] = stop_event
            _rtsp_running_sources.add(source_id)

            def _stream_worker():
                try:
                    logger.info("[RTSP_ANALYZE_TRACE][DETECTION_STARTED] Starting stream worker for %s", source_id)
                    run_detection_on_stream(
                        source_id=source_id,
                        sample_rate=1,
                        confidence=confidence,
                        on_frame_processed=on_frame_processed_callback,
                        stop_event=stop_event
                    )
                except Exception as e:
                    logger.error("[RTSP_ANALYZE_TRACE][STREAM_WORKER_ERROR] Failure in RTSP detection loop for '%s': %s", source_id, e, exc_info=True)
                finally:
                    _rtsp_running_sources.discard(source_id)
                    logger.info("[RTSP_ANALYZE_TRACE] Stream worker exited for '%s'", source_id)

            future = loop.run_in_executor(_executor, _stream_worker)
            _rtsp_futures[source_id] = future
            logger.info("[RTSP_ANALYZE_TRACE] Started continuous real-time detection for RTSP source '%s'", source_id)
            return {
                "source_id":          source_id,
                "status":             "processing_stream",
                "frames_processed":   0,
                "total_detections":   0,
                "unique_classes":     [],
                "frame_results":      [],
                "suspicious_events":  [],
            }
        else:
            # Run the blocking YOLO inference in a thread-pool worker for file uploads.
            # Deduplicate concurrent requests via _active_video_analyses.
            async def _run_analysis():
                results = await loop.run_in_executor(
                    _executor,
                    lambda: run_detection_on_video(
                        filename    = filename,
                        max_frames  = max_frames,
                        sample_rate = sample_rate,
                        confidence  = confidence,
                        on_frame_processed = on_frame_processed_callback
                    ),
                )
                serialized_susp_events = [ev.to_dict() for ev in collected_suspicious_events]
                results["suspicious_events"] = serialized_susp_events
                _results_cache[source_id] = results
                logger.info(
                    "Detection complete for source '%s': %d frames, %d detections, %d suspicious events",
                    source_id,
                    results["frames_processed"],
                    results["total_detections"],
                    len(serialized_susp_events),
                )
                return {
                    "source_id":          source_id,
                    "status":             "completed",
                    "frames_processed":   results["frames_processed"],
                    "total_detections":   results["total_detections"],
                    "unique_classes":     results["unique_classes"],
                    "frame_results":      results["frame_results"],
                    "suspicious_events":  serialized_susp_events,
                }

            analysis_task = asyncio.create_task(_run_analysis())
            _active_video_analyses[source_id] = analysis_task
            try:
                return await analysis_task
            finally:
                _active_video_analyses.pop(source_id, None)
                suspicious_engine.clear_source(source_id)

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except RuntimeError as exc:
        logger.error("Detection failed for source '%s': %s", source_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Detection failed: {exc}",
        )


# ---------------------------------------------------------------------------
# GET /results/{source_id}
# ---------------------------------------------------------------------------

@router.get("/results/{source_id}")
def get_detection_results(source_id: str):
    """
    Return cached detection results for a previously analysed source.
    """
    if source_id not in _results_cache:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No detection results found for source '{source_id}'. "
                   f"Run POST /analyze/{source_id} first.",
        )
    results = _results_cache[source_id]
    return {
        "source_id":          source_id,
        "status":             "completed",
        "frames_processed":   results.get("frames_processed", 0),
        "total_detections":   results.get("total_detections", 0),
        "unique_classes":     results.get("unique_classes", []),
        "frame_results":      results.get("frame_results", []),
        "suspicious_events":  results.get("suspicious_events", []),
    }

