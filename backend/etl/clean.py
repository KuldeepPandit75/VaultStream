"""Clean and join the raw pickles into validated, load-ready frames.

Contract with the raw data
--------------------------
``movies.pkl`` is user-curated and TREATED AS IMMUTABLE. This module never
writes it, never reorders it, and never drops rows from it. Its positional
RangeIndex is the join key to ``vectors.pkl`` and becomes ``movies.row_index``
in Postgres.

Consequences of the real data (measured, see etl/inspect_data.py):
  * movies.pkl  : 45,264 rows / 44,121 distinct ids -> id is NOT unique, so
                  row_index is the primary key and tmdb_id is a non-unique
                  indexed column. 1,142 rows are exact full-row duplicates.
  * metadata    : `id` is text, ~30 duplicate ids, and a handful of rows have
                  shifted columns (detected via `adult` not in {True, False}).
  * nested cols : Python-literal strings (single quotes) -> ast.literal_eval,
                  NOT json.loads.
  * relations   : keyed by tmdb_id, not row_index, so duplicated catalog rows
                  do not multiply cast/genre rows.

Usage:
    python -m etl.clean            # print the data-quality report
    python -m etl.clean --json     # machine-readable report
"""

from __future__ import annotations

import argparse
import ast
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

BACKEND_ROOT = Path(__file__).resolve().parent.parent

# Cap credits so we store what the UI actually shows instead of 500k+ rows.
MAX_CAST_PER_MOVIE = 15
CREW_JOBS_KEPT = ("Director", "Writer", "Screenplay", "Story", "Producer")

VALID_ADULT = {"True", "False"}


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _parse_literal(value: Any) -> Any:
    """Safely evaluate a Python-literal string; return None on anything odd."""
    if value is None or isinstance(value, float):  # NaN arrives as float
        return None
    if isinstance(value, (list, dict)):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or text in {"[]", "{}"}:
        return [] if text == "[]" else ({} if text == "{}" else None)
    try:
        return ast.literal_eval(text)
    except (ValueError, SyntaxError, MemoryError, RecursionError):
        return None


def _parse_list(value: Any) -> list[dict[str, Any]]:
    parsed = _parse_literal(value)
    return parsed if isinstance(parsed, list) else []


def _parse_dict(value: Any) -> dict[str, Any] | None:
    parsed = _parse_literal(value)
    return parsed if isinstance(parsed, dict) else None


def _norm_blank(item: Any) -> str | None:
    """Empty / whitespace / NaN / 'nan' / 'None' all collapse to None."""
    if item is None:
        return None
    if isinstance(item, float) and np.isnan(item):
        return None
    text = str(item).strip()
    if text == "" or text.lower() in {"nan", "none"}:
        return None
    return text


def _blank_to_none(series: pd.Series) -> pd.Series:
    """Normalise empty/whitespace/sentinel strings to a real ``None``.

    Built explicitly with dtype=object because pandas re-coerces ``None`` back
    to ``NaN`` when it infers the dtype of a mapped result.
    """
    return pd.Series(
        [_norm_blank(value) for value in series.tolist()],
        index=series.index,
        dtype="object",
    )


