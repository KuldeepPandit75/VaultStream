"""Import movies released after the curated dataset's ~2017 cutoff.

Why this exists
----------------
``movies.pkl`` is a static snapshot with negligible coverage after 2016 (see
``etl/clean.py``'s docstring on the dataset being immutable). This script pulls
newer titles directly from TMDB and appends them to the catalogue in the same
shape ``etl/seed.py`` writes: rows in ``movies``, bridged genres/keywords, and
capped cast/crew credits.

Scope, on purpose
-----------------
This script ONLY imports catalogue rows. It does not touch the recommendation
vector matrix (``data/vectors.npz`` / ``data/vector_row_map.npy``) in any way --
that is handled separately. A title imported here will simply score 0 in the
content-based recommender (below vector_index's similarity floor) until it is
vectorised through whatever process the vectors are rebuilt with.

How it works
-------------
1. ``/discover/movie`` pages by release-date window, sorted by popularity, to
   find candidate tmdb_ids -- skipping ones already in the catalogue.
2. ``/movie/{id}?append_to_response=videos,credits,keywords`` fetches full
   detail for each candidate in one call, including trailer info.
3. New rows get ``row_index`` values continuing from ``MAX(row_index) + 1``,
   preserving the contiguous 0..n-1 invariant the rest of the app relies on.
4. Dimension tables (genres, keywords, people) are upserted; the new movie,
   bridge, and credit rows are plain inserts scoped to just the new titles --
   unlike ``etl/seed.py``, existing credits are never touched or replaced.
5. The parsed trailer/poster/backdrop go into ``movie_media`` via the same
   ``services.media.store`` the artwork backfill uses, so playback works for
   these titles without a separate pass.

Safe to interrupt and resume: candidates already present in ``movies`` (by
tmdb_id) are skipped on the next run.

Usage:
    python -m etl.import_new_movies --dry-run                      # preview
    python -m etl.import_new_movies --start-year 2018 --limit 300 --apply
    python -m etl.import_new_movies --start-year 2018 --end-year 2026 --apply
"""

from __future__ import annotations

import argparse
import asyncio
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import httpx
from sqlalchemy import bindparam, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from vaultstream.config import get_settings
from vaultstream.db import SessionLocal
from vaultstream.models.catalog import (
    Genre,
    Keyword,
    Movie,
    MovieCredit,
    MovieGenre,
    MovieKeyword,
    Person,
)
from vaultstream.services import media as media_service
from vaultstream.services.tmdb import (
    MAX_RETRIES,
    MediaPayload,
    TMDBAuthError,
    _auth,
    _backoff,
    parse_media_payload,
)

DEFAULT_CONCURRENCY = 12
DISCOVER_PAGE_SIZE = 20  # fixed by TMDB
MAX_CAST_PER_MOVIE = 15
CREW_JOBS_KEPT = ("Director", "Writer", "Screenplay", "Story", "Producer")
# Movies written per transaction. Bounds each batch's worst case (~15 cast +
# ~5 crew + ~10 genres/keywords per movie) well under Postgres's 65,535
# bound-parameter ceiling, and keeps a run resumable if interrupted.
WRITE_BATCH_SIZE = 200

_DETAIL_PARAMS = {
    "append_to_response": "videos,credits,keywords",
    "language": "en-US",
}


# --------------------------------------------------------------------------- #
# TMDB fetching
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class NewMovie:
    """Everything needed to write one new catalogue row plus its relations."""

    tmdb_id: int
    imdb_id: str | None
    title: str
    original_title: str | None
    tagline: str | None
    overview: str | None
    release_date: date | None
    runtime: int | None
    vote_average: float | None
    vote_count: int | None
    popularity: float | None
    budget: int | None
    revenue: int | None
    original_language: str | None
    status: str | None
    homepage: str | None
    poster_path: str | None
    backdrop_path: str | None
    adult: bool
    genres: list[tuple[int, str]] = field(default_factory=list)
    keywords: list[tuple[int, str]] = field(default_factory=list)
    cast: list[dict[str, Any]] = field(default_factory=list)
    crew: list[dict[str, Any]] = field(default_factory=list)
    # Trailer resolution, parsed from the same `videos` block the movie/
    # discover response already carries -- populates `movie_media` so playback
    # has a trailer without a separate backfill pass for these new titles.
    media: MediaPayload | None = None


