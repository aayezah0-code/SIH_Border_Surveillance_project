import logging
from typing import List, Tuple, Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, status

from ai_engine.modules.behavior.virtual_fence import fence_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/fence", tags=["Virtual Fence"])

class FenceConfigRequest(BaseModel):
    type: str  # 'zone' or 'line'
    points: List[Tuple[float, float]]  # List of (x, y) normalized coords [0.0 - 1.0]
    loitering_duration: Optional[float] = None  # None or duration in seconds (10, 20, 30, 60, 300)

@router.post("/{source_id}", status_code=status.HTTP_200_OK)
def set_virtual_fence(source_id: str, config: FenceConfigRequest):
    """Set or update the virtual fence configuration for a given video source."""
    if config.type not in ['zone', 'line']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Fence type must be 'zone' or 'line'"
        )
        
    fence_registry.set_fence(source_id, config.type, config.points, config.loitering_duration)
    
    return {
        "status": "success", 
        "message": f"Virtual fence '{config.type}' updated for {source_id}"
    }

@router.get("/{source_id}", status_code=status.HTTP_200_OK)
def get_virtual_fence(source_id: str):
    """Get the active virtual fence configuration for a given video source."""
    config = fence_registry.get_fence(source_id)
    if not config or not config.points:
        return {"status": "none", "config": None}
    return {
        "status": "active",
        "config": {
            "type": config.type,
            "points": config.points,
            "loitering_duration": config.loitering_duration,
        }
    }

@router.delete("/{source_id}", status_code=status.HTTP_200_OK)
def clear_virtual_fence(source_id: str):
    """Clear the virtual fence configuration for a given video source."""
    fence_registry.clear_fence(source_id)
    return {"status": "success", "message": f"Virtual fence cleared for {source_id}"}
