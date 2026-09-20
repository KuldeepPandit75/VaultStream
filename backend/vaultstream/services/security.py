"""Password hashing and JWT access tokens.

Password hashing notes
----------------------
bcrypt is used directly. passlib is deliberately avoided: it is unmaintained
(last release 2020) and raises on bcrypt >= 4.1 because it reads the removed
``bcrypt.__about__`` attribute.

bcrypt silently ignores input beyond 72 bytes, which would make
``"<72 chars>" + anything`` an accepted password for an account created with a
longer secret. Passwords are therefore pre-hashed with SHA-256 and base64-encoded
first, giving a fixed 44-byte input. This is the same approach Django takes.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from vaultstream.config import get_settings

ACCESS_TOKEN_TYPE = "access"

# Length of the opaque refresh token, in bytes of entropy.
REFRESH_TOKEN_BYTES = 48


class TokenError(Exception):
    """Raised when an access token is missing, malformed, or expired."""


def _prepare_password(password: str) -> bytes:
    """SHA-256 + base64 so bcrypt never silently truncates a long password."""
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.b64encode(digest)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prepare_password(password), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare_password(password), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        # Malformed stored hash: treat as a failed login rather than a 500.
        return False


def create_access_token(user_id: int) -> tuple[str, datetime]:
    """Return (token, expiry). Short-lived and stateless."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.access_token_ttl_minutes)

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": ACCESS_TOKEN_TYPE,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": secrets.token_urlsafe(16),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_at


def decode_access_token(token: str) -> int:
    """Return the user id, or raise TokenError."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub", "type"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Access token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("Access token is invalid.") from exc

    # Reject a refresh-shaped token presented as an access token.
    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise TokenError("Wrong token type.")

    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TokenError("Access token subject is malformed.") from exc


def generate_refresh_token() -> tuple[str, str, datetime]:
    """Return (raw_token, sha256_hex, expires_at).

    The raw value goes to the client; only the digest is persisted.
    """
    settings = get_settings()
    raw = secrets.token_urlsafe(REFRESH_TOKEN_BYTES)
    expires_at = datetime.now(timezone.utc) + timedelta(
        days=settings.refresh_token_ttl_days
    )
    return raw, hash_refresh_token(raw), expires_at


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
