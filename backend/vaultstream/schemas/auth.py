"""Auth request/response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# bcrypt pre-hashing removes the 72-byte ceiling, but an upper bound still keeps
# a pathological input from burning CPU in the KDF.
PASSWORD_MIN = 8
PASSWORD_MAX = 256


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=PASSWORD_MIN, max_length=PASSWORD_MAX)
    display_name: str = Field(min_length=1, max_length=80)

    @field_validator("display_name")
    @classmethod
    def _strip_display_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("display_name must not be blank")
        return stripped

    @field_validator("password")
    @classmethod
    def _reject_whitespace_only(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("password must not be blank")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=PASSWORD_MAX)


class UserOut(BaseModel):
    """Public user representation. Never includes the password hash."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    display_name: str
    created_at: datetime
    last_login_at: datetime | None = None


class SessionOut(BaseModel):
    """Result of register/login/refresh.

    Tokens travel in httpOnly cookies, not in this body. `access_expires_at`
    lets the client schedule a refresh before the access token lapses.
    """

    user: UserOut
    access_expires_at: datetime
