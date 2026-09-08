"""
AI Configuration API Router — Sentinel AI Surveillance Platform
-----------------------------------------------------------------
Provides dedicated endpoints to view and safely update runtime AI parameters:
  - GET  /api/v1/config/ai  -> Return current active AI settings and system telemetry
  - POST /api/v1/config/ai  -> Validate and apply safe AI parameters across active feeds
"""

import logging
from typing import Any, Dict, Literal
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.services.ai_config_service import ai_config_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/config", tags=["AI Configuration"])


class AIConfigUpdatePayload(BaseModel):
    confidence: float = Field(..., ge=0.25, le=0.70, description="YOLO detection confidence threshold")
    iou: float = Field(..., ge=0.30, le=0.60, description="YOLO IoU / NMS threshold")
    low_light_mode: Literal["auto", "on", "off"] = Field(..., description="Low-light enhancement mode")
    frs_match_threshold: float = Field(..., ge=0.50, le=0.80, description="FRS personnel match similarity threshold")
    anpr_consensus_threshold: int = Field(..., description="ANPR consensus verification frames (1, 2, 3)")
    running_enabled: bool = Field(..., description="Enable or disable running detection")
    crawling_enabled: bool = Field(..., description="Enable or disable crawling detection")
    throwing_enabled: bool = Field(..., description="Enable or disable throwing detection")

    @field_validator("anpr_consensus_threshold")
    @classmethod
    def validate_anpr_consensus(cls, v: int) -> int:
        if v not in (1, 2, 3):
            raise ValueError("anpr_consensus_threshold must be 1, 2, or 3")
        return v


@router.get("/ai", status_code=status.HTTP_200_OK)
def get_ai_config() -> Dict[str, Any]:
    """
    Retrieve current global AI model configuration and system telemetry.
    """
    try:
        return ai_config_service.get_config()
    except Exception as exc:
        logger.error("[AIConfigRouter] Error getting AI config: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve AI configuration: {str(exc)}",
        )


@router.post("/ai", status_code=status.HTTP_200_OK)
def update_ai_config(payload: AIConfigUpdatePayload) -> Dict[str, Any]:
    """
    Safely update and apply global AI model configuration.
    Changes apply to all active surveillance sources without restarting streams.
    """
    try:
        updated = ai_config_service.update_config(payload.model_dump())
        logger.info("[AIConfigRouter] Successfully applied AI config update: %s", payload.model_dump())
        return {
            "status": "success",
            "message": "AI Model Configuration updated successfully",
            "config": updated,
        }
    except ValueError as val_err:
        logger.warning("[AIConfigRouter] Invalid AI config update rejected: %s", val_err)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(val_err),
        )
    except Exception as exc:
        logger.error("[AIConfigRouter] Failed to apply AI config update: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update AI configuration: {str(exc)}",
        )
