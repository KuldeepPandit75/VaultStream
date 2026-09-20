"""Catalog API schemas.

Note on identifiers: the public movie identifier is ``row_index``, the catalog's
primary key, not ``tmdb_id``. The curated catalog contains 1,142 duplicate
tmdb_ids, so tmdb_id does not identify a single row. ``tmdb_id`` is still
returned for cross-referencing TMDB.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")

# TMDB image renditions. w500 is the standard poster size; w1280 suits backdrops.
POSTER_SIZE = "w500"
BACKDROP_SIZE = "w1280"
PROFILE_SIZE = "w185"


class SortField(StrEnum):
    POPULARITY = "popularity"
    RATING = "rating"
    RELEASE_DATE = "release_date"
    TITLE = "title"
    VOTE_COUNT = "vote_count"


class SortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"


class GenreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class KeywordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class CollectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str | None = None
    poster_url: str | None = None
    backdrop_url: str | None = None


class CastMemberOut(BaseModel):
    person_id: int
    name: str
    character: str | None = None
    billing_order: int | None = None
    profile_url: str | None = None


class CrewMemberOut(BaseModel):
    person_id: int
    name: str
    job: str
    department: str | None = None
    profile_url: str | None = None


class MovieSummary(BaseModel):
    """Card-sized payload for grids and carousels."""

    row_index: int
    tmdb_id: int
    title: str
    release_year: int | None = None
    runtime: int | None = None
    vote_average: float | None = None
    vote_count: int | None = None
    popularity: float | None = None
    poster_path: str | None = None
    poster_url: str | None = None
    backdrop_url: str | None = None
    genres: list[str] = Field(default_factory=list)


class StreamSource(BaseModel):
    """Playback source for a title, resolved server-side."""

    row_index: int
    tmdb_id: int
    title: str
    # Only "youtube" today; the field exists so another driver (self-hosted HLS,
    # object storage) can be added without changing the client contract.
    type: str = "youtube"
    key: str
    name: str | None = None
    video_type: str | None = None


class OmdbRatingOut(BaseModel):
    """One rating from the OMDb Ratings array (IMDb / RT / Metacritic)."""

    source: str
    value: str


class OmdbDataOut(BaseModel):
    """Extended metadata from the OMDb API (IMDB, Rotten Tomatoes, etc.)."""

    imdb_rating: float | None = None
    imdb_votes: str | None = None
    rated: str | None = None  # Content rating: PG-13, R, etc.
    awards: str | None = None
    country: str | None = None
    box_office: str | None = None
    production: str | None = None
    dvd: str | None = None
    ratings: list[OmdbRatingOut] = Field(default_factory=list)
    metascore: str | None = None
    plot: str | None = None


class MovieDetail(MovieSummary):
    """Full payload for the detail page."""

    # True when a playable trailer is known to exist for this title.
    has_trailer: bool = False
    imdb_id: str | None = None
    imdb_url: str | None = None
    original_title: str | None = None
    original_language: str | None = None
    tagline: str | None = None
    overview: str | None = None
    release_date: date | None = None
    status: str | None = None
    homepage: str | None = None
    budget: int | None = None
    revenue: int | None = None
    adult: bool = False
    collection: CollectionOut | None = None
    keywords: list[KeywordOut] = Field(default_factory=list)
    cast: list[CastMemberOut] = Field(default_factory=list)
    crew: list[CrewMemberOut] = Field(default_factory=list)
    directors: list[str] = Field(default_factory=list)
    omdb: OmdbDataOut | None = None


class Page(BaseModel, Generic[T]):
    """Offset-paginated envelope."""

    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_prev: bool

    @classmethod
    def build(cls, items: list[T], total: int, page: int, page_size: int) -> Page[T]:
        total_pages = (total + page_size - 1) // page_size if page_size else 0
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        )
