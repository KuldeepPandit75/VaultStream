import Link from "next/link";
import { Suspense } from "react";

import { AnonymousHistoryRows } from "@/components/catalog/AnonymousHistoryRows";
import { ContinueWatchingRow } from "@/components/catalog/ContinueWatchingRow";
import { HeroCarousel } from "@/components/catalog/HeroCarousel";
import { MovieGrid, MovieGridSkeleton } from "@/components/catalog/MovieGrid";
import { RecommendationRows } from "@/components/catalog/RecommendationRows";
import { EmptyState } from "@/components/ui/EmptyState";
import { ApiError, listMovies } from "@/lib/api";
import type { MovieSummary } from "@/lib/types";

/** How many hero slides to show in the carousel. */
const HERO_COUNT = 5;

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
      page_size: 20,
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

/** Placeholder matching a carousel's shape, so the layout does not jump. */
function RowSkeleton({ label }: { label: string }) {
  return (
    <div aria-hidden="true">
      <div className="mb-4 h-6 w-48 rounded bg-vault-850 shimmer" />
      <div className="flex gap-4 overflow-hidden">
        {Array.from({ length: 8 }, (_, index) => (
          <div
            key={`${label}-${index}`}
            className="w-[8.5rem] shrink-0 space-y-2 sm:w-[9.5rem] lg:w-[10.5rem]"
          >
            <div className="shimmer aspect-[2/3] rounded-card bg-vault-850" />
            <div className="shimmer h-3.5 w-11/12 rounded bg-vault-850" />
          </div>
        ))}
      </div>
    </div>
  );
}

async function TrendingStrip() {
  const result = await loadTrending();

  if (!result.ok) {
    return <EmptyState title="Catalogue unavailable" description={result.message} />;
  }

  // Movies with backdrops go to the hero carousel; the rest fill the grid.
  const withBackdrop = result.items.filter((m) => m.backdrop_url);
  const heroMovies = withBackdrop.slice(0, HERO_COUNT);
  const gridMovies = result.items.filter(
    (m) => !heroMovies.includes(m),
  );

  return (
    <>
      {heroMovies.length > 0 && <HeroCarousel movies={heroMovies} />}

      <div className="mx-auto max-w-[1600px] px-4 sm:px-6 lg:px-8">
        {/* Each of these renders nothing when it doesn't apply or has no data.
            The server-rendered rows cover signed-in viewers; AnonymousHistoryRows
            covers everyone else, built client-side from localStorage. */}
        <div className="mt-10 space-y-12">
          <Suspense fallback={<RowSkeleton label="Continue watching" />}>
            <ContinueWatchingRow />
          </Suspense>

          <Suspense fallback={<RowSkeleton label="Top picks for you" />}>
            <RecommendationRows />
          </Suspense>

          <AnonymousHistoryRows />
        </div>

        {gridMovies.length > 0 && (
          <section className="mt-12" aria-labelledby="trending-heading">
            <h2
              id="trending-heading"
              className="mb-5 text-xl font-semibold tracking-tight"
            >
              Trending now
            </h2>
            <MovieGrid movies={gridMovies} label="Trending now" />
          </section>
        )}
      </div>
    </>
  );
}

export default function HomePage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-[1600px] px-4 py-12 sm:px-6 lg:px-8">
          {/* Hero skeleton */}
          <div
            className="shimmer w-full rounded-xl bg-vault-850"
            style={{ height: "clamp(400px, 60vh, 700px)" }}
          />
          <div className="mt-12">
            <MovieGridSkeleton count={14} />
          </div>
        </div>
      }
    >
      <TrendingStrip />
    </Suspense>
  );
}
