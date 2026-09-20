"""Recompute watch history against the corrected watched-threshold.

Why this exists
---------------
The original rule marked a title watched at "30 seconds OR 50%", which is wrong
for trailers whose runtimes vary from ~60s to ~210s: 30 seconds of a 208-second
trailer is 14%. Titles were therefore removed from Continue Watching after a
glance. The rule is now fraction-based (>= 85%).

It also deletes rows created by blocked autoplay, where the player reported a
paused state at position ~0 and produced a history row for something never
watched.

Read-only by default; pass --apply to write.

Usage:
    python -m etl.repair_history
    python -m etl.repair_history --apply
"""

from __future__ import annotations

import argparse

from sqlalchemy import delete, select

from vaultstream.db import SessionLocal
from vaultstream.models.catalog import Movie
from vaultstream.models.history import WatchEvent, WatchProgress
from vaultstream.services.history import MIN_RECORDABLE_SECONDS, is_completed


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair watch history.")
    parser.add_argument("--apply", action="store_true", help="Write changes.")
    args = parser.parse_args()

    with SessionLocal() as session:
        rows = list(
            session.execute(
                select(WatchProgress, Movie.title)
                .join(Movie, Movie.row_index == WatchProgress.row_index)
                .order_by(WatchProgress.updated_at.desc())
            ).all()
        )

        if not rows:
            print("No watch history to repair.")
            return 0

        to_delete: list[WatchProgress] = []
        to_flip: list[tuple[WatchProgress, str, bool, bool]] = []

        for record, title in rows:
            # Junk from blocked autoplay.
            if record.position_seconds < MIN_RECORDABLE_SECONDS:
                to_delete.append(record)
                continue

            should_be = is_completed(record.position_seconds, record.duration_seconds)
            if should_be != record.completed:
                to_flip.append((record, title, record.completed, should_be))

        rule = "=" * 76
        print(rule)
        print("Watch history repair" + ("" if args.apply else "  (dry run)"))
        print(rule)
        print(f"{'title':<28}{'pos':>8}{'dur':>8}{'pct':>7}  action")
        print("-" * 76)

        for record, title in rows:
            pct = (
                record.position_seconds / record.duration_seconds * 100
                if record.duration_seconds
                else 0.0
            )
            if record in to_delete:
                action = "DELETE (autoplay artefact)"
            else:
                flip = next((f for f in to_flip if f[0] is record), None)
                if flip:
                    action = f"completed {flip[2]} -> {flip[3]}"
                else:
                    action = "unchanged"
            print(
                f"{title[:27]:<28}{record.position_seconds:>8.1f}"
                f"{(record.duration_seconds or 0):>8.1f}{pct:>6.0f}%  {action}"
            )

        print("-" * 76)
        print(f"rows to delete : {len(to_delete)}")
        print(f"rows to reflag : {len(to_flip)}")

        if not args.apply:
            print("\nDry run. Re-run with --apply to write these changes.")
            return 0

        for record, _title, _was, should_be in to_flip:
            record.completed = should_be
            if not should_be:
                record.completed_at = None

        for record in to_delete:
            session.execute(
                delete(WatchEvent).where(
                    WatchEvent.user_id == record.user_id,
                    WatchEvent.row_index == record.row_index,
                )
            )
            session.delete(record)

        session.commit()
        print("\nApplied.")

        remaining = session.execute(
            select(WatchProgress).where(WatchProgress.completed.is_(False))
        ).scalars().all()
        print(f"Unfinished titles now eligible for Continue Watching: {len(remaining)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
