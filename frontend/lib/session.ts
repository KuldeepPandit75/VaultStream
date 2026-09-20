/**
 * Server-side session helpers.
 *
 * Import only from Server Components, layouts, or route handlers: this reads
 * request cookies and talks to the backend directly.
 */

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import type { AuthUser, RecommendationFeed } from "@/lib/types";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

/**
 * The signed-in user, or null.
 *
 * Never throws: an unreachable backend or an expired token both read as "not
 * signed in", so a transient failure degrades the page instead of breaking it.
 */
export async function getCurrentUser(): Promise<AuthUser | null> {
  const cookieStore = await cookies();
  const cookieHeader = cookieStore.toString();
  if (!cookieHeader) return null;

  try {
    const response = await fetch(`${API_BASE_URL}/auth/me`, {
      headers: { Accept: "application/json", cookie: cookieHeader },
      // Session state must never be cached across requests or users.
      cache: "no-store",
    });
    if (!response.ok) return null;

    const body = (await response.json()) as Partial<AuthUser>;
    if (typeof body?.id !== "number" || typeof body?.email !== "string") {
      return null;
    }
    return body as AuthUser;
  } catch {
    return null;
  }
}

/**
 * Authenticated GET against the backend, forwarding the request's cookies.
 *
 * Returns null on any failure, so a personalised row simply does not render
 * rather than taking the whole page down.
 */
export async function fetchAuthenticated<T>(path: string): Promise<T | null> {
  const cookieStore = await cookies();
  const cookieHeader = cookieStore.toString();
  if (!cookieHeader) return null;

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      headers: { Accept: "application/json", cookie: cookieHeader },
      // Per-user data must never be cached across requests.
      cache: "no-store",
    });
    if (!response.ok) return null;
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

/**
 * The personalised home-page block: "Top picks for you" plus
 * "Because you watched X" rows, or a labelled cold-start row.
 *
 * Returns null for anonymous visitors so the caller renders nothing.
 */
export async function getRecommendationFeed(
  limit = 18,
): Promise<RecommendationFeed | null> {
  const feed = await fetchAuthenticated<RecommendationFeed>(
    `/recommendations/feed?limit=${limit}`,
  );
  if (!feed || !Array.isArray(feed.rows)) return null;
  return feed;
}

/** Titles the signed-in user can resume. Empty for anonymous visitors. */
export async function getContinueWatching(limit = 20) {
  const rows = await fetchAuthenticated<unknown>(
    `/history/continue?limit=${limit}`,
  );
  return Array.isArray(rows) ? rows : [];
}

/** Saved playback position for a title, or 0. */
export async function getResumePosition(rowIndex: number): Promise<number> {
  const point = await fetchAuthenticated<{ position_seconds?: number }>(
    `/history/resume/${rowIndex}`,
  );
  const position = point?.position_seconds;
  return typeof position === "number" && position > 0 ? position : 0;
}

/**
 * Require a session, or redirect to the sign-in page.
 *
 * The current path is preserved in `?next=` so the user lands back where they
 * were after signing in.
 */
export async function requireUser(returnTo: string): Promise<AuthUser> {
  const user = await getCurrentUser();
  if (!user) {
    redirect(`/login?next=${encodeURIComponent(returnTo)}`);
  }
  return user;
}
