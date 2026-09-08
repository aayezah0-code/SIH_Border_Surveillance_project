"""
Tests for AI Configuration API and Service — Sentinel AI Surveillance Platform
"""

import sys
from pathlib import Path

# Add project root and backend to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent if Path(__file__).resolve().parent.name == "tests" else Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "backend"))

import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.services.ai_config_service import ai_config_service, DEFAULT_CONFIG

client = TestClient(app)


def test_get_ai_config():
    """Verify GET /api/v1/config/ai returns current settings and telemetry."""
    response = client.get("/api/v1/config/ai")
    assert response.status_code == 200
    data = response.json()

    assert "confidence" in data
    assert "iou" in data
    assert "low_light_mode" in data
    assert "frs_match_threshold" in data
    assert "anpr_consensus_threshold" in data
    assert "running_enabled" in data
    assert "crawling_enabled" in data
    assert "throwing_enabled" in data

    assert "system_status" in data
    status = data["system_status"]
    assert status["active_model"] == "YOLOv8 Nano (yolov8n.pt)"
    assert status["detection_engine"] == "ACTIVE"
    assert "inference_device" in status


def test_update_ai_config_valid():
    """Verify POST /api/v1/config/ai accepts and applies valid settings."""
    payload = {
        "confidence": 0.55,
        "iou": 0.50,
        "low_light_mode": "on",
        "frs_match_threshold": 0.70,
        "anpr_consensus_threshold": 3,
        "running_enabled": False,
        "crawling_enabled": True,
        "throwing_enabled": False,
    }
    response = client.post("/api/v1/config/ai", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    cfg = data["config"]

    assert cfg["confidence"] == 0.55
    assert cfg["iou"] == 0.50
    assert cfg["low_light_mode"] == "on"
    assert cfg["frs_match_threshold"] == 0.70
    assert cfg["anpr_consensus_threshold"] == 3
    assert cfg["running_enabled"] is False
    assert cfg["crawling_enabled"] is True
    assert cfg["throwing_enabled"] is False

    # Check that runtime engines were updated
    from ai_engine.modules.enhancement.low_light_enhancer import low_light_enhancer
    from ai_engine.modules.recognition.face_worker import face_worker
    from ai_engine.modules.recognition.anpr_worker import anpr_worker
    from backend.app.api.detection_router import suspicious_engine

    assert low_light_enhancer.mode == "on"
    assert face_worker.match_threshold == 0.70
    assert anpr_worker.consensus_threshold == 3
    assert suspicious_engine.enable_running is False
    assert suspicious_engine.enable_crawling is True
    assert suspicious_engine.enable_throwing is False

    # Restore defaults
    reset_payload = {
        "confidence": DEFAULT_CONFIG["confidence"],
        "iou": DEFAULT_CONFIG["iou"],
        "low_light_mode": DEFAULT_CONFIG["low_light_mode"],
        "frs_match_threshold": DEFAULT_CONFIG["frs_match_threshold"],
        "anpr_consensus_threshold": DEFAULT_CONFIG["anpr_consensus_threshold"],
        "running_enabled": DEFAULT_CONFIG["running_enabled"],
        "crawling_enabled": DEFAULT_CONFIG["crawling_enabled"],
        "throwing_enabled": DEFAULT_CONFIG["throwing_enabled"],
    }
    res_reset = client.post("/api/v1/config/ai", json=reset_payload)
    assert res_reset.status_code == 200


@pytest.mark.parametrize("invalid_conf", [0.10, 0.24, 0.71, 0.95, -0.5])
def test_reject_invalid_confidence(invalid_conf):
    """Verify rejection of out-of-range confidence thresholds."""
    payload = {
        "confidence": invalid_conf,
        "iou": 0.45,
        "low_light_mode": "auto",
        "frs_match_threshold": 0.65,
        "anpr_consensus_threshold": 2,
        "running_enabled": True,
        "crawling_enabled": True,
        "throwing_enabled": True,
    }
    response = client.post("/api/v1/config/ai", json=payload)
    assert response.status_code in (400, 422)


@pytest.mark.parametrize("invalid_iou", [0.10, 0.29, 0.61, 0.90])
def test_reject_invalid_iou(invalid_iou):
    """Verify rejection of out-of-range IoU thresholds."""
    payload = {
        "confidence": 0.40,
        "iou": invalid_iou,
        "low_light_mode": "auto",
        "frs_match_threshold": 0.65,
        "anpr_consensus_threshold": 2,
        "running_enabled": True,
        "crawling_enabled": True,
        "throwing_enabled": True,
    }
    response = client.post("/api/v1/config/ai", json=payload)
    assert response.status_code in (400, 422)


@pytest.mark.parametrize("invalid_frs", [0.30, 0.49, 0.81, 1.0])
def test_reject_invalid_frs_threshold(invalid_frs):
    """Verify rejection of out-of-range FRS thresholds."""
    payload = {
        "confidence": 0.40,
        "iou": 0.45,
        "low_light_mode": "auto",
        "frs_match_threshold": invalid_frs,
        "anpr_consensus_threshold": 2,
        "running_enabled": True,
        "crawling_enabled": True,
        "throwing_enabled": True,
    }
    response = client.post("/api/v1/config/ai", json=payload)
    assert response.status_code in (400, 422)


@pytest.mark.parametrize("invalid_anpr", [0, 4, 5, -1])
def test_reject_invalid_anpr_consensus(invalid_anpr):
    """Verify rejection of non-1/2/3 ANPR consensus thresholds."""
    payload = {
        "confidence": 0.40,
        "iou": 0.45,
        "low_light_mode": "auto",
        "frs_match_threshold": 0.65,
        "anpr_consensus_threshold": invalid_anpr,
        "running_enabled": True,
        "crawling_enabled": True,
        "throwing_enabled": True,
    }
    response = client.post("/api/v1/config/ai", json=payload)
    assert response.status_code in (400, 422)


@pytest.mark.parametrize("invalid_mode", ["invalid", "ultra", "night", ""])
def test_reject_invalid_low_light_mode(invalid_mode):
    """Verify rejection of invalid low-light modes."""
    payload = {
        "confidence": 0.40,
        "iou": 0.45,
        "low_light_mode": invalid_mode,
        "frs_match_threshold": 0.65,
        "anpr_consensus_threshold": 2,
        "running_enabled": True,
        "crawling_enabled": True,
        "throwing_enabled": True,
    }
    response = client.post("/api/v1/config/ai", json=payload)
    assert response.status_code in (400, 422)
