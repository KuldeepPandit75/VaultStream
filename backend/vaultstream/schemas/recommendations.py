"""Recommendation response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field

from vaultstream.schemas.catalog import MovieSummary


class RecommendationRow(BaseModel):
    """One carousel: a stable key, a human title, and its titles.

    ``reason`` is what the UI shows; ``personalised`` lets the client style a
    cold-start row differently from a genuinely personalised one instead of
    passing off popularity as taste.
    """

    key: str
    title: str
    reason: str | None = None
    personalised: bool = True
    # Present on "because you watched" rows.
    seed: MovieSummary | None = None
    items: list[MovieSummary] = Field(default_factory=list)


class RecommendationFeed(BaseModel):
    """Everything the personalised area of the home page needs."""

    rows: list[RecommendationRow] = Field(default_factory=list)
    # False when the user has no usable history yet.
    has_history: bool = False
