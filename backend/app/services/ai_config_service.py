"""
AI Configuration Service — Sentinel AI Surveillance Platform
--------------------------------------------------------------
Manages safe, global runtime configuration for AI subsystems:
  - YOLOv8 Detection Confidence & IoU thresholds
  - Low-Light Enhancement Mode ('auto', 'on', 'off')
  - FRS Personnel Match Threshold (0.50 - 0.80)
  - ANPR Consensus Verification Frames (1, 2, 3)
  - Behavioral Suspicious Activity Modules (Running, Crawling, Throwing)

Stores configuration in backend/data/ai_config.json (isolated from DB)
and applies updates live to running AI pipelines without restarting streams
or reloading model weights.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
CONFIG_FILE = DATA_DIR / "ai_config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "confidence": 0.40,
    "iou": 0.45,
    "low_light_mode": "auto",
    "frs_match_threshold": 0.65,
    "anpr_consensus_threshold": 2,
    "running_enabled": True,
    "crawling_enabled": True,
    "throwing_enabled": True,
}


class AIConfigService:
    """Thread-safe runtime AI configuration manager."""

    def __init__(self):
        self._lock = threading.RLock()
        self.confidence: float = DEFAULT_CONFIG["confidence"]
        self.iou: float = DEFAULT_CONFIG["iou"]
        self.low_light_mode: str = DEFAULT_CONFIG["low_light_mode"]
        self.frs_match_threshold: float = DEFAULT_CONFIG["frs_match_threshold"]
        self.anpr_consensus_threshold: int = DEFAULT_CONFIG["anpr_consensus_threshold"]
        self.running_enabled: bool = DEFAULT_CONFIG["running_enabled"]
        self.crawling_enabled: bool = DEFAULT_CONFIG["crawling_enabled"]
        self.throwing_enabled: bool = DEFAULT_CONFIG["throwing_enabled"]

        self._load_from_disk()
        self.apply()

    def _load_from_disk(self):
        """Load persisted settings from ai_config.json if present."""
        with self._lock:
            try:
                DATA_DIR.mkdir(parents=True, exist_ok=True)
                if CONFIG_FILE.exists():
                    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    if "confidence" in data and 0.25 <= float(data["confidence"]) <= 0.70:
                        self.confidence = float(data["confidence"])
                    if "iou" in data and 0.30 <= float(data["iou"]) <= 0.60:
                        self.iou = float(data["iou"])
                    if "low_light_mode" in data and str(data["low_light_mode"]).lower() in ("auto", "on", "off"):
                        self.low_light_mode = str(data["low_light_mode"]).lower()
                    if "frs_match_threshold" in data and 0.50 <= float(data["frs_match_threshold"]) <= 0.80:
                        self.frs_match_threshold = float(data["frs_match_threshold"])
                    if "anpr_consensus_threshold" in data and int(data["anpr_consensus_threshold"]) in (1, 2, 3):
                        self.anpr_consensus_threshold = int(data["anpr_consensus_threshold"])
                    if "running_enabled" in data:
                        self.running_enabled = bool(data["running_enabled"])
                    if "crawling_enabled" in data:
                        self.crawling_enabled = bool(data["crawling_enabled"])
                    if "throwing_enabled" in data:
                        self.throwing_enabled = bool(data["throwing_enabled"])
                    
                    logger.info("[AIConfigService] Loaded configuration from %s", CONFIG_FILE)
            except Exception as e:
                logger.error("[AIConfigService] Failed to load ai_config.json, using defaults: %s", e)

    def _save_to_disk(self):
        """Persist current settings to ai_config.json."""
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            payload = {
                "confidence": self.confidence,
                "iou": self.iou,
                "low_light_mode": self.low_light_mode,
                "frs_match_threshold": self.frs_match_threshold,
                "anpr_consensus_threshold": self.anpr_consensus_threshold,
                "running_enabled": self.running_enabled,
                "crawling_enabled": self.crawling_enabled,
                "throwing_enabled": self.throwing_enabled,
            }
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            logger.info("[AIConfigService] Persisted configuration to %s", CONFIG_FILE)
        except Exception as e:
            logger.error("[AIConfigService] Failed to save ai_config.json: %s", e)

    def apply(self):
        """Apply current configuration to running AI engines in memory."""
        with self._lock:
            # 1. Low-Light Enhancer
            try:
                from ai_engine.modules.enhancement.low_light_enhancer import low_light_enhancer
                low_light_enhancer.mode = self.low_light_mode
            except Exception as e:
                logger.warning("[AIConfigService] Could not update low_light_enhancer mode: %s", e)

            # 2. FRS Match Threshold
            try:
                from ai_engine.modules.recognition.face_worker import face_worker
                face_worker.match_threshold = self.frs_match_threshold
            except Exception as e:
                logger.warning("[AIConfigService] Could not update face_worker threshold: %s", e)

            # 3. ANPR Consensus Threshold
            try:
                from ai_engine.modules.recognition.anpr_worker import anpr_worker
                anpr_worker.consensus_threshold = self.anpr_consensus_threshold
            except Exception as e:
                logger.warning("[AIConfigService] Could not update anpr_worker consensus: %s", e)

            # 4. Behavioral Detectors (Suspicious Engine)
            import sys, importlib
            for mod_name in ("app.api.detection_router", "backend.app.api.detection_router"):
                try:
                    if mod_name in sys.modules:
                        eng = getattr(sys.modules[mod_name], "suspicious_engine", None)
                        if eng:
                            eng.enable_running = self.running_enabled
                            eng.enable_crawling = self.crawling_enabled
                            eng.enable_throwing = self.throwing_enabled
                    else:
                        mod = importlib.import_module(mod_name)
                        eng = getattr(mod, "suspicious_engine", None)
                        if eng:
                            eng.enable_running = self.running_enabled
                            eng.enable_crawling = self.crawling_enabled
                            eng.enable_throwing = self.throwing_enabled
                except Exception:
                    pass

            # 5. YOLO Active Detector Pool
            try:
                from app.services.detection_service import _detectors
                for det in _detectors.values():
                    det.confidence = self.confidence
                    det.iou = self.iou
            except Exception as e:
                logger.warning("[AIConfigService] Could not update active detectors: %s", e)

    def update_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and apply new configuration updates."""
        with self._lock:
            if "confidence" in updates:
                conf = float(updates["confidence"])
                if not (0.25 <= conf <= 0.70):
                    raise ValueError(f"confidence must be between 0.25 and 0.70, got {conf}")
                self.confidence = round(conf, 2)

            if "iou" in updates:
                iou_val = float(updates["iou"])
                if not (0.30 <= iou_val <= 0.60):
                    raise ValueError(f"iou must be between 0.30 and 0.60, got {iou_val}")
                self.iou = round(iou_val, 2)

            if "low_light_mode" in updates:
                mode = str(updates["low_light_mode"]).lower()
                if mode not in ("auto", "on", "off"):
                    raise ValueError(f"low_light_mode must be 'auto', 'on', or 'off', got {mode}")
                self.low_light_mode = mode

            if "frs_match_threshold" in updates:
                frs_t = float(updates["frs_match_threshold"])
                if not (0.50 <= frs_t <= 0.80):
                    raise ValueError(f"frs_match_threshold must be between 0.50 and 0.80, got {frs_t}")
                self.frs_match_threshold = round(frs_t, 2)

            if "anpr_consensus_threshold" in updates:
                anpr_c = int(updates["anpr_consensus_threshold"])
                if anpr_c not in (1, 2, 3):
                    raise ValueError(f"anpr_consensus_threshold must be 1, 2, or 3, got {anpr_c}")
                self.anpr_consensus_threshold = anpr_c

            if "running_enabled" in updates:
                self.running_enabled = bool(updates["running_enabled"])

            if "crawling_enabled" in updates:
                self.crawling_enabled = bool(updates["crawling_enabled"])

            if "throwing_enabled" in updates:
                self.throwing_enabled = bool(updates["throwing_enabled"])

            self.apply()
            self._save_to_disk()
            return self.get_config()

    def get_config(self) -> Dict[str, Any]:
        """Return the current active configuration along with read-only system telemetry."""
        with self._lock:
            # Gather telemetry safely
            active_sources_count = 0
            try:
                from app.services.video_service import list_sources
                active_sources_count = len(list_sources())
            except Exception:
                pass

            registered_personnel_count = 0
            try:
                from ai_engine.modules.recognition.face_registry import face_registry
                registered_personnel_count = len(face_registry.get_all_people())
            except Exception:
                pass

            return {
                "confidence": self.confidence,
                "iou": self.iou,
                "low_light_mode": self.low_light_mode,
                "frs_match_threshold": self.frs_match_threshold,
                "anpr_consensus_threshold": self.anpr_consensus_threshold,
                "running_enabled": self.running_enabled,
                "crawling_enabled": self.crawling_enabled,
                "throwing_enabled": self.throwing_enabled,
                "system_status": {
                    "active_model": "YOLOv8 Nano (yolov8n.pt)",
                    "detection_engine": "ACTIVE",
                    "inference_device": "CPU (Optimized)",
                    "active_sources_count": active_sources_count,
                    "registered_personnel_count": registered_personnel_count,
                },
            }


# Global singleton instance
ai_config_service = AIConfigService()
