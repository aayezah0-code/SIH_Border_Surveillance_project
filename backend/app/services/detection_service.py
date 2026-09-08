"""
Detection Service
-----------------
Bridge between the FastAPI layer and the AI engine's YOLODetector.

Responsibilities:
  - Initialise and cache the shared YOLODetector instance.
  - Provide high-level functions called by the detection router.
  - Keep all AI-engine imports isolated here so the router stays thin.

Future phases can extend this file to add:
  - Tracking  (ByteTrack / SORT)
  - Recognition (face / plate)
  - Behaviour analysis
"""

from __future__ import annotations

import logging
import sys
import os
from pathlib import Path
from typing import Optional
import cv2

logger = logging.getLogger(__name__)

# ── AI engine path bootstrap ──────────────────────────────────────────────────
# The ai_engine package lives one level above the backend directory.
_AI_ENGINE_ROOT = Path(__file__).resolve().parents[3]  # project root
if str(_AI_ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_AI_ENGINE_ROOT))

# ── Lazy detector pool ────────────────────────────────────────────────────────
_detectors: dict[str, "YOLODetector"] = {}

def get_detector(source_id: str = "default"):
    """Return a YOLODetector instance specific to this source."""
    global _detectors
    if source_id not in _detectors:
        try:
            from ai_engine.modules.detection.yolo_detector import YOLODetector
            det = YOLODetector()
            det._load_model()
            _detectors[source_id] = det
            logger.info("YOLODetector initialised successfully for source: %s", source_id)
        except Exception as exc:
            logger.error("Failed to initialise YOLODetector for %s: %s", source_id, exc)
            raise
    return _detectors[source_id]


# ── Uploads directory (same source as video_service) ─────────────────────────
from app.services.video_service import UPLOADS_DIR
from app.services.stream_manager import stream_manager
import time


def get_video_path(filename: str) -> Path:
    """Resolve an uploaded filename to its absolute path."""
    return Path(UPLOADS_DIR).resolve() / filename


# ── Public API used by the router ─────────────────────────────────────────────

def run_detection_on_video(
    filename: str,
    max_frames: int = 300,
    sample_rate: int = 5,
    confidence: float = 0.40,
    on_frame_processed: Optional[callable] = None,
    source_id: Optional[str] = None,   # Phase 6: passed to tracker for per-source reset
) -> dict:
    """
    Run YOLO object detection (+ ByteTrack tracking) on an uploaded video file.

    Returns a dict with:
      - filename
      - frames_processed
      - total_detections
      - unique_classes
      - frame_results  (list of per-frame dicts, each detection now includes track_id)
    """
    video_path = get_video_path(filename)

    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {filename}")

    from app.services.ai_config_service import ai_config_service
    eff_conf = ai_config_service.confidence if confidence == 0.40 else confidence
    detector = get_detector(source_id if source_id else "default")
    frame_results = detector.process_video(
        video_path=video_path,
        max_frames=max_frames,
        sample_rate=sample_rate,
        confidence=eff_conf,
        iou=ai_config_service.iou,
        on_frame_processed=on_frame_processed,
    )

    all_classes: set[str] = set()
    total_dets = 0
    for fr in frame_results:
        total_dets += len(fr.detections)
        for det in fr.detections:
            all_classes.add(det.class_name)

    return {
        "filename":          filename,
        "frames_processed":  len(frame_results),
        "total_detections":  total_dets,
        "unique_classes":    sorted(all_classes),
        "frame_results":     [fr.to_dict() for fr in frame_results],
    }


