"use client";

import { createContext, useContext, type ReactNode } from "react";

import type { AuthUser } from "@/lib/types";

/**
 * Exposes the server-resolved user to Client Components.
 *
 * The value originates in the root layout (a Server Component reading the
 * httpOnly cookie), so the browser never needs access to the token itself.
 */
const SessionContext = createContext<AuthUser | null>(null);

export function SessionProvider({
  user,
  children,
}: {
  user: AuthUser | null;
  children: ReactNode;
}) {
  return <SessionContext.Provider value={user}>{children}</SessionContext.Provider>;
}

/** The signed-in user, or null when anonymous. */
export function useSession(): AuthUser | null {
  return useContext(SessionContext);
}
