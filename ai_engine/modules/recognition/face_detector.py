"""
FaceDetector — Phase 6: OpenCV YuNet Face Detection & Alignment
----------------------------------------------------------------
Wraps OpenCV's official YuNet ONNX face detection model.
Extracts face bounding boxes and 5 facial landmarks (right eye, left eye,
nose tip, right mouth corner, left mouth corner) for affine alignment.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional, List, Tuple
from dataclasses import dataclass

import cv2
import numpy as np

logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).resolve().parent / "models"
DEFAULT_YUNET_MODEL = MODELS_DIR / "face_detection_yunet_2023mar.onnx"

# Quality filtering constants
MIN_FACE_WIDTH = 12
MIN_FACE_HEIGHT = 12
MIN_CONFIDENCE = 0.45
MIN_BLUR_VAR = 15.0  # Minimum Laplacian variance (discard severely blurry crops)


@dataclass
class DetectedFace:
    """A detected face with coordinates, confidence, landmarks, and raw array."""
    x: int
    y: int
    w: int
    h: int
    confidence: float
    landmarks: np.ndarray  # Shape: (5, 2)
    raw_face_array: np.ndarray  # Raw face array row returned by YuNet (length 15)
    is_good_quality: bool = True
    quality_reason: str = "OK"

    @property
    def bbox(self) -> Tuple[int, int, int, int]:
        return (self.x, self.y, self.w, self.h)


class FaceDetector:
    """Thread-safe wrapper around cv2.FaceDetectorYN."""

    def __init__(
        self,
        model_path: Optional[Path | str] = None,
        confidence_threshold: float = MIN_CONFIDENCE,
        nms_threshold: float = 0.3,
        top_k: int = 5000,
    ):
        self.model_path = Path(model_path) if model_path else DEFAULT_YUNET_MODEL
        self.conf_threshold = confidence_threshold
        self.nms_threshold = nms_threshold
        self.top_k = top_k
        self._detector: Optional[cv2.FaceDetectorYN] = None
        self._current_input_size: Tuple[int, int] = (300, 300)
        self._load_model()

    def _load_model(self):
        """Initialise the YuNet ONNX detector."""
        if not self.model_path.exists():
            logger.error("YuNet model not found at %s", self.model_path)
            self._detector = None
            return

        try:
            self._detector = cv2.FaceDetectorYN.create(
                model=str(self.model_path),
                config="",
                input_size=self._current_input_size,
                score_threshold=self.conf_threshold,
                nms_threshold=self.nms_threshold,
                top_k=self.top_k,
            )
            logger.info("YuNet face detector loaded successfully from %s", self.model_path)
        except Exception as exc:
            logger.error("Failed to load YuNet face detector: %s", exc)
            self._detector = None

    @property
    def is_ready(self) -> bool:
        return self._detector is not None

    def detect_faces(self, image: np.ndarray) -> List[DetectedFace]:
        """
        Detect faces in a BGR image crop or full frame.
        Returns a list of DetectedFace objects.
        """
        if not self.is_ready or image is None or image.size == 0:
            return []

        h, w = image.shape[:2]
        if h < MIN_FACE_HEIGHT or w < MIN_FACE_WIDTH:
            return []

        # Resize detector input dynamically to match image dimensions
        if (w, h) != self._current_input_size:
            self._current_input_size = (w, h)
            self._detector.setInputSize((w, h))

        try:
            status, raw_faces = self._detector.detect(image)
            if status == 0 or raw_faces is None:
                return []

            results: List[DetectedFace] = []
            for face in raw_faces:
                # YuNet output format:
                # [0..3]: x, y, w, h
                # [4..13]: right_eye, left_eye, nose_tip, right_mouth, left_mouth (x, y pairs)
                # [14]: confidence
                fx, fy, fw, fh = map(int, face[0:4])
                conf = float(face[14])
                landmarks = face[4:14].reshape((5, 2))

                # Quality checks
                is_good = True
                reason = "OK"

                if fw < MIN_FACE_WIDTH or fh < MIN_FACE_HEIGHT:
                    is_good = False
                    reason = f"Face too small ({fw}x{fh} < {MIN_FACE_WIDTH}x{MIN_FACE_HEIGHT})"
                else:
                    # Clip face crop bounds safely
                    cx1 = max(0, fx)
                    cy1 = max(0, fy)
                    cx2 = min(w, fx + fw)
                    cy2 = min(h, fy + fh)
                    if cx2 > cx1 and cy2 > cy1:
                        face_crop = image[cy1:cy2, cx1:cx2]
                        # Blur check via Laplacian variance
                        gray_crop = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY) if len(face_crop.shape) == 3 else face_crop
                        laplacian_var = cv2.Laplacian(gray_crop, cv2.CV_64F).var()
                        if laplacian_var < MIN_BLUR_VAR:
                            is_good = False
                            reason = f"Blurry face (var={laplacian_var:.1f} < {MIN_BLUR_VAR})"

                results.append(
                    DetectedFace(
                        x=fx,
                        y=fy,
                        w=fw,
                        h=fh,
                        confidence=conf,
                        landmarks=landmarks,
                        raw_face_array=face,
                        is_good_quality=is_good,
                        quality_reason=reason,
                    )
                )

            return results
        except Exception as exc:
            logger.error("Face detection failed on frame crop: %s", exc)
            return []
