"""Seed Postgres from the cleaned frames. Idempotent and re-runnable.

Strategy per table
------------------
  * Dimensions (collections, genres, keywords, people) and ``movies`` and
    ``movie_links``: INSERT ... ON CONFLICT DO UPDATE, so re-running refreshes
    values without disturbing rows that user data may reference.
  * Bridge tables (movie_genres, movie_keywords): ON CONFLICT DO NOTHING.
  * ``movie_credits`` has a surrogate key (one person can hold two credits on
    one film), so it cannot be upserted on a natural key. It is fully replaced
    inside the transaction. Nothing user-owned references it.

``movies.pkl`` is never written. Row order is asserted before loading, since
``row_index`` is the join key to the vector matrix.

Usage:
    python -m etl.seed
    python -m etl.seed --truncate     # wipe catalog tables first
    python -m etl.seed --dry-run      # clean + report, write nothing
"""

from __future__ import annotations

import argparse
import math
import time
from collections.abc import Iterable, Sequence
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from etl.clean import CleanedData, build_catalog
from vaultstream.db import SessionLocal
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

CHUNK_SIZE = 5_000


# --------------------------------------------------------------------------- #
# value coercion
# --------------------------------------------------------------------------- #
def _py(value: Any) -> Any:
    """Convert a pandas/numpy scalar into something psycopg can bind.

    psycopg3 does not adapt numpy scalars, and pandas NA sentinels (NaN, NaT,
    pd.NA) must all become None.
    """
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, np.generic):
        value = value.item()
        if isinstance(value, float) and math.isnan(value):
            return None
        return value
    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.date()
    if isinstance(value, np.datetime64):
        stamp = pd.Timestamp(value)
        return None if pd.isna(stamp) else stamp.date()
    return value


def _int_or_none(value: Any) -> int | None:
    value = _py(value)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _records(frame: pd.DataFrame, columns: Sequence[str]) -> list[dict[str, Any]]:
    """Turn a frame into bind-ready dicts with NA -> None."""
    subset = frame[list(columns)]
    return [
        {column: _py(value) for column, value in zip(columns, row, strict=True)}
        for row in subset.itertuples(index=False, name=None)
    ]


def _tuples(rows: Sequence[dict[str, Any]], columns: Sequence[str]) -> list[tuple]:
    """Project dict rows into positional tuples for COPY."""
    return [tuple(row[column] for column in columns) for row in rows]


def _chunks(items: Sequence[dict[str, Any]], size: int = CHUNK_SIZE) -> Iterable[list[dict]]:
    for start in range(0, len(items), size):
        yield list(items[start : start + size])


# --------------------------------------------------------------------------- #
# upsert helpers
# --------------------------------------------------------------------------- #
def _raw_cursor(session: Session):
    """The underlying psycopg cursor, needed for COPY.

    SQLAlchemy has no COPY abstraction, and parameter-binding inserts are far
    too slow at this scale: an executemany upsert of 194k people costs one
    server round trip per row, which measured at minutes rather than seconds.
    """
    return session.connection().connection.driver_connection.cursor()


def _quote(identifier: str) -> str:
    if not identifier.replace("_", "").isalnum():
        raise ValueError(f"Unsafe SQL identifier: {identifier!r}")
    return f'"{identifier}"'


def _bulk_upsert(
    session: Session,
    model: type,
    rows: Sequence[dict[str, Any]],
    columns: Sequence[str],
    conflict_columns: Sequence[str],
    update_columns: Sequence[str] | None = None,
) -> int:
    """COPY into a staging table, then a single INSERT ... SELECT ... ON CONFLICT.

    Orders of magnitude faster than parameterised inserts because the whole
    payload streams in one COPY, and the merge is one set-based statement.
    """
    if not rows:
        return 0

    table = model.__tablename__
    stage = f"stage_{table}"
    column_sql = ", ".join(_quote(column) for column in columns)
    stage_sql = _quote(stage)

    with _raw_cursor(session) as cursor:
        cursor.execute(f"DROP TABLE IF EXISTS {stage_sql}")
        # Inherit exact column types from the target without its constraints,
        # identity sequences, or indexes.
        cursor.execute(
            f"CREATE TEMP TABLE {stage_sql} AS "
            f"SELECT {column_sql} FROM {_quote(table)} WITH NO DATA"
        )

        with cursor.copy(f"COPY {stage_sql} ({column_sql}) FROM STDIN") as copy:
            for row in _tuples(rows, columns):
                copy.write_row(row)

        conflict_sql = ", ".join(_quote(column) for column in conflict_columns)
        # DISTINCT ON guards against "cannot affect row a second time", which
        # ON CONFLICT DO UPDATE raises if one statement touches a key twice.
        select_sql = (
            f"SELECT DISTINCT ON ({conflict_sql}) {column_sql} "
            f"FROM {stage_sql} ORDER BY {conflict_sql}"
        )
        if update_columns:
            assignments = ", ".join(
                f"{_quote(column)} = EXCLUDED.{_quote(column)}" for column in update_columns
            )
            action = f"DO UPDATE SET {assignments}"
        else:
            action = "DO NOTHING"

        cursor.execute(
            f"INSERT INTO {_quote(table)} ({column_sql}) {select_sql} "
            f"ON CONFLICT ({conflict_sql}) {action}"
        )
        cursor.execute(f"DROP TABLE {stage_sql}")

    return len(rows)


