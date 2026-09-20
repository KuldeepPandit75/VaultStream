/**
 * Same-origin proxy for the watch-history endpoints.
 *
 * The access cookie is scoped to `Path=/`, so it reaches this route and is
 * forwarded to the backend. Keeping this server-side means the browser never
 * learns the backend origin and no CORS negotiation is needed.
 *
 * An OPTIONAL catch-all (`[[...segments]]`) is required: a plain `[...segments]`
 * would not match `/api/history` itself, which is the list/clear endpoint.
 */

import { NextResponse } from "next/server";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

/** Restricts the proxy to the history endpoints the browser legitimately needs. */
function isAllowed(segments: string[]): boolean {
  if (segments.length === 0) return true; // GET / DELETE /api/history

  const [head] = segments;
  if (head === "resume") {
    return segments.length === 2 && /^\d+$/.test(segments[1]);
  }
  if (head === "progress" || head === "continue") {
    return segments.length === 1;
  }
  // DELETE /api/history/{row_index}
  return segments.length === 1 && /^\d+$/.test(head);
}

async function proxy(request: Request, segments: string[]): Promise<NextResponse> {
  if (!isAllowed(segments)) {
    return NextResponse.json({ detail: "Not found" }, { status: 404 });
  }

  const suffix = segments.length ? `/${segments.join("/")}` : "";
  const search = new URL(request.url).search;

  const headers = new Headers({ Accept: "application/json" });
  const cookie = request.headers.get("cookie");
  if (cookie) headers.set("cookie", cookie);
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);

  const body =
    request.method === "GET" || request.method === "HEAD"
      ? undefined
      : await request.text();

  let upstream: Response;
  try {
    upstream = await fetch(`${API_BASE_URL}/history${suffix}${search}`, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      redirect: "manual",
    });
  } catch {
    return NextResponse.json(
      { detail: "The history service is unreachable." },
      { status: 503 },
    );
  }

  if (upstream.status === 204) {
    return new NextResponse(null, {
      status: 204,
      headers: { "cache-control": "no-store" },
    });
  }

  const text = await upstream.text();
  return new NextResponse(text || null, {
    status: upstream.status,
    headers: {
      "content-type": upstream.headers.get("content-type") ?? "application/json",
      "cache-control": "no-store",
    },
  });
}

export async function GET(
  request: Request,
  { params }: RouteContext<"/api/history/[[...segments]]">,
) {
  const { segments } = await params;
  return proxy(request, segments ?? []);
}

export async function POST(
  request: Request,
  { params }: RouteContext<"/api/history/[[...segments]]">,
) {
  const { segments } = await params;
  return proxy(request, segments ?? []);
}

export async function DELETE(
  request: Request,
  { params }: RouteContext<"/api/history/[[...segments]]">,
) {
  const { segments } = await params;
  return proxy(request, segments ?? []);
}
