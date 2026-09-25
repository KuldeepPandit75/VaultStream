"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { useSession } from "@/components/auth/SessionProvider";
import { logout } from "@/lib/auth-client";

function initials(name: string): string {
  return (
    name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0])
      .join("")
      .toUpperCase() || "?"
  );
}

export function UserMenu() {
  const user = useSession();
  const router = useRouter();
  const [isOpen, setIsOpen] = useState(false);
  const [isSigningOut, setIsSigningOut] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Close on outside click and on Escape, the two behaviours users expect of a
  // menu. Escape also returns focus to the trigger implicitly.
  useEffect(() => {
    if (!isOpen) return;

    const onPointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setIsOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setIsOpen(false);
    };

    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [isOpen]);

  if (!user) {
    return (
      <div className="flex items-center gap-1 sm:gap-2">
        <Link
          href="/login"
          className="rounded-md px-2 py-2 text-xs font-medium text-vault-muted transition-colors hover:text-vault-text sm:px-3 sm:text-sm"
        >
          Sign in
        </Link>
        <Link
          href="/register"
          className="whitespace-nowrap rounded-full bg-brand-500 px-3 py-1.5 text-xs font-semibold text-vault-950 transition-colors hover:bg-brand-400 sm:px-4 sm:py-2 sm:text-sm"
        >
          Sign up
        </Link>
      </div>
    );
  }

  async function onSignOut() {
    setIsSigningOut(true);
    try {
      await logout();
    } catch {
      // Even if the call fails, clear local state: the cookie may already be
      // gone, and leaving the user stuck "signed in" is worse.
    }
    setIsOpen(false);
    router.replace("/");
    router.refresh();
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setIsOpen((open) => !open)}
        aria-expanded={isOpen}
        aria-haspopup="menu"
        className="flex items-center gap-2 rounded-full p-0.5 pr-2 transition-colors hover:bg-vault-800"
      >
        <span
          aria-hidden="true"
          className="grid size-8 shrink-0 place-items-center rounded-full bg-brand-500 text-xs font-bold text-vault-950"
        >
          {initials(user.display_name)}
        </span>
        <span className="hidden max-w-28 truncate text-sm font-medium sm:block">
          {user.display_name}
        </span>
        <span className="sr-only">Account menu</span>
      </button>

      {isOpen && (
        <div
          role="menu"
          aria-label="Account"
          className="absolute right-0 top-full z-50 mt-2 w-56 overflow-hidden rounded-xl border border-vault-700 bg-vault-850 shadow-raised"
        >
          <div className="border-b border-vault-800 px-4 py-3">
            <p className="truncate text-sm font-medium text-vault-text">
              {user.display_name}
            </p>
            <p className="truncate text-xs text-vault-faint">{user.email}</p>
          </div>

          <Link
            href="/account"
            role="menuitem"
            onClick={() => setIsOpen(false)}
            className="block px-4 py-2.5 text-sm text-vault-muted transition-colors hover:bg-vault-800 hover:text-vault-text"
          >
            Account
          </Link>

          <button
            type="button"
            role="menuitem"
            onClick={onSignOut}
            disabled={isSigningOut}
            className="block w-full px-4 py-2.5 text-left text-sm text-vault-muted transition-colors hover:bg-vault-800 hover:text-vault-text disabled:opacity-60"
          >
            {isSigningOut ? "Signing out…" : "Sign out"}
          </button>
        </div>
      )}
    </div>
  );
}
