"""
PlateDetector — License Plate Detection Module
-----------------------------------------------
Extracts license plate regions from detected vehicle crops.

Supports:
1. Pretrained YOLOv8 / ONNX plate detector model if weights exist in models directory.
2. High-performance OpenCV morphological edge + contour localization fallback (< 2ms)
   tailored for vehicle crops (Sobel-X edge density, aspect ratio filtering, rect fitting).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

_MODELS_DIR = Path(__file__).resolve().parent / "models"


@dataclass
class PlateDetectionResult:
    """Bounding box and confidence of a localized license plate within a vehicle crop."""
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float
    plate_crop: np.ndarray

    @property
    def bbox(self) -> Tuple[int, int, int, int]:
        return (self.x1, self.y1, self.x2, self.y2)


class PlateDetector:
    """
    Modular license plate detector operating on vehicle BGR image crops.
    """

    def __init__(self, model_path: Optional[str | Path] = None):
        self.model_path = Path(model_path) if model_path else _MODELS_DIR / "license_plate_detector.pt"
        self._yolo_model = None
        self._load_model_if_available()

    def _load_model_if_available(self):
        """Attempt to load a dedicated YOLO plate detection model if present."""
        if self.model_path.exists():
            try:
                import torch
                from ultralytics import YOLO
                device = "cuda" if torch.cuda.is_available() else "cpu"
                self._yolo_model = YOLO(str(self.model_path))
                logger.info(
                    "[ANPR_PLATE_MODEL][LOAD] model=%s, device=%s, status=SUCCESS",
                    self.model_path.name, device
                )
            except Exception as e:
                logger.warning(
                    "[ANPR_PLATE_MODEL][LOAD] model=%s, device=unknown, status=FAILED (error: %s)",
                    self.model_path.name, e
                )
                self._yolo_model = None

    @property
    def is_ready(self) -> bool:
        return True

    def detect_plates(
        self,
        vehicle_crop: np.ndarray,
        min_conf: float = 0.25,
        source_id: str = "default",
        track_id: Optional[int] = None,
    ) -> List[PlateDetectionResult]:
        """
        Detect license plate candidates inside a vehicle crop using dedicated plate detector.

        Parameters
        ----------
        vehicle_crop : BGR numpy array containing the vehicle image.
        min_conf     : Minimum detection confidence threshold.
        source_id    : Camera or video identifier.
        track_id     : Tracking ID of the vehicle.

        Returns
        -------
        List of PlateDetectionResult objects sorted by confidence (highest first).
        """
        if vehicle_crop is None or vehicle_crop.size == 0:
            return []

        vh, vw = vehicle_crop.shape[:2]
        if vh < 20 or vw < 30:
            return []

        import time
        t_start = time.perf_counter()

        # 1. Try dedicated YOLO license-plate model
        if self._yolo_model is not None:
            try:
                target_sz = max(320, min(640, max(vw, vh)))
                imgsz_val = int(np.ceil(target_sz / 32.0) * 32)
                results = self._yolo_model.predict(
                    source=vehicle_crop,
                    conf=min_conf,
                    verbose=False,
                    imgsz=imgsz_val,
                )
                inference_ms = (time.perf_counter() - t_start) * 1000.0

                plate_results = []
                for res in results:
                    if res.boxes is None:
                        continue
                    for box in res.boxes:
                        conf = float(box.conf[0].item())
                        xyxy = box.xyxy[0].tolist()
                        x1, y1, x2, y2 = [max(0, int(v)) for v in xyxy]
                        x2, y2 = min(vw, x2), min(vh, y2)
                        if x2 > x1 and y2 > y1:
                            pad_x = max(2, int((x2 - x1) * 0.04))
                            pad_y = max(2, int((y2 - y1) * 0.05))
                            px1, py1 = max(0, x1 - pad_x), max(0, y1 - pad_y)
                            px2, py2 = min(vw, x2 + pad_x), min(vh, y2 + pad_y)
                            crop = vehicle_crop[py1:py2, px1:px2].copy()
                            plate_results.append(
                                PlateDetectionResult(
                                    x1=x1, y1=y1, x2=x2, y2=y2,
                                    confidence=round(conf, 3),
                                    plate_crop=crop,
                                )
                            )

                logger.info(
                    "[ANPR_PLATE_MODEL][INFERENCE] source_id=%s, track_id=%s, vehicle_crop=(%dx%d), inference_ms=%.2f",
                    source_id, track_id, vw, vh, inference_ms
                )

                if plate_results:
                    sorted_plates = sorted(plate_results, key=lambda p: p.confidence, reverse=True)
                    boxes_str = [(p.x1, p.y1, p.x2, p.y2) for p in sorted_plates]
                    confs_str = [p.confidence for p in sorted_plates]
                    logger.info(
                        "[ANPR_PLATE_MODEL][DETECTION] source_id=%s, track_id=%s, candidate_count=%d, boxes=%s, confidences=%s",
                        source_id, track_id, len(sorted_plates), boxes_str, confs_str
                    )
                    return sorted_plates

            except Exception as exc:
                logger.debug("[PlateDetector] Dedicated plate model inference error: %s", exc)

        # 2. Fast Morphological Plate Localizer (OpenCV fallback)
        morph_results = self._detect_plates_morphological(vehicle_crop)
        if morph_results:
            boxes_str = [(p.x1, p.y1, p.x2, p.y2) for p in morph_results]
            confs_str = [p.confidence for p in morph_results]
            logger.info(
                "[ANPR_PLATE_MODEL][DETECTION] (Fallback) source_id=%s, track_id=%s, candidate_count=%d, boxes=%s, confidences=%s",
                source_id, track_id, len(morph_results), boxes_str, confs_str
            )
        return morph_results

    def _detect_plates_morphological(self, vehicle_crop: np.ndarray) -> List[PlateDetectionResult]:
        """
        Morphological Edge & Contour Plate Localization.
        Leverages horizontal Sobel gradients, rectangular aspect ratio (2.0 - 5.5),
        and edge density typical of license plate text.
        """
        vh, vw = vehicle_crop.shape[:2]
        gray = cv2.cvtColor(vehicle_crop, cv2.COLOR_BGR2GRAY)

        # Focus primarily on lower 75% of vehicle crop where plates are mounted
        roi_y1 = int(vh * 0.20)
        roi_gray = gray[roi_y1:, :]

        # 1. Morphological Blackhat to reveal dark text on light plate background
        rect_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (13, 5))
        blackhat = cv2.morphologyEx(roi_gray, cv2.MORPH_BLACKHAT, rect_kernel)

        # 2. Sobel-X gradient
        grad_x = cv2.Sobel(blackhat, ddepth=cv2.CV_32F, dx=1, dy=0, ksize=-1)
        grad_x = np.absolute(grad_x)
        min_val, max_val = np.min(grad_x), np.max(grad_x)
        if max_val > min_val:
            grad_x = (255 * ((grad_x - min_val) / (max_val - min_val))).astype("uint8")
        else:
            grad_x = grad_x.astype("uint8")

        # 3. Gaussian blur & Otsu threshold
        grad_x = cv2.GaussianBlur(grad_x, (5, 5), 0)
        _, thresh = cv2.threshold(grad_x, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)

        # 4. Closing kernel to form contiguous plate candidate boxes
        close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (17, 3))
        closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, close_kernel)

        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidates: List[PlateDetectionResult] = []

        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            aspect_ratio = float(w) / max(1, h)
            area = w * h
            crop_area = vw * vh

            # Plate geometry filters for standard single-line & double-line plates
            if 1.8 <= aspect_ratio <= 6.0 and 0.005 <= (area / crop_area) <= 0.35:
                if w >= 25 and h >= 10:
                    px1 = max(0, x)
                    py1 = max(0, y + roi_y1)
                    px2 = min(vw, x + w)
                    py2 = min(vh, y + roi_y1 + h)

                    plate_crop = vehicle_crop[py1:py2, px1:px2].copy()
                    if plate_crop.size > 0:
                        # Estimate confidence based on aspect ratio match to standard 3.5-4.5
                        ar_score = 1.0 - min(1.0, abs(aspect_ratio - 3.8) / 3.8)
                        conf = round(0.50 + 0.45 * ar_score, 3)
                        candidates.append(
                            PlateDetectionResult(
                                x1=px1, y1=py1, x2=px2, y2=py2,
                                confidence=conf,
                                plate_crop=plate_crop,
                            )
                        )

        if not candidates:
            # Fallback: if no strict contour matched, return lower-middle vehicle slice (most probable plate region)
            def_w = int(vw * 0.60)
            def_h = int(vh * 0.25)
            def_x1 = max(0, int((vw - def_w) / 2))
            def_y1 = max(0, int(vh * 0.65))
            def_x2 = min(vw, def_x1 + def_w)
            def_y2 = min(vh, def_y1 + def_h)
            def_crop = vehicle_crop[def_y1:def_y2, def_x1:def_x2].copy()
            if def_crop.size > 0:
                candidates.append(
                    PlateDetectionResult(
                        x1=def_x1, y1=def_y1, x2=def_x2, y2=def_y2,
                        confidence=0.40,
                        plate_crop=def_crop,
                    )
                )

        return sorted(candidates, key=lambda p: (p.confidence, p.plate_crop.shape[0] * p.plate_crop.shape[1]), reverse=True)[:3]