@dataclass
class CleanReport:
    """Counters describing what the pipeline did."""

    movies_rows: int = 0
    movies_distinct_ids: int = 0
    movies_exact_duplicate_rows: int = 0
    metadata_rows_in: int = 0
    metadata_malformed_dropped: int = 0
    metadata_unparseable_id_dropped: int = 0
    metadata_duplicate_ids_dropped: int = 0
    metadata_rows_out: int = 0
    adult_titles_flagged: int = 0
    credits_rows_in: int = 0
    credits_duplicate_ids_dropped: int = 0
    keywords_rows_in: int = 0
    keywords_duplicate_ids_dropped: int = 0
    links_rows_in: int = 0
    links_null_tmdb_dropped: int = 0
    coverage: dict[str, float] = field(default_factory=dict)
    matched: dict[str, int] = field(default_factory=dict)
    relation_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "movies": {
                "rows": self.movies_rows,
                "distinct_ids": self.movies_distinct_ids,
                "exact_duplicate_rows": self.movies_exact_duplicate_rows,
            },
            "metadata": {
                "rows_in": self.metadata_rows_in,
                "malformed_dropped": self.metadata_malformed_dropped,
                "unparseable_id_dropped": self.metadata_unparseable_id_dropped,
                "duplicate_ids_dropped": self.metadata_duplicate_ids_dropped,
                "rows_out": self.metadata_rows_out,
                "adult_titles_flagged": self.adult_titles_flagged,
            },
            "credits": {
                "rows_in": self.credits_rows_in,
                "duplicate_ids_dropped": self.credits_duplicate_ids_dropped,
            },
            "keywords": {
                "rows_in": self.keywords_rows_in,
                "duplicate_ids_dropped": self.keywords_duplicate_ids_dropped,
            },
            "links": {
                "rows_in": self.links_rows_in,
                "null_tmdb_dropped": self.links_null_tmdb_dropped,
            },
            "matched": self.matched,
            "field_coverage_pct": self.coverage,
            "relation_counts": self.relation_counts,
        }


@dataclass
class CleanedData:
    """Load-ready frames. ``movies`` is row-index-keyed; relations are tmdb_id-keyed."""

    movies: pd.DataFrame
    genres: pd.DataFrame
    movie_genres: pd.DataFrame
    keywords: pd.DataFrame
    movie_keywords: pd.DataFrame
    people: pd.DataFrame
    credits: pd.DataFrame
    collections: pd.DataFrame
    links: pd.DataFrame
    report: CleanReport


# --------------------------------------------------------------------------- #
# loaders
# --------------------------------------------------------------------------- #
def load_movies(root: Path = BACKEND_ROOT) -> pd.DataFrame:
    """Load the canonical curated catalog, adding row_index without reordering.

    Raises if the frame is not a clean 0..n-1 RangeIndex, because that ordering
    is the only thing tying these rows to vectors.pkl.
    """
    return load_movies_frame(pd.read_pickle(root / "movies.pkl"))


def load_movies_frame(movies: pd.DataFrame) -> pd.DataFrame:
    """Attach row_index to the canonical catalog without reordering it."""
    expected = pd.RangeIndex(start=0, stop=len(movies), step=1)
    if not movies.index.equals(expected):
        raise ValueError(
            "movies.pkl index is not a contiguous 0..n-1 RangeIndex; "
            "vector alignment cannot be guaranteed."
        )

    out = movies.copy()
    out.insert(0, "row_index", np.arange(len(out), dtype="int64"))
    out = out.rename(columns={"id": "tmdb_id"})
    out["tmdb_id"] = out["tmdb_id"].astype("int64")
    out["imdb_id"] = _blank_to_none(out["imdb_id"])
    out["title"] = out["title"].astype("string")
    out["tags"] = out["tags"].astype("string")
    out["poster_path"] = _blank_to_none(out["poster_path"])
    return out


def clean_metadata(root: Path = BACKEND_ROOT, report: CleanReport | None = None) -> pd.DataFrame:
    """Load and clean movies_metadata.pkl."""
    return clean_metadata_frame(
        pd.read_pickle(root / "movies_metadata.pkl"), report
    )


