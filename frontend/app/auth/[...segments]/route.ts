/**
 * Same-origin proxy for the backend auth endpoints.
 *
 * Why proxy instead of calling FastAPI from the browser:
 *   - `API_BASE_URL` stays server-only, so the backend origin is never shipped.
 *   - Auth becomes same-origin, so there is no CORS preflight and no need for
 *     `credentials: "include"`.
 *   - Session cookies are scoped to the app's own origin.
 *
 * Mounted at `/auth/*` deliberately, not `/api/auth/*`: the backend scopes the
 * refresh cookie to `Path=/auth`, so the browser only sends that long-lived
 * credential to these routes. Moving the mount point would break that scoping.
 */

import { NextResponse } from "next/server";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

/** Only these subpaths are proxied, so the route cannot reach other endpoints. */
const ALLOWED = new Set([
  "register",
  "login",
  "refresh",
  "logout",
  "logout-all",
  "me",
]);

async function proxy(request: Request, segments: string[]): Promise<NextResponse> {
  const path = segments.join("/");
  if (!ALLOWED.has(path)) {
    return NextResponse.json({ detail: "Not found" }, { status: 404 });
  }

  const headers = new Headers({ Accept: "application/json" });

  // Relay the browser's session cookies to the backend.
  const cookie = request.headers.get("cookie");
  if (cookie) headers.set("cookie", cookie);

  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);

  // Passed through so the backend can label sessions recognisably.
  const userAgent = request.headers.get("user-agent");
  if (userAgent) headers.set("user-agent", userAgent);

  const body =
    request.method === "GET" || request.method === "HEAD"
      ? undefined
      : await request.text();

  let upstream: Response;
  try {
    upstream = await fetch(`${API_BASE_URL}/auth/${path}`, {
      method: request.method,
      headers,
      body,
      // Auth responses must never be cached.
      cache: "no-store",
      redirect: "manual",
    });
  } catch {
    return NextResponse.json(
      { detail: "The authentication service is unreachable." },
      { status: 503 },
    );
  }

  const text = await upstream.text();
  const response = new NextResponse(text || null, {
    status: upstream.status,
    headers: {
      "content-type": upstream.headers.get("content-type") ?? "application/json",
      "cache-control": "no-store",
    },
  });

  // Relay every Set-Cookie header individually. A single joined header would be
  // parsed as one malformed cookie, because cookie values may contain commas.
  for (const value of upstream.headers.getSetCookie()) {
    response.headers.append("set-cookie", value);
  }

  return response;
}

export async function GET(
  request: Request,
  { params }: RouteContext<"/auth/[...segments]">,
) {
  const { segments } = await params;
  return proxy(request, segments);
}

export async function POST(
  request: Request,
  { params }: RouteContext<"/auth/[...segments]">,
) {
  const { segments } = await params;
  return proxy(request, segments);
}
