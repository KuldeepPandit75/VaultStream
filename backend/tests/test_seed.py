"""Task 3 acceptance tests: schema, seeding, idempotency, vector alignment.

Seeding runs against the disposable test database using a small synthetic
dataset, so these stay fast. The full 45k load is verified separately by
running `python -m etl.seed` against the dev database.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from etl.clean import CleanReport, CleanedData
from etl.seed import _quote, seed, table_counts
from etl.vectors import BACKEND_ROOT, _l2_normalize, densify_to_csr, load_vectors
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

import scipy.sparse as sp


# --------------------------------------------------------------------------- #
# synthetic dataset
# --------------------------------------------------------------------------- #
def _synthetic_cleaned() -> CleanedData:
    """A miniature catalog that reproduces the real data's shape.

    Includes a duplicated tmdb_id (rows 1 and 2) so idempotency and the
    row_index primary key are exercised the same way as production data.
    """
    movies = pd.DataFrame(
        {
            "row_index": [0, 1, 2, 3],
            "tmdb_id": [862, 105045, 105045, 8844],
            "imdb_id": ["tt0114709", "tt1", "tt1", "tt0113497"],
            "title": ["Toy Story", "The Promise", "The Promise", "Jumanji"],
            "tags": ["woody andy toy", "promise", "promise", "jungle"],
            "poster_path": ["/a.jpg", "/b.jpg", "/b.jpg", "/c.jpg"],
            "original_title": ["Toy Story", "The Promise", "The Promise", "Jumanji"],
            "tagline": ["A tagline", None, None, "Roll the dice"],
            "overview": ["Toys live.", None, None, "A board game."],
            "release_date": pd.to_datetime(
                ["1995-10-30", "2011-01-01", "2011-01-01", "1995-12-15"]
            ),
            "release_year": pd.array([1995, 2011, 2011, 1995], dtype="Int64"),
            "runtime": [81.0, None, None, 104.0],
            "vote_average": [7.7, 0.0, 0.0, 6.9],
            "vote_count": [5415.0, 0.0, 0.0, 2413.0],
            "popularity": [21.9, 0.1, 0.1, 17.0],
            "budget": [30000000.0, 0.0, 0.0, 65000000.0],
            "revenue": [373554033.0, 0.0, 0.0, 262797249.0],
            "original_language": ["en", "en", "en", "en"],
            "status": ["Released"] * 4,
            "homepage": [None, None, None, None],
            "adult": [False, False, False, False],
            "collection_id": pd.array([10194, None, None, None], dtype="Int64"),
            "backdrop_path": [None, None, None, None],
        }
    )
    return CleanedData(
        movies=movies,
        genres=pd.DataFrame({"id": [16, 35, 12], "name": ["Animation", "Comedy", "Adventure"]}),
        movie_genres=pd.DataFrame(
            {"tmdb_id": [862, 862, 8844], "genre_id": [16, 35, 12]}
        ),
        keywords=pd.DataFrame({"id": [931, 4290], "name": ["jealousy", "toy"]}),
        movie_keywords=pd.DataFrame({"tmdb_id": [862, 862], "keyword_id": [931, 4290]}),
        people=pd.DataFrame(
            {
                "id": [31, 7879, 2157],
                "name": ["Tom Hanks", "John Lasseter", "Robin Williams"],
                "profile_path": ["/th.jpg", None, "/rw.jpg"],
                "gender": [2, 2, 2],
            }
        ),
        credits=pd.DataFrame(
            {
                "tmdb_id": [862, 862, 8844],
                "person_id": [31, 7879, 2157],
                "credit_type": ["cast", "crew", "cast"],
                "role": ["Woody (voice)", "Director", "Alan Parrish"],
                "department": [None, "Directing", None],
                "billing_order": [0.0, None, 0.0],
            }
        ),
        collections=pd.DataFrame(
            {
                "id": [10194],
                "name": ["Toy Story Collection"],
                "poster_path": ["/tsc.jpg"],
                "backdrop_path": [None],
            }
        ),
        links=pd.DataFrame(
            {"tmdb_id": [862, 8844], "movielens_id": [1, 2], "imdb_numeric_id": [114709, 113497]}
        ),
        report=CleanReport(),
    )


@pytest.fixture
def seeded(db_session: Session) -> CleanedData:
    data = _synthetic_cleaned()
    seed(db_session, data, truncate=True)
    db_session.flush()
    return data


# --------------------------------------------------------------------------- #
# schema / seeding
# --------------------------------------------------------------------------- #
def test_seed_loads_expected_row_counts(db_session: Session, seeded: CleanedData) -> None:
    counts = table_counts(db_session)
    assert counts["movies"] == 4
    assert counts["genres"] == 3
    assert counts["movie_genres"] == 3
    assert counts["keywords"] == 2
    assert counts["people"] == 3
    assert counts["movie_credits"] == 3
    assert counts["collections"] == 1
    assert counts["movie_links"] == 2


def test_seed_is_idempotent(db_session: Session) -> None:
    """Re-seeding must not duplicate or lose rows."""
    data = _synthetic_cleaned()

    seed(db_session, data, truncate=True)
    db_session.flush()
    first = table_counts(db_session)

    seed(db_session, data)
    db_session.flush()
    second = table_counts(db_session)

    assert first == second


def test_seed_refreshes_changed_values_on_rerun(db_session: Session) -> None:
    """Upsert semantics: a changed source value should overwrite the stored one."""
    data = _synthetic_cleaned()
    seed(db_session, data, truncate=True)
    db_session.flush()

    data.movies.loc[data.movies["row_index"] == 0, "title"] = "Toy Story (Remastered)"
    seed(db_session, data)
    db_session.flush()

    title = db_session.execute(
        select(Movie.title).where(Movie.row_index == 0)
    ).scalar_one()
    assert title == "Toy Story (Remastered)"
    assert table_counts(db_session)["movies"] == 4


def test_duplicate_tmdb_ids_coexist_under_distinct_row_index(
    db_session: Session, seeded: CleanedData
) -> None:
    """The catalog's 1,142 duplicate rows must survive seeding intact."""
    rows = db_session.execute(
        select(Movie.row_index, Movie.tmdb_id).where(Movie.tmdb_id == 105045).order_by(Movie.row_index)
    ).all()
    assert [row.row_index for row in rows] == [1, 2]