async def _discover_ids(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    params: dict[str, str],
    start_year: int,
    end_year: int,
    limit: int,
) -> list[int]:
    """Popularity-ordered tmdb_ids released within [start_year, end_year]."""
    ids: list[int] = []
    seen: set[int] = set()
    page = 1
    max_pages = 500  # TMDB's own ceiling

    started = time.perf_counter()

    while len(ids) < limit and page <= max_pages:
        body = None
        for attempt in range(MAX_RETRIES):
            try:
                response = await client.get(
                    "/discover/movie",
                    headers=headers,
                    params={
                        **params,
                        "sort_by": "popularity.desc",
                        "primary_release_date.gte": f"{start_year}-01-01",
                        "primary_release_date.lte": f"{end_year}-12-31",
                        "include_adult": "false",
                        "page": page,
                    },
                    timeout=httpx.Timeout(20.0),
                )
            except httpx.HTTPError as exc:
                if attempt == MAX_RETRIES - 1:
                    print(f"  page {page}: giving up after retries ({exc})", flush=True)
                    return ids[:limit]
                await asyncio.sleep(_backoff(attempt))
                continue

            if response.status_code in (401, 403):
                raise TMDBAuthError("TMDB rejected the configured credentials.")
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else _backoff(attempt)
                print(f"  page {page}: TMDB 429, sleeping {delay:.1f}s", flush=True)
                await asyncio.sleep(delay)
                continue
            if response.status_code >= 500:
                if attempt == MAX_RETRIES - 1:
                    print(f"  page {page}: giving up after HTTP {response.status_code}", flush=True)
                    return ids[:limit]
                await asyncio.sleep(_backoff(attempt))
                continue

            response.raise_for_status()
            body = response.json()
            break

        if body is None:
            break

        results = body.get("results") or []
        if not results:
            break

        for movie in results:
            tmdb_id = movie.get("id")
            if tmdb_id is None or tmdb_id in seen:
                continue
            seen.add(tmdb_id)
            ids.append(int(tmdb_id))
            if len(ids) >= limit:
                break

        if page % 25 == 0 or page == 1:
            elapsed = time.perf_counter() - started
            print(
                f"  discover page {page}/{min(max_pages, int(body.get('total_pages') or max_pages))}  "
                f"({len(ids):,} ids so far, {elapsed:.0f}s elapsed)",
                flush=True,
            )

        if page >= int(body.get("total_pages") or 1):
            break
        page += 1

    return ids[:limit]


def _parse_detail(body: dict[str, Any]) -> NewMovie:
    genres = [
        (int(g["id"]), str(g["name"]))
        for g in (body.get("genres") or [])
        if g.get("id") is not None and g.get("name")
    ]
    keywords = [
        (int(k["id"]), str(k["name"]))
        for k in ((body.get("keywords") or {}).get("keywords") or [])
        if k.get("id") is not None and k.get("name")
    ]

    credits_block = body.get("credits") or {}
    cast = [
        member
        for member in (credits_block.get("cast") or [])[:MAX_CAST_PER_MOVIE]
        if isinstance(member, dict) and member.get("id") is not None
    ]
    crew = [
        member
        for member in (credits_block.get("crew") or [])
        if isinstance(member, dict)
        and member.get("id") is not None
        and member.get("job") in CREW_JOBS_KEPT
    ]

    release_date = None
    raw_date = body.get("release_date") or None
    if raw_date:
        try:
            release_date = date.fromisoformat(raw_date)
        except ValueError:
            release_date = None

    # `movies.collection_id` exists in the schema, but wiring a newly-discovered
    # collection through here would mean also upserting `collections`, which
    # isn't needed to import catalogue rows. Left unset (None).
    tmdb_id = int(body["id"])
    return NewMovie(
        tmdb_id=tmdb_id,
        imdb_id=body.get("imdb_id") or None,
        title=str(body.get("title") or body.get("original_title") or "Untitled"),
        original_title=body.get("original_title") or None,
        tagline=body.get("tagline") or None,
        overview=body.get("overview") or None,
        release_date=release_date,
        runtime=int(body["runtime"]) if body.get("runtime") else None,
        vote_average=float(body["vote_average"]) if body.get("vote_average") is not None else None,
        vote_count=int(body["vote_count"]) if body.get("vote_count") is not None else None,
        popularity=float(body["popularity"]) if body.get("popularity") is not None else None,
        budget=int(body["budget"]) if body.get("budget") else None,
        revenue=int(body["revenue"]) if body.get("revenue") else None,
        original_language=body.get("original_language") or None,
        status=body.get("status") or None,
        homepage=body.get("homepage") or None,
        poster_path=body.get("poster_path") or None,
        backdrop_path=body.get("backdrop_path") or None,
        adult=bool(body.get("adult") or False),
        genres=genres,
        keywords=keywords,
        cast=cast,
        crew=crew,
        media=parse_media_payload(tmdb_id, body),
    )


