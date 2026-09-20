"""ORM models.

Every model module must be imported here so that Alembic autogenerate and
``Base.metadata.create_all`` see the full schema.
"""

from __future__ import annotations

from vaultstream.models.auth import RefreshToken, User
from vaultstream.models.catalog import (
    Collection,
    Genre,
    Keyword,
    Movie,
    MovieCredit,
    MovieGenre,
    MovieKeyword,
    MovieLink,
    Person,
)
from vaultstream.models.history import WatchEvent, WatchProgress
from vaultstream.models.media import MovieMedia
from vaultstream.models.omdb import OmdbCache

__all__ = [
    "RefreshToken",
    "User",
    "WatchEvent",
    "WatchProgress",
    "Collection",
    "Genre",
    "Keyword",
    "Movie",
    "MovieCredit",
    "MovieGenre",
    "MovieKeyword",
    "MovieLink",
    "MovieMedia",
    "OmdbCache",
    "Person",
]
