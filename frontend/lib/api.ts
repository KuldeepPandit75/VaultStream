/**
 * Server-side API client for the VaultStream backend.
 *
 * This module must only be imported from Server Components or route handlers:
 * `API_BASE_URL` is deliberately not a `NEXT_PUBLIC_` variable so the backend
 * origin is never shipped to the browser.
 *
 * Next.js 16 does not cache `fetch` by default, so cache lifetimes are stated
 * explicitly per call.
 */

import type {
  FilterBounds,
  Genre,
  MovieDetail,
  MovieQuery,
  MovieSummary,
  Paginated,
  PersonDetail,
  StreamSource,
} from "@/lib/types";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

/**
 * Cache windows in seconds.
 *
 * Detail matches the list window because the TMDB media backfill rewrites
 * artwork and trailer availability in place; a longer window served posters and
 * a disabled Play button for minutes after the data had already been refreshed.
 * Reference data (genres, languages) only changes on a reseed.
 */
const REVALIDATE = {
  list: 60,
  detail: 60,
  reference: 3600,
} as const;

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly url: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

interface RequestOptions {
  revalidate?: number;
  signal?: AbortSignal;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const url = `${API_BASE_URL}${path}`;

  let response: Response;
  try {
    response = await fetch(url, {
      headers: { Accept: "application/json" },
      next: { revalidate: options.revalidate ?? REVALIDATE.list },
      signal: options.signal,
    });
  } catch {
    // Most commonly the backend simply is not running.
    throw new ApiError(
      503,
      url,
      `Cannot reach the VaultStream API at ${API_BASE_URL}. Is the backend running?`,
    );
  }

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body?.detail) detail = body.detail;
    } catch {
      // Non-JSON error body; keep the status text.
    }
    throw new ApiError(response.status, url, detail);
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new ApiError(502, url, "The API returned a response that was not JSON.");
  }
  return body as T;
}

/**
 * Validate the paginated envelope before handing it to components.
 *
 * A 200 response with an unexpected shape is a real failure mode here: an older
 * build of this backend served `GET /movies` as a bare array of titles, which
 * would surface as `undefined.toLocaleString()` deep inside a component instead
 * of a diagnosable error.
 */
function assertPaginated<T>(body: unknown, url: string): Paginated<T> {
  const candidate = body as Partial<Paginated<T>> | null;
  const isValid =
    candidate !== null &&
    typeof candidate === "object" &&
    Array.isArray(candidate.items) &&
    typeof candidate.total === "number" &&
    typeof candidate.page === "number" &&
    typeof candidate.total_pages === "number";

  if (!isValid) {
    const received = Array.isArray(body)
      ? `an array of ${body.length} items`
      : `keys [${Object.keys((body as object) ?? {}).join(", ")}]`;
    throw new ApiError(
      502,
      url,
      `Unexpected catalogue response: expected a paginated object but received ${received}. ` +
        "Check that API_BASE_URL points at the current VaultStream API.",
    );
  }
  return candidate as Paginated<T>;
}

function assertMovieDetail(body: unknown, url: string): MovieDetail {
  const candidate = body as Partial<MovieDetail> | null;
  if (
    candidate === null ||
    typeof candidate !== "object" ||
    typeof candidate.row_index !== "number" ||
    typeof candidate.title !== "string"
  ) {
    throw new ApiError(502, url, "Unexpected movie detail response from the API.");
  }
  return candidate as MovieDetail;
}

/** Build a query string, dropping empty values and expanding array params. */
export function buildQuery(query: MovieQuery): string {
  const params = new URLSearchParams();

  const append = (key: string, value: unknown) => {
    if (value === undefined || value === null || value === "") return;
    params.append(key, String(value));
  };

  append("q", query.q);
  for (const genre of query.genre ?? []) append("genre", genre);
  if (query.genre_match_all) append("genre_match_all", true);
  append("year_from", query.year_from);
  append("year_to", query.year_to);
  append("language", query.language);
  append("min_rating", query.min_rating);
  append("sort", query.sort);
  append("order", query.order);
  append("page", query.page);
  append("page_size", query.page_size);

  const serialised = params.toString();
  return serialised ? `?${serialised}` : "";
}

export async function listMovies(
  query: MovieQuery = {},
  options: RequestOptions = {},
): Promise<Paginated<MovieSummary>> {
  const path = `/movies${buildQuery(query)}`;
  const body = await request<unknown>(path, {
    revalidate: REVALIDATE.list,
    ...options,
  });
  return assertPaginated<MovieSummary>(body, path);
}

export async function getMovie(rowIndex: number): Promise<MovieDetail> {
  const path = `/movies/${rowIndex}`;
  const body = await request<unknown>(path, { revalidate: REVALIDATE.detail });
  return assertMovieDetail(body, path);
}

export async function getFilterBounds(): Promise<FilterBounds> {
  const body = await request<Partial<FilterBounds>>("/movies/filters", {
    revalidate: REVALIDATE.reference,
  });
  if (!body || !Array.isArray(body.genres) || !Array.isArray(body.languages)) {
    throw new ApiError(502, "/movies/filters", "Unexpected filter bounds response.");
  }
  return {
    genres: body.genres,
    languages: body.languages,
    min_year: body.min_year ?? null,
    max_year: body.max_year ?? null,
    default_page_size: body.default_page_size ?? 24,
    max_page_size: body.max_page_size ?? 100,
    quality_floor_vote_count: body.quality_floor_vote_count ?? 10,
  };
}

/** Playback source, or null when no trailer is available for the title. */
export async function getStreamSource(
  rowIndex: number,
): Promise<StreamSource | { unavailable: true; reason: string }> {
  const path = `/movies/${rowIndex}/stream`;
  try {
    const body = await request<Partial<StreamSource>>(path, {
      // Trailer keys are stable; the movie_media cache makes this cheap anyway.
      revalidate: REVALIDATE.detail,
    });
    if (!body || typeof body.key !== "string" || !body.key) {
      return { unavailable: true, reason: "No trailer is available for this title." };
    }
    return body as StreamSource;
  } catch (error) {
    if (error instanceof ApiError) {
      // 404 carries an explanatory reason; 503 means TMDB is unconfigured.
      return { unavailable: true, reason: error.message };
    }
    return { unavailable: true, reason: "Playback is unavailable right now." };
  }
}

export async function getPerson(personId: number): Promise<PersonDetail> {
  const path = `/people/${personId}`;
  const body = await request<Partial<PersonDetail>>(path, {
    revalidate: REVALIDATE.detail,
  });
  if (!body || typeof body.id !== "number" || typeof body.name !== "string") {
    throw new ApiError(502, path, "Unexpected person response from the API.");
  }
  return {
    id: body.id,
    name: body.name,
    profile_url: body.profile_url ?? null,
    gender: body.gender ?? null,
    known_for: body.known_for ?? null,
    cast_count: body.cast_count ?? 0,
    crew_count: body.crew_count ?? 0,
    cast_credits: body.cast_credits ?? [],
    crew_credits: body.crew_credits ?? [],
  };
}

export async function getCollectionSiblings(
  rowIndex: number,
): Promise<MovieSummary[]> {
  const path = `/movies/${rowIndex}/collection`;
  const body = await request<unknown>(path, { revalidate: REVALIDATE.detail });
  return Array.isArray(body) ? (body as MovieSummary[]) : [];
}

export async function listGenres(): Promise<Genre[]> {
  const body = await request<unknown>("/genres", {
    revalidate: REVALIDATE.reference,
  });
  if (!Array.isArray(body)) {
    throw new ApiError(502, "/genres", "Unexpected genres response.");
  }
  return body as Genre[];
}