async def _fetch_detail(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    params: dict[str, str],
    tmdb_id: int,
    semaphore: asyncio.Semaphore,
) -> NewMovie | None:
    async with semaphore:
        for attempt in range(MAX_RETRIES):
            response = await client.get(
                f"/movie/{tmdb_id}", headers=headers, params={**params, **_DETAIL_PARAMS}
            )
            if response.status_code == 404:
                return None
            if response.status_code in (401, 403):
                raise TMDBAuthError("TMDB rejected the configured credentials.")
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                await asyncio.sleep(float(retry_after) if retry_after else _backoff(attempt))
                continue
            if response.status_code >= 500:
                await asyncio.sleep(_backoff(attempt))
                continue
            response.raise_for_status()
            return _parse_detail(response.json())
    return None


# --------------------------------------------------------------------------- #
# writing
# --------------------------------------------------------------------------- #
def _existing_tmdb_ids(session: Session) -> set[int]:
    return {int(v) for v in session.execute(select(Movie.tmdb_id)).scalars().all()}


def _next_row_index(session: Session) -> int:
    current_max = session.execute(select(func.max(Movie.row_index))).scalar_one()
    return int(current_max) + 1 if current_max is not None else 0


def _write_movies(session: Session, movies: list[NewMovie], start_row_index: int) -> dict[str, int]:
    """Write one batch: dimensions upserted, movie/bridge/credit rows inserted."""
    counts = {"movies": 0, "genres": 0, "keywords": 0, "people": 0,
              "movie_genres": 0, "movie_keywords": 0, "movie_credits": 0,
              "movie_media": 0}
    if not movies:
        return counts

    # --- dimensions: genres, keywords, people (upsert; shared across movies) ---
    #
    # Each upsert uses executemany (a list of dicts passed as the second
    # `execute()` argument, matched against a single bindparam-based
    # statement) rather than `.values([...])`, which inlines every row into
    # one VALUES clause and blew past Postgres's 65,535-bound-parameter limit
    # once a batch spans a few thousand movies' worth of people/keywords.
    genre_rows = {gid: name for m in movies for gid, name in m.genres}
    if genre_rows:
        statement = insert(Genre).values(id=bindparam("id"), name=bindparam("name"))
        statement = statement.on_conflict_do_update(
            index_elements=["id"], set_={"name": statement.excluded.name}
        )
        session.execute(
            statement, [{"id": gid, "name": name} for gid, name in genre_rows.items()]
        )
        counts["genres"] = len(genre_rows)

    keyword_rows = {kid: name for m in movies for kid, name in m.keywords}
    if keyword_rows:
        statement = insert(Keyword).values(id=bindparam("id"), name=bindparam("name"))
        statement = statement.on_conflict_do_update(
            index_elements=["id"], set_={"name": statement.excluded.name}
        )
        session.execute(
            statement, [{"id": kid, "name": name} for kid, name in keyword_rows.items()]
        )
        counts["keywords"] = len(keyword_rows)

    people_rows: dict[int, dict[str, Any]] = {}
    for m in movies:
        for member in m.cast + m.crew:
            person_id = int(member["id"])
            people_rows.setdefault(
                person_id,
                {
                    "id": person_id,
                    "name": str(member.get("name") or "")[:300],
                    "profile_path": member.get("profile_path") or None,
                    "gender": int(member.get("gender") or 0),
                },
            )
    if people_rows:
        statement = insert(Person).values(
            id=bindparam("id"),
            name=bindparam("name"),
            profile_path=bindparam("profile_path"),
            gender=bindparam("gender"),
        )
        statement = statement.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "name": statement.excluded.name,
                "profile_path": statement.excluded.profile_path,
                "gender": statement.excluded.gender,
            },
        )
        session.execute(statement, list(people_rows.values()))
        counts["people"] = len(people_rows)

    # --- the movies themselves, plus bridges/credits (plain insert: all new) ---
    movie_rows = []
    genre_bridge = []
    keyword_bridge = []
    credit_rows = []

    for offset, m in enumerate(movies):
        row_index = start_row_index + offset
        movie_rows.append(
            {
                "row_index": row_index,
                "tmdb_id": m.tmdb_id,
                "imdb_id": m.imdb_id,
                "title": m.title,
                "original_title": m.original_title,
                "tagline": m.tagline,
                "overview": m.overview,
                "tags": None,
                "release_date": m.release_date,
                "release_year": m.release_date.year if m.release_date else None,
                "runtime": m.runtime,
                "vote_average": m.vote_average,
                "vote_count": m.vote_count,
                "popularity": m.popularity,
                "budget": m.budget,
                "revenue": m.revenue,
                "original_language": m.original_language,
                "status": m.status,
                "homepage": m.homepage,
                "poster_path": m.poster_path,
                "backdrop_path": m.backdrop_path,
                "adult": m.adult,
                "collection_id": None,
            }
        )

        for gid, _name in m.genres:
            genre_bridge.append({"tmdb_id": m.tmdb_id, "genre_id": gid})
        for kid, _name in m.keywords:
            keyword_bridge.append({"tmdb_id": m.tmdb_id, "keyword_id": kid})

        for billing_order, member in enumerate(m.cast):
            credit_rows.append(
                {
                    "tmdb_id": m.tmdb_id,
                    "person_id": int(member["id"]),
                    "credit_type": "cast",
                    "role": (member.get("character") or None),
                    "department": None,
                    "billing_order": billing_order,
                }
            )
        seen_crew: set[tuple[int, str]] = set()
        for member in m.crew:
            key = (int(member["id"]), str(member.get("job") or ""))
            if key in seen_crew:
                continue
            seen_crew.add(key)
            credit_rows.append(
                {
                    "tmdb_id": m.tmdb_id,
                    "person_id": int(member["id"]),
                    "credit_type": "crew",
                    "role": member.get("job") or None,
                    "department": member.get("department") or None,
                    "billing_order": None,
                }
            )

    session.execute(insert(Movie), movie_rows)
    counts["movies"] = len(movie_rows)

    if genre_bridge:
        statement = insert(MovieGenre).values(genre_bridge)
        statement = statement.on_conflict_do_nothing(index_elements=["tmdb_id", "genre_id"])
        session.execute(statement)
        counts["movie_genres"] = len(genre_bridge)

    if keyword_bridge:
        statement = insert(MovieKeyword).values(keyword_bridge)
        statement = statement.on_conflict_do_nothing(index_elements=["tmdb_id", "keyword_id"])
        session.execute(statement)
        counts["movie_keywords"] = len(keyword_bridge)

    if credit_rows:
        session.execute(insert(MovieCredit), credit_rows)
        counts["movie_credits"] = len(credit_rows)

    # Trailer/backdrop cache, keyed by tmdb_id -- same table the artwork
    # backfill writes to, so playback and the media-refresh path both work
    # unchanged for these new titles.
    media_payloads = [m.media for m in movies if m.media is not None]
    if media_payloads:
        counts["movie_media"] = media_service.store(session, media_payloads)

    return counts


