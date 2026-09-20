"""Authentication endpoints.

Tokens are delivered as httpOnly cookies rather than in the response body, so
JavaScript on the page cannot read them and an XSS bug cannot exfiltrate a
session.

SameSite=Lax is sufficient in development because `localhost:3000` and
`localhost:8000` differ only by port, and the same-site check is based on the
registrable domain rather than the port. For a cross-site deployment this must
become SameSite=None with Secure, plus CSRF protection.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from vaultstream.api.deps import ACCESS_COOKIE, REFRESH_COOKIE, CurrentUser
from vaultstream.config import get_settings
from vaultstream.db import get_db
from vaultstream.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    SessionOut,
    UserOut,
)
from vaultstream.services import auth as auth_service
from vaultstream.services.security import create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookies(
    response: Response, access_token: str, refresh_token: str
) -> None:
    settings = get_settings()

    response.set_cookie(
        ACCESS_COOKIE,
        access_token,
        max_age=settings.access_token_ttl_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
        domain=settings.cookie_domain,
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=settings.refresh_token_ttl_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        # Scoped to the refresh endpoints only, so the long-lived credential is
        # not attached to every catalogue request.
        path="/auth",
        domain=settings.cookie_domain,
    )


def _clear_session_cookies(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        ACCESS_COOKIE, path="/", domain=settings.cookie_domain, httponly=True,
        samesite="lax", secure=settings.cookie_secure,
    )
    response.delete_cookie(
        REFRESH_COOKIE, path="/auth", domain=settings.cookie_domain, httponly=True,
        samesite="lax", secure=settings.cookie_secure,
    )


def _establish_session(
    response: Response,
    db: Session,
    user,  # noqa: ANN001 - vaultstream.models.auth.User
    user_agent: str | None,
) -> datetime:
    access_token, access_expires_at = create_access_token(user.id)
    refresh_token = auth_service.issue_refresh_token(db, user, user_agent)
    _set_session_cookies(response, access_token, refresh_token)
    return access_expires_at


@router.post(
    "/register",
    response_model=SessionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account and sign in",
    responses={409: {"description": "Email already registered"}},
)
def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> SessionOut:
    try:
        user = auth_service.register(
            db, payload.email, payload.password, payload.display_name
        )
    except auth_service.EmailAlreadyRegistered as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That email address is already registered.",
        ) from exc

    expires_at = _establish_session(
        response, db, user, request.headers.get("User-Agent")
    )
    db.commit()
    db.refresh(user)
    return SessionOut(user=UserOut.model_validate(user), access_expires_at=expires_at)


@router.post(
    "/login",
    response_model=SessionOut,
    summary="Sign in",
    responses={401: {"description": "Invalid credentials"}},
)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> SessionOut:
    try:
        user = auth_service.authenticate(db, payload.email, payload.password)
    except auth_service.InvalidCredentials as exc:
        # Deliberately identical for unknown email and wrong password.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        ) from exc
    except auth_service.AccountDisabled as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been disabled.",
        ) from exc

    expires_at = _establish_session(
        response, db, user, request.headers.get("User-Agent")
    )
    db.commit()
    db.refresh(user)
    return SessionOut(user=UserOut.model_validate(user), access_expires_at=expires_at)


@router.post(
    "/refresh",
    response_model=SessionOut,
    summary="Exchange the refresh cookie for a new session",
    responses={401: {"description": "Missing, expired, or already-used token"}},
)
def refresh(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> SessionOut:
    raw_token = request.cookies.get(REFRESH_COOKIE)
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token supplied.",
        )

    try:
        user, new_refresh = auth_service.rotate_refresh_token(
            db, raw_token, request.headers.get("User-Agent")
        )
    except auth_service.InvalidRefreshToken as exc:
        db.commit()  # persist any revocations made during theft detection
        _clear_session_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc

    access_token, expires_at = create_access_token(user.id)
    _set_session_cookies(response, access_token, new_refresh)
    db.commit()
    db.refresh(user)
    return SessionOut(user=UserOut.model_validate(user), access_expires_at=expires_at)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Sign out")
def logout(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Idempotent: succeeds even with no session, so the client can always clear."""
    raw_token = request.cookies.get(REFRESH_COOKIE)
    if raw_token:
        auth_service.revoke_refresh_token(db, raw_token)
        db.commit()

    _clear_session_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserOut, summary="The signed-in user")
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.post(
    "/logout-all",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke every session for the signed-in user",
)
def logout_all(
    user: CurrentUser,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    auth_service.revoke_all_for_user(db, user.id)
    db.commit()
    _clear_session_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