def _bulk_insert(
    session: Session,
    model: type,
    rows: Sequence[dict[str, Any]],
    columns: Sequence[str],
) -> int:
    """Straight COPY into the target table (no conflict handling needed)."""
    if not rows:
        return 0
    column_sql = ", ".join(_quote(column) for column in columns)
    with _raw_cursor(session) as cursor:
        with cursor.copy(
            f"COPY {_quote(model.__tablename__)} ({column_sql}) FROM STDIN"
        ) as copy:
            for row in _tuples(rows, columns):
                copy.write_row(row)
    return len(rows)


# --------------------------------------------------------------------------- #
# row builders
# --------------------------------------------------------------------------- #
MOVIE_COLUMNS = (
    "row_index", "tmdb_id", "imdb_id", "title", "original_title", "tagline",
    "overview", "tags", "release_date", "release_year", "runtime",
    "vote_average", "vote_count", "popularity", "budget", "revenue",
    "original_language", "status", "homepage", "poster_path", "backdrop_path",
    "adult", "collection_id",
)

# Integer-typed DB columns arriving as pandas floats/Int64.
_MOVIE_INT_COLUMNS = (
    "release_year", "runtime", "vote_count", "budget", "revenue", "collection_id",
)


def _movie_rows(movies: pd.DataFrame) -> list[dict[str, Any]]:
    rows = _records(movies, MOVIE_COLUMNS)
    for row in rows:
        for column in _MOVIE_INT_COLUMNS:
            row[column] = _int_or_none(row[column])
        row["adult"] = bool(row["adult"]) if row["adult"] is not None else False
        row["title"] = "" if row["title"] is None else str(row["title"])
        if row["tags"] is not None:
            row["tags"] = str(row["tags"])
    return rows


def _credit_rows(credits: pd.DataFrame) -> list[dict[str, Any]]:
    rows = _records(
        credits,
        ("tmdb_id", "person_id", "credit_type", "role", "department", "billing_order"),
    )
    for row in rows:
        row["billing_order"] = _int_or_none(row["billing_order"])
        # DB column is String(500); a few character fields are longer.
        if row["role"] is not None:
            row["role"] = str(row["role"])[:500]
    return rows


# --------------------------------------------------------------------------- #
# orchestration
# --------------------------------------------------------------------------- #
CATALOG_TABLES_IN_FK_ORDER = (
    MovieCredit, MovieGenre, MovieKeyword, MovieLink, Movie, Person, Keyword, Genre, Collection,
)


def truncate_catalog(session: Session) -> None:
    """Wipe catalog tables. Does not touch user/auth/history tables."""
    names = ", ".join(model.__tablename__ for model in CATALOG_TABLES_IN_FK_ORDER)
    session.execute(text(f"TRUNCATE TABLE {names} RESTART IDENTITY CASCADE"))


