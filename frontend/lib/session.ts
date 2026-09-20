/**
 * Server-side session helpers.
 *
 * Import only from Server Components, layouts, or route handlers: this reads
 * request cookies and talks to the backend directly.
 */

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import type { AuthUser } from "@/lib/types";

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
