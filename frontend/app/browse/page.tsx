import type { Metadata } from "next";
import { Suspense } from "react";

import { FilterSidebar } from "@/components/catalog/FilterSidebar";
import { LoadMore } from "@/components/catalog/LoadMore";
import { MovieGrid, MovieGridSkeleton } from "@/components/catalog/MovieGrid";
import { SortSelect } from "@/components/catalog/SortSelect";
import { ClearFiltersLink, EmptyState } from "@/components/ui/EmptyState";
import { ApiError, buildQuery, getFilterBounds, listMovies } from "@/lib/api";
import type {
  FilterBounds,
  MovieQuery,
  MovieSummary,
  Paginated,
  SortField,
  SortOrder,
} from "@/lib/types";

export const metadata: Metadata = {
  title: "Browse",
  description: "Search and filter the full VaultStream catalogue.",
};

const SORT_FIELDS: readonly SortField[] = [
  "popularity",
  "rating",
  "release_date",
  "title",
  "vote_count",
];

type RawParams = Record<string, string | string[] | undefined>;

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function toArray(value: string | string[] | undefined): string[] {
  if (value === undefined) return [];
  return Array.isArray(value) ? value : [value];
}

function parseNumber(value: string | undefined): number | undefined {
  if (!value) return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

/** Translate raw URL params into a validated query for the API. */
function parseQuery(params: RawParams): MovieQuery {
  const sort = first(params.sort);
  const order = first(params.order);

  return {
    q: first(params.q),
    genre: toArray(params.genre),
    genre_match_all: first(params.genre_match_all) === "true",
    year_from: parseNumber(first(params.year_from)),
    year_to: parseNumber(first(params.year_to)),
    language: first(params.language),
    min_rating: parseNumber(first(params.min_rating)),
    sort: SORT_FIELDS.includes(sort as SortField) ? (sort as SortField) : "popularity",
    order: order === "asc" ? "asc" : ("desc" as SortOrder),
    page: parseNumber(first(params.page)) ?? 1,
  };
}

function describeQuery(query: MovieQuery): string {
  const parts: string[] = [];
  if (query.q) parts.push(`matching “${query.q}”`);
  if (query.genre?.length) {
    parts.push(`in ${query.genre.join(query.genre_match_all ? " + " : " / ")}`);
  }
  if (query.year_from && query.year_to) parts.push(`from ${query.year_from}–${query.year_to}`);
  else if (query.year_from) parts.push(`from ${query.year_from} onwards`);
  else if (query.year_to) parts.push(`up to ${query.year_to}`);
  if (query.min_rating) parts.push(`rated ${query.min_rating}+`);
  return parts.join(", ");
}

/*
 * Data loaders return a discriminated result instead of throwing, and construct
 * no JSX: React defers rendering, so a try/catch around JSX would not catch
 * render-time errors anyway.
 */
type Result<T> = { ok: true; data: T } | { ok: false; message: string };

function toMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

async function loadFilterBounds(): Promise<Result<FilterBounds>> {
  try {
    return { ok: true, data: await getFilterBounds() };
  } catch (error) {
    return { ok: false, message: toMessage(error, "The catalogue service is unavailable.") };
  }
}

async function loadResults(
  query: MovieQuery,
): Promise<Result<Paginated<MovieSummary>>> {
  try {
    return { ok: true, data: await listMovies(query) };
  } catch (error) {
    return { ok: false, message: toMessage(error, "Could not load results.") };
  }
}

/**
 * Fetches the page once and renders the count, grid, and loader together.
 * Previously the count and the grid each issued their own request and relied on
 * fetch memoisation to avoid doing the work twice.
 */
async function CatalogResults({ query }: { query: MovieQuery }) {
  const result = await loadResults(query);

  if (!result.ok) {
    return <EmptyState title="Catalogue unavailable" description={result.message} />;
  }

  const page = result.data;

  if (page.total === 0) {
    return (
      <EmptyState
        title="No titles match those filters"
        description="Try removing a filter, widening the year range, or searching a different title."
        action={<ClearFiltersLink />}
      />
    );
  }

  // Query string for the client loader, minus `page` (it supplies its own).
  const loaderQuery = buildQuery({ ...query, page: undefined }).replace(/^\?/, "");

  return (
    <>
      <p className="mb-5 text-sm text-vault-muted tabular-nums">
        {page.total.toLocaleString()} {page.total === 1 ? "title" : "titles"}
      </p>
      <MovieGrid movies={page.items} label="Catalogue results" />
      <LoadMore
        initialPage={page.page}
        totalPages={page.total_pages}
        query={loaderQuery}
      />
    </>
  );
}

export default async function BrowsePage({ searchParams }: PageProps<"/browse">) {
  // Next.js 16: searchParams is a Promise and must be awaited.
  const params = (await searchParams) as RawParams;
  const query = parseQuery(params);
  const description = describeQuery(query);

  const bounds = await loadFilterBounds();
  if (!bounds.ok) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-20">
        <EmptyState title="Catalogue unavailable" description={bounds.message} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[1600px] px-4 py-8 sm:px-6 lg:px-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Browse</h1>
          {description && <p className="mt-1 text-sm text-vault-muted">{description}</p>}
        </div>
        <Suspense fallback={<span className="h-8 w-40" />}>
          <SortSelect />
        </Suspense>
      </div>

      <div className="mt-8 lg:grid lg:grid-cols-[220px_1fr] lg:gap-10">
        <aside aria-label="Filters">
          <Suspense fallback={<div className="shimmer h-64 rounded-lg bg-vault-850" />}>
            <FilterSidebar bounds={bounds.data} />
          </Suspense>
        </aside>

        <section aria-label="Catalogue results" className="mt-8 min-w-0 lg:mt-0">
          <Suspense key={JSON.stringify(query)} fallback={<MovieGridSkeleton />}>
            <CatalogResults query={query} />
          </Suspense>
        </section>
      </div>
    </div>
  );
}
