/**
 * Browser-side watch history for anonymous visitors, kept in localStorage.
 *
 * Signed-in viewers get server-side history and recommendations (see
 * `lib/session.ts`, `lib/history-client.ts`). Anonymous viewers have no
 * account to attach history to, so the same information lives in the
 * browser instead: capped, resettable, and never sent anywhere until the
 * caller explicitly asks the backend to hydrate it into titles.
 *
 * Client-only module: `localStorage` does not exist during SSR. Every export
 * guards against that (and against a full/blocked storage quota) and degrades
 * to a no-op rather than throwing, matching `history-client.ts`'s convention.
 */

const STORAGE_KEY = "vs_anon_history";
const STORAGE_VERSION = 1;
// Enough to seed a "because you watched" style feed without the payload
// growing unbounded over a long anonymous session.
const MAX_ENTRIES = 25;
// Mirrors the server-side rule in vaultstream/services/history.py: most of the
// title must have been seen, not just a fixed number of seconds.
const WATCHED_MIN_FRACTION = 0.85;

export interface LocalWatchEntry {
  row_index: number;
  position_seconds: number;
  duration_seconds: number | null;
  completed: boolean;
  updated_at: string; // ISO timestamp; Date is not JSON-serialisable as-is
}

interface StoredShape {
  version: number;
  entries: LocalWatchEntry[];
}

function isBrowser(): boolean {
  return typeof window !== "undefined";
}

function readAll(): LocalWatchEntry[] {
  if (!isBrowser()) return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Partial<StoredShape>;
    if (parsed?.version !== STORAGE_VERSION || !Array.isArray(parsed.entries)) {
      return [];
    }
    return parsed.entries.filter(
      (entry): entry is LocalWatchEntry =>
        typeof entry?.row_index === "number" &&
        typeof entry?.position_seconds === "number",
    );
  } catch {
    return [];
  }
}

function writeAll(entries: LocalWatchEntry[]): void {
  if (!isBrowser()) return;
  try {
    const payload: StoredShape = { version: STORAGE_VERSION, entries };
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  } catch {
    // Storage full, disabled, or blocked (private browsing in some browsers).
    // Losing this session's history is acceptable; nothing else depends on it.
  }
}

/** Whether enough of the title has been seen to call it watched. */
function isCompleted(position: number, duration: number | null): boolean {
  if (duration && duration > 0) return position / duration >= WATCHED_MIN_FRACTION;
  return false;
}

/**
 * Upsert a resume point for the anonymous viewer.
 *
 * Most-recently-updated entries are kept first so `getRecentHistory` can read
 * off the front without re-sorting on every call.
 */
export function recordLocalProgress(
  rowIndex: number,
  positionSeconds: number,
  durationSeconds: number | null,
): void {
  if (!isBrowser()) return;

  const entries = readAll();
  const next: LocalWatchEntry = {
    row_index: rowIndex,
    position_seconds: Math.max(0, positionSeconds),
    duration_seconds: durationSeconds && durationSeconds > 0 ? durationSeconds : null,
    completed: isCompleted(positionSeconds, durationSeconds),
    updated_at: new Date().toISOString(),
  };

  const withoutThisTitle = entries.filter((entry) => entry.row_index !== rowIndex);
  writeAll([next, ...withoutThisTitle].slice(0, MAX_ENTRIES));
}

/** Most recent entries first, most-recent-first order preserved. */
export function getLocalHistory(): LocalWatchEntry[] {
  return readAll();
}

/** Row indexes only, most recent first -- what the recommender needs as seeds. */
export function getRecentRowIndexes(limit = 5): number[] {
  return readAll()
    .slice(0, limit)
    .map((entry) => entry.row_index);
}

export function removeLocalEntry(rowIndex: number): void {
  writeAll(readAll().filter((entry) => entry.row_index !== rowIndex));
}

export function clearLocalHistory(): void {
  writeAll([]);
}

export function hasLocalHistory(): boolean {
  return readAll().length > 0;
}
