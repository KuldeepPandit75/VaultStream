/**
 * Proxy for client-side catalog pagination (infinite scroll).
 *
 * Exists so the browser never needs the backend origin: `API_BASE_URL` stays a
 * server-only variable and no CORS negotiation happens in the browser.
 *
 * Only known query parameters are forwarded, so the client cannot reach
 * arbitrary backend endpoints or inject unexpected filters.
 */

import { NextResponse } from "next/server";

import { ApiError, listMovies } from "@/lib/api";
import type { MovieQuery, SortField, SortOrder } from "@/lib/types";

const SORT_FIELDS: readonly SortField[] = [
  "popularity",
  "rating",
  "release_date",
  "title",
  "vote_count",
];
const SORT_ORDERS: readonly SortOrder[] = ["asc", "desc"];

function toInt(value: string | null, min: number, max: number): number | undefined {
  if (value === null) return undefined;
  const parsed = Number.parseInt(value, 10);
  if (Number.isNaN(parsed) || parsed < min || parsed > max) return undefined;
  return parsed;
}

function toFloat(value: string | null, min: number, max: number): number | undefined {
  if (value === null) return undefined;
  const parsed = Number.parseFloat(value);
  if (Number.isNaN(parsed) || parsed < min || parsed > max) return undefined;
  return parsed;
}

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;

  const sort = params.get("sort");
  const order = params.get("order");

  const query: MovieQuery = {
    q: params.get("q")?.slice(0, 200) || undefined,
    genre: params.getAll("genre").slice(0, 20),
    genre_match_all: params.get("genre_match_all") === "true",
    year_from: toInt(params.get("year_from"), 1870, 2100),
    year_to: toInt(params.get("year_to"), 1870, 2100),
    language: params.get("language")?.slice(0, 20) || undefined,
    min_rating: toFloat(params.get("min_rating"), 0, 10),
    sort: SORT_FIELDS.includes(sort as SortField) ? (sort as SortField) : undefined,
    order: SORT_ORDERS.includes(order as SortOrder) ? (order as SortOrder) : undefined,
    page: toInt(params.get("page"), 1, 100_000) ?? 1,
    page_size: toInt(params.get("page_size"), 1, 100),
  };

  try {
    const page = await listMovies(query);
    return NextResponse.json(page);
  } catch (error) {
    if (error instanceof ApiError) {
      return NextResponse.json(
        { detail: error.message },
        { status: error.status === 503 ? 503 : 502 },
      );
    }
    return NextResponse.json({ detail: "Unexpected error" }, { status: 500 });
  }
}
