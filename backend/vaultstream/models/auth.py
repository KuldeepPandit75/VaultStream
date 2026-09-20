"""User accounts and refresh-token sessions."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vaultstream.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Stored lowercased and uniquely indexed so "A@b.com" and "a@b.com" are the
    # same account.
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_users_email", "email", unique=True),)


class RefreshToken(Base):
    """A refresh-token session.

    The raw token is never stored: only its SHA-256 digest, so a database leak
    does not hand out usable sessions. Tokens are opaque random strings rather
    than JWTs precisely so they can be revoked server-side.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # SHA-256 hex digest of the raw token.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Truncated UA string, so a user can recognise their own sessions.
    user_agent: Mapped[str | None] = mapped_column(String(255))

    user: Mapped[User] = relationship(back_populates="refresh_tokens")

    __table_args__ = (
        Index("ix_refresh_tokens_token_hash", "token_hash", unique=True),
        Index("ix_refresh_tokens_user_id", "user_id"),
        Index("ix_refresh_tokens_expires_at", "expires_at"),
    )

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None
