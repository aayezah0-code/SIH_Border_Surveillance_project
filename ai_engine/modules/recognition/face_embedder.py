"""
FaceEmbedder — Phase 6: OpenCV SFace Biometric Feature Extractor
-----------------------------------------------------------------
Wraps OpenCV's official SFace (SphereFace / ArcFace family) ONNX model.
Takes an image and detected face landmarks, performs affine alignment,
and extracts a 128-dimensional L2-normalized biometric embedding vector.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).resolve().parent / "models"
DEFAULT_SFACE_MODEL = MODELS_DIR / "face_recognition_sface_2021dec.onnx"

# Biometric recognition thresholds
# Cosine similarity for SFace:
# >= 0.65 -> Strong biometric match (Known person)
# <  0.65 -> Insufficient confidence (Unknown person)
KNOWN_THRESHOLD = 0.65


class FaceEmbedder:
    """Thread-safe wrapper around cv2.FaceRecognizerSF."""

    def __init__(self, model_path: Optional[Path | str] = None):
        self.model_path = Path(model_path) if model_path else DEFAULT_SFACE_MODEL
        self._recognizer: Optional[cv2.FaceRecognizerSF] = None
        self._load_model()

    def _load_model(self):
        """Initialise the SFace ONNX recognizer."""
        if not self.model_path.exists():
            logger.error("SFace model not found at %s", self.model_path)
            self._recognizer = None
            return

        try:
            self._recognizer = cv2.FaceRecognizerSF.create(
                model=str(self.model_path),
                config="",
            )
            logger.info("SFace face recognizer loaded successfully from %s", self.model_path)
        except Exception as exc:
            logger.error("Failed to load SFace face recognizer: %s", exc)
            self._recognizer = None

    @property
    def is_ready(self) -> bool:
        return self._recognizer is not None

    def extract_embedding(self, image: np.ndarray, raw_face_array: np.ndarray) -> Optional[np.ndarray]:
        """
        Align the detected face and extract its 128-D normalized embedding vector.
        raw_face_array is the 15-element array returned by YuNet.
        """
        if not self.is_ready or image is None or image.size == 0 or raw_face_array is None:
            return None

        try:
            # 1. Align and crop face to standard 112x112 canonical orientation
            aligned_face = self._recognizer.alignCrop(image, raw_face_array)
            if aligned_face is None or aligned_face.size == 0:
                return None

            if aligned_face.shape[:2] != (112, 112):
                aligned_face = cv2.resize(aligned_face, (112, 112), interpolation=cv2.INTER_CUBIC)

            # 2. Extract 128-D feature representation
            embedding = self._recognizer.feature(aligned_face)
            if embedding is None or len(embedding) == 0:
                return None

            # 3. Ensure float32 1D array & L2 normalize
            vec = embedding.flatten().astype(np.float32)
            norm = np.linalg.norm(vec)
            if norm > 1e-6:
                vec = vec / norm
            return vec
        except Exception as exc:
            logger.error("Failed to extract face embedding: %s", exc)
            return None

    @staticmethod
    def compute_similarity(embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """
        Compute Cosine Similarity between two L2-normalized 128-D vectors.
        Returns a float in range [-1.0, 1.0].
        """
        if embedding1 is None or embedding2 is None:
            return 0.0
        # Dot product for unit-length vectors
        return float(np.dot(embedding1.flatten(), embedding2.flatten()))

    @staticmethod
    def match_against_gallery(
        query_embedding: np.ndarray,
        gallery: dict[str, np.ndarray],
        threshold: float = KNOWN_THRESHOLD,
    ) -> Tuple[Optional[str], float, str]:
        """
        Compare query embedding against a dictionary of {person_id: centroid_embedding}.
        
        Returns:
          (matched_person_id, highest_score, status)
          where status is 'KNOWN_PERSON' or 'UNKNOWN_PERSON'.
        """
        if not gallery or query_embedding is None:
            return None, 0.0, "UNKNOWN_PERSON"

        best_id: Optional[str] = None
        best_score: float = -1.0

        for pid, ref_emb in gallery.items():
            score = FaceEmbedder.compute_similarity(query_embedding, ref_emb)
            if score > best_score:
                best_score = score
                best_id = pid

        if best_score >= threshold and best_id is not None:
            return best_id, best_score, "KNOWN_PERSON"
        else:
            return None, max(0.0, best_score), "UNKNOWN_PERSON"
