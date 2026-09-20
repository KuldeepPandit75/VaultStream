"""TMDB API client and response parsing.

One request per movie retrieves current artwork *and* the trailer list:
``GET /movie/{tmdb_id}?append_to_response=videos``. That keeps the full-catalogue
refresh to ~44k requests rather than double.

Rate limits: TMDB disabled the old 40-per-10-seconds cap in Dec 2019 and now
documents a ceiling "in the 40 requests per second range", with 429 on breach.
We stay under that and honour Retry-After.
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field
from typing import Any

import httpx

from vaultstream.config import get_settings

logger = logging.getLogger("vaultstream.tmdb")

# Kept below TMDB's documented ~40 req/s ceiling.
DEFAULT_CONCURRENCY = 16
MAX_RETRIES = 4

# Trailer preference, best first. "Official" trailers win over fan uploads, and
# a full trailer beats a teaser, which beats an arbitrary clip.
VIDEO_TYPE_PRIORITY = ("Trailer", "Teaser", "Clip", "Featurette")


class TMDBAuthError(RuntimeError):
    """Raised when TMDB rejects the configured credentials."""


class TMDBNotConfigured(RuntimeError):
    """Raised when no TMDB credential is configured."""


@dataclass(slots=True)
class CastProfile:
    """A cast/crew member's id and current TMDB profile image path."""

    person_id: int
    profile_path: str | None


@dataclass(slots=True)
class MediaPayload:
    """Parsed subset of a TMDB movie response."""

    tmdb_id: int
    poster_path: str | None = None
    backdrop_path: str | None = None
    trailer_key: str | None = None
    trailer_site: str | None = None
    trailer_type: str | None = None
    trailer_name: str | None = None
    # Present only when the request appended `credits`; refreshes cast/crew photos.
    profiles: list[CastProfile] = field(default_factory=list)
    not_found: bool = False
    error: str | None = None

    @property
    def ok(self) -> bool:
        return not self.not_found and self.error is None


def _auth(api_key: str) -> tuple[dict[str, str], dict[str, str]]:
    """Return (headers, params) for either credential style.

    TMDB issues two credentials: a short v3 API key passed as a query parameter,
    and a long v4 read access token (a JWT) passed as a bearer header. Accept
    both so users can paste whichever they find first.
    """
    if api_key.startswith("eyJ"):  # JWT => v4 read access token
        return {"Authorization": f"Bearer {api_key}"}, {}
    return {}, {"api_key": api_key}


