"""
Face Recognition API Router — Phase 6: Face Recognition
--------------------------------------------------------
Endpoints:
  GET    /api/v1/faces/status       — Status of face detection and embedding models.
  GET    /api/v1/faces              — List all registered personnel.
  GET    /api/v1/faces/{person_id}  — Get metadata for a registered person.
  POST   /api/v1/faces/register     — Register a person with 1+ face portrait photos.
  DELETE /api/v1/faces/{person_id}  — Delete a registered person from gallery.
"""

from __future__ import annotations

import logging
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status
from pydantic import BaseModel

from ai_engine.modules.recognition.face_registry import face_registry
from ai_engine.modules.recognition.face_detector import FaceDetector
from ai_engine.modules.recognition.face_embedder import FaceEmbedder

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/faces", tags=["Face Recognition"])


# ---------------------------------------------------------------------------
# GET /status
# ---------------------------------------------------------------------------

@router.get("/status")
def get_face_recognition_status():
    """Report readiness of face detection and recognition models."""
    detector = FaceDetector()
    embedder = FaceEmbedder()
    registered_people = face_registry.get_all_people()

    return {
        "face_detector_ready": detector.is_ready,
        "face_embedder_ready": embedder.is_ready,
        "detector_model": str(detector.model_path.name),
        "embedder_model": str(embedder.model_path.name),
        "registered_count": len(registered_people),
    }


# ---------------------------------------------------------------------------
# GET / (List all personnel)
# ---------------------------------------------------------------------------

@router.get("")
def list_registered_faces():
    """List all registered personnel in the face recognition gallery."""
    people = face_registry.get_all_people()
    return {
        "count": len(people),
        "personnel": people,
    }


# ---------------------------------------------------------------------------
# GET /{person_id}
# ---------------------------------------------------------------------------

@router.get("/{person_id}")
def get_person_details(person_id: str):
    """Retrieve details for a specific registered person."""
    person = face_registry.get_person(person_id)
    if not person:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Person with ID '{person_id}' not found.",
        )
    return person


# ---------------------------------------------------------------------------
# POST /register
# ---------------------------------------------------------------------------

@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    openapi_extra={
        "requestBody": {
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "title": "Name",
                                "description": "Full name of the person",
                            },
                            "role": {
                                "type": "string",
                                "title": "Role",
                                "default": "Authorized Personnel",
                                "description": "Role / designation of the person",
                            },
                            "photos": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                    "format": "binary",
                                },
                                "title": "Photos",
                                "description": "One or more face images (JPG, JPEG, PNG)",
                            },
                        },
                        "required": ["name", "photos"],
                    }
                }
            }
        }
    },
)
async def register_person_face(
    name: str = Form(...),
    role: str = Form("Authorized Personnel"),
    photos: list[UploadFile] = File(..., description="Upload 1 or more face photos"),
):
    """
    Register a new person by providing a name and 1 or more face photos.
    Generates normalized 128-D centroid embeddings and saves to gallery.
    """
    if not name or not name.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Name cannot be empty.",
        )

    if not photos or len(photos) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one face photo must be uploaded.",
        )

    image_bytes_list: List[bytes] = []
    for photo in photos:
        content = await photo.read()
        if content:
            image_bytes_list.append(content)

    if not image_bytes_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded photo files are empty or unreadable.",
        )

    success, msg, record = face_registry.register_person(
        name=name.strip(),
        role=role.strip(),
        image_bytes_list=image_bytes_list,
    )

    if not success or not record:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=msg,
        )

    return {
        "message": "Person registered successfully.",
        "person": record,
    }


# ---------------------------------------------------------------------------
# GET /{person_id}/photo/{filename}
# ---------------------------------------------------------------------------

@router.get("/{person_id}/photo/{filename}")
def get_person_photo(person_id: str, filename: str):
    """Serve a registered person's face photo."""
    from pathlib import Path
    from fastapi.responses import FileResponse
    from ai_engine.modules.recognition.face_registry import PHOTOS_DIR

    safe_pid = Path(person_id).name
    safe_name = Path(filename).name
    photo_path = PHOTOS_DIR / safe_pid / safe_name

    if not photo_path.exists() or not photo_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Photo '{safe_name}' not found for person '{safe_pid}'.",
        )

    return FileResponse(
        path=str(photo_path),
        media_type="image/jpeg",
        filename=safe_name,
        headers={"Cache-Control": "public, max-age=3600"},
    )


# ---------------------------------------------------------------------------
# DELETE /{person_id}
# ---------------------------------------------------------------------------

@router.delete("/{person_id}", status_code=status.HTTP_200_OK)
def delete_registered_person(person_id: str):
    """Remove a person and their embeddings from the face gallery."""
    success = face_registry.delete_person(person_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Person with ID '{person_id}' not found.",
        )
    return {"message": f"Person '{person_id}' deleted successfully."}

