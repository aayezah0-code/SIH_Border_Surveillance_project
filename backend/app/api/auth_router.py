"""
Authentication router — register (OTP initiation), verify-otp, login, and /me endpoints.

Flow:
  POST /register     → Creates a pending registration + sends a 6-digit OTP email.
                       Returns pending_id (no JWT yet, no UserModel row yet).
  POST /verify-otp   → Validates the OTP. On success, creates the UserModel row
                       and returns a JWT token (full login).
  POST /login        → Standard username/password login for existing verified users.
  GET  /me           → Returns current user info (requires Bearer token).
"""
import random
import string
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import UserModel, PendingRegistrationModel
from app.schemas.auth_schemas import (
    LoginRequest,
    RegisterRequest,
    RegisterPendingResponse,
    VerifyOTPRequest,
    TokenResponse,
    UserOut,
)
from app.services.auth_service import (
    hash_password,
    verify_password,
    create_token,
    get_current_user,
    new_user_id,
)
from app.services.email_service import send_otp_email

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])

OTP_EXPIRY_MINUTES = 15


# ─── Helper ───────────────────────────────────────────────────────────────────
def _generate_otp(length: int = 6) -> str:
    """Generate a cryptographically adequate 6-digit OTP."""
    return "".join(random.choices(string.digits, k=length))


def _new_pending_id() -> str:
    return f"pnd_{uuid.uuid4().hex}"


# ─── Register (initiate OTP flow) ─────────────────────────────────────────────
@router.post(
    "/register",
    response_model=RegisterPendingResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    """
    Start the registration process.
    Validates uniqueness, creates a pending record, and sends a 6-digit OTP
    to the user's email. The actual UserModel row is NOT created yet.
    """
    # Check username uniqueness against confirmed users
    if db.query(UserModel).filter(UserModel.username == payload.username).first():
        raise HTTPException(status_code=409, detail="Username already taken")
    # Check email uniqueness against confirmed users
    if db.query(UserModel).filter(UserModel.email == payload.email).first():
        raise HTTPException(status_code=409, detail="Email already registered")

    # Clean up any pre-existing pending record for the same email (allow re-try)
    db.query(PendingRegistrationModel).filter(
        PendingRegistrationModel.email == payload.email
    ).delete()
    db.flush()

    otp_code   = _generate_otp()
    pending_id = _new_pending_id()
    expires_at = datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES)

    pending = PendingRegistrationModel(
        pending_id=pending_id,
        username=payload.username,
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        otp_code=otp_code,
        expires_at=expires_at,
    )
    db.add(pending)
    db.commit()

    # Send OTP email (console fallback if SMTP not configured)
    try:
        send_otp_email(
            to_email=payload.email,
            username=payload.username,
            otp_code=otp_code,
        )
    except RuntimeError as exc:
        # Roll back the pending record so the user can retry
        db.query(PendingRegistrationModel).filter(
            PendingRegistrationModel.pending_id == pending_id
        ).delete()
        db.commit()
        raise HTTPException(
            status_code=502,
            detail="Verification email could not be sent. Please try again.",
        )

    return RegisterPendingResponse(
        pending_id=pending_id,
        email=payload.email,
        message=(
            f"A 6-digit verification code has been sent to {payload.email}. "
            "It is valid for 15 minutes."
        ),
    )


# ─── Verify OTP (complete registration) ───────────────────────────────────────
@router.post("/verify-otp", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def verify_otp(payload: VerifyOTPRequest, db: Session = Depends(get_db)):
    """
    Verify the 6-digit OTP. On success:
      1. Deletes the pending_registrations row.
      2. Creates the real UserModel row.
      3. Returns a JWT token (same as login response).
    """
    pending = (
        db.query(PendingRegistrationModel)
        .filter(PendingRegistrationModel.pending_id == payload.pending_id)
        .first()
    )

    if not pending:
        raise HTTPException(
            status_code=404,
            detail="Verification session not found. Please register again.",
        )

    # Check expiry
    if datetime.utcnow() > pending.expires_at:
        db.delete(pending)
        db.commit()
        raise HTTPException(
            status_code=410,
            detail="Verification code has expired. Please register again.",
        )

    # Check OTP
    if pending.otp_code != payload.otp_code.strip():
        raise HTTPException(status_code=400, detail="Incorrect verification code.")

    # Double-check uniqueness (race condition guard)
    if db.query(UserModel).filter(UserModel.username == pending.username).first():
        db.delete(pending)
        db.commit()
        raise HTTPException(status_code=409, detail="Username already taken.")
    if db.query(UserModel).filter(UserModel.email == pending.email).first():
        db.delete(pending)
        db.commit()
        raise HTTPException(status_code=409, detail="Email already registered.")

    # Create the verified user
    user_id = new_user_id()
    user = UserModel(
        user_id=user_id,
        username=pending.username,
        email=pending.email,
        full_name=pending.full_name,
        hashed_password=pending.hashed_password,
    )
    db.add(user)

    # Remove the pending record
    db.delete(pending)
    db.commit()
    db.refresh(user)

    token = create_token(user.user_id, user.username)
    return TokenResponse(
        access_token=token,
        user=UserOut(
            user_id=user.user_id,
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active,
        ),
    )


# ─── Login ────────────────────────────────────────────────────────────────────
@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    # Allow login by username OR email
    user = (
        db.query(UserModel)
        .filter(
            (UserModel.username == payload.username)
            | (UserModel.email == payload.username)
        )
        .first()
    )
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    # Update last_login
    user.last_login = datetime.utcnow()
    db.commit()

    token = create_token(user.user_id, user.username)
    return TokenResponse(
        access_token=token,
        user=UserOut(
            user_id=user.user_id,
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active,
        ),
    )


# ─── Me (protected) ───────────────────────────────────────────────────────────
@router.get("/me", response_model=UserOut)
def get_me(current_user: UserModel = Depends(get_current_user)):
    return UserOut(
        user_id=current_user.user_id,
        username=current_user.username,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        is_active=current_user.is_active,
    )