def select_trailer(videos: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pick the most appropriate YouTube video, or None.

    Ordering: official before unofficial, then by type priority, then by
    published date so the newest official trailer wins.
    """
    candidates = [
        video
        for video in videos
        if isinstance(video, dict)
        and video.get("site") == "YouTube"
        and video.get("key")
        and video.get("type") in VIDEO_TYPE_PRIORITY
    ]
    if not candidates:
        return None

    def sort_key(video: dict[str, Any]) -> tuple[int, int, str]:
        official = 0 if video.get("official") else 1
        try:
            type_rank = VIDEO_TYPE_PRIORITY.index(video.get("type", ""))
        except ValueError:
            type_rank = len(VIDEO_TYPE_PRIORITY)
        # Descending publish date: invert by negating via reverse string compare.
        published = video.get("published_at") or ""
        return (official, type_rank, published)

    candidates.sort(key=sort_key)
    # Among equally-ranked entries prefer the newest.
    best_rank = sort_key(candidates[0])[:2]
    same_rank = [v for v in candidates if sort_key(v)[:2] == best_rank]
    same_rank.sort(key=lambda v: v.get("published_at") or "", reverse=True)
    return same_rank[0]


def _parse_profiles(body: dict[str, Any]) -> list[CastProfile]:
    """Extract (person_id, profile_path) for every cast and crew member.

    Present only when the request appended `credits`. One movie call refreshes
    every person's photo for that film, which is far cheaper than one call per
    person: ~44k movie requests versus ~194k person requests for this catalogue.
    """
    credits_block = body.get("credits") or {}
    members = (credits_block.get("cast") or []) + (credits_block.get("crew") or [])

    profiles: dict[int, str | None] = {}
    for member in members:
        if not isinstance(member, dict):
            continue
        person_id = member.get("id")
        if person_id is None:
            continue
        # A person may appear in both cast and crew; keep whichever has a photo.
        existing = profiles.get(person_id)
        candidate = member.get("profile_path")
        if existing is None or (candidate and not existing):
            profiles[person_id] = candidate

    return [
        CastProfile(person_id=person_id, profile_path=path)
        for person_id, path in profiles.items()
    ]


def parse_media_payload(tmdb_id: int, body: dict[str, Any]) -> MediaPayload:
    """Turn a TMDB movie response into a MediaPayload."""
    videos = ((body.get("videos") or {}).get("results")) or []
    trailer = select_trailer(videos)

    return MediaPayload(
        tmdb_id=tmdb_id,
        poster_path=body.get("poster_path") or None,
        backdrop_path=body.get("backdrop_path") or None,
        trailer_key=(trailer or {}).get("key"),
        trailer_site=(trailer or {}).get("site"),
        trailer_type=(trailer or {}).get("type"),
        trailer_name=(trailer or {}).get("name"),
        profiles=_parse_profiles(body),
    )


def _movie_path(tmdb_id: int) -> str:
    return f"/movie/{tmdb_id}"


# `credits` is appended so one request refreshes cast/crew profile photos too.
_REQUEST_PARAMS = {"append_to_response": "videos,credits", "language": "en-US"}


def fetch_media_sync(tmdb_id: int, client: httpx.Client | None = None) -> MediaPayload:
    """Blocking single lookup, for on-demand resolution inside a request."""
    settings = get_settings()
    if not settings.tmdb_api_key:
        raise TMDBNotConfigured(
            "TMDB_API_KEY is not set. Add it to backend/.env to enable artwork "
            "and trailer resolution."
        )

    headers, params = _auth(settings.tmdb_api_key)
    owns_client = client is None
    client = client or httpx.Client(base_url=settings.tmdb_api_base, timeout=15)

    try:
        response = client.get(
            _movie_path(tmdb_id),
            params={**params, **_REQUEST_PARAMS},
            headers=headers,
        )
        if response.status_code == 404:
            return MediaPayload(tmdb_id=tmdb_id, not_found=True)
        if response.status_code in (401, 403):
            raise TMDBAuthError("TMDB rejected the configured credentials.")
        response.raise_for_status()
        return parse_media_payload(tmdb_id, response.json())
    except (TMDBAuthError, TMDBNotConfigured):
        raise
    except httpx.HTTPError as exc:
        return MediaPayload(tmdb_id=tmdb_id, error=f"{type(exc).__name__}: {exc}")
    finally:
        if owns_client:
            client.close()


async def fetch_media_async(
    client: httpx.AsyncClient,
    tmdb_id: int,
    api_key: str,
    semaphore: asyncio.Semaphore,
) -> MediaPayload:
    """Concurrent lookup with retry and 429 backoff, used by the bulk backfill."""
    headers, params = _auth(api_key)

    async with semaphore:
        for attempt in range(MAX_RETRIES):
            try:
                response = await client.get(
                    _movie_path(tmdb_id),
                    params={**params, **_REQUEST_PARAMS},
                    headers=headers,
                )
            except httpx.HTTPError as exc:
                if attempt == MAX_RETRIES - 1:
                    return MediaPayload(
                        tmdb_id=tmdb_id, error=f"{type(exc).__name__}: {exc}"
                    )
                await asyncio.sleep(_backoff(attempt))
                continue

            if response.status_code == 404:
                return MediaPayload(tmdb_id=tmdb_id, not_found=True)

            if response.status_code in (401, 403):
                raise TMDBAuthError("TMDB rejected the configured credentials.")

            if response.status_code == 429:
                # Honour Retry-After when TMDB supplies it.
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else _backoff(attempt)
                logger.warning("TMDB 429; sleeping %.1fs", delay)
                await asyncio.sleep(delay)
                continue

            if response.status_code >= 500:
                if attempt == MAX_RETRIES - 1:
                    return MediaPayload(
                        tmdb_id=tmdb_id, error=f"HTTP {response.status_code}"
                    )
                await asyncio.sleep(_backoff(attempt))
                continue

            try:
                return parse_media_payload(tmdb_id, response.json())
            except ValueError as exc:
                return MediaPayload(tmdb_id=tmdb_id, error=f"Invalid JSON: {exc}")

        return MediaPayload(tmdb_id=tmdb_id, error="Retries exhausted")


def _backoff(attempt: int) -> float:
    """Exponential backoff with jitter, to avoid a synchronised retry storm."""
    return min(2**attempt, 8) + random.random()
