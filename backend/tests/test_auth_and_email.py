"""
Unit and Integration Tests for Sentinel AI Auth & Email Verification System
-----------------------------------------------------------------------------
Tests:
  1. Backend import / startup check
  2. Email service unit tests (dev mode fallback, mocked SMTP connection/auth/send)
  3. Registration flow test (creates pending record, returns pending_id)
  4. OTP verification test (completes registration, issues JWT)
  5. Resend flow test (re-registration replaces pending record)
  6. Expired OTP test (expired token returns 410)
  7. Unverified login test (cannot login before verifying OTP)
  8. Existing verified user login test (login succeeds for verified accounts)
"""

import os
import sys
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

# Ensure project root is in sys.path
from pathlib import Path
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.main import app
from app.db.database import Base, engine, SessionLocal
import app.db.models as _db_models
from app.db.models import UserModel, PendingRegistrationModel
from app.services.email_service import get_smtp_config, send_otp_email
from app.services.auth_service import hash_password

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_test_database(caplog):
    import logging
    caplog.set_level(logging.INFO)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    # Clean up test rows before test
    db.query(PendingRegistrationModel).delete()
    db.query(UserModel).filter(UserModel.username.like("op_test%")).delete()
    db.query(UserModel).filter(UserModel.username.in_(["op_expired", "op_unverified", "op_verified"])).delete()
    db.commit()
    db.close()

    yield

    db = SessionLocal()
    # Clean up test rows after test
    db.query(PendingRegistrationModel).delete()
    db.query(UserModel).filter(UserModel.username.like("op_test%")).delete()
    db.query(UserModel).filter(UserModel.username.in_(["op_expired", "op_unverified", "op_verified"])).delete()
    db.commit()
    db.close()


# ─── 1. Backend Import / Startup Check ────────────────────────────────────────
def test_backend_import_and_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


# ─── 2. Email Service Unit Tests ──────────────────────────────────────────────
def test_email_service_dev_fallback(caplog):
    """When SMTP_USER is empty, send_otp_email uses dev fallback and logs [EMAIL_TRACE]."""
    with patch.dict(os.environ, {"SMTP_USER": "", "SMTP_PASSWORD": ""}):
        send_otp_email("test@example.com", "testuser", "123456")
        assert "[EMAIL_TRACE]" in caplog.text
        assert "Development fallback enabled" in caplog.text


def test_email_service_smtp_success(caplog):
    """Mock successful SMTP server response."""
    with patch.dict(os.environ, {"SMTP_USER": "test@gmail.com", "SMTP_PASSWORD": "app_password_123"}):
        with patch("smtplib.SMTP") as mock_smtp:
            instance = mock_smtp.return_value.__enter__.return_value
            send_otp_email("recipient@example.com", "testuser", "654321")
            instance.login.assert_called_once_with("test@gmail.com", "app_password_123")
            instance.sendmail.assert_called_once()
            assert "[EMAIL_TRACE]" in caplog.text
            assert "accepted by server" in caplog.text


def test_email_service_smtp_auth_failure(caplog):
    """Mock SMTP authentication error."""
    import smtplib
    with patch.dict(os.environ, {"SMTP_USER": "baduser@gmail.com", "SMTP_PASSWORD": "wrongpassword"}):
        with patch("smtplib.SMTP") as mock_smtp:
            instance = mock_smtp.return_value.__enter__.return_value
            instance.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Authentication failed")
            with pytest.raises(RuntimeError) as exc_info:
                send_otp_email("recipient@example.com", "testuser", "654321")
            assert "SMTP authentication failed" in str(exc_info.value)
            assert "[EMAIL_TRACE]" in caplog.text


def test_email_service_smtp_connection_failure(caplog):
    """Mock SMTP connection error."""
    import smtplib
    with patch.dict(os.environ, {"SMTP_USER": "test@gmail.com", "SMTP_PASSWORD": "password"}):
        with patch("smtplib.SMTP") as mock_smtp:
            instance = mock_smtp.return_value.__enter__.return_value
            instance.ehlo.side_effect = smtplib.SMTPConnectError(421, b"Connection refused")
            with pytest.raises(RuntimeError) as exc_info:
                send_otp_email("recipient@example.com", "testuser", "654321")
            assert "SMTP connection failed" in str(exc_info.value)
            assert "[EMAIL_TRACE]" in caplog.text


