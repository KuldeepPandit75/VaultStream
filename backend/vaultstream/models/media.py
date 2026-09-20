"""Cached TMDB media lookups: current artwork plus trailer keys.

Why this table exists
---------------------
The curated catalogue's ``poster_path`` values date from 2017 and TMDB has since
replaced the underlying files for most popular titles. Measured availability of
the stored paths was 12-37% depending on the slice, and every rendition (w92
through original) 404s, so the files are gone rather than merely resized.

Rather than mutate ``movies.poster_path`` -- which is user-supplied data -- the
refreshed paths live here and are preferred at read time. That keeps the source
data intact and makes the refresh reversible by truncating one table.

Keyed by ``tmdb_id`` so the 1,142 duplicate catalogue rows share a single fetch.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from vaultstream.db import Base

# Resolution outcomes, stored as text for readability in psql.
RESOLUTION_OK = "ok"
RESOLUTION_NOT_FOUND = "not_found"
RESOLUTION_ERROR = "error"


class MovieMedia(Base):
    __tablename__ = "movie_media"

    tmdb_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)

    # Current artwork from TMDB. Null means TMDB itself has none.
    poster_path: Mapped[str | None] = mapped_column(String(255))
    backdrop_path: Mapped[str | None] = mapped_column(String(255))

    # Trailer. `trailer_key` null means TMDB lists no usable video.
    trailer_key: Mapped[str | None] = mapped_column(String(64))
    trailer_site: Mapped[str | None] = mapped_column(String(32))
    trailer_type: Mapped[str | None] = mapped_column(String(32))
    trailer_name: Mapped[str | None] = mapped_column(String(300))

    # ok | not_found | error
    resolution: Mapped[str] = mapped_column(String(16), nullable=False, default=RESOLUTION_OK)
    fetch_error: Mapped[str | None] = mapped_column(Text)

    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Set when TMDB returns 404 for the id, so the backfill never retries it.
    not_found: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        Index("ix_movie_media_resolution", "resolution"),
        Index("ix_movie_media_trailer_key", "trailer_key"),
        Index("ix_movie_media_fetched_at", "fetched_at"),
    )

    @property
    def has_trailer(self) -> bool:
        return bool(self.trailer_key)
