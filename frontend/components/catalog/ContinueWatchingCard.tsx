"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Poster } from "@/components/catalog/Poster";
import { removeFromHistory } from "@/lib/history-client";
import { formatYear } from "@/lib/format";
import { formatTime } from "@/lib/youtube";
import type { WatchProgress } from "@/lib/types";

/**
 * A resumable title with a progress bar and a remove action.
 *
 * Client-side because removal mutates the row without a full page reload.
 */
export function ContinueWatchingCard({ entry }: { entry: WatchProgress }) {
  const router = useRouter();
  const [isRemoving, setIsRemoving] = useState(false);
  const [isRemoved, setIsRemoved] = useState(false);

  const { movie } = entry;
  const percent = entry.percent_complete ?? 0;
  const remaining =
    entry.duration_seconds && entry.duration_seconds > entry.position_seconds
      ? entry.duration_seconds - entry.position_seconds
      : null;

  if (isRemoved) return null;

  async function onRemove() {
    setIsRemoving(true);
    const ok = await removeFromHistory(movie.row_index);
    if (ok) {
      setIsRemoved(true);
      router.refresh();
    } else {
      setIsRemoving(false);
    }
  }

  return (
    <article className="group relative">
      <Link
        href={`/watch/${movie.row_index}`}
        aria-label={`Resume ${movie.title}${
          remaining ? `, ${formatTime(remaining)} remaining` : ""
        }`}
        className="block rounded-card focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-brand-400"
      >
        <div className="relative aspect-[2/3] overflow-hidden rounded-card bg-vault-800 shadow-poster">
          <Poster
            src={movie.poster_url}
            title={movie.title}
            width={200}
            height={300}
            sizes="(max-width: 480px) 45vw, (max-width: 768px) 30vw, (max-width: 1280px) 20vw, 200px"
            className="size-full object-cover transition-transform duration-500 ease-out-quart group-hover:scale-[1.04]"
          />

          {/* Resume affordance, so the card reads as "continue" not "start". */}
          <div className="absolute inset-0 grid place-items-center bg-vault-950/25 opacity-0 transition-opacity group-hover:opacity-100">
            <span
              aria-hidden="true"
              className="grid size-12 place-items-center rounded-full bg-brand-500/95 text-vault-950"
            >
              <svg viewBox="0 0 24 24" fill="currentColor" className="size-6">
                <path d="M7 5v14l12-7z" />
              </svg>
            </span>
          </div>

          <div className="absolute inset-x-0 bottom-0 space-y-1.5 bg-gradient-to-t from-vault-950 to-transparent px-2 pb-2 pt-6">
            <div
              className="h-1 overflow-hidden rounded-full bg-white/25"
              role="progressbar"
              aria-valuenow={Math.round(percent)}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label={`${Math.round(percent)}% watched`}
            >
              <div
                className="h-full rounded-full bg-brand-500"
                style={{ width: `${Math.min(Math.max(percent, 2), 100)}%` }}
              />
            </div>
            {remaining !== null && (
              <p className="text-[0.6875rem] text-vault-muted tabular-nums">
                {formatTime(remaining)} left
              </p>
            )}
          </div>
        </div>

        <div className="mt-2 space-y-0.5 pr-7">
          <h3 className="line-clamp-2 text-sm font-medium leading-snug text-vault-text transition-colors group-hover:text-brand-300">
            {movie.title}
          </h3>
          <p className="text-xs text-vault-faint tabular-nums">
            {formatYear(movie.release_year)}
          </p>
        </div>
      </Link>

      {/* Outside the link so it is its own control, not a nested interactive. */}
      <button
        type="button"
        onClick={onRemove}
        disabled={isRemoving}
        aria-label={`Remove ${movie.title} from Continue Watching`}
        className="absolute right-0 top-[calc(100%-2.75rem)] mt-2 grid size-6 place-items-center rounded-full text-vault-faint opacity-0 transition-all hover:bg-vault-800 hover:text-vault-text focus-visible:opacity-100 group-hover:opacity-100 disabled:opacity-40"
      >
        <svg aria-hidden="true" viewBox="0 0 20 20" fill="none" className="size-3.5">
          <path
            d="m5 5 10 10M15 5 5 15"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
          />
        </svg>
      </button>
    </article>
  );
}