def clean_metadata_frame(
    meta: pd.DataFrame, report: CleanReport | None = None
) -> pd.DataFrame:
    """Clean a metadata frame into one row per tmdb_id (pure, testable)."""
    rep = report or CleanReport()
    rep.metadata_rows_in = len(meta)

    # 1. Drop structurally broken rows. A shifted row puts a date in `budget`,
    #    which reliably shows up as `adult` holding something other than a bool.
    malformed = ~meta["adult"].isin(VALID_ADULT)
    rep.metadata_malformed_dropped = int(malformed.sum())
    meta = meta[~malformed]

    # 2. Coerce the text id to int, dropping anything unparseable.
    numeric_id = pd.to_numeric(meta["id"], errors="coerce")
    unparseable = numeric_id.isna()
    rep.metadata_unparseable_id_dropped = int(unparseable.sum())
    meta = meta[~unparseable].copy()
    meta["tmdb_id"] = numeric_id[~unparseable].astype("int64")

    # 3. One row per movie.
    duplicated = meta["tmdb_id"].duplicated(keep="first")
    rep.metadata_duplicate_ids_dropped = int(duplicated.sum())
    meta = meta[~duplicated].copy()

    # 4. Types.
    meta["adult"] = meta["adult"].eq("True")
    rep.adult_titles_flagged = int(meta["adult"].sum())

    for col in ("budget", "revenue", "runtime", "popularity", "vote_average", "vote_count"):
        meta[col] = pd.to_numeric(meta[col], errors="coerce")

    meta["release_date"] = pd.to_datetime(meta["release_date"], errors="coerce")
    meta["release_year"] = meta["release_date"].dt.year.astype("Int64")

    # runtime of 0 is "unknown", not a zero-length film.
    meta["runtime"] = meta["runtime"].replace(0, np.nan)

    for col in ("overview", "tagline", "homepage", "poster_path", "original_language",
                "original_title", "status", "title", "imdb_id"):
        meta[col] = _blank_to_none(meta[col])

    # 5. Nested columns.
    meta["genres_parsed"] = meta["genres"].map(_parse_list)
    meta["collection_parsed"] = meta["belongs_to_collection"].map(_parse_dict)
    meta["production_companies_parsed"] = meta["production_companies"].map(_parse_list)
    meta["spoken_languages_parsed"] = meta["spoken_languages"].map(_parse_list)

    keep = [
        "tmdb_id", "imdb_id", "title", "original_title", "tagline", "overview",
        "release_date", "release_year", "runtime", "vote_average", "vote_count",
        "popularity", "budget", "revenue", "original_language", "status",
        "homepage", "poster_path", "adult",
        "genres_parsed", "collection_parsed", "production_companies_parsed",
        "spoken_languages_parsed",
    ]
    result = meta[keep].reset_index(drop=True)
    rep.metadata_rows_out = len(result)
    return result


def clean_keywords(root: Path = BACKEND_ROOT, report: CleanReport | None = None) -> pd.DataFrame:
    return clean_keywords_frame(pd.read_pickle(root / "keywords.pkl"), report)


def clean_keywords_frame(
    kw: pd.DataFrame, report: CleanReport | None = None
) -> pd.DataFrame:
    rep = report or CleanReport()
    rep.keywords_rows_in = len(kw)
    duplicated = kw["id"].duplicated(keep="first")
    rep.keywords_duplicate_ids_dropped = int(duplicated.sum())
    kw = kw[~duplicated].copy()
    kw["tmdb_id"] = kw["id"].astype("int64")
    kw["keywords_parsed"] = kw["keywords"].map(_parse_list)
    return kw[["tmdb_id", "keywords_parsed"]].reset_index(drop=True)


def clean_credits(root: Path = BACKEND_ROOT, report: CleanReport | None = None) -> pd.DataFrame:
    return clean_credits_frame(pd.read_pickle(root / "credits.pkl"), report)


def clean_credits_frame(
    credits: pd.DataFrame, report: CleanReport | None = None
) -> pd.DataFrame:
    rep = report or CleanReport()
    rep.credits_rows_in = len(credits)
    duplicated = credits["id"].duplicated(keep="first")
    rep.credits_duplicate_ids_dropped = int(duplicated.sum())
    credits = credits[~duplicated].copy()
    credits["tmdb_id"] = credits["id"].astype("int64")
    credits["cast_parsed"] = credits["cast"].map(_parse_list)
    credits["crew_parsed"] = credits["crew"].map(_parse_list)
    return credits[["tmdb_id", "cast_parsed", "crew_parsed"]].reset_index(drop=True)


def clean_links(root: Path = BACKEND_ROOT, report: CleanReport | None = None) -> pd.DataFrame:
    return clean_links_frame(pd.read_pickle(root / "links.pkl"), report)