# ─── 3. Registration Flow Test ────────────────────────────────────────────────
def test_registration_creates_pending_record():
    payload = {
        "username": "op_test1",
        "email": "op_test1@sentinel.ai",
        "password": "password123",
        "full_name": "Test Officer"
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 202
    data = response.json()
    assert "pending_id" in data
    assert data["email"] == payload["email"]
    assert "access_token" not in data  # No JWT on register!

    # Verify pending row exists in DB
    db = SessionLocal()
    pending = db.query(PendingRegistrationModel).filter_by(pending_id=data["pending_id"]).first()
    assert pending is not None
    assert pending.username == payload["username"]
    assert pending.email == payload["email"]
    assert len(pending.otp_code) == 6
    db.close()


# ─── 4. OTP Verification Test ──────────────────────────────────────────────────
def test_otp_verification_creates_user_and_token():
    # Step A: Register
    payload = {
        "username": "op_test2",
        "email": "op_test2@sentinel.ai",
        "password": "password123"
    }
    reg_res = client.post("/api/v1/auth/register", json=payload)
    pending_id = reg_res.json()["pending_id"]

    # Retrieve OTP code from DB
    db = SessionLocal()
    pending = db.query(PendingRegistrationModel).filter_by(pending_id=pending_id).first()
    otp_code = pending.otp_code
    db.close()

    # Step B: Verify OTP
    verify_res = client.post("/api/v1/auth/verify-otp", json={"pending_id": pending_id, "otp_code": otp_code})
    assert verify_res.status_code == 201
    vdata = verify_res.json()
    assert "access_token" in vdata
    assert vdata["user"]["username"] == payload["username"]

    # Verify pending record is deleted & UserModel exists
    db = SessionLocal()
    assert db.query(PendingRegistrationModel).filter_by(pending_id=pending_id).first() is None
    user = db.query(UserModel).filter_by(username=payload["username"]).first()
    assert user is not None
    db.close()


# ─── 5. Resend / Re-registration Test ─────────────────────────────────────────
def test_resend_replaces_old_pending_record():
    payload = {
        "username": "op_test3",
        "email": "op_test3@sentinel.ai",
        "password": "password123"
    }
    res1 = client.post("/api/v1/auth/register", json=payload)
    pid1 = res1.json()["pending_id"]

    # Re-register with same email
    res2 = client.post("/api/v1/auth/register", json=payload)
    pid2 = res2.json()["pending_id"]
    assert pid1 != pid2

    db = SessionLocal()
    # Old pending should be deleted
    assert db.query(PendingRegistrationModel).filter_by(pending_id=pid1).first() is None
    # New pending should exist
    assert db.query(PendingRegistrationModel).filter_by(pending_id=pid2).first() is not None
    db.close()


# ─── 6. Expired OTP Test ──────────────────────────────────────────────────────
def test_expired_otp_returns_410():
    db = SessionLocal()
    pending = PendingRegistrationModel(
        pending_id="pnd_expired_test",
        username="op_expired",
        email="expired@sentinel.ai",
        hashed_password=hash_password("password123"),
        otp_code="112233",
        expires_at=datetime.utcnow() - timedelta(minutes=1),  # Already expired
    )
    db.add(pending)
    db.commit()
    db.close()

    res = client.post("/api/v1/auth/verify-otp", json={"pending_id": "pnd_expired_test", "otp_code": "112233"})
    assert res.status_code == 410
    assert "expired" in res.json()["detail"].lower()


# ─── 7. Unverified Login Test ─────────────────────────────────────────────────
def test_unverified_user_cannot_login():
    # Registering creates pending record, NOT UserModel row
    payload = {
        "username": "op_unverified",
        "email": "unverified@sentinel.ai",
        "password": "password123"
    }
    client.post("/api/v1/auth/register", json=payload)

    # Attempt login without verifying OTP
    login_res = client.post("/api/v1/auth/login", json={"username": "op_unverified", "password": "password123"})
    assert login_res.status_code == 401
    assert "Invalid credentials" in login_res.json()["detail"]


# ─── 8. Existing Verified User Login Test ─────────────────────────────────────
def test_verified_user_login_success():
    # Create verified user directly
    db = SessionLocal()
    user = UserModel(
        user_id="usr_verified_123",
        username="op_verified",
        email="verified@sentinel.ai",
        hashed_password=hash_password("password123"),
        role="operator",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.close()

    login_res = client.post("/api/v1/auth/login", json={"username": "op_verified", "password": "password123"})
    assert login_res.status_code == 200
    ldata = login_res.json()
    assert "access_token" in ldata
    assert ldata["user"]["username"] == "op_verified"
