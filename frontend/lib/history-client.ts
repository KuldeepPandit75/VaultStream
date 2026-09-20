/** Browser-side watch-history calls, via the same-origin proxy. */

import type { WatchProgress } from "@/lib/types";

/**
 * Report a playback position.
 *
 * Never throws: a dropped progress ping must not interrupt playback, and the
 * next ping a few seconds later supersedes it anyway.
 */
export async function reportProgress(
  rowIndex: number,
  positionSeconds: number,
  durationSeconds: number | null,
): Promise<boolean> {
  try {
    const response = await fetch("/api/history/progress", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        row_index: rowIndex,
        position_seconds: Math.max(0, positionSeconds),
        duration_seconds:
          durationSeconds && durationSeconds > 0 ? durationSeconds : null,
      }),
      // Progress is fire-and-forget; don't let it sit in any cache.
      cache: "no-store",
    });
    return response.ok;
  } catch {
    return false;
  }
}

export async function fetchContinueWatching(): Promise<WatchProgress[]> {
  try {
    const response = await fetch("/api/history/continue", { cache: "no-store" });
    if (!response.ok) return [];
    const body = await response.json();
    return Array.isArray(body) ? (body as WatchProgress[]) : [];
  } catch {
    return [];
  }
}

export async function removeFromHistory(rowIndex: number): Promise<boolean> {
  try {
    const response = await fetch(`/api/history/${rowIndex}`, {
      method: "DELETE",
      cache: "no-store",
    });
    return response.ok;
  } catch {
    return false;
  }
}

export async function clearHistory(): Promise<boolean> {
  try {
    const response = await fetch("/api/history", {
      method: "DELETE",
      cache: "no-store",
    });
    return response.ok;
  } catch {
    return false;
  }
}
