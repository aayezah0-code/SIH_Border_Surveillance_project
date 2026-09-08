"""
SQLAlchemy ORM Models for Sentinel AI Surveillance Platform
------------------------------------------------------------
Defines tables and indexes for:
  1. cameras (CameraSourceModel)
  2. surveillance_sessions (SurveillanceSessionModel)
  3. detection_events (DetectionEventModel)
  4. threat_alerts (ThreatAlertModel)
  5. intrusion_events (IntrusionEventModel)
  6. evidence_snapshots (EvidenceSnapshotModel)
  7. personnel (PersonnelModel)
  8. personnel_images (PersonnelImageModel)
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    Text,
    ForeignKey,
    Index,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


class CameraSourceModel(Base):
    __tablename__ = "cameras"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(String(128), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    location = Column(String(255), nullable=True)
    source_type = Column(String(50), nullable=False, default="RTSP")  # RTSP, FILE, WEBCAM
    uri = Column(String(1024), nullable=True)
    stream_url = Column(String(1024), nullable=True)
    status = Column(String(50), default="CONNECTED")  # CONNECTED, IDLE, PLAYING, STOPPED, ERROR
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    sessions = relationship("SurveillanceSessionModel", back_populates="camera", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "source_id": self.source_id,
            "name": self.name,
            "location": self.location,
            "source_type": self.source_type,
            "uri": self.uri,
            "stream_url": self.stream_url,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class SurveillanceSessionModel(Base):
    __tablename__ = "surveillance_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(128), unique=True, nullable=False, index=True)
    source_id = Column(String(128), ForeignKey("cameras.source_id", ondelete="CASCADE"), nullable=False, index=True)
    camera_name = Column(String(255), nullable=True)
    source_type = Column(String(50), nullable=False, default="RTSP")
    start_time = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    end_time = Column(DateTime, nullable=True)
    status = Column(String(50), default="ACTIVE")  # ACTIVE, COMPLETED, FAILED, TERMINATED
    connection_error = Column(Text, nullable=True)
    total_events = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    camera = relationship("CameraSourceModel", back_populates="sessions")
    detection_events = relationship("DetectionEventModel", back_populates="session", cascade="all, delete-orphan")
    threat_alerts = relationship("ThreatAlertModel", back_populates="session", cascade="all, delete-orphan")
    intrusion_events = relationship("IntrusionEventModel", back_populates="session", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "source_id": self.source_id,
            "camera_name": self.camera_name,
            "source_type": self.source_type,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "status": self.status,
            "connection_error": self.connection_error,
            "total_events": self.total_events,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class DetectionEventModel(Base):
    __tablename__ = "detection_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(128), unique=True, nullable=False, index=True)
    source_id = Column(String(128), nullable=False, index=True)
    session_id = Column(String(128), ForeignKey("surveillance_sessions.session_id", ondelete="SET NULL"), nullable=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    timestamp_sec = Column(Float, default=0.0)
    event_type = Column(String(100), nullable=False, index=True)  # e.g., "Person Movement Detected", "Authorized Personnel Detected"
    object_class = Column(String(100), nullable=False, default="PERSON")
    track_id = Column(Integer, nullable=True, index=True)
    confidence = Column(Float, nullable=True)
    bbox_x1 = Column(Float, nullable=True)
    bbox_y1 = Column(Float, nullable=True)
    bbox_x2 = Column(Float, nullable=True)
    bbox_y2 = Column(Float, nullable=True)
    person_name = Column(String(255), nullable=True, index=True)
    person_role = Column(String(255), nullable=True)
    person_status = Column(String(50), nullable=True)  # KNOWN_PERSON, UNKNOWN_PERSON, N/A
    threat_level = Column(String(50), default="LOW", index=True)  # SAFE, LOW, MEDIUM, HIGH, CRITICAL
    severity = Column(String(50), default="Info")  # Info, Low, Medium, High, Critical
    description = Column(Text, nullable=True)
    evidence_ref = Column(String(512), nullable=True)
    extra_metadata = Column(Text, nullable=True)  # JSON-encoded extra fields
    status = Column(String(50), default="Logged")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    session = relationship("SurveillanceSessionModel", back_populates="detection_events")

    __table_args__ = (
        Index("ix_detection_source_timestamp", "source_id", "timestamp"),
        Index("ix_detection_threat_type", "threat_level", "event_type"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "event_id": self.event_id,
            "source_id": self.source_id,
            "session_id": self.session_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "timestamp_sec": self.timestamp_sec,
            "event_type": self.event_type,
            "object_class": self.object_class,
            "track_id": self.track_id,
            "confidence": self.confidence,
            "person_name": self.person_name,
            "person_role": self.person_role,
            "person_status": self.person_status,
            "threat_level": self.threat_level,
            "severity": self.severity,
            "description": self.description,
            "evidence_ref": self.evidence_ref,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ThreatAlertModel(Base):
    __tablename__ = "threat_alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_id = Column(String(128), unique=True, nullable=False, index=True)
    source_id = Column(String(128), nullable=False, index=True)
    session_id = Column(String(128), ForeignKey("surveillance_sessions.session_id", ondelete="SET NULL"), nullable=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    alert_type = Column(String(150), nullable=False, index=True)  # e.g., "Priority Object Detected — PERSON #1"
    severity = Column(String(50), default="Critical")  # Critical, High, Medium, Safe
    threat_level = Column(String(50), default="HIGH", index=True)
    track_id = Column(Integer, nullable=True, index=True)
    object_class = Column(String(100), default="PERSON")
    person_name = Column(String(255), nullable=True)
    confidence = Column(Float, nullable=True)
    confidence_pct = Column(Integer, nullable=True)
    is_intrusion = Column(Boolean, default=False)
    event_type = Column(String(100), nullable=True)  # zone_intrusion, line_crossing, loitering, priority_person_alert
    camera_label = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    evidence_ref = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    session = relationship("SurveillanceSessionModel", back_populates="threat_alerts")

    def to_dict(self):
        return {
            "id": self.id,
            "alert_id": self.alert_id,
            "source_id": self.source_id,
            "session_id": self.session_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "alert_type": self.alert_type,
            "severity": self.severity,
            "threat_level": self.threat_level,
            "track_id": self.track_id,
            "object_class": self.object_class,
            "person_name": self.person_name,
            "confidence": self.confidence,
            "confidence_pct": self.confidence_pct,
            "is_intrusion": self.is_intrusion,
            "event_type": self.event_type,
            "camera_label": self.camera_label,
            "description": self.description,
            "evidence_ref": self.evidence_ref,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class IntrusionEventModel(Base):
    __tablename__ = "intrusion_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    intrusion_id = Column(String(128), unique=True, nullable=False, index=True)
    source_id = Column(String(128), nullable=False, index=True)
    session_id = Column(String(128), ForeignKey("surveillance_sessions.session_id", ondelete="SET NULL"), nullable=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    timestamp_sec = Column(Float, default=0.0)
    event_type = Column(String(50), nullable=False, index=True)  # zone_intrusion, line_crossing, loitering
    track_id = Column(Integer, nullable=True, index=True)
    object_class = Column(String(100), default="PERSON")
    person_name = Column(String(255), nullable=True)
    person_status = Column(String(50), default="UNKNOWN_PERSON")
    duration_sec = Column(Float, nullable=True)  # For loitering
    threshold_sec = Column(Float, nullable=True) # For loitering
    severity = Column(String(50), default="Critical")
    description = Column(Text, nullable=True)
    evidence_ref = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    session = relationship("SurveillanceSessionModel", back_populates="intrusion_events")

    def to_dict(self):
        return {
            "id": self.id,
            "intrusion_id": self.intrusion_id,
            "source_id": self.source_id,
            "session_id": self.session_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "timestamp_sec": self.timestamp_sec,
            "event_type": self.event_type,
            "track_id": self.track_id,
            "object_class": self.object_class,
            "person_name": self.person_name,
            "person_status": self.person_status,
            "duration_sec": self.duration_sec,
            "threshold_sec": self.threshold_sec,
            "severity": self.severity,
            "description": self.description,
            "evidence_ref": self.evidence_ref,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class EvidenceSnapshotModel(Base):
    __tablename__ = "evidence_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    evidence_id = Column(String(128), unique=True, nullable=False, index=True)
    event_id = Column(String(128), nullable=True, index=True)
    source_id = Column(String(128), nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    timestamp_sec = Column(Float, default=0.0)
    filename = Column(String(255), nullable=False)
    filepath = Column(String(1024), nullable=False)
    url = Column(String(512), nullable=False)
    event_type = Column(String(100), nullable=True, index=True)
    track_id = Column(Integer, nullable=True, index=True)
    object_class = Column(String(100), nullable=True)
    confidence = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "evidence_id": self.evidence_id,
            "event_id": self.event_id,
            "source_id": self.source_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "timestamp_sec": self.timestamp_sec,
            "filename": self.filename,
            "filepath": self.filepath,
            "url": self.url,
            "event_type": self.event_type,
            "track_id": self.track_id,
            "object_class": self.object_class,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class PersonnelModel(Base):
    __tablename__ = "personnel"

    id = Column(Integer, primary_key=True, autoincrement=True)
    person_id = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False, index=True)
    role = Column(String(255), default="Authorized Personnel")
    is_active = Column(Boolean, default=True, index=True)
    registered_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    photos_count = Column(Integer, default=0)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    images = relationship("PersonnelImageModel", back_populates="person", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "person_id": self.person_id,
            "name": self.name,
            "role": self.role,
            "is_active": self.is_active,
            "registered_at": self.registered_at.strftime("%Y-%m-%d %H:%M:%S") if self.registered_at else None,
            "photos_count": self.photos_count,
            "notes": self.notes,
            "photos": [img.filename for img in self.images] if self.images else [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class PersonnelImageModel(Base):
    __tablename__ = "personnel_images"

    id = Column(Integer, primary_key=True, autoincrement=True)
    person_id = Column(String(64), ForeignKey("personnel.person_id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    filepath = Column(String(1024), nullable=False)
    url = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    person = relationship("PersonnelModel", back_populates="images")

    def to_dict(self):
        return {
            "id": self.id,
            "person_id": self.person_id,
            "filename": self.filename,
            "filepath": self.filepath,
            "url": self.url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class UserModel(Base):
    """Application user account for authentication."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), unique=True, nullable=False, index=True)
    username = Column(String(128), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(50), default="operator")  # operator, admin, viewer
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_login = Column(DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "username": self.username,
            "email": self.email,
            "full_name": self.full_name,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
        }