def test_row_index_is_dense_and_zero_based(db_session: Session, seeded: CleanedData) -> None:
    """row_index must remain 0..n-1 because it indexes the vector matrix."""
    indexes = db_session.execute(select(Movie.row_index).order_by(Movie.row_index)).scalars().all()
    assert list(indexes) == list(range(len(indexes)))


def test_seed_rejects_misaligned_row_index(db_session: Session) -> None:
    data = _synthetic_cleaned()
    data.movies.loc[0, "row_index"] = 99
    with pytest.raises(ValueError, match="row_index"):
        seed(db_session, data, truncate=True)


def test_spot_check_relations_for_toy_story(db_session: Session, seeded: CleanedData) -> None:
    """Genres, top-billed cast, director, collection and link all resolve."""
    genre_names = set(
        db_session.execute(
            select(Genre.name).join(MovieGenre, MovieGenre.genre_id == Genre.id).where(
                MovieGenre.tmdb_id == 862
            )
        )
        .scalars()
        .all()
    )
    assert genre_names == {"Animation", "Comedy"}

    lead = db_session.execute(
        select(Person.name, MovieCredit.role)
        .join(MovieCredit, MovieCredit.person_id == Person.id)
        .where(
            MovieCredit.tmdb_id == 862,
            MovieCredit.credit_type == "cast",
        )
        .order_by(MovieCredit.billing_order)
    ).first()
    assert lead is not None
    assert lead.name == "Tom Hanks"
    assert lead.role == "Woody (voice)"

    director = db_session.execute(
        select(Person.name)
        .join(MovieCredit, MovieCredit.person_id == Person.id)
        .where(MovieCredit.tmdb_id == 862, MovieCredit.role == "Director")
    ).scalar_one()
    assert director == "John Lasseter"

    collection_name = db_session.execute(
        select(Collection.name)
        .join(Movie, Movie.collection_id == Collection.id)
        .where(Movie.row_index == 0)
    ).scalar_one()
    assert collection_name == "Toy Story Collection"

    keyword_names = set(
        db_session.execute(
            select(Keyword.name)
            .join(MovieKeyword, MovieKeyword.keyword_id == Keyword.id)
            .where(MovieKeyword.tmdb_id == 862)
        )
        .scalars()
        .all()
    )
    assert keyword_names == {"jealousy", "toy"}

    movielens_id = db_session.execute(
        select(MovieLink.movielens_id).where(MovieLink.tmdb_id == 862)
    ).scalar_one()
    assert movielens_id == 1


def test_nulls_and_types_survive_the_copy(db_session: Session, seeded: CleanedData) -> None:
    """COPY must preserve NULLs rather than writing empty strings or zeros."""
    movie = db_session.execute(select(Movie).where(Movie.row_index == 1)).scalar_one()
    assert movie.overview is None
    assert movie.tagline is None
    assert movie.runtime is None
    assert movie.collection_id is None

    toy_story = db_session.execute(select(Movie).where(Movie.row_index == 0)).scalar_one()
    assert toy_story.runtime == 81
    assert toy_story.release_date.isoformat() == "1995-10-30"
    assert toy_story.release_year == 1995
    assert toy_story.budget == 30_000_000
    assert toy_story.adult is False


