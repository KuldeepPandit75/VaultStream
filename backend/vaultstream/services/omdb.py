"""OMDb API client with database-backed caching.

Fetches extended movie metadata (IMDB rating, Rotten Tomatoes, Metacritic,
awards, content rating, etc.) from the Open Movie Database by ``imdb_id``.

The free tier allows 1,000 requests per day, so every successful response is
cached in ``omdb_cache`` and reused until the configurable TTL expires
(default 24 hours).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import Session

from vaultstream.config import get_settings
from vaultstream.models.omdb import OmdbCache

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class OmdbRating:
    """One rating from the OMDb ``Ratings`` array."""

    source: str
    value: str


@dataclass(slots=True)
class OmdbData:
    """Typed representation of an OMDb response.

    Only fields useful for the detail page are surfaced; the raw JSON is
    kept in the cache for future expansion.
    """

    imdb_rating: float | None = None
    imdb_votes: str | None = None
    rated: str | None = None  # Content rating: PG-13, R, etc.
    awards: str | None = None
    country: str | None = None
    box_office: str | None = None
    production: str | None = None
    dvd: str | None = None
    ratings: list[OmdbRating] = field(default_factory=list)
    metascore: str | None = None
    plot: str | None = None


def _parse_omdb_response(raw: dict) -> OmdbData | None:
    """Parse a raw OMDb JSON dict into an ``OmdbData`` instance.

    Returns ``None`` if the response is not a successful match.
    """
    if raw.get("Response") != "True":
        return None

    # Parse imdb_rating
    imdb_rating: float | None = None
    raw_rating = raw.get("imdbRating")
    if raw_rating and raw_rating != "N/A":
        try:
            imdb_rating = float(raw_rating)
        except (ValueError, TypeError):
            pass

    # Parse ratings array
    ratings: list[OmdbRating] = []
    for entry in raw.get("Ratings", []):
        source = entry.get("Source", "")
        value = entry.get("Value", "")
        if source and value:
            ratings.append(OmdbRating(source=source, value=value))

    def _clean(val: str | None) -> str | None:
        if not val or val == "N/A":
            return None
        return val

    return OmdbData(
        imdb_rating=imdb_rating,
        imdb_votes=_clean(raw.get("imdbVotes")),
        rated=_clean(raw.get("Rated")),
        awards=_clean(raw.get("Awards")),
        country=_clean(raw.get("Country")),
        box_office=_clean(raw.get("BoxOffice")),
        production=_clean(raw.get("Production")),
        dvd=_clean(raw.get("DVD")),
        ratings=ratings,
        metascore=_clean(raw.get("Metascore")),
        plot=_clean(raw.get("Plot")),
    )


def _is_cache_fresh(entry: OmdbCache) -> bool:
    """Check whether a cache entry is within the configured TTL."""
    settings = get_settings()
    ttl = timedelta(hours=settings.omdb_cache_ttl_hours)
    now = datetime.now(timezone.utc)
    fetched = entry.fetched_at
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    return (now - fetched) < ttl


def _fetch_from_api(imdb_id: str) -> dict | None:
    """Call the OMDb API. Returns the raw JSON dict or ``None`` on failure."""
    settings = get_settings()
    if not settings.omdb_api_key:
        return None

    url = settings.omdb_api_base
    params = {"i": imdb_id, "apikey": settings.omdb_api_key, "plot": "short"}

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        logger.warning("OMDb fetch failed for %s: %s", imdb_id, exc)
        return None


def get_omdb_data(session: Session, imdb_id: str) -> OmdbData | None:
    """Fetch OMDb data for the given IMDB ID, using the DB cache.

    Returns ``None`` when:
    - No ``OMDB_API_KEY`` is configured
    - The IMDB ID is missing or invalid
    - The API returns a non-success response
    """
    if not imdb_id:
        return None

    settings = get_settings()
    if not settings.omdb_api_key:
        return None

    # Check cache first
    cached = session.get(OmdbCache, imdb_id)
    if cached and _is_cache_fresh(cached):
        try:
            raw = json.loads(cached.data)
            return _parse_omdb_response(raw)
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("Bad OMDb cache entry for %s: %s", imdb_id, exc)

    # Fetch from API
    raw = _fetch_from_api(imdb_id)
    if raw is None:
        return None

    # Upsert into cache
    json_str = json.dumps(raw, ensure_ascii=False)
    now = datetime.now(timezone.utc)
    if cached:
        cached.data = json_str
        cached.fetched_at = now
    else:
        entry = OmdbCache(imdb_id=imdb_id, data=json_str, fetched_at=now)
        session.add(entry)

    try:
        session.commit()
    except Exception as exc:
        logger.warning("Failed to cache OMDb data for %s: %s", imdb_id, exc)
        session.rollback()

    return _parse_omdb_response(raw)
