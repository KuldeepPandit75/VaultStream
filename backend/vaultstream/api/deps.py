"""Shared API dependencies, including authentication."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from vaultstream.db import get_db
from vaultstream.models.auth import User
from vaultstream.services import auth as auth_service
from vaultstream.services.security import TokenError, decode_access_token

ACCESS_COOKIE = "vs_access"
REFRESH_COOKIE = "vs_refresh"

UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Authentication required.",
    headers={"WWW-Authenticate": "Bearer"},
)


def _token_from_request(request: Request) -> str | None:
    """Prefer the cookie; accept a bearer header for API clients and tests."""
    cookie = request.cookies.get(ACCESS_COOKIE)
    if cookie:
        return cookie

    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return None


def get_current_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """Resolve the signed-in user, or raise 401."""
    token = _token_from_request(request)
    if not token:
        raise UNAUTHENTICATED

    try:
        user_id = decode_access_token(token)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = auth_service.get_user(db, user_id)
    if user is None or not user.is_active:
        raise UNAUTHENTICATED
    return user


def get_optional_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> User | None:
    """Like get_current_user but returns None instead of raising.

    Used by endpoints that personalise when signed in but still work anonymously.
    """
    token = _token_from_request(request)
    if not token:
        return None
    try:
        user_id = decode_access_token(token)
    except TokenError:
        return None
    user = auth_service.get_user(db, user_id)
    return user if user is not None and user.is_active else None


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]