class PendingRegistrationModel(Base):
    """
    Holds in-flight registrations awaiting OTP email verification.
    A row is created on /register and deleted after successful /verify-otp.
    Expired rows are ignored (checked by the verify endpoint).
    """
    __tablename__ = "pending_registrations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # Temporary ID referenced by the verify endpoint
    pending_id = Column(String(64), unique=True, nullable=False, index=True)
    username = Column(String(128), nullable=False)
    email = Column(String(255), nullable=False, index=True)
    full_name = Column(String(255), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    otp_code = Column(String(6), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # OTP expires 15 minutes after creation
    expires_at = Column(DateTime, nullable=False)


class VehicleANPRModel(Base):
    __tablename__ = "vehicle_anpr_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    anpr_id = Column(String(128), unique=True, nullable=False, index=True)
    source_id = Column(String(128), nullable=False, index=True)
    session_id = Column(String(128), ForeignKey("surveillance_sessions.session_id", ondelete="SET NULL"), nullable=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    timestamp_sec = Column(Float, default=0.0)
    track_id = Column(Integer, nullable=True, index=True)
    vehicle_class = Column(String(100), default="CAR", index=True)
    plate_number = Column(String(64), nullable=False, index=True)
    ocr_confidence = Column(Float, nullable=False)
    plate_confidence = Column(Float, nullable=True)
    is_watchlist_match = Column(Boolean, default=False, index=True)
    watchlist_category = Column(String(100), nullable=True)
    evidence_ref = Column(String(512), nullable=True)
    status = Column(String(50), default="Recognized")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_anpr_plate_timestamp", "plate_number", "timestamp"),
        Index("ix_anpr_source_plate", "source_id", "plate_number"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "anpr_id": self.anpr_id,
            "source_id": self.source_id,
            "session_id": self.session_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "timestamp_sec": self.timestamp_sec,
            "track_id": self.track_id,
            "vehicle_class": self.vehicle_class,
            "plate_number": self.plate_number,
            "ocr_confidence": self.ocr_confidence,
            "plate_confidence": self.plate_confidence,
            "is_watchlist_match": self.is_watchlist_match,
            "watchlist_category": self.watchlist_category,
            "evidence_ref": self.evidence_ref,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

