"""Cached OMDb API responses.

Keyed by ``imdb_id`` so that repeat visits to the same movie detail page
don't consume the daily OMDb request budget (1,000 on the free tier).
A 24-hour TTL keeps ratings reasonably fresh without hammering the API.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from vaultstream.db import Base


class OmdbCache(Base):
    __tablename__ = "omdb_cache"

    imdb_id: Mapped[str] = mapped_column(String(16), primary_key=True)

    # Full OMDb JSON response stored as text so we don't lose fields
    # when the upstream schema changes.
    data: Mapped[str] = mapped_column(Text, nullable=False)

    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_omdb_cache_fetched_at", "fetched_at"),
    )