# --------------------------------------------------------------------------- #
# orchestration
# --------------------------------------------------------------------------- #
async def _run(
    start_year: int, end_year: int, limit: int, concurrency: int
) -> tuple[list[NewMovie], int]:
    settings = get_settings()
    if not settings.tmdb_api_key:
        raise RuntimeError(
            "TMDB_API_KEY is not set. Add it to backend/.env:\n"
            "    TMDB_API_KEY=your_key_here"
        )
    headers, params = _auth(settings.tmdb_api_key)

    with SessionLocal() as session:
        existing = _existing_tmdb_ids(session)

    async with httpx.AsyncClient(
        base_url=settings.tmdb_api_base,
        timeout=httpx.Timeout(20.0),
        limits=httpx.Limits(max_connections=concurrency * 2),
    ) as client:
        print(f"Discovering candidates for {start_year}-{end_year}...", flush=True)
        candidate_ids = await _discover_ids(
            client, headers, params, start_year, end_year, limit
        )
        new_ids = [tmdb_id for tmdb_id in candidate_ids if tmdb_id not in existing]
        skipped_existing = len(candidate_ids) - len(new_ids)
        print(
            f"  found {len(candidate_ids)} candidates, "
            f"{skipped_existing} already in the catalogue, "
            f"{len(new_ids)} to fetch",
            flush=True,
        )

        if not new_ids:
            return [], skipped_existing

        semaphore = asyncio.Semaphore(concurrency)
        started = time.perf_counter()
        movies: list[NewMovie] = []

        tasks = [
            _fetch_detail(client, headers, params, tmdb_id, semaphore)
            for tmdb_id in new_ids
        ]
        for index, coro in enumerate(asyncio.as_completed(tasks), start=1):
            result = await coro
            if result is not None:
                movies.append(result)
            if index % 100 == 0 or index == len(tasks):
                elapsed = time.perf_counter() - started
                rate = index / elapsed if elapsed else 0
                print(f"  {index:>5}/{len(tasks)}  {rate:4.1f} req/s", flush=True)

    return movies, skipped_existing


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import movies released after the curated dataset's cutoff."
    )
    parser.add_argument("--start-year", type=int, default=2018)
    parser.add_argument("--end-year", type=int, default=date.today().year)
    parser.add_argument(
        "--limit", type=int, default=300,
        help="Max candidate titles to consider (default 300).",
    )
    parser.add_argument(
        "--concurrency", type=int, default=DEFAULT_CONCURRENCY,
        help=f"Parallel detail requests (default {DEFAULT_CONCURRENCY}).",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Write to the database. Without this flag, only previews.",
    )
    args = parser.parse_args()

    try:
        movies, skipped_existing = asyncio.run(
            _run(args.start_year, args.end_year, args.limit, args.concurrency)
        )
    except (RuntimeError, TMDBAuthError) as exc:
        print(f"\nError: {exc}")
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted before any rows were written.")
        return 130

    rule = "=" * 66
    print()
    print(rule)
    print("Import candidates")
    print(rule)
    print(f"  already in catalogue : {skipped_existing:,}")
    print(f"  new titles fetched   : {len(movies):,}")
    for m in movies[:15]:
        year = m.release_date.year if m.release_date else "?"
        print(f"    - {m.title} ({year})  tmdb_id={m.tmdb_id}")
    if len(movies) > 15:
        print(f"    ... and {len(movies) - 15} more")
    print(rule)

    if not movies:
        print("Nothing to write.")
        return 0

    if not args.apply:
        print("\n--dry-run (default): nothing written. Re-run with --apply to write.")
        return 0

    # Written in bounded batches, each its own transaction: keeps any single
    # statement's bound-parameter count well under Postgres's 65,535 limit,
    # and means an interruption partway through keeps everything written so
    # far (row_index continues from whatever is already in the table).
    total_counts: dict[str, int] = {}
    written = 0
    with SessionLocal() as session:
        start_row_index = _next_row_index(session)

    for batch_start in range(0, len(movies), WRITE_BATCH_SIZE):
        batch = movies[batch_start : batch_start + WRITE_BATCH_SIZE]
        with SessionLocal() as session:
            row_index = _next_row_index(session)
            batch_counts = _write_movies(session, batch, row_index)
            session.commit()
        for table, count in batch_counts.items():
            total_counts[table] = total_counts.get(table, 0) + count
        written += len(batch)
        print(f"  wrote {written:,}/{len(movies):,} movies", flush=True)

    counts = total_counts

    print()
    print(rule)
    print("Written to Postgres")
    print(rule)
    for table, count in counts.items():
        print(f"  {table:<16}: {count:,}")
    print(
        f"  row_index range : {start_row_index:,} .. "
        f"{start_row_index + len(movies) - 1:,}"
    )
    print(rule)
    print(
        "\nNote: the recommendation vector matrix was NOT updated. These titles\n"
        "will not appear in similarity/personalised recommendations until the\n"
        "vectors are rebuilt separately."
    )
    print(
        "Poster/backdrop/trailer are populated from this same TMDB response "
        "(movie_media), so browse and playback work immediately."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
