"""Task 13 acceptance tests: similarity, taste centroid, cold start, alignment.

A small synthetic vector matrix is injected so the maths is checkable by hand.
The real 45,264-row artifact is exercised separately at the end, guarded by a
skip when it has not been built.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest
import scipy.sparse as sp
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from etl.clean import CleanReport, CleanedData
from etl.seed import seed
from etl.vectors import BACKEND_ROOT, _l2_normalize, densify_to_csr, load_vectors
from vaultstream.models.auth import User
from vaultstream.models.catalog import Movie
from vaultstream.models.history import WatchProgress
from vaultstream.services import auth as auth_service
from vaultstream.services import recommender
from vaultstream.services.recommender import HistoryEntry, VectorIndex
from vaultstream.services.security import create_access_token

# --------------------------------------------------------------------------- #
# synthetic world
# --------------------------------------------------------------------------- #
# Six titles in three obvious clusters, so expected neighbours are unambiguous:
#   rows 0,1 -> animation cluster
#   rows 2,3 -> horror cluster
#   row  4   -> duplicate of row 0 (same tmdb_id), as in the real catalogue
#   row  5   -> low-quality title that the quality floor must exclude
FEATURES = 6
_DENSE = np.array(
    [
        [3, 3, 0, 0, 0, 0],  # 0 Bright Toys
        [3, 2, 0, 0, 1, 0],  # 1 Bright Toys Two
        [0, 0, 4, 3, 0, 0],  # 2 Dark House
        [0, 0, 3, 4, 0, 0],  # 3 Dark House Returns
        [3, 3, 0, 0, 0, 0],  # 4 duplicate of row 0
        [3, 3, 0, 0, 0, 1],  # 5 Obscure Toy Short (fails quality floor)
    ],
    dtype=np.int64,
)

ROWS = [
    # row_index, tmdb_id, title, votes, poster
    (0, 100, "Bright Toys", 5000, "/a.jpg"),
    (1, 101, "Bright Toys Two", 4000, "/b.jpg"),
    (2, 200, "Dark House", 3000, "/c.jpg"),
    (3, 201, "Dark House Returns", 2000, "/d.jpg"),
    (4, 100, "Bright Toys", 5000, "/a.jpg"),  # duplicate tmdb_id
    (5, 300, "Obscure Toy Short", 2, "/e.jpg"),  # below the vote floor
]


def _catalog() -> CleanedData:
    movies = pd.DataFrame(
        {
            "row_index": [r[0] for r in ROWS],
            "tmdb_id": [r[1] for r in ROWS],
            "title": [r[2] for r in ROWS],
            "original_title": [r[2] for r in ROWS],
            "vote_count": [float(r[3]) for r in ROWS],
            "poster_path": [r[4] for r in ROWS],
            "imdb_id": [f"tt{r[1]:07d}" for r in ROWS],
            "tags": ["t"] * len(ROWS),
            "backdrop_path": [None] * len(ROWS),
            "release_year": pd.array([2000] * len(ROWS), dtype="Int64"),
            "release_date": pd.to_datetime(["2000-01-01"] * len(ROWS)),
            "runtime": [100.0] * len(ROWS),
            "vote_average": [7.0] * len(ROWS),
            "popularity": [50.0, 40.0, 30.0, 20.0, 40.0, 1.0],
            "original_language": ["en"] * len(ROWS),
            "status": ["Released"] * len(ROWS),
            "tagline": [None] * len(ROWS),
            "overview": ["o"] * len(ROWS),
            "homepage": [None] * len(ROWS),
            "budget": [0.0] * len(ROWS),
            "revenue": [0.0] * len(ROWS),
            "adult": [False] * len(ROWS),
            "collection_id": pd.array([None] * len(ROWS), dtype="Int64"),
        }
    )
    int_cols = lambda cols: pd.DataFrame(  # noqa: E731
        {c: pd.Series(dtype="int64") for c in cols}
    )
    return CleanedData(
        movies=movies,
        genres=pd.DataFrame({"id": [16], "name": ["Animation"]}),
        movie_genres=pd.DataFrame({"tmdb_id": [100, 101], "genre_id": [16, 16]}),
        keywords=pd.DataFrame(
            {"id": pd.Series(dtype="int64"), "name": pd.Series(dtype="string")}
        ),
        movie_keywords=int_cols(["tmdb_id", "keyword_id"]),
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
        links=int_cols(["tmdb_id", "movielens_id", "imdb_numeric_id"]),
        report=CleanReport(),
    )


@pytest.fixture
def world(db_session: Session) -> Session:
    """Seeded synthetic catalogue plus a matching injected vector index."""
    seed(db_session, _catalog(), truncate=True)
    db_session.flush()

    matrix = _l2_normalize(densify_to_csr(_DENSE))
    row_map = np.array([r[1] for r in ROWS], dtype=np.int64)
    recommender.set_index(VectorIndex(matrix=matrix, row_map=row_map))
    yield db_session
    recommender.reset_index()


@pytest.fixture
def user_id(world: Session) -> int:
    user = auth_service.register(
        world, "rec@example.com", "a-strong-passphrase", "Rec"
    )
    world.flush()
    return int(user.id)


@pytest.fixture
def api(db_client: TestClient, user_id: int) -> TestClient:
    token, _ = create_access_token(user_id)
    db_client.headers["Authorization"] = f"Bearer {token}"
    return db_client


def _watch(session: Session, user_id: int, row_index: int, *, completed=True, age_days=0):
    session.add(
        WatchProgress(
            user_id=user_id,
            row_index=row_index,
            position_seconds=60.0,
            duration_seconds=120.0,
            completed=completed,
            updated_at=datetime.now(timezone.utc) - timedelta(days=age_days),
        )
    )
    session.flush()


# --------------------------------------------------------------------------- #
# similarity
# --------------------------------------------------------------------------- #
def test_similar_returns_the_same_cluster(world: Session) -> None:
    titles = [m.title for m in recommender.similar_to(world, 0, limit=5)]
    # Row 1 is the only other quality-passing animation title.
    assert titles[0] == "Bright Toys Two"
    assert "Dark House" not in titles


def test_similar_excludes_the_seed_and_its_duplicate_rows(world: Session) -> None:
    """Row 4 shares tmdb_id 100 with row 0, so it must not be recommended."""
    results = recommender.similar_to(world, 0, limit=5)
    assert all(m.row_index not in (0, 4) for m in results)
    assert all(m.tmdb_id != 100 for m in results)


def test_similar_applies_the_quality_floor(world: Session) -> None:
    """Row 5 is highly similar to row 0 but has 2 votes."""
    results = recommender.similar_to(world, 0, limit=5)
    assert "Obscure Toy Short" not in [m.title for m in results]


def test_similar_deduplicates_by_tmdb_id(world: Session) -> None:
    results = recommender.similar_to(world, 2, limit=5)
    tmdb_ids = [m.tmdb_id for m in results]
    assert len(tmdb_ids) == len(set(tmdb_ids))


def test_similar_for_out_of_range_row_is_empty(world: Session) -> None:
    assert recommender.similar_to(world, 9999, limit=5) == []


def test_similar_endpoint_is_public_and_404s_for_unknown(
    db_client: TestClient, world: Session
) -> None:
    assert db_client.get("/movies/0/similar").status_code == 200
    assert db_client.get("/movies/4242/similar").status_code == 404


# --------------------------------------------------------------------------- #
# taste centroid
# --------------------------------------------------------------------------- #
def test_centroid_of_one_title_equals_that_title(world: Session) -> None:
    entries = [
        HistoryEntry(0, 1.0, datetime.now(timezone.utc), True),
    ]
    centroid = recommender.taste_centroid(entries)
    assert centroid is not None
    index = recommender.get_index()
    # Cosine similarity with the single source row must be 1.
    assert float((index.matrix[0] @ centroid.T).toarray().ravel()[0]) == pytest.approx(
        1.0, abs=1e-5
    )


def test_centroid_sits_between_two_clusters(world: Session) -> None:
    now = datetime.now(timezone.utc)
    centroid = recommender.taste_centroid(
        [HistoryEntry(0, 1.0, now, True), HistoryEntry(2, 1.0, now, True)]
    )
    assert centroid is not None
    index = recommender.get_index()
    to_animation = float((index.matrix[0] @ centroid.T).toarray().ravel()[0])
    to_horror = float((index.matrix[2] @ centroid.T).toarray().ravel()[0])
    # Equal weights, so it should be roughly equidistant and similar to both.
    assert to_animation == pytest.approx(to_horror, abs=0.05)
    assert 0.5 < to_animation < 1.0


def test_centroid_is_unit_length(world: Session) -> None:
    centroid = recommender.taste_centroid(
        [HistoryEntry(0, 1.0, datetime.now(timezone.utc), True)]
    )
    assert centroid is not None
    norm = float(np.sqrt(centroid.multiply(centroid).sum()))
    assert norm == pytest.approx(1.0, abs=1e-5)


def test_centroid_is_none_without_usable_history(world: Session) -> None:
    assert recommender.taste_centroid([]) is None
    # Zero weight contributes nothing.
    assert (
        recommender.taste_centroid(
            [HistoryEntry(0, 0.0, datetime.now(timezone.utc), True)]
        )
        is None
    )
    # Out-of-range rows are ignored.
    assert (
        recommender.taste_centroid(
            [HistoryEntry(9999, 1.0, datetime.now(timezone.utc), True)]
        )
        is None
    )


def test_recency_weighting_favours_recent_watches(world: Session, user_id: int) -> None:
    """An old horror watch should lose to a fresh animation watch."""
    _watch(world, user_id, 2, completed=True, age_days=120)  # old horror
    _watch(world, user_id, 0, completed=True, age_days=0)  # fresh animation

    entries = recommender._weighted_history(world, user_id)
    weights = {entry.row_index: entry.weight for entry in entries}
    assert weights[0] > weights[2]

    picks = recommender.for_you(world, user_id, limit=5)
    # The fresh cluster should lead; row 1 is the unwatched animation title.
    assert picks[0].title == "Bright Toys Two"


def test_partial_watch_counts_less_than_a_completed_one(
    world: Session, user_id: int
) -> None:
    _watch(world, user_id, 0, completed=False, age_days=0)
    _watch(world, user_id, 2, completed=True, age_days=0)

    weights = {
        entry.row_index: entry.weight
        for entry in recommender._weighted_history(world, user_id)
    }
    assert weights[2] > weights[0]


# --------------------------------------------------------------------------- #
# for-you
# --------------------------------------------------------------------------- #
def test_for_you_excludes_watched_titles_and_their_duplicates(
    world: Session, user_id: int
) -> None:
    _watch(world, user_id, 0)
    picks = recommender.for_you(world, user_id, limit=10)
    assert all(pick.row_index not in (0, 4) for pick in picks)
    assert all(pick.tmdb_id != 100 for pick in picks)


def test_for_you_is_empty_without_history(world: Session, user_id: int) -> None:
    """Empty, not a popularity list dressed up as personalisation."""
    assert recommender.for_you(world, user_id, limit=10) == []


def test_for_you_endpoint_falls_back_to_popular_and_says_so(api: TestClient) -> None:
    body = api.get("/recommendations/for-you").json()
    assert body["key"] == "popular"
    assert body["personalised"] is False
    assert "Watch something" in body["reason"]
    assert len(body["items"]) > 0


def test_for_you_endpoint_is_personalised_once_there_is_history(
    api: TestClient, world: Session, user_id: int
) -> None:
    _watch(world, user_id, 2)  # a horror title
    body = api.get("/recommendations/for-you").json()
    assert body["key"] == "for-you"
    assert body["personalised"] is True
    assert [item["title"] for item in body["items"]][0] == "Dark House Returns"


def test_for_you_requires_authentication(db_client: TestClient, world: Session) -> None:
    assert db_client.get("/recommendations/for-you").status_code == 401


# --------------------------------------------------------------------------- #
# because you watched
# --------------------------------------------------------------------------- #
def test_because_you_watched_builds_one_row_per_seed(
    api: TestClient, world: Session, user_id: int
) -> None:
    _watch(world, user_id, 0, age_days=0)
    _watch(world, user_id, 2, age_days=1)

    rows = api.get("/recommendations/because-you-watched").json()
    titles = [row["title"] for row in rows]
    assert "Because you watched Bright Toys" in titles
    assert "Because you watched Dark House" in titles
    for row in rows:
        assert row["seed"] is not None
        assert row["items"]


def test_because_you_watched_does_not_repeat_a_seed_film(
    api: TestClient, world: Session, user_id: int
) -> None:
    """Rows 0 and 4 are the same film; only one row should be produced."""
    _watch(world, user_id, 0)
    _watch(world, user_id, 4)

    rows = api.get("/recommendations/because-you-watched").json()
    seeds = [row["seed"]["tmdb_id"] for row in rows]
    assert seeds.count(100) <= 1


def test_because_you_watched_is_empty_without_history(api: TestClient) -> None:
    assert api.get("/recommendations/because-you-watched").json() == []


def test_because_you_watched_never_recommends_watched_titles(
    api: TestClient, world: Session, user_id: int
) -> None:
    _watch(world, user_id, 0)
    _watch(world, user_id, 2)

    rows = api.get("/recommendations/because-you-watched").json()
    for row in rows:
        for item in row["items"]:
            assert item["tmdb_id"] not in (100, 200)


# --------------------------------------------------------------------------- #
# feed
# --------------------------------------------------------------------------- #
def test_feed_reports_cold_start(api: TestClient) -> None:
    body = api.get("/recommendations/feed").json()
    assert body["has_history"] is False
    assert len(body["rows"]) == 1
    assert body["rows"][0]["personalised"] is False


def test_feed_combines_picks_and_seed_rows(
    api: TestClient, world: Session, user_id: int
) -> None:
    _watch(world, user_id, 0)
    body = api.get("/recommendations/feed").json()

    assert body["has_history"] is True
    keys = [row["key"] for row in body["rows"]]
    assert "for-you" in keys
    assert any(key.startswith("because-") for key in keys)
    assert all(row["personalised"] for row in body["rows"])


def test_two_users_with_different_history_get_different_rows(
    db_client: TestClient, world: Session
) -> None:
    """The headline requirement: recommendations follow the individual."""
    animation_fan = auth_service.register(
        world, "anim@example.com", "a-strong-passphrase", "Anim"
    )
    horror_fan = auth_service.register(
        world, "horror@example.com", "a-strong-passphrase", "Horror"
    )
    world.flush()

    _watch(world, int(animation_fan.id), 0)
    _watch(world, int(horror_fan.id), 2)

    animation_picks = [
        m.title for m in recommender.for_you(world, int(animation_fan.id), limit=5)
    ]
    horror_picks = [
        m.title for m in recommender.for_you(world, int(horror_fan.id), limit=5)
    ]

    assert animation_picks[0] == "Bright Toys Two"
    assert horror_picks[0] == "Dark House Returns"
    assert animation_picks != horror_picks


# --------------------------------------------------------------------------- #
# cold start
# --------------------------------------------------------------------------- #
def test_popular_fallback_respects_exclusions_and_dedupes(world: Session) -> None:
    items = recommender.popular_fallback(world, limit=10, exclude={0})
    tmdb_ids = [item.tmdb_id for item in items]
    assert len(tmdb_ids) == len(set(tmdb_ids))
    assert 0 not in [item.row_index for item in items]


def test_popular_fallback_excludes_low_quality(world: Session) -> None:
    titles = [item.title for item in recommender.popular_fallback(world, limit=10)]
    assert "Obscure Toy Short" not in titles


# --------------------------------------------------------------------------- #
# alignment
# --------------------------------------------------------------------------- #
def test_verify_alignment_passes_for_a_consistent_world(world: Session) -> None:
    recommender.verify_alignment(world)  # must not raise


def test_verify_alignment_detects_a_size_mismatch(world: Session) -> None:
    truncated = recommender.get_index()
    recommender.set_index(
        VectorIndex(matrix=truncated.matrix[:3], row_map=truncated.row_map[:3])
    )
    with pytest.raises(ValueError, match="size mismatch"):
        recommender.verify_alignment(world)


def test_verify_alignment_detects_a_shifted_row_map(world: Session) -> None:
    """The failure mode that would silently corrupt every recommendation."""
    index = recommender.get_index()
    shifted = np.roll(index.row_map, 1)
    recommender.set_index(VectorIndex(matrix=index.matrix, row_map=shifted))
    with pytest.raises(ValueError, match="alignment broken"):
        recommender.verify_alignment(world)


def test_health_endpoint_reports_the_index(db_client: TestClient, world: Session) -> None:
    body = db_client.get("/recommendations/health").json()
    assert body["loaded"] is True
    assert body["aligned"] is True
    assert body["rows"] == len(ROWS)


# --------------------------------------------------------------------------- #
# the real artifact
# --------------------------------------------------------------------------- #
_ARTIFACTS = [
    BACKEND_ROOT / "data" / "vectors.npz",
    BACKEND_ROOT / "data" / "vector_row_map.npy",
]
requires_vectors = pytest.mark.skipif(
    not all(path.exists() for path in _ARTIFACTS),
    reason="vector artifacts not built (run: python -m etl.vectors)",
)


@requires_vectors
def test_real_matrix_is_normalised_and_self_similar() -> None:
    matrix, row_map = load_vectors()
    assert matrix.shape[0] == row_map.shape[0]
    assert sp.issparse(matrix)

    # A normalised row must have cosine similarity 1 with itself.
    for row in (0, 1000, 20_000, matrix.shape[0] - 1):
        similarity = float((matrix[row] @ matrix[row].T).toarray().ravel()[0])
        if matrix[row].nnz:
            assert similarity == pytest.approx(1.0, abs=1e-4)
