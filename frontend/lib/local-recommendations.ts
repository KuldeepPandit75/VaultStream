/** Browser-side lookups backing anonymous (localStorage-based) recommendations. */

import type { MovieSummary } from "@/lib/types";

/** Resolve row_indexes to summaries. Unknown ids are silently dropped. */
export async function resolveMovies(rowIndexes: number[]): Promise<MovieSummary[]> {
  if (rowIndexes.length === 0) return [];
  try {
    const params = new URLSearchParams();
    for (const id of rowIndexes) params.append("ids", String(id));
    const response = await fetch(`/api/catalog/movies/batch?${params}`, {
      cache: "no-store",
    });
    if (!response.ok) return [];
    const body = await response.json();
    return Array.isArray(body) ? (body as MovieSummary[]) : [];
  } catch {
    return [];
  }
}

/** Titles similar to one seed title. Public endpoint; no session needed. */
export async function fetchSimilar(
  rowIndex: number,
  limit = 12,
): Promise<MovieSummary[]> {
  try {
    const response = await fetch(
      `/api/catalog/movies/${rowIndex}/similar?limit=${limit}`,
      { cache: "no-store" },
    );
    if (!response.ok) return [];
    const body = await response.json();
    return Array.isArray(body) ? (body as MovieSummary[]) : [];
  } catch {
    return [];
  }
}