def seed(
    session: Session,
    data: CleanedData | None = None,
    *,
    truncate: bool = False,
    verbose: bool = False,
) -> dict[str, int]:
    """Load cleaned data into Postgres. Safe to call repeatedly."""

    def _log(message: str) -> None:
        if verbose:
            print(f"    {message}", flush=True)

    data = data or build_catalog()
    movies = data.movies

    # Guard the vector-alignment contract before writing anything.
    expected = np.arange(len(movies), dtype="int64")
    if not np.array_equal(movies["row_index"].to_numpy(), expected):
        raise ValueError("row_index is not 0..n-1; refusing to seed misaligned data.")

    if truncate:
        truncate_catalog(session)

    counts: dict[str, int] = {}
    clock = time.perf_counter()

    def _done(table: str, count: int) -> None:
        nonlocal clock
        elapsed = time.perf_counter() - clock
        clock = time.perf_counter()
        _log(f"{table:<16} {count:>9,} rows  ({elapsed:5.1f}s)")

    # --- dimensions first (movies FK -> collections; credits FK -> people) ---
    collection_columns = ("id", "name", "poster_path", "backdrop_path")
    counts["collections"] = _bulk_upsert(
        session,
        Collection,
        _records(data.collections, collection_columns),
        collection_columns,
        ("id",),
        ("name", "poster_path", "backdrop_path"),
    )
    _done("collections", counts["collections"])

    counts["genres"] = _bulk_upsert(
        session, Genre, _records(data.genres, ("id", "name")), ("id", "name"), ("id",), ("name",)
    )
    _done("genres", counts["genres"])

    counts["keywords"] = _bulk_upsert(
        session,
        Keyword,
        _records(data.keywords, ("id", "name")),
        ("id", "name"),
        ("id",),
        ("name",),
    )
    _done("keywords", counts["keywords"])

    person_columns = ("id", "name", "profile_path", "gender")
    people_rows = _records(data.people, person_columns)
    for row in people_rows:
        row["gender"] = _int_or_none(row["gender"]) or 0
        row["name"] = "" if row["name"] is None else str(row["name"])[:300]
    counts["people"] = _bulk_upsert(
        session,
        Person,
        people_rows,
        person_columns,
        ("id",),
        ("name", "profile_path", "gender"),
    )
    _done("people", counts["people"])

    # --- the catalog itself ---
    counts["movies"] = _bulk_upsert(
        session,
        Movie,
        _movie_rows(movies),
        MOVIE_COLUMNS,
        ("row_index",),
        [column for column in MOVIE_COLUMNS if column != "row_index"],
    )
    _done("movies", counts["movies"])

    # --- bridges ---
    counts["movie_genres"] = _bulk_upsert(
        session,
        MovieGenre,
        _records(data.movie_genres, ("tmdb_id", "genre_id")),
        ("tmdb_id", "genre_id"),
        ("tmdb_id", "genre_id"),
    )
    _done("movie_genres", counts["movie_genres"])

    counts["movie_keywords"] = _bulk_upsert(
        session,
        MovieKeyword,
        _records(data.movie_keywords, ("tmdb_id", "keyword_id")),
        ("tmdb_id", "keyword_id"),
        ("tmdb_id", "keyword_id"),
    )
    _done("movie_keywords", counts["movie_keywords"])

    link_columns = ("tmdb_id", "movielens_id", "imdb_numeric_id")
    counts["movie_links"] = _bulk_upsert(
        session,
        MovieLink,
        _records(data.links, link_columns),
        link_columns,
        ("tmdb_id",),
        ("movielens_id", "imdb_numeric_id"),
    )
    _done("movie_links", counts["movie_links"])

    # --- credits: full replace (surrogate PK has no natural conflict target) ---
    credit_columns = (
        "tmdb_id", "person_id", "credit_type", "role", "department", "billing_order",
    )
    session.execute(delete(MovieCredit))
    counts["movie_credits"] = _bulk_insert(
        session, MovieCredit, _credit_rows(data.credits), credit_columns
    )
    _done("movie_credits", counts["movie_credits"])

    return counts


def table_counts(session: Session) -> dict[str, int]:
    result: dict[str, int] = {}
    for model in reversed(CATALOG_TABLES_IN_FK_ORDER):
        result[model.__tablename__] = int(
            session.execute(select(func.count()).select_from(model)).scalar_one()
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the VaultStream catalog.")
    parser.add_argument("--truncate", action="store_true", help="Wipe catalog tables first.")
    parser.add_argument("--dry-run", action="store_true", help="Clean and report only.")
    args = parser.parse_args()

    rule = "=" * 68
    started = time.perf_counter()

    print("[1/3] Cleaning source data (reads ~270MB of pickles, ~60s)...", flush=True)
    data = build_catalog()
    print(f"      catalog rows: {len(data.movies):,}", flush=True)

    if args.dry_run:
        print("\n--dry-run: nothing written.")
        return 0

    print("[2/3] Writing to Postgres...", flush=True)
    with SessionLocal() as session:
        counts = seed(session, data, truncate=args.truncate, verbose=True)
        print("[3/3] Committing...", flush=True)
        session.commit()
        actual = table_counts(session)

    elapsed = time.perf_counter() - started
    print()
    print(rule)
    print("Seed complete")
    print(rule)
    print(f"{'table':<18}{'submitted':>12}{'in database':>14}")
    print("-" * 68)
    for table, in_db in actual.items():
        print(f"{table:<18}{counts.get(table, 0):>12,}{in_db:>14,}")
    print("-" * 68)
    print(f"elapsed: {elapsed:,.1f}s")
    print(rule)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
