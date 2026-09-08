"""
Recognition Module — Phase 6: Face Recognition & ANPR
------------------------------------------------------
Provides standalone face recognition (YuNet/SFace) and Automatic Number
Plate Recognition (PlateDetector, PlateOCR, ANPRWorker) for surveillance feeds.
"""

from ai_engine.modules.recognition.face_detector import FaceDetector
from ai_engine.modules.recognition.face_embedder import FaceEmbedder
from ai_engine.modules.recognition.face_registry import face_registry
from ai_engine.modules.recognition.face_worker import face_worker, FaceRecognitionWorker
from ai_engine.modules.recognition.plate_detector import PlateDetector, PlateDetectionResult
from ai_engine.modules.recognition.plate_ocr import PlateOCR, OCRResult
from ai_engine.modules.recognition.anpr_worker import anpr_worker, ANPRWorker

__all__ = [
    "FaceDetector",
    "FaceEmbedder",
    "face_registry",
    "face_worker",
    "FaceRecognitionWorker",
    "PlateDetector",
    "PlateDetectionResult",
    "PlateOCR",
    "OCRResult",
    "anpr_worker",
    "ANPRWorker",
]
