"""Watch progress and the watch-event log.

Two tables, two jobs:

``watch_progress`` holds exactly one row per (user, title) and answers "where
was I?" for Continue Watching. It is upserted on every progress ping.

``watch_events`` is an append-only log. It is deliberately NOT written on every
ping -- a 5-second poll would generate thousands of rows per user per hour.
Events are recorded when a viewing session starts and when a title is completed,
which is enough to distinguish a rewatch from a resume and to weight
recommendations by recency without the progress row overwriting that history.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from vaultstream.db import Base

# Event kinds.
EVENT_START = "start"
EVENT_COMPLETE = "complete"


class WatchProgress(Base):
    """Resume point for one user and one catalogue row."""

    __tablename__ = "watch_progress"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # The catalogue primary key, so progress is unambiguous even though
    # tmdb_id repeats across rows.
    row_index: Mapped[int] = mapped_column(
        ForeignKey("movies.row_index", ondelete="CASCADE"), nullable=False
    )

    position_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    duration_seconds: Mapped[float | None] = mapped_column(Float)

    # True once the watched threshold is crossed; drives "already watched"
    # exclusion in recommendations.
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    first_watched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        # One resume point per user per title; also the upsert conflict target.
        UniqueConstraint("user_id", "row_index", name="uq_watch_progress_user_movie"),
        # Continue Watching reads by user ordered by recency.
        Index("ix_watch_progress_user_updated", "user_id", "updated_at"),
        Index("ix_watch_progress_row_index", "row_index"),
    )


class WatchEvent(Base):
    """Append-only record of session starts and completions."""

    __tablename__ = "watch_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    row_index: Mapped[int] = mapped_column(
        ForeignKey("movies.row_index", ondelete="CASCADE"), nullable=False
    )

    # "start" | "complete"
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    position_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    duration_seconds: Mapped[float | None] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_watch_events_user_created", "user_id", "created_at"),
        Index("ix_watch_events_row_index", "row_index"),
    )
