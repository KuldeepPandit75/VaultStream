"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { MovieCard } from "@/components/catalog/MovieCard";
import type { MovieSummary, Paginated } from "@/lib/types";

/**
 * Appends further pages below the server-rendered first page.
 *
 * Auto-loads when the sentinel scrolls into view, but always renders a real
 * button as well: an IntersectionObserver alone leaves keyboard and
 * screen-reader users with no way to reach page 2.
 */
export function LoadMore({
  initialPage,
  totalPages,
  query,
}: {
  initialPage: number;
  totalPages: number;
  /** Serialised browse filters, without a `page` parameter. */
  query: string;
}) {
  const [movies, setMovies] = useState<MovieSummary[]>([]);
  const [page, setPage] = useState(initialPage);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  // Reset when the filters change; otherwise old results would linger below the
  // new server-rendered page. Adjusted during render rather than in an effect,
  // so the stale list is never painted.
  const resetKey = `${query}|${initialPage}`;
  const [syncedKey, setSyncedKey] = useState(resetKey);
  if (resetKey !== syncedKey) {
    setSyncedKey(resetKey);
    setMovies([]);
    setPage(initialPage);
    setError(null);
  }

  const hasMore = page < totalPages;

  const loadNext = useCallback(async () => {
    if (isLoading || !hasMore) return;

    setIsLoading(true);
    setError(null);
    const nextPage = page + 1;

    try {
      const params = new URLSearchParams(query);
      params.set("page", String(nextPage));
      const response = await fetch(`/api/catalog/movies?${params.toString()}`);
      if (!response.ok) {
        const body = (await response.json().catch(() => null)) as
          | { detail?: string }
          | null;
        throw new Error(body?.detail ?? "Could not load more titles.");
      }
      const data = (await response.json()) as Paginated<MovieSummary>;
      setMovies((existing) => [...existing, ...data.items]);
      setPage(data.page);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load more titles.");
    } finally {
      setIsLoading(false);
    }
  }, [hasMore, isLoading, page, query]);

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel || !hasMore) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) void loadNext();
      },
      { rootMargin: "600px 0px" },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [hasMore, loadNext]);

  return (
    <>
      {movies.length > 0 && (
        <ul
          className="mt-7 grid grid-cols-2 gap-x-4 gap-y-7 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 2xl:grid-cols-7"
          aria-label="Additional results"
        >
          {movies.map((movie) => (
            <li key={`${movie.row_index}`}>
              <MovieCard movie={movie} />
            </li>
          ))}
        </ul>
      )}

      {/* Announce loading and errors to assistive tech. */}
      <div aria-live="polite" className="mt-8 flex flex-col items-center gap-3">
        {error && (
          <p className="text-sm text-negative" role="alert">
            {error}
          </p>
        )}

        {hasMore ? (
          <>
            <button
              type="button"
              onClick={() => void loadNext()}
              disabled={isLoading}
              className="rounded-full border border-vault-700 bg-vault-850 px-6 py-2.5 text-sm font-semibold text-vault-text transition-colors hover:border-brand-500 hover:text-brand-300 disabled:cursor-wait disabled:opacity-60"
            >
              {isLoading ? "Loading…" : "Load more"}
            </button>
            <div ref={sentinelRef} aria-hidden="true" className="h-px w-full" />
          </>
        ) : (
          movies.length > 0 && (
            <p className="text-sm text-vault-faint">End of results.</p>
          )
        )}
      </div>
    </>
  );
}
