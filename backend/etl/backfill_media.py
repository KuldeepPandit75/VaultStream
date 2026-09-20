"""Bulk-refresh artwork and trailer keys from TMDB.

Why a backfill is necessary
---------------------------
The catalogue's stored poster paths date from 2017 and TMDB has replaced most of
the files since. Measured availability of the stored paths was 12-37% depending
on the slice, so browse grids would be mostly placeholders without this.

One request per distinct tmdb_id returns the current poster, backdrop, and
trailer list together, so 44,121 requests refresh the whole catalogue. At the
default concurrency that lands around 20-40 minutes.

Safe to interrupt and resume: already-resolved ids are skipped unless --force.

Usage:
    python -m etl.backfill_media --limit 200          # try a slice first
    python -m etl.backfill_media                      # whole catalogue
    python -m etl.backfill_media --order popularity   # best-looking rows first
    python -m etl.backfill_media --force              # re-fetch everything
"""

from __future__ import annotations

import argparse
import asyncio
import time

import httpx
from sqlalchemy import bindparam, distinct, select, update

from vaultstream.config import get_settings
from vaultstream.db import SessionLocal
from vaultstream.models.catalog import Movie, Person
from vaultstream.models.media import MovieMedia
from vaultstream.services import media as media_service
from vaultstream.services.tmdb import (
    DEFAULT_CONCURRENCY,
    MediaPayload,
    TMDBAuthError,
    fetch_media_async,
)

# Rows are committed in batches so an interrupted run keeps its progress.
COMMIT_EVERY = 250


def _store_profiles(session, payloads: list[MediaPayload]) -> int:
    """Update refreshed profile_path values for people already in the catalogue.

    A plain UPDATE, not an upsert: `people.name` is NOT NULL and TMDB's credits
    payload does not reliably include it, so inserting an unknown person id
    would violate that constraint. Rows not already in `people` (from the
    original credits.pkl import) are simply skipped -- nothing references them.
    """
    updates: dict[int, str] = {}
    for payload in payloads:
        for profile in payload.profiles:
            if profile.profile_path:
                updates[profile.person_id] = profile.profile_path

    if not updates:
        return 0

    known_ids = {
        int(value)
        for value in session.execute(
            select(Person.id).where(Person.id.in_(list(updates)))
        )
        .scalars()
        .all()
    }
    if not known_ids:
        return 0

    # executemany-style bulk update: one round trip for the whole batch instead
    # of one UPDATE per person, which matters at this table's scale (194k rows).
    # Executed against the Core table, not the ORM entity: the ORM's bulk
    # UPDATE-by-primary-key path insists on PK-shaped parameter names and
    # rejects a plain WHERE + bindparam combination (InvalidRequestError).
    # Core has no such restriction.
    table = Person.__table__
    session.execute(
        table.update()
        .where(table.c.id == bindparam("_id"))
        .values(profile_path=bindparam("_profile_path")),
        [
            {"_id": person_id, "_profile_path": updates[person_id]}
            for person_id in known_ids
        ],
    )
    return len(known_ids)


def _pending_ids(force: bool, limit: int | None, order: str) -> list[int]:
    """Distinct tmdb_ids needing resolution, most valuable first."""
    with SessionLocal() as session:
        statement = select(distinct(Movie.tmdb_id))

        if order == "popularity":
            # Order by the best popularity among rows sharing the id.
            from sqlalchemy import func

            statement = (
                select(Movie.tmdb_id)
                .group_by(Movie.tmdb_id)
                .order_by(func.max(Movie.popularity).desc().nulls_last())
            )
        elif order == "votes":
            from sqlalchemy import func

            statement = (
                select(Movie.tmdb_id)
                .group_by(Movie.tmdb_id)
                .order_by(func.max(Movie.vote_count).desc().nulls_last())
            )

        ids = [int(value) for value in session.execute(statement).scalars().all()]

        if not force:
            resolved = {
                int(value)
                for value in session.execute(
                    select(MovieMedia.tmdb_id).where(MovieMedia.not_found.is_(False))
                )
                .scalars()
                .all()
            }
            ids = [value for value in ids if value not in resolved]

    return ids[:limit] if limit else ids


