"""Watch history schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from vaultstream.schemas.catalog import MovieSummary


class ProgressUpdate(BaseModel):
    """A progress ping from the player."""

    row_index: int = Field(ge=0)
    position_seconds: float = Field(ge=0, le=86_400)
    # Absent while the player is still buffering and duration is unknown.
    duration_seconds: float | None = Field(default=None, ge=0, le=86_400)


class WatchProgressOut(BaseModel):
    """Stored progress for one title, with the movie attached for rendering."""

    row_index: int
    position_seconds: float
    duration_seconds: float | None = None
    completed: bool
    # 0-100, for the progress bar on a card. None when duration is unknown.
    percent_complete: float | None = None
    updated_at: datetime
    movie: MovieSummary


class ProgressAck(BaseModel):
    """Response to a progress ping. Small on purpose: this is a hot endpoint."""

    row_index: int
    position_seconds: float
    completed: bool
    percent_complete: float | None = None


class ResumePoint(BaseModel):
    """Where playback should start for a title."""

    row_index: int
    position_seconds: float
    completed: bool
