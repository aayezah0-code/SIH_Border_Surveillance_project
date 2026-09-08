import sys
from pathlib import Path

# Bootstrap project root into sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.video_router import router as video_router
from app.api.detection_router import router as detection_router
from app.api.fence_router import router as fence_router
from app.api.websocket_router import router as websocket_router
from app.api.face_router import router as face_router
from app.api.evidence_router import router as evidence_router
from app.api.event_router import router as event_router
from app.api.anpr_router import router as anpr_router
from app.api.config_router import router as config_router
from app.api.auth_router import router as auth_router
from app.db.database import init_db

app = FastAPI(
    title="Border Surveillance API",
    description="Backend API for the SIH AI-Based Border Surveillance Platform",
    version="1.0.0"
)

# Configure CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this to the frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Routers ---
app.include_router(video_router)
app.include_router(detection_router)
app.include_router(fence_router)
app.include_router(websocket_router)
app.include_router(face_router)
app.include_router(evidence_router)
app.include_router(event_router)
app.include_router(anpr_router)
app.include_router(config_router)
app.include_router(auth_router)


@app.on_event("startup")
async def on_startup():
    """Register event loop and initialize SQLite tables."""
    import asyncio
    from app.websockets.manager import manager
    manager.set_event_loop(asyncio.get_running_loop())
    init_db()


@app.get("/")
def read_root():
    return {"message": "Welcome to the Border Surveillance API"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}
