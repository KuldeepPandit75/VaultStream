"""Schemas for people (cast/crew) and collections."""

from __future__ import annotations

from pydantic import BaseModel

from vaultstream.schemas.catalog import MovieSummary

# TMDB gender encoding.
GENDER_LABELS = {0: None, 1: "Female", 2: "Male", 3: "Non-binary"}


class PersonCredit(BaseModel):
    """One filmography entry."""

    row_index: int
    tmdb_id: int
    title: str
    release_year: int | None = None
    poster_url: str | None = None
    vote_average: float | None = None
    # Character for cast credits, job title for crew credits.
    role: str | None = None
    credit_type: str
    department: str | None = None


class PersonDetail(BaseModel):
    """A person plus their filmography.

    The source dataset carries only id, name, profile image and gender for
    people -- there is no biography, birthday or birthplace -- so this is
    deliberately a filmography-centric view rather than a biography page.
    """

    id: int
    name: str
    profile_url: str | None = None
    gender: str | None = None
    # Department they appear in most often, e.g. "Acting" or "Directing".
    known_for: str | None = None
    cast_count: int = 0
    crew_count: int = 0
    cast_credits: list[PersonCredit] = []
    crew_credits: list[PersonCredit] = []


class CollectionDetail(BaseModel):
    """A franchise and its member titles, in release order."""

    id: int
    name: str | None = None
    poster_url: str | None = None
    backdrop_url: str | None = None
    movies: list[MovieSummary] = []
