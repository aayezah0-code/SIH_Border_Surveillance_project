"""
FaceRegistry — Phase 6: Personnel Gallery & File-Based Storage
--------------------------------------------------------------
Manages known personnel registrations without any external database.
Stores:
  - backend/data/known_faces/metadata.json
  - backend/data/known_faces/embeddings/{person_id}.npy
  - backend/data/known_faces/photos/{person_id}/{filename}

Keeps an in-memory dictionary {person_id: 128-D float32 centroid vector}
for fast vector similarity calculations.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Tuple

import cv2
import numpy as np

from ai_engine.modules.recognition.face_detector import FaceDetector
from ai_engine.modules.recognition.face_embedder import FaceEmbedder, KNOWN_THRESHOLD

logger = logging.getLogger(__name__)

# Base persistence directory
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "backend" / "data" / "known_faces"
METADATA_FILE = DATA_DIR / "metadata.json"
EMBEDDINGS_DIR = DATA_DIR / "embeddings"
PHOTOS_DIR = DATA_DIR / "photos"


class FaceRegistry:
    """Thread-safe in-memory personnel gallery with filesystem persistence."""

    def __init__(self):
        self._lock = threading.Lock()
        self._metadata: Dict[str, dict] = {}
        self._gallery: Dict[str, np.ndarray] = {}  # {person_id: 128-D np.ndarray}
        self._detector: Optional[FaceDetector] = None
        self._embedder: Optional[FaceEmbedder] = None
        self._init_storage()
        self._load_gallery()

    def _get_detector(self) -> FaceDetector:
        if self._detector is None:
            self._detector = FaceDetector()
        return self._detector

    def _get_embedder(self) -> FaceEmbedder:
        if self._embedder is None:
            self._embedder = FaceEmbedder()
        return self._embedder

    def _init_storage(self):
        """Ensure directories and metadata file exist."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)
        PHOTOS_DIR.mkdir(parents=True, exist_ok=True)

        if not METADATA_FILE.exists():
            with open(METADATA_FILE, "w", encoding="utf-8") as f:
                json.dump({}, f, indent=2)

    def _load_gallery(self):
        """Load all registered personnel embeddings into memory."""
        with self._lock:
            try:
                if METADATA_FILE.exists():
                    with open(METADATA_FILE, "r", encoding="utf-8") as f:
                        self._metadata = json.load(f)
                else:
                    self._metadata = {}

                self._gallery = {}
                for person_id in self._metadata.keys():
                    emb_path = EMBEDDINGS_DIR / f"{person_id}.npy"
                    if emb_path.exists():
                        vec = np.load(emb_path).astype(np.float32)
                        # Ensure unit normalization
                        norm = np.linalg.norm(vec)
                        if norm > 1e-6:
                            vec = vec / norm
                        self._gallery[person_id] = vec

                logger.info(
                    "FaceRegistry initialized with %d registered personnel in gallery.",
                    len(self._gallery),
                )
            except Exception as exc:
                logger.error("Failed to load FaceRegistry: %s", exc)
                self._metadata = {}
                self._gallery = {}

    def _save_metadata(self):
        """Persist metadata dictionary to JSON."""
        try:
            with open(METADATA_FILE, "w", encoding="utf-8") as f:
                json.dump(self._metadata, f, indent=2)
        except Exception as exc:
            logger.error("Failed to save metadata.json: %s", exc)

    def _sync_to_db(self, record: dict, photo_names: List[str]):
        """Persist personnel record and photos to SQLite DB."""
        try:
            from app.db.database import get_db_context
            from app.db.models import PersonnelModel, PersonnelImageModel
            with get_db_context() as db:
                p = db.query(PersonnelModel).filter_by(person_id=record["person_id"]).first()
                if not p:
                    p = PersonnelModel(
                        person_id=record["person_id"],
                        name=record["name"],
                        role=record.get("role", "Authorized Personnel"),
                        photos_count=len(photo_names),
                        registered_at=datetime.strptime(record["registered_at"], "%Y-%m-%d %H:%M:%S") if isinstance(record.get("registered_at"), str) else datetime.utcnow(),
                    )
                    db.add(p)
                    db.flush()
                else:
                    p.name = record["name"]
                    p.role = record.get("role", "Authorized Personnel")
                    p.photos_count = len(photo_names)
                    p.is_active = True

                # Clear old image records if any and re-add
                db.query(PersonnelImageModel).filter_by(person_id=record["person_id"]).delete()
                for p_name in photo_names:
                    p_path = PHOTOS_DIR / record["person_id"] / p_name
                    img_rec = PersonnelImageModel(
                        person_id=record["person_id"],
                        filename=p_name,
                        filepath=str(p_path),
                        url=f"/api/v1/faces/{record['person_id']}/photo/{p_name}",
                    )
                    db.add(img_rec)
        except Exception as exc:
            logger.error("[FaceRegistry] Database sync error on register: %s", exc)

    def _delete_from_db(self, person_id: str):
        """Delete personnel record and photo records from SQLite DB."""
        try:
            from app.db.database import get_db_context
            from app.db.models import PersonnelModel, PersonnelImageModel
            with get_db_context() as db:
                db.query(PersonnelImageModel).filter_by(person_id=person_id).delete()
                db.query(PersonnelModel).filter_by(person_id=person_id).delete()
        except Exception as exc:
            logger.error("[FaceRegistry] Database deletion error for %s: %s", person_id, exc)

    def register_person(
        self,
        name: str,
        role: str = "Authorized Personnel",
        image_bytes_list: Optional[List[bytes]] = None,
        image_paths: Optional[List[Path | str]] = None,
    ) -> Tuple[bool, str, Optional[dict]]:
        """
        Register a new person from 1 or more face photos.
        Extracts face embeddings, computes the normalized centroid vector, and saves.
        """
        if not name or not name.strip():
            return False, "Person name is required.", None

        detector = self._get_detector()
        embedder = self._get_embedder()

        if not detector.is_ready or not embedder.is_ready:
            return False, "Face recognition models are not loaded/ready.", None

        valid_embeddings: List[np.ndarray] = []
        person_id = str(uuid.uuid4())[:8]
        person_photos_dir = PHOTOS_DIR / person_id
        person_photos_dir.mkdir(parents=True, exist_ok=True)
        saved_photo_names: List[str] = []

        # Process image bytes
        if image_bytes_list:
            for idx, img_b in enumerate(image_bytes_list):
                nparr = np.frombuffer(img_b, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if img is None:
                    continue

                faces = detector.detect_faces(img)
                if not faces:
                    continue

                # Take the highest confidence / largest face
                best_face = max(faces, key=lambda f: f.confidence * (f.w * f.h))
                emb = embedder.extract_embedding(img, best_face.raw_face_array)
                if emb is not None:
                    valid_embeddings.append(emb)
                    photo_name = f"photo_{idx + 1}.jpg"
                    cv2.imwrite(str(person_photos_dir / photo_name), img)
                    saved_photo_names.append(photo_name)

        # Process image paths
        if image_paths:
            for idx, p in enumerate(image_paths):
                img = cv2.imread(str(p))
                if img is None:
                    continue

                faces = detector.detect_faces(img)
                if not faces:
                    continue

                best_face = max(faces, key=lambda f: f.confidence * (f.w * f.h))
                emb = embedder.extract_embedding(img, best_face.raw_face_array)
                if emb is not None:
                    valid_embeddings.append(emb)
                    photo_name = f"photo_{len(saved_photo_names) + 1}.jpg"
                    cv2.imwrite(str(person_photos_dir / photo_name), img)
                    saved_photo_names.append(photo_name)

        if not valid_embeddings:
            shutil.rmtree(person_photos_dir, ignore_errors=True)
            return False, "No clear, valid faces were detected in the provided images.", None

        # Compute normalized centroid vector: e = sum(e_i) / ||sum(e_i)||
        sum_vec = np.sum(valid_embeddings, axis=0)
        norm = np.linalg.norm(sum_vec)
        centroid = (sum_vec / norm).astype(np.float32) if norm > 1e-6 else valid_embeddings[0]

        # Save embedding to disk
        emb_path = EMBEDDINGS_DIR / f"{person_id}.npy"
        np.save(emb_path, centroid)

        record = {
            "person_id": person_id,
            "name": name.strip(),
            "role": role.strip() if role else "Personnel",
            "registered_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "photos_count": len(saved_photo_names),
            "photos": saved_photo_names,
        }

        with self._lock:
            self._metadata[person_id] = record
            self._gallery[person_id] = centroid
            self._save_metadata()

        # Sync to DB
        self._sync_to_db(record, saved_photo_names)

        logger.info("Successfully registered person '%s' (ID: %s) with %d photos.", name, person_id, len(saved_photo_names))
        return True, "Person registered successfully.", record

    def delete_person(self, person_id: str) -> bool:
        """Delete a registered person and clean up files."""
        with self._lock:
            if person_id not in self._metadata:
                return False

            del self._metadata[person_id]
            self._gallery.pop(person_id, None)
            self._save_metadata()

        # Delete from DB
        self._delete_from_db(person_id)

        # Clean disk files
        emb_path = EMBEDDINGS_DIR / f"{person_id}.npy"
        if emb_path.exists():
            emb_path.unlink(missing_ok=True)

        person_photos_dir = PHOTOS_DIR / person_id
        if person_photos_dir.exists():
            shutil.rmtree(person_photos_dir, ignore_errors=True)

        logger.info("Deleted registered person ID: %s", person_id)
        return True


    def get_all_people(self) -> List[dict]:
        """Return all registered personnel records."""
        with self._lock:
            return list(self._metadata.values())

    def get_person(self, person_id: str) -> Optional[dict]:
        """Get a specific person record."""
        with self._lock:
            return self._metadata.get(person_id)

    def identify_face_embedding(self, query_embedding: np.ndarray, threshold: float = KNOWN_THRESHOLD) -> Tuple[Optional[dict], float, str]:
        """
        Compare query embedding against registered gallery.
        Returns (person_metadata or None, score, 'KNOWN_PERSON' | 'UNKNOWN_PERSON').
        """
        with self._lock:
            gallery_copy = dict(self._gallery)
            metadata_copy = dict(self._metadata)

        if not gallery_copy or query_embedding is None:
            return None, 0.0, "UNKNOWN_PERSON"

        matched_id, score, status = FaceEmbedder.match_against_gallery(
            query_embedding, gallery_copy, threshold=threshold
        )

        if matched_id and status == "KNOWN_PERSON":
            person_info = metadata_copy.get(matched_id)
            return person_info, score, "KNOWN_PERSON"
        else:
            return None, score, "UNKNOWN_PERSON"


# Global singleton instance
face_registry = FaceRegistry()
