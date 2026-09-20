import Link from "next/link";
import { Suspense } from "react";

import { MovieGrid, MovieGridSkeleton } from "@/components/catalog/MovieGrid";
import { EmptyState } from "@/components/ui/EmptyState";
import { ApiError, listMovies } from "@/lib/api";
import type { MovieSummary } from "@/lib/types";

/**
 * Interim landing page. Task 15 replaces this with the full hero + carousel
 * home page once auth, watch history, and recommendations exist.
 */
type TrendingResult =
  | { ok: true; items: MovieSummary[] }
  | { ok: false; message: string };

/**
 * Data loading is kept out of the component so no JSX is constructed inside a
 * try/catch: React defers rendering, so render-time errors would escape it.
 */
async function loadTrending(): Promise<TrendingResult> {
  try {
    const page = await listMovies({
      sort: "popularity",
      order: "desc",
      page_size: 14,
    });
    return { ok: true, items: page.items };
  } catch (error) {
    return {
      ok: false,
      message:
        error instanceof ApiError
          ? error.message
          : "Could not load titles right now.",
    };
  }
}

async function TrendingStrip() {
  const result = await loadTrending();

  if (!result.ok) {
    return <EmptyState title="Catalogue unavailable" description={result.message} />;
  }
  return <MovieGrid movies={result.items} label="Trending now" />;
}

export default function HomePage() {
  return (
    <div className="mx-auto max-w-[1600px] px-4 py-12 sm:px-6 lg:px-8">
      <section className="max-w-2xl">
        <h1 className="text-balance-title text-4xl font-bold tracking-tight sm:text-5xl">
          Over 44,000 films.{" "}
          <span className="text-brand-400">One catalogue.</span>
        </h1>
        <p className="mt-4 text-base leading-relaxed text-vault-muted">
          Search decades of cinema, explore cast and crew, and watch official
          trailers. Sign in later to get recommendations based on what you
          watch.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Link
            href="/browse"
            className="rounded-full bg-brand-500 px-6 py-3 text-sm font-semibold text-vault-950 transition-colors hover:bg-brand-400"
          >
            Browse the catalogue
          </Link>
          <Link
            href="/browse?sort=rating&order=desc&min_rating=8"
            className="rounded-full border border-vault-700 px-6 py-3 text-sm font-semibold text-vault-text transition-colors hover:border-brand-500 hover:text-brand-300"
          >
            Top rated
          </Link>
        </div>
      </section>

      <section className="mt-16" aria-labelledby="trending-heading">
        <h2 id="trending-heading" className="mb-5 text-xl font-semibold tracking-tight">
          Trending now
        </h2>
        <Suspense fallback={<MovieGridSkeleton count={14} />}>
          <TrendingStrip />
        </Suspense>
      </section>
    </div>
  );
}
