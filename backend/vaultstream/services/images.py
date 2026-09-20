"""TMDB image URL construction.

The dataset stores bare paths like ``/rhIRbceoE9lR4veEXuwCC2wARtG.jpg``. The
absolute URL is built server-side so the frontend never needs to know the CDN
layout or size conventions.
"""

from __future__ import annotations

from vaultstream.config import get_settings
from vaultstream.schemas.catalog import BACKDROP_SIZE, POSTER_SIZE, PROFILE_SIZE


def _image_url(path: str | None, size: str) -> str | None:
    if not path:
        return None
    base = get_settings().tmdb_image_base.rstrip("/")
    normalised = path if path.startswith("/") else f"/{path}"
    return f"{base}/{size}{normalised}"


def poster_url(path: str | None) -> str | None:
    return _image_url(path, POSTER_SIZE)


def backdrop_url(path: str | None) -> str | None:
    return _image_url(path, BACKDROP_SIZE)


def profile_url(path: str | None) -> str | None:
    return _image_url(path, PROFILE_SIZE)


def imdb_url(imdb_id: str | None) -> str | None:
    if not imdb_id:
        return None
    return f"https://www.imdb.com/title/{imdb_id}/"
