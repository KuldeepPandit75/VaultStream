/**
 * Browser-side auth calls.
 *
 * These hit the same-origin `/auth/*` proxy, so cookies are handled by the
 * browser and no token is ever exposed to JavaScript.
 */

import type { SessionResponse } from "@/lib/types";

export interface AuthFailure {
  message: string;
  /** Field-level errors keyed by input name, from FastAPI's 422 payload. */
  fieldErrors?: Record<string, string>;
}

export class AuthError extends Error {
  constructor(
    readonly failure: AuthFailure,
    readonly status: number,
  ) {
    super(failure.message);
    this.name = "AuthError";
  }
}

interface ValidationDetail {
  loc?: (string | number)[];
  msg?: string;
}

/** Turn FastAPI's error shapes into a flat message plus per-field errors. */
function parseError(status: number, body: unknown): AuthFailure {
  const detail = (body as { detail?: unknown } | null)?.detail;

  if (typeof detail === "string") {
    return { message: detail };
  }

  if (Array.isArray(detail)) {
    const fieldErrors: Record<string, string> = {};
    for (const item of detail as ValidationDetail[]) {
      // loc is like ["body", "email"]; the field name is the last element.
      const field = item.loc?.[item.loc.length - 1];
      if (typeof field === "string" && item.msg) {
        fieldErrors[field] = cleanMessage(item.msg);
      }
    }
    const first = Object.values(fieldErrors)[0];
    return {
      message: first ?? "Please check the details you entered.",
      fieldErrors,
    };
  }

  if (status === 503) {
    return { message: "The service is temporarily unavailable. Try again shortly." };
  }
  return { message: "Something went wrong. Please try again." };
}

function cleanMessage(message: string): string {
  // Pydantic prefixes validation messages with "Value error, ".
  return message.replace(/^Value error,\s*/i, "");
}

async function post<T>(path: string, payload?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      method: "POST",
      headers: payload ? { "Content-Type": "application/json" } : {},
      body: payload ? JSON.stringify(payload) : undefined,
    });
  } catch {
    throw new AuthError(
      { message: "Could not reach the server. Check your connection." },
      0,
    );
  }

  if (response.status === 204) return undefined as T;

  const body = await response.json().catch(() => null);

  if (!response.ok) {
    throw new AuthError(parseError(response.status, body), response.status);
  }
  return body as T;
}

export function login(email: string, password: string): Promise<SessionResponse> {
  return post<SessionResponse>("/auth/login", { email, password });
}

export function register(
  email: string,
  password: string,
  displayName: string,
): Promise<SessionResponse> {
  return post<SessionResponse>("/auth/register", {
    email,
    password,
    display_name: displayName,
  });
}

export function logout(): Promise<void> {
  return post<void>("/auth/logout");
}

export function logoutEverywhere(): Promise<void> {
  return post<void>("/auth/logout-all");
}
