"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { logoutEverywhere } from "@/lib/auth-client";

export function SignOutEverywhere() {
  const router = useRouter();
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onClick() {
    setIsPending(true);
    setError(null);
    try {
      await logoutEverywhere();
      router.replace("/");
      router.refresh();
    } catch {
      setError("Could not revoke sessions. Please try again.");
      setIsPending(false);
    }
  }

  return (
    <div aria-live="polite">
      <button
        type="button"
        onClick={onClick}
        disabled={isPending}
        className="rounded-full border border-negative/50 px-5 py-2.5 text-sm font-semibold text-negative transition-colors hover:bg-negative/10 disabled:opacity-60"
      >
        {isPending ? "Revoking…" : "Sign out everywhere"}
      </button>
      {error && (
        <p role="alert" className="mt-2 text-sm text-negative">
          {error}
        </p>
      )}
    </div>
  );
}