def clean_links_frame(
    links: pd.DataFrame, report: CleanReport | None = None
) -> pd.DataFrame:
    rep = report or CleanReport()
    rep.links_rows_in = len(links)
    missing = links["tmdbId"].isna()
    rep.links_null_tmdb_dropped = int(missing.sum())
    links = links[~missing].copy()
    links["tmdb_id"] = links["tmdbId"].astype("int64")
    links = links[~links["tmdb_id"].duplicated(keep="first")]
    return (
        links.rename(columns={"movieId": "movielens_id", "imdbId": "imdb_numeric_id"})[
            ["tmdb_id", "movielens_id", "imdb_numeric_id"]
        ]
        .astype("int64")
        .reset_index(drop=True)
    )


# --------------------------------------------------------------------------- #
# relation extraction
# --------------------------------------------------------------------------- #
def _explode_named_entities(
    frame: pd.DataFrame, list_column: str, wanted_ids: set[int]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split a [{id, name}, ...] column into (dimension, bridge) frames."""
    dimension: dict[int, str] = {}
    bridge: list[tuple[int, int]] = []

    for tmdb_id, items in zip(frame["tmdb_id"], frame[list_column], strict=True):
        if tmdb_id not in wanted_ids or not items:
            continue
        seen: set[int] = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            entity_id, name = item.get("id"), item.get("name")
            if entity_id is None or not name:
                continue
            entity_id = int(entity_id)
            dimension.setdefault(entity_id, str(name).strip())
            if entity_id not in seen:
                seen.add(entity_id)
                bridge.append((int(tmdb_id), entity_id))

    dim_df = pd.DataFrame(
        sorted(dimension.items()), columns=["id", "name"]
    ).astype({"id": "int64", "name": "string"})
    bridge_df = pd.DataFrame(bridge, columns=["tmdb_id", "entity_id"]).astype("int64")
    return dim_df, bridge_df


def _extract_credits(
    credits: pd.DataFrame, wanted_ids: set[int]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build (people, credits) capped at top billed cast plus key crew jobs."""
    people: dict[int, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []

    for tmdb_id, cast, crew in zip(
        credits["tmdb_id"], credits["cast_parsed"], credits["crew_parsed"], strict=True
    ):
        if tmdb_id not in wanted_ids:
            continue
        tmdb_id = int(tmdb_id)

        members = [c for c in (cast or []) if isinstance(c, dict) and c.get("id") is not None]
        members.sort(key=lambda c: c.get("order") if isinstance(c.get("order"), int) else 10**6)
        for member in members[:MAX_CAST_PER_MOVIE]:
            person_id = int(member["id"])
            people.setdefault(
                person_id,
                {
                    "id": person_id,
                    "name": str(member.get("name") or "").strip(),
                    "profile_path": member.get("profile_path") or None,
                    "gender": int(member.get("gender") or 0),
                },
            )
            order = member.get("order")
            rows.append(
                {
                    "tmdb_id": tmdb_id,
                    "person_id": person_id,
                    "credit_type": "cast",
                    "role": str(member.get("character") or "").strip() or None,
                    "department": None,
                    "billing_order": int(order) if isinstance(order, int) else None,
                }
            )

        seen_crew: set[tuple[int, str]] = set()
        for member in crew or []:
            if not isinstance(member, dict) or member.get("id") is None:
                continue
            job = str(member.get("job") or "").strip()
            if job not in CREW_JOBS_KEPT:
                continue
            person_id = int(member["id"])
            key = (person_id, job)
            if key in seen_crew:
                continue
            seen_crew.add(key)
            people.setdefault(
                person_id,
                {
                    "id": person_id,
                    "name": str(member.get("name") or "").strip(),
                    "profile_path": member.get("profile_path") or None,
                    "gender": int(member.get("gender") or 0),
                },
            )
            rows.append(
                {
                    "tmdb_id": tmdb_id,
                    "person_id": person_id,
                    "credit_type": "crew",
                    "role": job,
                    "department": str(member.get("department") or "").strip() or None,
                    "billing_order": None,
                }
            )

    people_df = pd.DataFrame(
        sorted(people.values(), key=lambda p: p["id"]),
        columns=["id", "name", "profile_path", "gender"],
    )
    if people_df.empty:
        people_df = pd.DataFrame(columns=["id", "name", "profile_path", "gender"])
    credits_df = pd.DataFrame(
        rows,
        columns=["tmdb_id", "person_id", "credit_type", "role", "department", "billing_order"],
    )
    return people_df, credits_df


def _extract_collections(metadata: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Build the collections dimension and a tmdb_id -> collection_id series."""
    collections: dict[int, dict[str, Any]] = {}
    mapping: dict[int, int] = {}

    for tmdb_id, payload in zip(
        metadata["tmdb_id"], metadata["collection_parsed"], strict=True
    ):
        if not isinstance(payload, dict):
            continue
        collection_id = payload.get("id")
        if collection_id is None:
            continue
        collection_id = int(collection_id)
        collections.setdefault(
            collection_id,
            {
                "id": collection_id,
                "name": str(payload.get("name") or "").strip() or None,
                "poster_path": payload.get("poster_path") or None,
                "backdrop_path": payload.get("backdrop_path") or None,
            },
        )
        mapping[int(tmdb_id)] = collection_id

    collections_df = pd.DataFrame(
        sorted(collections.values(), key=lambda c: c["id"]),
        columns=["id", "name", "poster_path", "backdrop_path"],
    )
    return collections_df, pd.Series(mapping, dtype="Int64")


# --------------------------------------------------------------------------- #
# orchestration
# --------------------------------------------------------------------------- #
def build_catalog(root: Path = BACKEND_ROOT) -> CleanedData:
    """Run the whole pipeline, preserving movies.pkl row order exactly."""
    report = CleanReport()

    movies = load_movies(root)
    report.movies_rows = len(movies)
    report.movies_distinct_ids = int(movies["tmdb_id"].nunique())
    report.movies_exact_duplicate_rows = int(
        movies.drop(columns=["row_index"]).duplicated().sum()
    )
    wanted_ids = set(movies["tmdb_id"].tolist())

    metadata = clean_metadata(root, report)
    keywords_raw = clean_keywords(root, report)
    credits_raw = clean_credits(root, report)
    links = clean_links(root, report)
    links = links[links["tmdb_id"].isin(wanted_ids)].reset_index(drop=True)

    # --- relations (tmdb_id-keyed, so duplicate catalog rows don't multiply) ---
    genres, movie_genres = _explode_named_entities(metadata, "genres_parsed", wanted_ids)
    movie_genres = movie_genres.rename(columns={"entity_id": "genre_id"})

    keyword_dim, movie_keywords = _explode_named_entities(
        keywords_raw, "keywords_parsed", wanted_ids
    )
    movie_keywords = movie_keywords.rename(columns={"entity_id": "keyword_id"})

    people, credits = _extract_credits(credits_raw, wanted_ids)
    collections, collection_map = _extract_collections(metadata)

    # --- LEFT JOIN metadata onto the canonical catalog, order preserved ---
    metadata_cols = [
        "tmdb_id", "tagline", "overview", "release_date", "release_year", "runtime",
        "vote_average", "vote_count", "popularity", "budget", "revenue",
        "original_language", "original_title", "status", "homepage", "adult",
    ]
    before = movies["row_index"].to_numpy(copy=True)
    enriched = movies.merge(
        metadata[metadata_cols], on="tmdb_id", how="left", validate="many_to_one"
    )
    if not np.array_equal(enriched["row_index"].to_numpy(), before):
        raise ValueError("LEFT JOIN altered movies.pkl row order; refusing to continue.")

    enriched["collection_id"] = enriched["tmdb_id"].map(collection_map).astype("Int64")
    # Populated later by the TMDB resolver (Task 8); the dataset has no backdrops.
    enriched["backdrop_path"] = pd.Series([None] * len(enriched), dtype="object")
    # adult is missing for rows with no metadata match: default to not-adult but
    # such rows are also excluded from browse by the quality floor.
    enriched["adult"] = enriched["adult"].fillna(False).astype(bool)

    # --- coverage ---
    report.matched = {
        "metadata": int(enriched["overview"].notna().sum()),
        "genres": int(movie_genres["tmdb_id"].nunique()),
        "keywords": int(movie_keywords["tmdb_id"].nunique()),
        "credits": int(credits["tmdb_id"].nunique()),
        "links": int(links["tmdb_id"].nunique()),
        "collections": int(enriched["collection_id"].notna().sum()),
    }
    total = len(enriched)
    for column in (
        "overview", "tagline", "release_date", "runtime", "vote_average",
        "popularity", "poster_path", "original_language",
    ):
        report.coverage[column] = round(
            float(enriched[column].notna().sum()) / total * 100, 2
        )
    report.relation_counts = {
        "genres": len(genres),
        "movie_genres": len(movie_genres),
        "keywords": len(keyword_dim),
        "movie_keywords": len(movie_keywords),
        "people": len(people),
        "credits": len(credits),
        "collections": len(collections),
        "links": len(links),
    }

    return CleanedData(
        movies=enriched,
        genres=genres,
        movie_genres=movie_genres,
        keywords=keyword_dim,
        movie_keywords=movie_keywords,
        people=people,
        credits=credits,
        collections=collections,
        links=links,
        report=report,
    )


def _print_report(data: CleanedData) -> None:
    rep = data.report
    rule = "=" * 72
    print(rule)
    print("VaultStream ETL data-quality report")
    print(rule)

    print("\nCANONICAL CATALOG (movies.pkl - immutable, order preserved)")
    print(f"  rows                     : {rep.movies_rows:,}")
    print(f"  distinct tmdb ids        : {rep.movies_distinct_ids:,}")
    print(f"  exact duplicate rows     : {rep.movies_exact_duplicate_rows:,}")
    print("  primary key              : row_index (0..n-1), tmdb_id is non-unique")

    print("\nMETADATA CLEANING")
    print(f"  rows in                  : {rep.metadata_rows_in:,}")
    print(f"  malformed dropped        : {rep.metadata_malformed_dropped:,}")
    print(f"  unparseable id dropped   : {rep.metadata_unparseable_id_dropped:,}")
    print(f"  duplicate ids dropped    : {rep.metadata_duplicate_ids_dropped:,}")
    print(f"  rows out                 : {rep.metadata_rows_out:,}")
    print(f"  adult titles flagged     : {rep.adult_titles_flagged:,}")

    print("\nSUPPORTING FRAMES")
    print(f"  credits rows in          : {rep.credits_rows_in:,} "
          f"(dupes dropped {rep.credits_duplicate_ids_dropped:,})")
    print(f"  keywords rows in         : {rep.keywords_rows_in:,} "
          f"(dupes dropped {rep.keywords_duplicate_ids_dropped:,})")
    print(f"  links rows in            : {rep.links_rows_in:,} "
          f"(null tmdbId dropped {rep.links_null_tmdb_dropped:,})")

    print("\nJOIN COVERAGE (movies with at least one match)")
    for key, value in rep.matched.items():
        pct = value / rep.movies_rows * 100
        print(f"  {key:<24} : {value:>7,} / {rep.movies_rows:,}  ({pct:5.1f}%)")

    print("\nFIELD COVERAGE (% of catalog rows non-null)")
    for key, value in rep.coverage.items():
        print(f"  {key:<24} : {value:5.1f}%")

    print("\nRELATION ROW COUNTS (to be loaded in Task 3)")
    for key, value in rep.relation_counts.items():
        print(f"  {key:<24} : {value:>9,}")

    print()
    print(rule)
    print("Clean complete. No source file was modified.")
    print(rule)


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean and join VaultStream source data.")
    parser.add_argument("--json", action="store_true", help="Emit the report as JSON.")
    args = parser.parse_args()

    data = build_catalog()
    if args.json:
        print(json.dumps(data.report.to_dict(), indent=2))
    else:
        _print_report(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
