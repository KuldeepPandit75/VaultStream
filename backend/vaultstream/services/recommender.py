"""Content-based recommendations over the bag-of-words vectors.

Why a sparse dot product rather than sklearn's NearestNeighbors
--------------------------------------------------------------
The persisted matrix is already L2-normalised, so cosine similarity reduces
exactly to a dot product -- which is what a brute-force cosine KNN computes
internally anyway. Doing it directly:

  * removes any dependency on a fitted sklearn estimator (the original
    ``model.pkl`` was 1.81 GB and tied to the sklearn version that wrote it);
  * gives the full similarity vector, so already-watched titles can be masked
    before ranking. With a KNN you must over-fetch ``k + len(watched)``
    neighbours and hope that is enough after filtering.

Alignment contract
------------------
Row ``i`` of the matrix is row ``i`` of ``movies.pkl``, which is
``movies.row_index`` in Postgres. ``vector_row_map.npy`` holds the tmdb_id for
each row so that contract can be asserted rather than assumed.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock

import numpy as np
import scipy.sparse as sp
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from etl.vectors import load_vectors
from vaultstream.config import get_settings
from vaultstream.models.catalog import Movie
from vaultstream.models.history import WatchProgress
from vaultstream.schemas.catalog import MovieSummary
from vaultstream.services import media as media_service
from vaultstream.services.catalog import _genre_names_for, _to_summary

logger = logging.getLogger("vaultstream.recommender")

# Recency weighting: a title watched this many days ago counts half as much.
RECENCY_HALF_LIFE_DAYS = 14.0
# A part-watched title is a weaker signal of taste than a finished one.
PARTIAL_WATCH_WEIGHT = 0.5
# How many recent titles feed the taste centroid.
MAX_HISTORY_FOR_CENTROID = 40
# Candidates pulled before quality filtering and de-duplication.
CANDIDATE_MULTIPLIER = 12
MIN_CANDIDATES = 120
# Ignore near-zero similarities; they are noise, not signal.
MIN_SIMILARITY = 0.02


@dataclass(slots=True)
class VectorIndex:
    """The similarity matrix plus its row -> tmdb_id map."""

    matrix: sp.csr_matrix
    row_map: np.ndarray

    @property
    def n_rows(self) -> int:
        return int(self.matrix.shape[0])


_index: VectorIndex | None = None
_index_lock = Lock()


def set_index(index: VectorIndex | None) -> None:
    """Replace the loaded index.

    Exists so tests can supply a small synthetic matrix aligned to a small
    catalogue; the real artifact has 45,264 rows and would fail the alignment
    check against a test fixture.
    """
    global _index
    with _index_lock:
        _index = index


def reset_index() -> None:
    """Drop the cached index so the next call reloads from disk."""
    set_index(None)


def get_index() -> VectorIndex:
    """Load the vector artifacts once per process (thread-safe)."""
    global _index
    if _index is not None:
        return _index

    with _index_lock:
        if _index is None:  # re-check inside the lock
            matrix, row_map = load_vectors()
            _index = VectorIndex(matrix=matrix.tocsr(), row_map=row_map)
            logger.info(
                "Loaded vector index: %s rows x %s features, %s non-zeros",
                f"{_index.matrix.shape[0]:,}",
                f"{_index.matrix.shape[1]:,}",
                f"{_index.matrix.nnz:,}",
            )
    return _index


def verify_alignment(session: Session, sample_size: int = 64) -> None:
    """Assert the matrix lines up with the catalogue. Raises on mismatch.

    Checks the row count exactly and a spread of individual rows, because a
    silent off-by-one here would corrupt every recommendation without raising.
    """
    index = get_index()

    total = int(session.execute(select(func.count()).select_from(Movie)).scalar_one())
    if total != index.n_rows:
        raise ValueError(
            f"Vector/catalogue size mismatch: matrix has {index.n_rows:,} rows "
            f"but movies has {total:,}."
        )

    if total == 0:
        return

    probes = np.unique(
        np.linspace(0, total - 1, num=min(sample_size, total)).astype(int)
    )
    rows = dict(
        session.execute(
            select(Movie.row_index, Movie.tmdb_id).where(
                Movie.row_index.in_([int(p) for p in probes])
            )
        ).all()
    )

    for row_index in probes:
        expected = rows.get(int(row_index))
        actual = int(index.row_map[int(row_index)])
        if expected is None:
            raise ValueError(f"movies has no row_index {int(row_index)}")
        if expected != actual:
            raise ValueError(
                f"Vector alignment broken at row {int(row_index)}: "
                f"map says tmdb_id {actual}, catalogue says {expected}."
            )


# --------------------------------------------------------------------------- #
# similarity primitives
# --------------------------------------------------------------------------- #
def _similarities(query: sp.csr_matrix) -> np.ndarray:
    """Cosine similarity of one unit-length query against every row."""
    index = get_index()
    return np.asarray((index.matrix @ query.T).todense()).ravel()


def _normalize(vector: sp.csr_matrix) -> sp.csr_matrix:
    """Scale a sparse row vector to unit length; zero vectors pass through."""
    norm = float(np.sqrt(vector.multiply(vector).sum()))
    if norm == 0.0:
        return vector
    return vector.multiply(1.0 / norm).tocsr()


def _top_candidates(
    scores: np.ndarray, exclude: set[int], wanted: int
) -> list[tuple[int, float]]:
    """Highest-scoring rows, excluding given rows, as (row_index, score)."""
    if exclude:
        scores = scores.copy()
        # -inf rather than 0 so excluded rows can never survive the cut.
        indexes = np.fromiter(
            (i for i in exclude if 0 <= i < scores.shape[0]), dtype=np.int64
        )
        if indexes.size:
            scores[indexes] = -np.inf

    count = min(wanted, scores.shape[0])
    # argpartition is O(n) versus a full O(n log n) sort of 45k scores.
    partitioned = np.argpartition(-scores, count - 1)[:count]
    ordered = partitioned[np.argsort(-scores[partitioned])]

    return [
        (int(row), float(scores[row]))
        for row in ordered
        if np.isfinite(scores[row]) and scores[row] >= MIN_SIMILARITY
    ]


# --------------------------------------------------------------------------- #
# hydration
# --------------------------------------------------------------------------- #
def _hydrate(
    session: Session,
    candidates: list[tuple[int, float]],
    limit: int,
    *,
    apply_quality_floor: bool = True,
) -> list[MovieSummary]:
    """Filter candidates through the catalogue and return summaries in rank order.

    Runs one query over the candidate rows rather than scanning the catalogue,
    and collapses duplicate tmdb_ids so a repeated catalogue row cannot appear
    twice in one carousel.
    """
    if not candidates:
        return []

    settings = get_settings()
    ranked = {row_index: score for row_index, score in candidates}

    conditions = [Movie.row_index.in_(list(ranked))]
    if apply_quality_floor:
        conditions += [
            Movie.adult.is_(False),
            Movie.poster_path.isnot(None),
            Movie.vote_count >= settings.quality_floor_vote_count,
        ]

    movies = list(
        session.execute(select(Movie).where(*conditions)).scalars().all()
    )
    movies.sort(key=lambda movie: -ranked.get(movie.row_index, 0.0))

    seen_tmdb: set[int] = set()
    chosen: list[Movie] = []
    for movie in movies:
        if movie.tmdb_id in seen_tmdb:
            continue
        seen_tmdb.add(movie.tmdb_id)
        chosen.append(movie)
        if len(chosen) >= limit:
            break

    tmdb_ids = [movie.tmdb_id for movie in chosen]
    genre_map = _genre_names_for(session, tmdb_ids)
    media_map = media_service.get_cached_many(session, tmdb_ids)

    return [
        _to_summary(
            movie, genre_map.get(movie.tmdb_id, []), media_map.get(movie.tmdb_id)
        )
        for movie in chosen
    ]


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #
def similar_to(
    session: Session, row_index: int, limit: int = 12, exclude: set[int] | None = None
) -> list[MovieSummary]:
    """Titles most like a given one."""
    index = get_index()
    if not 0 <= row_index < index.n_rows:
        return []

    scores = _similarities(index.matrix[row_index])

    excluded = set(exclude or ())
    excluded.add(row_index)
    # Also drop the duplicate catalogue rows of the same film.
    movie = session.get(Movie, row_index)
    if movie is not None:
        excluded.update(
            int(value)
            for value in session.execute(
                select(Movie.row_index).where(Movie.tmdb_id == movie.tmdb_id)
            )
            .scalars()
            .all()
        )

    candidates = _top_candidates(
        scores, excluded, max(limit * CANDIDATE_MULTIPLIER, MIN_CANDIDATES)
    )
    return _hydrate(session, candidates, limit)


@dataclass(slots=True)
class HistoryEntry:
    row_index: int
    weight: float
    updated_at: datetime
    completed: bool


def _weighted_history(
    session: Session, user_id: int, limit: int = MAX_HISTORY_FOR_CENTROID
) -> list[HistoryEntry]:
    """Recent watch history with a recency- and completion-derived weight."""
    records = list(
        session.execute(
            select(
                WatchProgress.row_index,
                WatchProgress.updated_at,
                WatchProgress.completed,
            )
            .where(WatchProgress.user_id == user_id)
            .order_by(WatchProgress.updated_at.desc())
            .limit(limit)
        ).all()
    )

    now = datetime.now(timezone.utc)
    entries: list[HistoryEntry] = []
    for row_index, updated_at, completed in records:
        age_days = max((now - updated_at).total_seconds() / 86_400.0, 0.0)
        # Exponential decay with a 14-day half-life.
        recency = math.pow(0.5, age_days / RECENCY_HALF_LIFE_DAYS)
        weight = recency * (1.0 if completed else PARTIAL_WATCH_WEIGHT)
        entries.append(
            HistoryEntry(
                row_index=int(row_index),
                weight=weight,
                updated_at=updated_at,
                completed=bool(completed),
            )
        )
    return entries


def taste_centroid(entries: list[HistoryEntry]) -> sp.csr_matrix | None:
    """Weighted average of watched vectors, L2-normalised. None if unusable."""
    index = get_index()
    usable = [
        entry
        for entry in entries
        if 0 <= entry.row_index < index.n_rows and entry.weight > 0
    ]
    if not usable:
        return None

    rows = index.matrix[[entry.row_index for entry in usable]]
    weights = np.array([entry.weight for entry in usable], dtype=np.float32)
    total = float(weights.sum())
    if total <= 0:
        return None

    # (1 x n) @ (n x features) sums the weighted rows in one operation.
    weighted = sp.csr_matrix(weights.reshape(1, -1) / total) @ rows
    centroid = _normalize(sp.csr_matrix(weighted))
    return centroid if centroid.nnz else None


def for_you(
    session: Session, user_id: int, limit: int = 20
) -> list[MovieSummary]:
    """One blended row reflecting everything the user has watched recently.

    Returns an empty list when there is no usable history, so the caller can
    decide what to show instead rather than being handed a popularity list
    disguised as personalisation.
    """
    entries = _weighted_history(session, user_id)
    centroid = taste_centroid(entries)
    if centroid is None:
        return []

    scores = _similarities(centroid)
    watched = {entry.row_index for entry in entries}
    # Exclude every catalogue row of any watched film, not just the row watched.
    watched |= _sibling_rows(session, watched)

    candidates = _top_candidates(
        scores, watched, max(limit * CANDIDATE_MULTIPLIER, MIN_CANDIDATES)
    )
    return _hydrate(session, candidates, limit)


def _sibling_rows(session: Session, row_indexes: set[int]) -> set[int]:
    """All catalogue rows sharing a tmdb_id with any of the given rows."""
    if not row_indexes:
        return set()
    tmdb_ids = [
        int(value)
        for value in session.execute(
            select(Movie.tmdb_id).where(Movie.row_index.in_(list(row_indexes)))
        )
        .scalars()
        .all()
    ]
    if not tmdb_ids:
        return set()
    return {
        int(value)
        for value in session.execute(
            select(Movie.row_index).where(Movie.tmdb_id.in_(tmdb_ids))
        )
        .scalars()
        .all()
    }


def because_you_watched(
    session: Session, user_id: int, *, rows: int = 3, limit: int = 20
) -> list[tuple[MovieSummary, list[MovieSummary]]]:
    """Per-seed rows: (seed movie, similar titles).

    Seeds are the most recently watched distinct films, which makes each row
    self-explanatory in the UI.
    """
    entries = _weighted_history(session, user_id, limit=rows * 4)
    if not entries:
        return []

    watched = {entry.row_index for entry in entries}
    watched |= _sibling_rows(session, watched)

    result: list[tuple[MovieSummary, list[MovieSummary]]] = []
    used_tmdb: set[int] = set()

    for entry in entries:
        if len(result) >= rows:
            break

        seed = session.get(Movie, entry.row_index)
        if seed is None or seed.tmdb_id in used_tmdb:
            continue

        similar = similar_to(session, entry.row_index, limit=limit, exclude=watched)
        if not similar:
            continue

        used_tmdb.add(seed.tmdb_id)
        genre_map = _genre_names_for(session, [seed.tmdb_id])
        media = media_service.get_cached(session, seed.tmdb_id)
        result.append(
            (
                _to_summary(seed, genre_map.get(seed.tmdb_id, []), media),
                similar,
            )
        )

    return result


def popular_fallback(
    session: Session, limit: int = 20, exclude: set[int] | None = None
) -> list[MovieSummary]:
    """Cold-start row: well-regarded popular titles, no personalisation."""
    settings = get_settings()
    conditions = [
        Movie.adult.is_(False),
        Movie.poster_path.isnot(None),
        Movie.vote_count >= max(settings.quality_floor_vote_count, 200),
    ]
    if exclude:
        conditions.append(Movie.row_index.notin_(list(exclude)))

    # Over-fetch so de-duplication still leaves a full row.
    movies = list(
        session.execute(
            select(Movie)
            .where(*conditions)
            .order_by(Movie.popularity.desc().nulls_last(), Movie.row_index.asc())
            .limit(limit * 3)
        )
        .scalars()
        .all()
    )

    seen: set[int] = set()
    chosen: list[Movie] = []
    for movie in movies:
        if movie.tmdb_id in seen:
            continue
        seen.add(movie.tmdb_id)
        chosen.append(movie)
        if len(chosen) >= limit:
            break

    tmdb_ids = [movie.tmdb_id for movie in chosen]
    genre_map = _genre_names_for(session, tmdb_ids)
    media_map = media_service.get_cached_many(session, tmdb_ids)
    return [
        _to_summary(
            movie, genre_map.get(movie.tmdb_id, []), media_map.get(movie.tmdb_id)
        )
        for movie in chosen
    ]
