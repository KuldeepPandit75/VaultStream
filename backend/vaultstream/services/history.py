"""Watch progress recording and history queries."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from vaultstream.models.catalog import Movie
from vaultstream.models.history import (
    EVENT_COMPLETE,
    EVENT_START,
    WatchEvent,
    WatchProgress,
)
from vaultstream.schemas.history import ResumePoint, WatchProgressOut
from vaultstream.services import media as media_service
from vaultstream.services.catalog import _genre_names_for, _to_summary

# A title counts as watched once most of it has actually been seen.
#
# This is fraction-first on purpose. An earlier rule of "30 seconds OR half"
# was wrong for trailers, whose runtimes vary from ~60s to ~210s: 30 seconds of
# a 208-second trailer is 14%, yet it marked the title finished and removed it
# from Continue Watching.
WATCHED_MIN_FRACTION = 0.85
# Only used when the player never reported a duration.
WATCHED_FALLBACK_SECONDS = 90.0

# Pings below this are noise, not viewing. Browsers block unmuted autoplay, so
# YouTube reports a paused state at position ~0; recording that would create a
# history row (and a recommendation signal) for something never watched.
MIN_RECORDABLE_SECONDS = 3.0

# Below this, a resume point is noise rather than intent.
MIN_RESUME_SECONDS = 5.0
# Within this much of the end, treat it as finished rather than resumable.
END_TOLERANCE_SECONDS = 5.0

# A gap longer than this starts a new viewing session (and a new "start" event).
SESSION_GAP = timedelta(minutes=30)


def is_completed(position: float, duration: float | None) -> bool:
    """Whether enough of the title has been seen to call it watched.

    Fraction-based when the duration is known, so a long trailer is not marked
    finished after a few seconds. Falls back to an absolute threshold only when
    the player never reported a duration.
    """
    if duration and duration > 0:
        return position / duration >= WATCHED_MIN_FRACTION
    return position >= WATCHED_FALLBACK_SECONDS


def percent_complete(position: float, duration: float | None) -> float | None:
    if not duration or duration <= 0:
        return None
    return round(min(position / duration, 1.0) * 100, 1)


class ProgressTooSmall(Exception):
    """Raised when a ping is below the recordable threshold."""


def record_progress(
    session: Session,
    user_id: int,
    row_index: int,
    position_seconds: float,
    duration_seconds: float | None,
) -> WatchProgress | None:
    """Upsert a resume point. Returns None when the movie does not exist.

    Idempotent: the player pings every few seconds and each ping simply
    overwrites the stored position.

    Raises ProgressTooSmall for a position under MIN_RECORDABLE_SECONDS, unless
    progress already exists for the title (in which case an early position is a
    genuine rewind and should be stored).
    """
    movie = session.get(Movie, row_index)
    if movie is None:
        return None

    duration = duration_seconds if duration_seconds and duration_seconds > 0 else None
    # A client clock can overshoot the real duration slightly; clamp it.
    position = max(0.0, position_seconds)
    if duration:
        position = min(position, duration)

    now = datetime.now(timezone.utc)
    existing = session.execute(
        select(WatchProgress).where(
            WatchProgress.user_id == user_id, WatchProgress.row_index == row_index
        )
    ).scalar_one_or_none()

    # Discard the blocked-autoplay artefact: a paused state at position ~0 on a
    # title with no prior progress is not viewing.
    if existing is None and position < MIN_RECORDABLE_SECONDS:
        raise ProgressTooSmall(position)

    completed_now = is_completed(position, duration)
    # Completion is sticky: rewinding after finishing does not un-watch a title.
    completed = completed_now or bool(existing and existing.completed)

    starts_new_session = existing is None or (
        existing.updated_at is not None and now - existing.updated_at > SESSION_GAP
    )
    newly_completed = completed and not (existing and existing.completed)

    statement = insert(WatchProgress).values(
        user_id=user_id,
        row_index=row_index,
        position_seconds=position,
        duration_seconds=duration,
        completed=completed,
        completed_at=now if newly_completed else None,
        updated_at=now,
    )
    statement = statement.on_conflict_do_update(
        index_elements=["user_id", "row_index"],
        set_={
            "position_seconds": statement.excluded.position_seconds,
            # Keep a known duration if this ping happened before it was known.
            "duration_seconds": func.coalesce(
                statement.excluded.duration_seconds, WatchProgress.duration_seconds
            ),
            "completed": statement.excluded.completed,
            "completed_at": func.coalesce(
                WatchProgress.completed_at, statement.excluded.completed_at
            ),
            "updated_at": statement.excluded.updated_at,
        },
    )
    session.execute(statement)

    # Append events sparingly, so the log stays meaningful and bounded.
    if starts_new_session:
        session.add(
            WatchEvent(
                user_id=user_id,
                row_index=row_index,
                event_type=EVENT_START,
                position_seconds=position,
                duration_seconds=duration,
            )
        )
    if newly_completed:
        session.add(
            WatchEvent(
                user_id=user_id,
                row_index=row_index,
                event_type=EVENT_COMPLETE,
                position_seconds=position,
                duration_seconds=duration,
            )
        )

    session.flush()

    # populate_existing is required: the upsert above is a Core statement, so the
    # ORM identity map still holds the pre-update instance and a plain select
    # would hand back the stale row (e.g. completed=False after completing).
    return session.execute(
        select(WatchProgress)
        .where(
            WatchProgress.user_id == user_id, WatchProgress.row_index == row_index
        )
        .execution_options(populate_existing=True)
    ).scalar_one()


def get_resume_point(
    session: Session, user_id: int, row_index: int
) -> ResumePoint | None:
    """Where to start playback, or None when there is nothing worth resuming."""
    record = session.execute(
        select(WatchProgress)
        .where(
            WatchProgress.user_id == user_id, WatchProgress.row_index == row_index
        )
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()

    if record is None:
        return None

    position = record.position_seconds
    # Finished, or effectively at the end: start over rather than resume at the
    # final second.
    if record.duration_seconds and position >= record.duration_seconds - END_TOLERANCE_SECONDS:
        position = 0.0
    elif position < MIN_RESUME_SECONDS:
        position = 0.0

    return ResumePoint(
        row_index=record.row_index,
        position_seconds=position,
        completed=record.completed,
    )


def _attach_movies(
    session: Session, records: list[WatchProgress]
) -> list[WatchProgressOut]:
    """Hydrate progress rows with their movie summaries in two queries."""
    if not records:
        return []

    row_indexes = [record.row_index for record in records]
    movies = {
        movie.row_index: movie
        for movie in session.execute(
            select(Movie).where(Movie.row_index.in_(row_indexes))
        )
        .scalars()
        .all()
    }
    tmdb_ids = [movie.tmdb_id for movie in movies.values()]
    genre_map = _genre_names_for(session, tmdb_ids)
    media_map = media_service.get_cached_many(session, tmdb_ids)

    result: list[WatchProgressOut] = []
    for record in records:
        movie = movies.get(record.row_index)
        if movie is None:
            continue  # movie removed by a reseed; skip rather than fail
        result.append(
            WatchProgressOut(
                row_index=record.row_index,
                position_seconds=record.position_seconds,
                duration_seconds=record.duration_seconds,
                completed=record.completed,
                percent_complete=percent_complete(
                    record.position_seconds, record.duration_seconds
                ),
                updated_at=record.updated_at,
                movie=_to_summary(
                    movie,
                    genre_map.get(movie.tmdb_id, []),
                    media_map.get(movie.tmdb_id),
                ),
            )
        )
    return result


def list_history(
    session: Session, user_id: int, *, limit: int = 50, offset: int = 0
) -> list[WatchProgressOut]:
    """Everything the user has started, most recent first."""
    records = list(
        session.execute(
            select(WatchProgress)
            .where(WatchProgress.user_id == user_id)
            .order_by(WatchProgress.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return _attach_movies(session, records)


def count_history(session: Session, user_id: int) -> int:
    return int(
        session.execute(
            select(func.count())
            .select_from(WatchProgress)
            .where(WatchProgress.user_id == user_id)
        ).scalar_one()
    )


def list_continue_watching(
    session: Session, user_id: int, *, limit: int = 20
) -> list[WatchProgressOut]:
    """Titles worth offering to resume.

    Excludes finished titles, trivial positions, and anything already at the end.
    """
    conditions = [
        WatchProgress.user_id == user_id,
        WatchProgress.completed.is_(False),
        WatchProgress.position_seconds >= MIN_RESUME_SECONDS,
    ]

    records = list(
        session.execute(
            select(WatchProgress)
            .where(*conditions)
            .order_by(WatchProgress.updated_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )

    # Drop rows sitting within a few seconds of the end.
    resumable = [
        record
        for record in records
        if not record.duration_seconds
        or record.position_seconds < record.duration_seconds - END_TOLERANCE_SECONDS
    ]
    return _attach_movies(session, resumable)


def delete_progress(session: Session, user_id: int, row_index: int) -> bool:
    """Remove one title from history. Returns False when nothing was stored."""
    result = session.execute(
        delete(WatchProgress).where(
            WatchProgress.user_id == user_id, WatchProgress.row_index == row_index
        )
    )
    return bool(result.rowcount)


def clear_history(session: Session, user_id: int) -> int:
    """Delete all progress and events for a user. Returns rows of progress removed."""
    session.execute(delete(WatchEvent).where(WatchEvent.user_id == user_id))
    result = session.execute(
        delete(WatchProgress).where(WatchProgress.user_id == user_id)
    )
    return int(result.rowcount or 0)


def watched_row_indexes(session: Session, user_id: int) -> set[int]:
    """Every title the user has started, for excluding from recommendations."""
    return {
        int(value)
        for value in session.execute(
            select(WatchProgress.row_index).where(WatchProgress.user_id == user_id)
        )
        .scalars()
        .all()
    }
