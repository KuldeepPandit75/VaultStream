/**
 * Proxy for the public "similar titles" endpoint.
 *
 * Backs anonymous recommendations: with no session, the client seeds the
 * recommender from titles found in localStorage instead of server-side watch
 * history, calling this per seed title.
 */

import { NextResponse } from "next/server";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

function toLimit(raw: string | null): number {
  const parsed = raw ? Number.parseInt(raw, 10) : NaN;
  if (!Number.isSafeInteger(parsed)) return 12;
  return Math.min(Math.max(parsed, 1), 50);
}

export async function GET(
  request: Request,
  { params }: { params: Promise<{ row_index: string }> },
) {
  const { row_index } = await params;
  if (!/^\d+$/.test(row_index)) {
    return NextResponse.json([], { status: 400 });
  }

  const limit = toLimit(new URL(request.url).searchParams.get("limit"));

  try {
    const response = await fetch(
      `${API_BASE_URL}/movies/${row_index}/similar?limit=${limit}`,
      { headers: { Accept: "application/json" }, cache: "no-store" },
    );
    if (!response.ok) {
      return NextResponse.json([], { status: response.status });
    }
    const body = await response.json();
    return NextResponse.json(Array.isArray(body) ? body : []);
  } catch {
    return NextResponse.json([], { status: 502 });
  }
}
