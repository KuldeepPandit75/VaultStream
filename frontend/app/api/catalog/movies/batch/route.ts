/**
 * Proxy for resolving several row_indexes to summaries in one call.
 *
 * Backs the anonymous (localStorage) history/recommendation feature: the
 * browser only holds row_index values and needs posters/titles to render
 * them, without exposing `API_BASE_URL` to the client.
 */

import { NextResponse } from "next/server";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";
const MAX_IDS = 40;

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;

  const ids = params
    .getAll("ids")
    .map((value) => Number.parseInt(value, 10))
    .filter((value) => Number.isSafeInteger(value) && value >= 0)
    .slice(0, MAX_IDS);

  if (ids.length === 0) {
    return NextResponse.json([]);
  }

  const upstream = new URLSearchParams();
  for (const id of ids) upstream.append("ids", String(id));

  try {
    const response = await fetch(`${API_BASE_URL}/movies/batch?${upstream}`, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok) {
      return NextResponse.json([], { status: response.status });
    }
    const body = await response.json();
    return NextResponse.json(Array.isArray(body) ? body : []);
  } catch {
    return NextResponse.json([], { status: 502 });
  }
}