def run_detection_on_stream(
    source_id: str,
    sample_rate: int = 1,
    confidence: float = 0.40,
    on_frame_processed: Optional[callable] = None,
    stop_event=None,
):
    """
    Run YOLO object detection continuously on an RTSP stream in real-time.
    Runs until stop_event is set or the stream disconnects permanently.
    """
    stream = stream_manager.get_stream(source_id)
    if not stream:
        from app.services.video_service import get_source
        src = get_source(source_id)
        if src and getattr(src, "uri", None) and getattr(src, "source_type", None) == "RTSP":
            stream = stream_manager.add_stream(source_id, src.uri)
    if not stream:
        raise RuntimeError(f"Stream {source_id} not found or not active")
        
    detector = get_detector(source_id)
    detector._reset_tracker()
    
    from ai_engine.modules.detection.yolo_detector import FrameDetections
    
    frame_idx = 0
    start_time = time.time()
    logger.info("[RTSP_ANALYZE_TRACE][SESSION_STARTED] Starting RTSP detection loop for %s", source_id)
    
    while True:
        if stop_event and stop_event.is_set():
            break
            
        if not stream.is_connected:
            time.sleep(0.5)
            continue
            
        frame = stream.get_latest_frame()
        if frame is None:
            time.sleep(0.05)
            continue
            
        try:
            timestamp = time.time() - start_time

            # Phase 2A: Low-light enhancement check with resolution-matched pre-scaling
            from ai_engine.modules.enhancement.low_light_enhancer import low_light_enhancer
            h_rtsp, w_rtsp = frame.shape[:2]
            if max(h_rtsp, w_rtsp) > 640:
                scale_rtsp = 640.0 / max(h_rtsp, w_rtsp)
                new_w, new_h = max(1, int(w_rtsp * scale_rtsp)), max(1, int(h_rtsp * scale_rtsp))
                proc_rtsp = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
                scale_back_rtsp_x = w_rtsp / new_w
                scale_back_rtsp_y = h_rtsp / new_h
            else:
                proc_rtsp = frame
                scale_back_rtsp_x = 1.0
                scale_back_rtsp_y = 1.0

            from app.services.ai_config_service import ai_config_service
            base_conf = ai_config_service.confidence if confidence == 0.40 else confidence
            det_frame, was_enhanced, _, eff_conf = low_light_enhancer.enhance_if_needed(
                proc_rtsp, base_conf=base_conf, low_light_conf=0.30
            )

            dets = detector._track_frame(det_frame, confidence=eff_conf, iou=ai_config_service.iou, imgsz=480)
            if scale_back_rtsp_x != 1.0 or scale_back_rtsp_y != 1.0:
                for d in dets:
                    d.x1 = int(round(d.x1 * scale_back_rtsp_x))
                    d.y1 = int(round(d.y1 * scale_back_rtsp_y))
                    d.x2 = int(round(d.x2 * scale_back_rtsp_x))
                    d.y2 = int(round(d.y2 * scale_back_rtsp_y))
            
            # Phase 6: Non-blocking asynchronous handoff to FaceRecognitionWorker (< 0.05ms)
            # Phase 8: Non-blocking asynchronous handoff to ANPRWorker (< 0.05ms)
            for det in dets:
                c_name = det.class_name.lower()
                if c_name == "person":
                    try:
                        from ai_engine.modules.recognition.face_worker import face_worker
                        face_worker.submit_crop(
                            source_id=source_id,
                            track_id=det.track_id,
                            frame=frame,
                            bbox=det.bbox,
                            timestamp_sec=timestamp,
                        )
                    except Exception as e:
                        logger.error(f"[FACE_TRACE][STREAM_SUBMIT_ERROR] {e}")
                elif c_name in ("car", "truck", "bus", "motorcycle"):
                    try:
                        from ai_engine.modules.recognition.anpr_worker import anpr_worker
                        anpr_worker.submit_vehicle_crop(
                            source_id=source_id,
                            track_id=det.track_id,
                            frame=frame,
                            vehicle_bbox=det.bbox,
                            vehicle_class=det.class_name,
                            timestamp_sec=timestamp,
                        )
                    except Exception as e:
                        logger.error(f"[ANPR_TRACE][STREAM_SUBMIT_ERROR] {e}")

            frame_data = FrameDetections(
                frame_index=frame_idx,
                timestamp_sec=timestamp,
                detections=dets,
                frame_width=frame.shape[1],
                frame_height=frame.shape[0]
            )
            # Evidence capture: attach raw frame as optional attribute (not in to_dict)
            frame_data._raw_frame = frame.copy()
            
            if on_frame_processed:
                on_frame_processed(frame_data)
        except Exception as e:
            logger.error("Detection error on frame %s for source %s: %s", frame_idx, source_id, e, exc_info=True)
                
        frame_idx += 1
        
        # 30 FPS cap (~0.03s per frame) to prevent 100% CPU lock while maintaining real-time latency
        time.sleep(0.03)


def detector_status() -> dict:
    """Return a status dict describing whether the detector is ready."""
    try:
        det = get_detector("default")
        return {
            "ready":      det.is_ready,
            "model_name": det.model_name,
            "confidence": det.confidence,
            "iou":        det.iou,
        }
    except Exception as exc:
        return {"ready": False, "error": str(exc)}
