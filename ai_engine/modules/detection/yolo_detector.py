"""
YOLODetector — Phase 4: Basic AI Object Detection
--------------------------------------------------
Wraps the Ultralytics YOLOv8n model into a clean, reusable service.

Public surface:
  YOLODetector.detect_frame(frame: np.ndarray) -> list[DetectionResult]
  YOLODetector.process_video(video_path, ...)  -> list[FrameDetections]

Intentionally minimal — tracking, recognition and behaviour analysis
will be added in later phases by sub-classing or composing this service.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, Callable

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ── COCO classes we care about for border surveillance ────────────────────────
# Full COCO label list will be used, but we tag the priority ones.
PRIORITY_CLASSES = {
    "person",
    "car",
    "truck",
    "motorcycle",
    "bicycle",
    "bus",
    "boat",
    "airplane",
    "dog",
    "horse",
    "backpack",
    "handbag",
    "suitcase",
}

# Default detection parameters
DEFAULT_CONFIDENCE = 0.40   # minimum confidence threshold
DEFAULT_IOU        = 0.45   # NMS IoU threshold
MAX_FRAMES         = 300    # cap on frames processed per video to keep API responsive
FRAME_SAMPLE_RATE  = 5      # process every Nth frame (1 = every frame)

# YOLOv8 nano — fast, ~6 MB, auto-downloaded on first use
DEFAULT_MODEL = "yolov8n.pt"


# ── Data containers ───────────────────────────────────────────────────────────

@dataclass
class DetectionResult:
    """A single detected object in one frame."""
    class_id:   int
    class_name: str
    confidence: float
    x1: int
    y1: int
    x2: int
    y2: int
    track_id:   Optional[int] = None
    is_priority: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        return (self.x1, self.y1, self.x2, self.y2)


@dataclass
class FrameDetections:
    """All detections for a single video frame."""
    frame_index: int
    timestamp_sec: float
    detections:  list[DetectionResult]
    frame_width: int = 0
    frame_height: int = 0

    def to_dict(self) -> dict:
        return {
            "frame_index":    self.frame_index,
            "timestamp_sec":  round(self.timestamp_sec, 3),
            "frame_width":    self.frame_width,
            "frame_height":   self.frame_height,
            "detections":     [d.to_dict() for d in self.detections],
        }


# ── Detector ──────────────────────────────────────────────────────────────────

class SimpleTracker:
    """Lightweight, zero-overhead IoU object tracker for real-time video feeds."""
    def __init__(self, iou_threshold: float = 0.25, max_age: int = 30):
        self.next_id = 1
        self.tracks = {}  # track_id -> {'bbox': (x1,y1,x2,y2), 'class_name': str, 'age': 0}
        self.iou_threshold = iou_threshold
        self.max_age = max_age

    def reset(self):
        self.next_id = 1
        self.tracks.clear()

    def update(self, detections: list[DetectionResult]) -> list[DetectionResult]:
        for tid in list(self.tracks.keys()):
            self.tracks[tid]['age'] += 1
            if self.tracks[tid]['age'] > self.max_age:
                del self.tracks[tid]

        for det in detections:
            if det.track_id is not None:
                continue

            best_id = None
            best_iou = 0.0
            d_box = (det.x1, det.y1, det.x2, det.y2)

            for tid, tdata in self.tracks.items():
                if tdata['class_name'] == det.class_name:
                    t_box = tdata['bbox']
                    ix1 = max(d_box[0], t_box[0])
                    iy1 = max(d_box[1], t_box[1])
                    ix2 = min(d_box[2], t_box[2])
                    iy2 = min(d_box[3], t_box[3])

                    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
                    if inter > 0:
                        area_d = (d_box[2] - d_box[0]) * (d_box[3] - d_box[1])
                        area_t = (t_box[2] - t_box[0]) * (t_box[3] - t_box[1])
                        union = area_d + area_t - inter
                        iou = inter / union if union > 0 else 0
                        if iou > best_iou:
                            best_iou = iou
                            best_id = tid

            if best_id is not None and best_iou >= self.iou_threshold:
                det.track_id = best_id
                self.tracks[best_id] = {'bbox': d_box, 'class_name': det.class_name, 'age': 0}
            else:
                det.track_id = self.next_id
                self.tracks[self.next_id] = {'bbox': d_box, 'class_name': det.class_name, 'age': 0}
                self.next_id += 1

        return detections


class YOLODetector:
    """
    Thin wrapper around Ultralytics YOLO.

    Usage::

        detector = YOLODetector()                 # loads yolov8n.pt
        results   = detector.detect_frame(frame)  # frame is an BGR np.ndarray
        video_res = detector.process_video("/path/to/video.mp4")
    """

    _instance: Optional["YOLODetector"] = None   # singleton holder

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        confidence: float = DEFAULT_CONFIDENCE,
        iou: float = DEFAULT_IOU,
    ):
        self.model_name = model_name
        self.confidence = confidence
        self.iou        = iou
        self._model     = None
        self._fallback_tracker = SimpleTracker()

    # ── Singleton factory ─────────────────────────────────────────────────────

    @classmethod
    def get_instance(cls) -> "YOLODetector":
        """Return the shared detector instance, creating it on first call."""
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._load_model()
        return cls._instance

    # ── Model loading ─────────────────────────────────────────────────────────

    def _load_model(self):
        """Load the YOLO model. Called once at startup."""
        try:
            from ultralytics import YOLO  # imported here to keep startup fast
            logger.info("Loading YOLO model: %s", self.model_name)
            t0 = time.time()
            self._model = YOLO(self.model_name)
            logger.info("YOLO model loaded in %.2fs", time.time() - t0)
        except ImportError as exc:
            raise RuntimeError(
                "ultralytics package is not installed. "
                "Run: pip install ultralytics"
            ) from exc
        except Exception as exc:
            raise RuntimeError(f"Failed to load YOLO model: {exc}") from exc

    def _reset_tracker(self):
        """
        Reset tracker state for fresh IDs starting from #1.
        """
        self._fallback_tracker.reset()
        if self._model is not None:
            try:
                if hasattr(self._model, 'predictor') and self._model.predictor is not None:
                    if hasattr(self._model.predictor, 'trackers'):
                        delattr(self._model.predictor, 'trackers')
            except Exception as exc:
                pass

    @property
    def is_ready(self) -> bool:
        return self._model is not None

    # ── Core detection ────────────────────────────────────────────────────────

    def detect_frame(
        self,
        frame: np.ndarray,
        confidence: Optional[float] = None,
        iou: Optional[float] = None,
        imgsz: int = 640,
    ) -> list[DetectionResult]:
        """
        Run YOLO on a single BGR frame.

        Parameters
        ----------
        frame      : BGR numpy array (as returned by cv2.imread / cap.read)
        confidence : override instance confidence threshold
        iou        : override instance IoU threshold
        imgsz      : image size for YOLO inference (smaller = faster)

        Returns
        -------
        List of DetectionResult objects (may be empty).
        """
        if not self.is_ready:
            self._load_model()

        conf = confidence if confidence is not None else self.confidence
        iou_ = iou        if iou        is not None else self.iou

        import torch
        device_str = "cuda:0" if torch.cuda.is_available() else "cpu"

        results = self._model.predict(
            source=frame,
            conf=conf,
            iou=iou_,
            imgsz=imgsz,
            verbose=False,
            stream=False,
            device=device_str,
        )

        dets = self._parse_results(results)
        return self._fallback_tracker.update(dets)

    def _track_frame(
        self,
        frame: np.ndarray,
        confidence: Optional[float] = None,
        iou: Optional[float] = None,
        imgsz: int = 640,
    ) -> list[DetectionResult]:
        """
        Run YOLO + ByteTrack/SimpleTracker on a single BGR frame.
        """
        conf = confidence if confidence is not None else self.confidence
        iou_ = iou        if iou        is not None else self.iou

        if not self.is_ready:
            self._load_model()

        import torch
        device_str = "cuda:0" if torch.cuda.is_available() else "cpu"

        try:
            results = self._model.track(
                source=frame,
                persist=True,
                tracker="bytetrack.yaml",
                conf=conf,
                iou=iou_,
                imgsz=imgsz,
                verbose=False,
                stream=False,
                device=device_str,
            )
            dets = self._parse_results(results)
            # Ensure every detection has a valid track_id
            return self._fallback_tracker.update(dets)
        except Exception:
            return self.detect_frame(frame, confidence=confidence, iou=iou, imgsz=imgsz)

    def _parse_results(self, results) -> list[DetectionResult]:
        detections: list[DetectionResult] = []
        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                cls_id   = int(box.cls[0].item())
                cls_name = result.names[cls_id]
                conf_val = float(box.conf[0].item())
                xyxy     = box.xyxy[0].tolist()
                x1, y1, x2, y2 = (int(v) for v in xyxy)
                
                # box.id is a tensor; handle both scalar and 1-element cases
                track_id: Optional[int] = None
                if box.id is not None:
                    try:
                        track_id = int(box.id[0].item())
                    except Exception:
                        try:
                            track_id = int(box.id.item())
                        except Exception:
                            track_id = None

                detections.append(DetectionResult(
                    class_id   = cls_id,
                    class_name = cls_name,
                    confidence = round(conf_val, 4),
                    x1=x1, y1=y1, x2=x2, y2=y2,
                    track_id   = track_id,
                    is_priority=cls_name in PRIORITY_CLASSES,
                ))
        return detections

    # ── Video processing ──────────────────────────────────────────────────────

    def process_video(
        self,
        video_path: str | Path,
        max_frames: int = MAX_FRAMES,
        sample_rate: int = FRAME_SAMPLE_RATE,
        confidence: Optional[float] = None,
        iou: Optional[float] = None,
        on_frame_processed: Optional[Callable] = None,
    ) -> list[FrameDetections]:
        """
        Process a video file and return detections per sampled frame.

        Parameters
        ----------
        video_path  : path to the video file
        max_frames  : maximum number of frames to process (safety cap)
        sample_rate : process every Nth frame (reduces load)
        confidence  : detection confidence threshold override
        iou         : NMS IoU threshold override
        on_frame_processed : optional callback fired after each sampled frame is processed

        Returns
        -------
        List of FrameDetections (one entry per processed frame).
        """
        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"Video not found: {video_path}")

        # Open video capture
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open video: {video_path}")
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0

        if not self.is_ready:
            self._load_model()

        self._reset_tracker()
        
        import torch
        device_str = "cuda:0" if torch.cuda.is_available() else "cpu"
        
        conf = confidence if confidence is not None else self.confidence
        iou_ = iou if iou is not None else self.iou

        all_results: list[FrameDetections] = []
        processed     = 0
        raw_frame_idx = 0
        
        # Prepare ANPR worker for fresh offline video source
        try:
            from ai_engine.modules.recognition.anpr_worker import anpr_worker
            anpr_worker.prepare_for_offline_source(video_path.stem)
        except Exception as e:
            logger.debug("ANPR worker prep failed: %s", e)

        try:
            from ai_engine.modules.enhancement.low_light_enhancer import low_light_enhancer

            while processed < max_frames:
                ret = cap.grab()
                if not ret:
                    break

                if raw_frame_idx % sample_rate != 0:
                    raw_frame_idx += 1
                    continue

                ret, raw_frame = cap.retrieve()
                if not ret or raw_frame is None:
                    raw_frame_idx += 1
                    continue

                frame_idx = raw_frame_idx
                timestamp = frame_idx / fps
                raw_frame_idx += 1

                orig_h, orig_w = raw_frame.shape[:2]

                # Performance Optimization (Step 3 & 4):
                # For high-res footage (>=1080p), pre-rescaling to imgsz=832 before enhancement avoids
                # processing 8.3M pixels on CPU and prevents Bayer sensor noise amplification by CLAHE.
                if max(orig_h, orig_w) >= 1920:
                    inference_imgsz = 832
                    scale = inference_imgsz / max(orig_h, orig_w)
                    new_w, new_h = int(orig_w * scale), int(orig_h * scale)
                    proc_frame = cv2.resize(raw_frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
                    scale_back_x = orig_w / new_w
                    scale_back_y = orig_h / new_h
                else:
                    inference_imgsz = 640
                    proc_frame = raw_frame
                    scale_back_x = 1.0
                    scale_back_y = 1.0

                # Low-light enhancement check with adaptive confidence
                det_frame, was_enhanced, _, eff_conf = low_light_enhancer.enhance_if_needed(
                    proc_frame, base_conf=conf, low_light_conf=0.30
                )

                # Run YOLO prediction + tracker for complete object detection coverage
                pred_results = self._model.predict(
                    source=det_frame,
                    conf=eff_conf,
                    iou=iou_,
                    imgsz=inference_imgsz,
                    verbose=False,
                    device=device_str,
                )

                raw_dets = self._parse_results(pred_results)
                dets = self._fallback_tracker.update(raw_dets)
                if scale_back_x != 1.0 or scale_back_y != 1.0:
                    for d in dets:
                        d.x1 = int(round(d.x1 * scale_back_x))
                        d.y1 = int(round(d.y1 * scale_back_y))
                        d.x2 = int(round(d.x2 * scale_back_x))
                        d.y2 = int(round(d.y2 * scale_back_y))

                h, w = orig_h, orig_w

                frame_data = FrameDetections(
                    frame_index   = frame_idx,
                    timestamp_sec = timestamp,
                    detections    = dets,
                    frame_width   = w,
                    frame_height  = h,
                )
                # Evidence capture: attach original raw frame (never modified)
                frame_data._raw_frame = raw_frame

                all_results.append(frame_data)
                processed += 1

                logger.debug(
                    "Frame %d @ %.2fs — %d detection(s)",
                    frame_idx, timestamp, len(dets),
                )

                # Phase 6: Non-blocking asynchronous handoff to FaceRecognitionWorker on original raw_frame
                # Phase 8: Controlled Offline handoff to ANPRWorker for vehicles on original raw_frame
                for det in dets:
                    c_name = det.class_name.lower()
                    if c_name == "person":
                        try:
                            from ai_engine.modules.recognition.face_worker import face_worker
                            face_worker.submit_crop(
                                source_id=video_path.stem,
                                track_id=det.track_id,
                                frame=raw_frame,
                                bbox=det.bbox,
                                timestamp_sec=timestamp,
                            )
                        except Exception as e:
                            logger.error(f"[FACE_TRACE][UPLOAD_SUBMIT_ERROR] {e}")
                    elif c_name in ("car", "truck", "bus", "motorcycle"):
                        try:
                            fh, fw = raw_frame.shape[:2]
                            logger.info(
                                "[ANPR_TRACE][VEHICLE_DETECTED] source_id=%s, track_id=%s, vehicle_class=%s, frame_dim=(%d, %d), bbox=%s",
                                video_path.stem, det.track_id, det.class_name, fw, fh, det.bbox
                            )
                            # Collect competing vehicle bounding boxes in this frame for plate association
                            competing_boxes = [
                                (d.track_id, d.bbox)
                                for d in dets
                                if d.class_name.lower() in ("car", "truck", "bus", "motorcycle") and d.track_id != det.track_id
                            ]
                            from ai_engine.modules.recognition.anpr_worker import anpr_worker
                            anpr_worker.submit_vehicle_crop(
                                source_id=video_path.stem,
                                track_id=det.track_id,
                                frame=raw_frame,
                                vehicle_bbox=det.bbox,
                                vehicle_class=det.class_name,
                                timestamp_sec=timestamp,
                                is_offline=True,
                                frame_idx=frame_idx,
                                competing_bboxes=competing_boxes,
                            )
                        except Exception as e:
                            logger.error(f"[ANPR_TRACE][UPLOAD_SUBMIT_ERROR] {e}")

                if on_frame_processed:
                    on_frame_processed(frame_data)

        except Exception as e:
            logger.error("Error during video processing: %s", e)
            raise
        finally:
            cap.release()

        # End-of-video drain: wait for queued background ANPR tasks to finalize safely
        try:
            from ai_engine.modules.recognition.anpr_worker import anpr_worker
            anpr_worker.drain_offline(video_path.stem, timeout=30.0)
        except Exception as e:
            logger.error("ANPR worker drain failed: %s", e)

        logger.info(
            "Processed %d frames from '%s'. Total detections: %d",
            processed,
            video_path.name,
            sum(len(f.detections) for f in all_results),
        )
        return all_results