def test_trigram_search_index_is_usable(db_session: Session, seeded: CleanedData) -> None:
    """pg_trgm must be installed and similarity search must work on titles."""
    installed = db_session.execute(
        text("SELECT count(*) FROM pg_extension WHERE extname = 'pg_trgm'")
    ).scalar_one()
    assert installed == 1

    # Deliberately misspelled to prove fuzzy matching, not exact matching.
    hits = db_session.execute(
        text("SELECT title FROM movies WHERE title ILIKE :pattern"),
        {"pattern": "%toy stor%"},
    ).scalars().all()
    assert "Toy Story" in hits


def test_quote_rejects_sql_injection_in_identifiers() -> None:
    with pytest.raises(ValueError, match="Unsafe SQL identifier"):
        _quote('movies"; DROP TABLE movies; --')
    assert _quote("movie_credits") == '"movie_credits"'


# --------------------------------------------------------------------------- #
# vector artifact
# --------------------------------------------------------------------------- #
def test_l2_normalize_produces_unit_rows_and_tolerates_empty_rows() -> None:
    dense = np.array([[3, 4, 0], [0, 0, 0], [1, 1, 1]], dtype=np.int64)
    normalised = _l2_normalize(densify_to_csr(dense))

    norms = np.sqrt(np.asarray(normalised.multiply(normalised).sum(axis=1))).ravel()
    assert norms[0] == pytest.approx(1.0)
    assert norms[1] == 0.0  # all-zero row stays zero, no NaN
    assert norms[2] == pytest.approx(1.0)
    assert not np.isnan(normalised.data).any()
    assert normalised.dtype == np.float32


def test_l2_normalize_tolerates_trailing_empty_rows() -> None:
    """Regression: a movie with no tags/features sitting at the end of the
    matrix pushed indptr[:-1] to exactly len(data), which IndexError'd in
    np.add.reduceat since every index into reduceat must be < len(data)."""
    dense = np.array([[1, 1, 0], [0, 0, 5], [0, 0, 0], [0, 0, 0]], dtype=np.int64)
    normalised = _l2_normalize(densify_to_csr(dense))

    norms = np.sqrt(np.asarray(normalised.multiply(normalised).sum(axis=1))).ravel()
    assert norms[0] == pytest.approx(1.0)
    assert norms[1] == pytest.approx(1.0)
    assert norms[2] == 0.0
    assert norms[3] == 0.0
    assert not np.isnan(normalised.data).any()


def test_l2_normalize_tolerates_an_entirely_empty_matrix() -> None:
    dense = np.zeros((3, 4), dtype=np.int64)
    normalised = _l2_normalize(densify_to_csr(dense))
    assert normalised.nnz == 0
    assert normalised.shape == (3, 4)


def test_normalized_dot_product_equals_cosine_similarity() -> None:
    """Cosine similarity reduces to a dot product once rows are unit length."""
    dense = np.array([[1, 1, 0], [1, 1, 0], [0, 0, 5]], dtype=np.int64)
    matrix = _l2_normalize(densify_to_csr(dense))
    similarity = (matrix @ matrix.T).toarray()
    assert similarity[0, 1] == pytest.approx(1.0)  # identical direction
    assert similarity[0, 2] == pytest.approx(0.0)  # orthogonal


def test_densify_to_csr_is_chunk_size_invariant() -> None:
    dense = np.random.default_rng(0).integers(0, 3, size=(37, 11))
    whole = densify_to_csr(dense, chunk_rows=1000)
    chunked = densify_to_csr(dense, chunk_rows=4)
    assert whole.shape == chunked.shape == (37, 11)
    assert (whole != chunked).nnz == 0


_VECTOR_ARTIFACTS = [
    BACKEND_ROOT / "data" / "vectors.npz",
    BACKEND_ROOT / "data" / "vector_row_map.npy",
]
requires_vectors = pytest.mark.skipif(
    not all(path.exists() for path in _VECTOR_ARTIFACTS),
    reason="vector artifacts not built (run: python -m etl.vectors)",
)


@requires_vectors
def test_vector_row_map_aligns_with_movies_pkl() -> None:
    """Row i of the matrix must correspond to row i of the curated catalog."""
    matrix, row_map = load_vectors()
    movies = pd.read_pickle(BACKEND_ROOT / "movies.pkl")

    assert matrix.shape[0] == len(movies) == row_map.shape[0]
    assert np.array_equal(row_map, movies["id"].to_numpy(dtype=np.int64))
    assert sp.issparse(matrix)
    assert matrix.dtype == np.float32


@requires_vectors
def test_vector_rows_are_unit_length_or_zero() -> None:
    matrix, _ = load_vectors()
    norms = np.sqrt(np.asarray(matrix.multiply(matrix).sum(axis=1))).ravel()
    nonzero = norms > 0
    assert np.allclose(norms[nonzero], 1.0, atol=1e-5)
    assert not np.isnan(norms).any()
