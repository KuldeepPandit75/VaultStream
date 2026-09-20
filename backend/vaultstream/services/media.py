"""Cache-aware media resolution: current artwork and trailer keys."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from vaultstream.config import get_settings
from vaultstream.models.media import (
    RESOLUTION_ERROR,
    RESOLUTION_NOT_FOUND,
    RESOLUTION_OK,
    MovieMedia,
)
from vaultstream.services.tmdb import (
    MediaPayload,
    TMDBNotConfigured,
    fetch_media_sync,
)

logger = logging.getLogger("vaultstream.media")


def get_cached(session: Session, tmdb_id: int) -> MovieMedia | None:
    return session.get(MovieMedia, tmdb_id)


def get_cached_many(
    session: Session, tmdb_ids: Iterable[int]
) -> dict[int, MovieMedia]:
    """Batch cache read, so a page of results costs one query."""
    ids = {int(value) for value in tmdb_ids}
    if not ids:
        return {}
    rows = session.execute(
        select(MovieMedia).where(MovieMedia.tmdb_id.in_(ids))
    ).scalars()
    return {row.tmdb_id: row for row in rows}


def _payload_to_values(payload: MediaPayload) -> dict[str, object]:
    if payload.not_found:
        resolution = RESOLUTION_NOT_FOUND
    elif payload.error:
        resolution = RESOLUTION_ERROR
    else:
        resolution = RESOLUTION_OK

    return {
        "tmdb_id": payload.tmdb_id,
        "poster_path": payload.poster_path,
        "backdrop_path": payload.backdrop_path,
        "trailer_key": payload.trailer_key,
        "trailer_site": payload.trailer_site,
        "trailer_type": payload.trailer_type,
        "trailer_name": payload.trailer_name,
        "resolution": resolution,
        "fetch_error": payload.error,
        "not_found": payload.not_found,
    }


UPSERT_COLUMNS = (
    "poster_path",
    "backdrop_path",
    "trailer_key",
    "trailer_site",
    "trailer_type",
    "trailer_name",
    "resolution",
    "fetch_error",
    "not_found",
)


def store(session: Session, payloads: Sequence[MediaPayload]) -> int:
    """Upsert resolved media rows. Returns the number submitted."""
    if not payloads:
        return 0

    rows = [_payload_to_values(payload) for payload in payloads]
    statement = insert(MovieMedia)
    statement = statement.on_conflict_do_update(
        index_elements=["tmdb_id"],
        set_={
            **{column: statement.excluded[column] for column in UPSERT_COLUMNS},
            # Refresh the timestamp so staleness is measurable.
            "fetched_at": statement.excluded.fetched_at,
        },
    )
    # fetched_at has a server default; supply it explicitly so the excluded
    # reference above resolves.
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    for row in rows:
        row["fetched_at"] = now

    session.execute(statement, rows)
    return len(rows)


def resolve(session: Session, tmdb_id: int, *, force: bool = False) -> MovieMedia | None:
    """Return cached media, fetching from TMDB on a miss.

    Returns None when TMDB is not configured and nothing is cached, so callers
    can degrade rather than fail.
    """
    cached = None if force else get_cached(session, tmdb_id)
    if cached is not None:
        return cached

    if not get_settings().tmdb_api_key:
        return None

    try:
        payload = fetch_media_sync(tmdb_id)
    except TMDBNotConfigured:
        return None

    store(session, [payload])
    session.commit()
    return get_cached(session, tmdb_id)


def effective_artwork(
    stored_poster: str | None,
    stored_backdrop: str | None,
    media: MovieMedia | None,
) -> tuple[str | None, str | None]:
    """Prefer refreshed TMDB artwork, falling back to the catalogue's own paths.

    The catalogue's 2017 poster paths are mostly dead on TMDB's CDN, so a
    refreshed value always wins. The stored path is still used when no refresh
    has happened yet, since roughly a third of them do still resolve.
    """
    poster = (media.poster_path if media else None) or stored_poster
    backdrop = (media.backdrop_path if media else None) or stored_backdrop
    return poster, backdrop


def coverage(session: Session) -> dict[str, int]:
    """Counts for the backfill report and ops visibility."""
    from sqlalchemy import func

    total = int(
        session.execute(select(func.count()).select_from(MovieMedia)).scalar_one()
    )
    with_poster = int(
        session.execute(
            select(func.count()).select_from(MovieMedia).where(
                MovieMedia.poster_path.isnot(None)
            )
        ).scalar_one()
    )
    with_backdrop = int(
        session.execute(
            select(func.count()).select_from(MovieMedia).where(
                MovieMedia.backdrop_path.isnot(None)
            )
        ).scalar_one()
    )
    with_trailer = int(
        session.execute(
            select(func.count()).select_from(MovieMedia).where(
                MovieMedia.trailer_key.isnot(None)
            )
        ).scalar_one()
    )
    not_found = int(
        session.execute(
            select(func.count()).select_from(MovieMedia).where(
                MovieMedia.not_found.is_(True)
            )
        ).scalar_one()
    )
    errors = int(
        session.execute(
            select(func.count()).select_from(MovieMedia).where(
                MovieMedia.resolution == RESOLUTION_ERROR
            )
        ).scalar_one()
    )
    return {
        "rows": total,
        "with_poster": with_poster,
        "with_backdrop": with_backdrop,
        "with_trailer": with_trailer,
        "not_found": not_found,
        "errors": errors,
    }
