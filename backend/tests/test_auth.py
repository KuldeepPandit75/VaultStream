"""Task 9 acceptance tests: registration, login, refresh rotation, logout."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from vaultstream.api.deps import ACCESS_COOKIE, REFRESH_COOKIE
from vaultstream.config import get_settings
from vaultstream.models.auth import RefreshToken, User
from vaultstream.services import auth as auth_service
from vaultstream.services.security import (
    create_access_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)

CREDENTIALS = {
    "email": "Viewer@Example.com",
    "password": "correct horse battery staple",
    "display_name": "  Viewer  ",
}


def _register(client: TestClient, **overrides: object) -> dict:
    payload = {**CREDENTIALS, **overrides}
    response = client.post("/auth/register", json=payload)
    return {"status": response.status_code, "body": response.json() if response.content else None}


# --------------------------------------------------------------------------- #
# password hashing
# --------------------------------------------------------------------------- #
def test_password_hash_is_salted_and_verifies() -> None:
    first = hash_password("hunter2hunter2")
    second = hash_password("hunter2hunter2")
    assert first != second  # unique salt per hash
    assert verify_password("hunter2hunter2", first)
    assert not verify_password("wrong", first)


def test_password_beyond_bcrypt_72_byte_limit_is_not_truncated() -> None:
    """Without SHA-256 pre-hashing, bcrypt ignores bytes past 72.

    That would make any 72+ byte prefix a valid password, so this asserts two
    long passwords sharing a 72-byte prefix do not collide.
    """
    base = "A" * 72
    stored = hash_password(base + "-genuine-suffix")
    assert verify_password(base + "-genuine-suffix", stored)
    assert not verify_password(base + "-different-suffix", stored)
    assert not verify_password(base, stored)


def test_verify_password_rejects_malformed_stored_hash() -> None:
    """A corrupt hash must fail the login, not raise a 500."""
    assert verify_password("anything", "not-a-bcrypt-hash") is False
    assert verify_password("anything", "") is False


# --------------------------------------------------------------------------- #
# access tokens
# --------------------------------------------------------------------------- #
def test_access_token_round_trips() -> None:
    from vaultstream.services.security import decode_access_token

    token, expires_at = create_access_token(4242)
    assert decode_access_token(token) == 4242
    assert expires_at > datetime.now(timezone.utc)


def test_expired_access_token_is_rejected() -> None:
    from vaultstream.services.security import TokenError, decode_access_token

    settings = get_settings()
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    token = jwt.encode(
        {
            "sub": "1",
            "type": "access",
            "iat": int((past - timedelta(minutes=1)).timestamp()),
            "exp": int(past.timestamp()),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(TokenError, match="expired"):
        decode_access_token(token)


def test_token_signed_with_another_secret_is_rejected() -> None:
    from vaultstream.services.security import TokenError, decode_access_token

    token = jwt.encode(
        {
            "sub": "1",
            "type": "access",
            "exp": int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp()),
        },
        "an-attackers-secret",
        algorithm="HS256",
    )
    with pytest.raises(TokenError):
        decode_access_token(token)


def test_wrong_token_type_is_rejected() -> None:
    """A refresh-shaped token must not be usable as an access token."""
    from vaultstream.services.security import TokenError, decode_access_token

    settings = get_settings()
    token = jwt.encode(
        {
            "sub": "1",
            "type": "refresh",
            "exp": int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp()),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(TokenError, match="token type"):
        decode_access_token(token)


# --------------------------------------------------------------------------- #
# registration
# --------------------------------------------------------------------------- #
def test_register_creates_account_and_session(db_client: TestClient) -> None:
    result = _register(db_client)

    assert result["status"] == 201
    body = result["body"]
    assert body["user"]["email"] == "viewer@example.com"  # normalised to lowercase
    assert body["user"]["display_name"] == "Viewer"  # trimmed
    assert "access_expires_at" in body

    assert ACCESS_COOKIE in db_client.cookies
    assert REFRESH_COOKIE in db_client.cookies


def test_register_never_returns_the_password_hash(db_client: TestClient) -> None:
    body = _register(db_client)["body"]
    serialised = str(body)
    assert "password" not in serialised
    assert "hash" not in serialised


def test_duplicate_email_is_rejected_case_insensitively(db_client: TestClient) -> None:
    assert _register(db_client)["status"] == 201
    again = _register(db_client, email="VIEWER@example.COM")
    assert again["status"] == 409
    assert "already registered" in again["body"]["detail"]


def test_register_validates_input(db_client: TestClient) -> None:
    assert _register(db_client, email="not-an-email")["status"] == 422
    assert _register(db_client, password="short")["status"] == 422
    assert _register(db_client, display_name="   ")["status"] == 422
    assert _register(db_client, password="        ")["status"] == 422


def test_password_is_stored_hashed(db_client: TestClient, db_session: Session) -> None:
    _register(db_client)
    user = db_session.execute(
        select(User).where(User.email == "viewer@example.com")
    ).scalar_one()

    assert user.password_hash != CREDENTIALS["password"]
    assert user.password_hash.startswith("$2b$")
    assert verify_password(CREDENTIALS["password"], user.password_hash)


# --------------------------------------------------------------------------- #
# login
# --------------------------------------------------------------------------- #
def test_login_succeeds_and_stamps_last_login(
    db_client: TestClient, db_session: Session
) -> None:
    _register(db_client)
    db_client.cookies.clear()

    response = db_client.post(
        "/auth/login",
        json={"email": "viewer@example.com", "password": CREDENTIALS["password"]},
    )
    assert response.status_code == 200
    assert response.json()["user"]["last_login_at"] is not None
    assert ACCESS_COOKIE in db_client.cookies


def test_login_with_wrong_password_is_401(db_client: TestClient) -> None:
    _register(db_client)
    response = db_client.post(
        "/auth/login",
        json={"email": "viewer@example.com", "password": "definitely wrong"},
    )
    assert response.status_code == 401


def test_login_for_unknown_email_is_indistinguishable(db_client: TestClient) -> None:
    """Identical response for unknown account and wrong password."""
    _register(db_client)

    unknown = db_client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "whatever123"}
    )
    wrong = db_client.post(
        "/auth/login", json={"email": "viewer@example.com", "password": "whatever123"}
    )
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]


def test_disabled_account_cannot_log_in(
    db_client: TestClient, db_session: Session
) -> None:
    _register(db_client)
    user = db_session.execute(
        select(User).where(User.email == "viewer@example.com")
    ).scalar_one()
    user.is_active = False
    db_session.flush()

    response = db_client.post(
        "/auth/login",
        json={"email": "viewer@example.com", "password": CREDENTIALS["password"]},
    )
    assert response.status_code == 403


# --------------------------------------------------------------------------- #
# /auth/me
# --------------------------------------------------------------------------- #
def test_me_returns_the_signed_in_user(db_client: TestClient) -> None:
    _register(db_client)
    response = db_client.get("/auth/me")
    assert response.status_code == 200
    assert response.json()["email"] == "viewer@example.com"


def test_me_without_a_session_is_401(db_client: TestClient) -> None:
    response = db_client.get("/auth/me")
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"


def test_me_accepts_a_bearer_header(db_client: TestClient, db_session: Session) -> None:
    _register(db_client)
    user = db_session.execute(
        select(User).where(User.email == "viewer@example.com")
    ).scalar_one()
    db_client.cookies.clear()

    token, _ = create_access_token(user.id)
    response = db_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200


def test_me_rejects_a_token_for_a_deleted_user(db_client: TestClient) -> None:
    token, _ = create_access_token(999_999)
    response = db_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


# --------------------------------------------------------------------------- #
# refresh rotation
# --------------------------------------------------------------------------- #
def test_refresh_rotates_the_token(db_client: TestClient) -> None:
    _register(db_client)
    original = db_client.cookies.get(REFRESH_COOKIE)

    response = db_client.post("/auth/refresh")
    assert response.status_code == 200

    rotated = db_client.cookies.get(REFRESH_COOKIE)
    assert rotated is not None
    assert rotated != original  # single-use


def test_refresh_without_a_cookie_is_401(db_client: TestClient) -> None:
    response = db_client.post("/auth/refresh")
    assert response.status_code == 401
    assert "No refresh token" in response.json()["detail"]


def test_reusing_a_rotated_token_revokes_every_session(
    db_client: TestClient, db_session: Session
) -> None:
    """Replay of a spent token is treated as theft: kill the whole family."""
    _register(db_client)
    stolen = db_client.cookies.get(REFRESH_COOKIE)

    assert db_client.post("/auth/refresh").status_code == 200  # rotates `stolen`

    db_client.cookies.set(REFRESH_COOKIE, stolen)
    replay = db_client.post("/auth/refresh")
    assert replay.status_code == 401
    assert "already been used" in replay.json()["detail"]

    live = db_session.execute(
        select(RefreshToken).where(RefreshToken.revoked_at.is_(None))
    ).scalars().all()
    assert live == []


def test_refresh_with_an_expired_token_is_401(
    db_client: TestClient, db_session: Session
) -> None:
    _register(db_client)
    raw = db_client.cookies.get(REFRESH_COOKIE)

    record = db_session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw))
    ).scalar_one()
    record.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.flush()

    response = db_client.post("/auth/refresh")
    assert response.status_code == 401
    assert "expired" in response.json()["detail"]


def test_refresh_token_is_stored_only_as_a_digest(
    db_client: TestClient, db_session: Session
) -> None:
    _register(db_client)
    raw = db_client.cookies.get(REFRESH_COOKIE)

    stored = db_session.execute(select(RefreshToken.token_hash)).scalars().all()
    assert raw not in stored
    assert hash_refresh_token(raw) in stored


# --------------------------------------------------------------------------- #
# logout
# --------------------------------------------------------------------------- #
def test_logout_revokes_the_session(
    db_client: TestClient, db_session: Session
) -> None:
    _register(db_client)
    raw = db_client.cookies.get(REFRESH_COOKIE)

    assert db_client.post("/auth/logout").status_code == 204

    record = db_session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw))
    ).scalar_one()
    assert record.revoked_at is not None


def test_logout_is_idempotent_without_a_session(db_client: TestClient) -> None:
    assert db_client.post("/auth/logout").status_code == 204


def test_logout_all_revokes_every_session(
    db_client: TestClient, db_session: Session
) -> None:
    _register(db_client)
    user = db_session.execute(
        select(User).where(User.email == "viewer@example.com")
    ).scalar_one()
    # A second device.
    auth_service.issue_refresh_token(db_session, user, "another-device")
    db_session.flush()

    assert db_client.post("/auth/logout-all").status_code == 204

    live = db_session.execute(
        select(RefreshToken).where(RefreshToken.revoked_at.is_(None))
    ).scalars().all()
    assert live == []


def test_logout_all_requires_authentication(db_client: TestClient) -> None:
    assert db_client.post("/auth/logout-all").status_code == 401


# --------------------------------------------------------------------------- #
# cookie attributes
# --------------------------------------------------------------------------- #
def test_session_cookies_are_httponly_and_scoped(db_client: TestClient) -> None:
    response = db_client.post("/auth/register", json=CREDENTIALS)
    cookie_headers = response.headers.get_list("set-cookie")

    access = next(h for h in cookie_headers if h.startswith(f"{ACCESS_COOKIE}="))
    refresh = next(h for h in cookie_headers if h.startswith(f"{REFRESH_COOKIE}="))

    for header in (access, refresh):
        assert "HttpOnly" in header
        assert "SameSite=lax" in header.replace("samesite", "SameSite")

    assert "Path=/;" in access or access.rstrip().endswith("Path=/")
    # The long-lived credential is not sent with ordinary catalogue requests.
    assert "Path=/auth" in refresh


# --------------------------------------------------------------------------- #
# service-level behaviour
# --------------------------------------------------------------------------- #
def test_purge_expired_tokens(db_session: Session) -> None:
    user = auth_service.register(
        db_session, "purge@example.com", "a-good-password", "Purge"
    )
    raw = auth_service.issue_refresh_token(db_session, user)
    record = db_session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw))
    ).scalar_one()
    record.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.flush()

    assert auth_service.purge_expired_tokens(db_session) == 1


def test_normalise_email() -> None:
    assert auth_service.normalise_email("  Mixed@Case.COM ") == "mixed@case.com"
