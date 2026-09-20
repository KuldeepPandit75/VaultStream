"""Registration, login, and refresh-token session management."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from functools import lru_cache

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vaultstream.models.auth import RefreshToken, User
from vaultstream.services.security import (
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)

logger = logging.getLogger("vaultstream.auth")


class EmailAlreadyRegistered(Exception):
    pass


class InvalidCredentials(Exception):
    pass


class AccountDisabled(Exception):
    pass


class InvalidRefreshToken(Exception):
    pass


def normalise_email(email: str) -> str:
    return email.strip().lower()


def get_user(session: Session, user_id: int) -> User | None:
    return session.get(User, user_id)


def get_user_by_email(session: Session, email: str) -> User | None:
    return session.execute(
        select(User).where(User.email == normalise_email(email))
    ).scalar_one_or_none()


def register(
    session: Session, email: str, password: str, display_name: str
) -> User:
    """Create an account. Raises EmailAlreadyRegistered on a duplicate."""
    normalised = normalise_email(email)

    if get_user_by_email(session, normalised) is not None:
        raise EmailAlreadyRegistered(normalised)

    user = User(
        email=normalised,
        password_hash=hash_password(password),
        display_name=display_name.strip(),
    )
    session.add(user)
    try:
        session.flush()
    except IntegrityError as exc:
        # Lost a race against a concurrent signup with the same address.
        session.rollback()
        raise EmailAlreadyRegistered(normalised) from exc
    return user


def authenticate(session: Session, email: str, password: str) -> User:
    """Verify credentials and stamp last_login_at."""
    user = get_user_by_email(session, email)

    if user is None:
        # Verify against a throwaway hash anyway so a missing account and a wrong
        # password take a similar amount of time, denying a trivial
        # account-enumeration oracle.
        verify_password(password, _timing_equalisation_hash())
        raise InvalidCredentials()

    if not verify_password(password, user.password_hash):
        raise InvalidCredentials()

    if not user.is_active:
        raise AccountDisabled()

    user.last_login_at = datetime.now(timezone.utc)
    session.flush()
    return user


@lru_cache(maxsize=1)
def _timing_equalisation_hash() -> str:
    """A real bcrypt hash, computed once and lazily.

    Built on first use rather than at import so module import does not pay for a
    bcrypt round.
    """
    return hash_password("timing-equalisation-placeholder")


def issue_refresh_token(
    session: Session, user: User, user_agent: str | None = None
) -> str:
    """Create a session and return the raw token (stored only as a digest)."""
    raw, digest, expires_at = generate_refresh_token()
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=digest,
            expires_at=expires_at,
            user_agent=(user_agent or "")[:255] or None,
        )
    )
    session.flush()
    return raw


def revoke_all_for_user(session: Session, user_id: int) -> int:
    """Revoke every live session for a user. Returns the number revoked."""
    now = datetime.now(timezone.utc)
    result = session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    return int(result.rowcount or 0)


def rotate_refresh_token(
    session: Session, raw_token: str, user_agent: str | None = None
) -> tuple[User, str]:
    """Exchange a refresh token for a new one.

    Rotation on every use means a stolen token is only useful until the real
    client refreshes. Presenting an already-rotated token is treated as evidence
    of theft, so the whole session family for that user is revoked.
    """
    digest = hash_refresh_token(raw_token)
    record = session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == digest)
    ).scalar_one_or_none()

    if record is None:
        raise InvalidRefreshToken("Unknown refresh token.")

    now = datetime.now(timezone.utc)

    if record.revoked_at is not None:
        # Reuse of a rotated token: assume compromise and end all sessions.
        revoked = revoke_all_for_user(session, record.user_id)
        logger.warning(
            "Refresh token reuse detected for user %s; revoked %s sessions",
            record.user_id,
            revoked,
        )
        raise InvalidRefreshToken("Refresh token has already been used.")

    if record.expires_at <= now:
        record.revoked_at = now
        session.flush()
        raise InvalidRefreshToken("Refresh token has expired.")

    user = session.get(User, record.user_id)
    if user is None or not user.is_active:
        record.revoked_at = now
        session.flush()
        raise InvalidRefreshToken("Account is unavailable.")

    record.revoked_at = now
    session.flush()

    return user, issue_refresh_token(session, user, user_agent)


def revoke_refresh_token(session: Session, raw_token: str) -> bool:
    """Revoke one session. Returns False when the token was unknown or already dead."""
    digest = hash_refresh_token(raw_token)
    record = session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == digest)
    ).scalar_one_or_none()

    if record is None or record.revoked_at is not None:
        return False

    record.revoked_at = datetime.now(timezone.utc)
    session.flush()
    return True


def purge_expired_tokens(session: Session) -> int:
    """Delete rows past expiry. Housekeeping; safe to call any time."""
    from sqlalchemy import delete

    result = session.execute(
        delete(RefreshToken).where(
            RefreshToken.expires_at <= datetime.now(timezone.utc)
        )
    )
    return int(result.rowcount or 0)
