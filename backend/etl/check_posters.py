"""Measure how much catalogue artwork TMDB still serves.

The metadata dates from 2017 and TMDB has removed some images since, so a
fraction of `poster_path` values now 404. This samples the catalogue and reports
the availability rate, which determines how visible the poster fallback is.

Usage:
    python -m etl.check_posters
    python -m etl.check_posters --sample 200 --sort rating
"""

from __future__ import annotations

import argparse
import concurrent.futures

import httpx

API_BASE = "http://127.0.0.1:8000"


def _head(client: httpx.Client, movie: dict) -> tuple[str, int]:
    url = movie.get("poster_url")
    if not url:
        return movie["title"], 0
    try:
        return movie["title"], client.head(url, timeout=15).status_code
    except httpx.HTTPError:
        return movie["title"], -1


def check(sample: int, sort: str, min_votes: int | None) -> None:
    params: dict[str, object] = {
        "page_size": min(sample, 100),
        "sort": sort,
        "order": "desc",
    }
    if min_votes is not None:
        params["min_votes"] = min_votes

    with httpx.Client(follow_redirects=True, timeout=30) as client:
        page = client.get(f"{API_BASE}/movies", params=params).json()
        movies = page["items"]

        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(lambda m: _head(client, m), movies))

    available = [title for title, status in results if status == 200]
    missing_path = [title for title, status in results if status == 0]
    broken = [(title, status) for title, status in results if status not in (200, 0)]

    checked = len(results)
    print(f"sort={sort} sampled={checked} (of {page['total']:,} matching)")
    print(f"  artwork available : {len(available):>4}")
    print(f"  artwork 404/error : {len(broken):>4}")
    print(f"  no poster_path    : {len(missing_path):>4}")
    rate = len(available) / checked * 100 if checked else 0
    print(f"  availability      : {rate:.1f}%")
    if broken:
        print("  examples of broken artwork:")
        for title, status in broken[:10]:
            print(f"    [{status}] {title}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TMDB artwork availability.")
    parser.add_argument("--sample", type=int, default=100)
    parser.add_argument("--sort", default="popularity")
    parser.add_argument("--min-votes", type=int, default=None)
    args = parser.parse_args()
    check(args.sample, args.sort, args.min_votes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
