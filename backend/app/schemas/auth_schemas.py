"""
Pydantic schemas for Authentication endpoints.
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)
    full_name: Optional[str] = Field(None, max_length=255)


class RegisterPendingResponse(BaseModel):
    """Returned by /register — tells the client to proceed to OTP verification."""
    pending_id: str
    email: str
    message: str = "Verification code sent to your email."


class VerifyOTPRequest(BaseModel):
    pending_id: str
    otp_code: str = Field(..., min_length=6, max_length=6)


class LoginRequest(BaseModel):
    username: str  # accepts username OR email
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class UserOut(BaseModel):
    user_id: str
    username: str
    email: str
    full_name: Optional[str]
    role: str
    is_active: bool

    class Config:
        from_attributes = True


TokenResponse.model_rebuild()