async def _run(ids: list[int], concurrency: int) -> dict[str, int]:
    settings = get_settings()
    api_key = settings.tmdb_api_key
    assert api_key  # checked by the caller

    semaphore = asyncio.Semaphore(concurrency)
    counters = {"fetched": 0, "posters": 0, "backdrops": 0, "trailers": 0,
                "profiles": 0, "not_found": 0, "errors": 0}
    started = time.perf_counter()
    buffer: list[MediaPayload] = []

    def flush(force: bool = False) -> None:
        nonlocal buffer
        if not buffer or (len(buffer) < COMMIT_EVERY and not force):
            return
        with SessionLocal() as session:
            media_service.store(session, buffer)
            counters["profiles"] += _store_profiles(session, buffer)
            session.commit()
        buffer = []

    async with httpx.AsyncClient(
        base_url=settings.tmdb_api_base,
        timeout=httpx.Timeout(20.0),
        limits=httpx.Limits(max_connections=concurrency * 2),
    ) as client:
        tasks = [
            fetch_media_async(client, tmdb_id, api_key, semaphore) for tmdb_id in ids
        ]

        for index, coro in enumerate(asyncio.as_completed(tasks), start=1):
            payload = await coro
            buffer.append(payload)

            counters["fetched"] += 1
            if payload.not_found:
                counters["not_found"] += 1
            elif payload.error:
                counters["errors"] += 1
            else:
                if payload.poster_path:
                    counters["posters"] += 1
                if payload.backdrop_path:
                    counters["backdrops"] += 1
                if payload.trailer_key:
                    counters["trailers"] += 1

            flush()

            if index % 500 == 0 or index == len(ids):
                elapsed = time.perf_counter() - started
                rate = index / elapsed if elapsed else 0
                remaining = (len(ids) - index) / rate if rate else 0
                print(
                    f"  {index:>6,}/{len(ids):,}  "
                    f"{rate:5.1f} req/s  "
                    f"posters={counters['posters']:,} "
                    f"trailers={counters['trailers']:,} "
                    f"profiles={counters['profiles']:,} "
                    f"404={counters['not_found']:,} "
                    f"err={counters['errors']:,}  "
                    f"eta={remaining / 60:.1f}m",
                    flush=True,
                )

    flush(force=True)
    counters["elapsed_s"] = int(time.perf_counter() - started)
    return counters


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh TMDB artwork and trailers.")
    parser.add_argument("--limit", type=int, default=None, help="Only N titles.")
    parser.add_argument(
        "--concurrency", type=int, default=DEFAULT_CONCURRENCY,
        help=f"Parallel requests (default {DEFAULT_CONCURRENCY}).",
    )
    parser.add_argument(
        "--order", choices=("popularity", "votes", "any"), default="popularity",
        help="Resolve the most visible titles first.",
    )
    parser.add_argument("--force", action="store_true", help="Re-fetch resolved rows.")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.tmdb_api_key:
        print(
            "TMDB_API_KEY is not set.\n"
            "Add it to backend/.env (server-side only, never NEXT_PUBLIC_):\n"
            "    TMDB_API_KEY=your_key_here\n"
            "Create one free at https://www.themoviedb.org/settings/api"
        )
        return 1

    print("Selecting titles to resolve...", flush=True)
    ids = _pending_ids(args.force, args.limit, args.order)
    if not ids:
        print("Nothing to do - every title is already resolved.")
        return 0

    print(f"Resolving {len(ids):,} titles at concurrency {args.concurrency}...", flush=True)

    try:
        counters = asyncio.run(_run(ids, args.concurrency))
    except TMDBAuthError as exc:
        print(f"\nAuthentication failed: {exc}")
        print("Check TMDB_API_KEY in backend/.env.")
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted. Progress up to the last batch was committed; "
              "re-run to resume.")
        return 130

    rule = "=" * 66
    print()
    print(rule)
    print("Media backfill complete")
    print(rule)
    for key, value in counters.items():
        print(f"  {key:<12}: {value:,}")

    with SessionLocal() as session:
        stats = media_service.coverage(session)
    print("  --- cache totals ---")
    for key, value in stats.items():
        print(f"  {key:<12}: {value:,}")
    print(rule)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
