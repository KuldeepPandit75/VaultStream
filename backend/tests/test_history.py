"""Task 12 acceptance tests: watch progress, Continue Watching, history."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from etl.clean import CleanReport, CleanedData
from etl.seed import seed
from vaultstream.models.history import (
    EVENT_COMPLETE,
    EVENT_START,
    WatchEvent,
    WatchProgress,
)
from vaultstream.services import auth as auth_service
from vaultstream.services import history as history_service
from vaultstream.services.security import create_access_token

TRAILER_DURATION = 120.0


def _catalog() -> CleanedData:
    rows = [(0, 862, "Toy Story"), (1, 8844, "Jumanji"), (2, 129, "Spirited Away")]
    movies = pd.DataFrame(
        {
            "row_index": [r[0] for r in rows],
            "tmdb_id": [r[1] for r in rows],
            "title": [r[2] for r in rows],
            "original_title": [r[2] for r in rows],
            "imdb_id": [f"tt{r[1]:07d}" for r in rows],
            "tags": ["t"] * len(rows),
            "poster_path": ["/p.jpg"] * len(rows),
            "backdrop_path": [None] * len(rows),
            "release_year": pd.array([1995, 1995, 2001], dtype="Int64"),
            "release_date": pd.to_datetime(["1995-10-30", "1995-12-15", "2001-07-20"]),
            "runtime": [81.0, 104.0, 125.0],
            "vote_average": [7.7, 6.9, 8.3],
            "vote_count": [5000.0, 2000.0, 3000.0],
            "popularity": [21.0, 17.0, 41.0],
            "original_language": ["en", "en", "ja"],
            "status": ["Released"] * len(rows),
            "tagline": [None] * len(rows),
            "overview": ["o"] * len(rows),
            "homepage": [None] * len(rows),
            "budget": [0.0] * len(rows),
            "revenue": [0.0] * len(rows),
            "adult": [False] * len(rows),
            "collection_id": pd.array([None] * len(rows), dtype="Int64"),
        }
    )
    empty = lambda cols: pd.DataFrame({c: pd.Series(dtype="int64") for c in cols})  # noqa: E731
    return CleanedData(
        movies=movies,
        genres=pd.DataFrame({"id": [16], "name": ["Animation"]}),
        movie_genres=pd.DataFrame({"tmdb_id": [862], "genre_id": [16]}),
        keywords=pd.DataFrame(
            {"id": pd.Series(dtype="int64"), "name": pd.Series(dtype="string")}
        ),
        movie_keywords=empty(["tmdb_id", "keyword_id"]),
        people=pd.DataFrame(
            {
                "id": pd.Series(dtype="int64"),
                "name": pd.Series(dtype="string"),
                "profile_path": pd.Series(dtype="object"),
                "gender": pd.Series(dtype="int64"),
            }
        ),
        credits=pd.DataFrame(
            {
                "tmdb_id": pd.Series(dtype="int64"),
                "person_id": pd.Series(dtype="int64"),
                "credit_type": pd.Series(dtype="string"),
                "role": pd.Series(dtype="object"),
                "department": pd.Series(dtype="object"),
                "billing_order": pd.Series(dtype="object"),
            }
        ),
        collections=pd.DataFrame(
            {
                "id": pd.Series(dtype="int64"),
                "name": pd.Series(dtype="object"),
                "poster_path": pd.Series(dtype="object"),
                "backdrop_path": pd.Series(dtype="object"),
            }
        ),
        links=empty(["tmdb_id", "movielens_id", "imdb_numeric_id"]),
        report=CleanReport(),
    )


@pytest.fixture
def api(db_client: TestClient, db_session: Session) -> TestClient:
    """Seeded catalogue plus a signed-in user, authenticated via bearer token."""
    seed(db_session, _catalog(), truncate=True)
    user = auth_service.register(
        db_session, "viewer@example.com", "a-strong-passphrase", "Viewer"
    )
    db_session.flush()

    token, _ = create_access_token(user.id)
    db_client.headers["Authorization"] = f"Bearer {token}"
    return db_client


@pytest.fixture
def user_id(db_session: Session, api: TestClient) -> int:
    from vaultstream.models.auth import User

    return int(
        db_session.execute(
            select(User.id).where(User.email == "viewer@example.com")
        ).scalar_one()
    )


def _ping(api: TestClient, row_index: int, position: float, duration=TRAILER_DURATION):
    return api.post(
        "/history/progress",
        json={
            "row_index": row_index,
            "position_seconds": position,
            "duration_seconds": duration,
        },
    )


# --------------------------------------------------------------------------- #
# threshold logic
# --------------------------------------------------------------------------- #
def test_watched_threshold_is_fraction_based() -> None:
    """Regression: an absolute 30s rule marked long trailers finished at 14%.

    Trailer runtimes vary from ~60s to ~210s, so "watched" has to mean "most of
    it was seen", not "a fixed number of seconds elapsed".
    """
    # 30s of a 208s trailer is 14% - decidedly not watched.
    assert history_service.is_completed(30.0, 208.0) is False
    # Halfway is still not watched.
    assert history_service.is_completed(104.0, 208.0) is False
    # 85% or more is.
    assert history_service.is_completed(177.0, 208.0) is True
    assert history_service.is_completed(208.0, 208.0) is True

    # Short trailer, same rule.
    assert history_service.is_completed(30.0, 62.0) is False
    assert history_service.is_completed(55.0, 62.0) is True

    # Unknown duration falls back to an absolute threshold.
    assert history_service.is_completed(89.0, None) is False
    assert history_service.is_completed(95.0, None) is True


def test_tiny_first_ping_is_not_recorded(
    api: TestClient, db_session: Session, user_id: int
) -> None:
    """Blocked autoplay reports a paused state at ~0; that is not viewing."""
    body = _ping(api, 0, 0.08).json()
    assert body["position_seconds"] == 0.0

    rows = (
        db_session.execute(
            select(WatchProgress).where(WatchProgress.user_id == user_id)
        )
        .scalars()
        .all()
    )
    assert rows == []


def test_rewinding_to_the_start_is_still_recorded(api: TestClient) -> None:
    """Once real progress exists, an early position is a genuine rewind."""
    _ping(api, 0, 40.0)
    body = _ping(api, 0, 1.0).json()
    assert body["position_seconds"] == 1.0


def test_percent_complete_handles_unknown_and_overshoot() -> None:
    assert history_service.percent_complete(30.0, 120.0) == 25.0
    assert history_service.percent_complete(10.0, None) is None
    assert history_service.percent_complete(10.0, 0) is None
    # Never exceeds 100 even if the client clock overshoots.
    assert history_service.percent_complete(130.0, 120.0) == 100.0


# --------------------------------------------------------------------------- #
# recording progress
# --------------------------------------------------------------------------- #
def test_progress_requires_authentication(db_client: TestClient) -> None:
    response = db_client.post(
        "/history/progress", json={"row_index": 0, "position_seconds": 10}
    )
    assert response.status_code == 401


def test_progress_ping_creates_a_resume_point(api: TestClient) -> None:
    body = _ping(api, 0, 12.0).json()
    assert body["row_index"] == 0
    assert body["position_seconds"] == 12.0
    assert body["completed"] is False
    assert body["percent_complete"] == 10.0


def test_repeated_pings_upsert_rather_than_duplicate(
    api: TestClient, db_session: Session, user_id: int
) -> None:
    for position in (5.0, 10.0, 15.0, 20.0):
        _ping(api, 0, position)

    rows = (
        db_session.execute(
            select(WatchProgress).where(
                WatchProgress.user_id == user_id, WatchProgress.row_index == 0
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].position_seconds == 20.0


def test_crossing_the_threshold_marks_completed(api: TestClient) -> None:
    # 85% of the 120s fixture duration is 102s.
    assert _ping(api, 0, 20.0).json()["completed"] is False
    assert _ping(api, 0, 60.0).json()["completed"] is False  # halfway is not watched
    assert _ping(api, 0, 105.0).json()["completed"] is True


def test_completion_is_sticky_when_rewinding(api: TestClient) -> None:
    """Rewinding after finishing must not un-watch a title."""
    _ping(api, 0, 110.0)
    assert _ping(api, 0, 3.0).json()["completed"] is True


def test_position_is_clamped_to_duration(api: TestClient) -> None:
    body = _ping(api, 0, 500.0, duration=120.0).json()
    assert body["position_seconds"] == 120.0


def test_duration_is_retained_when_a_later_ping_omits_it(
    api: TestClient, db_session: Session, user_id: int
) -> None:
    """The first pings can arrive before the player knows the duration."""
    _ping(api, 0, 10.0, duration=120.0)
    api.post(
        "/history/progress",
        json={"row_index": 0, "position_seconds": 20.0, "duration_seconds": None},
    )
    record = db_session.execute(
        select(WatchProgress).where(
            WatchProgress.user_id == user_id, WatchProgress.row_index == 0
        )
    ).scalar_one()
    assert record.duration_seconds == 120.0


def test_progress_for_unknown_movie_is_404(api: TestClient) -> None:
    response = _ping(api, 999_999, 10.0)
    assert response.status_code == 404


def test_progress_validates_payload(api: TestClient) -> None:
    assert api.post(
        "/history/progress", json={"row_index": -1, "position_seconds": 5}
    ).status_code == 422
    assert api.post(
        "/history/progress", json={"row_index": 0, "position_seconds": -5}
    ).status_code == 422


# --------------------------------------------------------------------------- #
# event log
# --------------------------------------------------------------------------- #
def test_events_are_not_written_on_every_ping(
    api: TestClient, db_session: Session, user_id: int
) -> None:
    """A 5-second poll must not generate one row per ping."""
    for position in range(1, 21):
        _ping(api, 0, float(position))

    events = (
        db_session.execute(select(WatchEvent).where(WatchEvent.user_id == user_id))
        .scalars()
        .all()
    )
    # One "start" only: same session, threshold never crossed.
    assert [event.event_type for event in events] == [EVENT_START]


def test_completion_writes_exactly_one_complete_event(
    api: TestClient, db_session: Session, user_id: int
) -> None:
    _ping(api, 0, 10.0)
    _ping(api, 0, 40.0)
    _ping(api, 0, 105.0)  # crosses 85%
    _ping(api, 0, 115.0)

    events = (
        db_session.execute(
            select(WatchEvent).where(
                WatchEvent.user_id == user_id, WatchEvent.event_type == EVENT_COMPLETE
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1


def test_a_gap_starts_a_new_session_event(
    api: TestClient, db_session: Session, user_id: int
) -> None:
    _ping(api, 0, 10.0)
    record = db_session.execute(
        select(WatchProgress).where(
            WatchProgress.user_id == user_id, WatchProgress.row_index == 0
        )
    ).scalar_one()
    # Simulate returning the next day.
    record.updated_at = datetime.now(timezone.utc) - timedelta(hours=24)
    db_session.flush()

    _ping(api, 0, 12.0)

    starts = (
        db_session.execute(
            select(WatchEvent).where(
                WatchEvent.user_id == user_id, WatchEvent.event_type == EVENT_START
            )
        )
        .scalars()
        .all()
    )
    assert len(starts) == 2


# --------------------------------------------------------------------------- #
# resume
# --------------------------------------------------------------------------- #
def test_resume_point_returns_zero_for_an_untouched_title(api: TestClient) -> None:
    body = api.get("/history/resume/1").json()
    assert body["position_seconds"] == 0.0
    assert body["completed"] is False


def test_resume_point_returns_the_stored_position(api: TestClient) -> None:
    _ping(api, 0, 45.0)
    assert api.get("/history/resume/0").json()["position_seconds"] == 45.0


def test_resume_ignores_a_trivial_position(api: TestClient) -> None:
    """A couple of seconds is an accident, not an intent to resume."""
    _ping(api, 0, 2.0)
    assert api.get("/history/resume/0").json()["position_seconds"] == 0.0


def test_resume_restarts_when_at_the_end(api: TestClient) -> None:
    _ping(api, 0, 119.0, duration=120.0)
    body = api.get("/history/resume/0").json()
    assert body["position_seconds"] == 0.0
    assert body["completed"] is True


# --------------------------------------------------------------------------- #
# continue watching
# --------------------------------------------------------------------------- #
def test_continue_watching_lists_unfinished_titles_newest_first(
    api: TestClient,
) -> None:
    _ping(api, 0, 20.0)
    _ping(api, 1, 25.0)

    body = api.get("/history/continue").json()
    titles = [entry["movie"]["title"] for entry in body]
    assert titles == ["Jumanji", "Toy Story"]  # most recent ping first
    assert body[0]["percent_complete"] is not None


def test_continue_watching_excludes_completed_titles(api: TestClient) -> None:
    _ping(api, 0, 110.0)  # completed (>85% of 120s)
    _ping(api, 1, 20.0)  # in progress

    titles = [e["movie"]["title"] for e in api.get("/history/continue").json()]
    assert titles == ["Jumanji"]


def test_continue_watching_excludes_trivial_progress(api: TestClient) -> None:
    _ping(api, 0, 1.0)
    assert api.get("/history/continue").json() == []


def test_continue_watching_excludes_titles_sitting_at_the_end(
    api: TestClient, db_session: Session, user_id: int
) -> None:
    """A title within the end tolerance is finished, not resumable.

    The record is forced into this state directly because the normal thresholds
    would already have marked it completed, which is a different exclusion.
    """
    _ping(api, 0, 20.0)
    record = db_session.execute(
        select(WatchProgress).where(
            WatchProgress.user_id == user_id, WatchProgress.row_index == 0
        )
    ).scalar_one()
    record.position_seconds = 118.0  # within END_TOLERANCE_SECONDS of 120
    record.completed = False
    db_session.flush()

    assert api.get("/history/continue").json() == []


def test_continue_watching_carries_the_movie_summary(api: TestClient) -> None:
    _ping(api, 0, 20.0)
    entry = api.get("/history/continue").json()[0]
    assert entry["movie"]["row_index"] == 0
    assert entry["movie"]["title"] == "Toy Story"
    assert entry["movie"]["poster_url"] is not None
    assert entry["movie"]["genres"] == ["Animation"]


def test_continue_watching_requires_authentication(db_client: TestClient) -> None:
    assert db_client.get("/history/continue").status_code == 401


# --------------------------------------------------------------------------- #
# history listing and deletion
# --------------------------------------------------------------------------- #
def test_history_includes_completed_titles(api: TestClient) -> None:
    _ping(api, 0, 110.0)
    _ping(api, 1, 10.0)

    titles = [entry["movie"]["title"] for entry in api.get("/history").json()]
    assert set(titles) == {"Toy Story", "Jumanji"}


def test_history_is_paginated(api: TestClient) -> None:
    _ping(api, 0, 10.0)
    _ping(api, 1, 10.0)
    _ping(api, 2, 10.0)

    first = api.get("/history", params={"limit": 2}).json()
    second = api.get("/history", params={"limit": 2, "offset": 2}).json()
    assert len(first) == 2
    assert len(second) == 1
    assert not {e["row_index"] for e in first} & {e["row_index"] for e in second}


def test_delete_removes_one_title(api: TestClient) -> None:
    _ping(api, 0, 20.0)
    _ping(api, 1, 20.0)

    assert api.delete("/history/0").status_code == 204
    remaining = [e["row_index"] for e in api.get("/history").json()]
    assert remaining == [1]


def test_delete_is_idempotent(api: TestClient) -> None:
    assert api.delete("/history/2").status_code == 204
    assert api.delete("/history/2").status_code == 204


def test_clear_history_removes_progress_and_events(
    api: TestClient, db_session: Session, user_id: int
) -> None:
    _ping(api, 0, 60.0)
    _ping(api, 1, 20.0)

    assert api.delete("/history").status_code == 204
    assert api.get("/history").json() == []
    events = (
        db_session.execute(select(WatchEvent).where(WatchEvent.user_id == user_id))
        .scalars()
        .all()
    )
    assert events == []


# --------------------------------------------------------------------------- #
# isolation between users
# --------------------------------------------------------------------------- #
def test_history_is_scoped_to_the_owning_user(
    api: TestClient, db_session: Session
) -> None:
    _ping(api, 0, 30.0)

    other = auth_service.register(
        db_session, "other@example.com", "another-passphrase", "Other"
    )
    db_session.flush()
    token, _ = create_access_token(other.id)

    api.headers["Authorization"] = f"Bearer {token}"
    assert api.get("/history").json() == []
    assert api.get("/history/continue").json() == []
    assert api.get("/history/resume/0").json()["position_seconds"] == 0.0


def test_watched_row_indexes_only_returns_the_users_own(
    api: TestClient, db_session: Session, user_id: int
) -> None:
    _ping(api, 0, 30.0)
    _ping(api, 2, 10.0)
    assert history_service.watched_row_indexes(db_session, user_id) == {0, 2}
    assert history_service.watched_row_indexes(db_session, user_id + 999) == set()
