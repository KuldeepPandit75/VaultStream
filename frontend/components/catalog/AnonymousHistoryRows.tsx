"use client";

import { useEffect, useRef, useState } from "react";

import { Carousel, CarouselItem } from "@/components/catalog/Carousel";
import { MovieCard } from "@/components/catalog/MovieCard";
import { useSession } from "@/components/auth/SessionProvider";
import { getLocalHistory, type LocalWatchEntry } from "@/lib/local-history";
import { fetchSimilar, resolveMovies } from "@/lib/local-recommendations";
import type { MovieSummary } from "@/lib/types";

interface HistoryItem {
  entry: LocalWatchEntry;
  movie: MovieSummary;
}

interface SeedRow {
  key: string;
  seed: MovieSummary;
  items: MovieSummary[];
}

/** Titles with real progress, most recently watched first, unfinished only. */
function resumableEntries(entries: LocalWatchEntry[]): LocalWatchEntry[] {
  return entries.filter((entry) => !entry.completed && entry.position_seconds >= 5);
}

/**
 * Continue watching + "Because you watched" rows for anonymous visitors,
 * built entirely from localStorage.
 *
 * A client component by necessity: localStorage and the signed-in check both
 * only resolve in the browser. Renders nothing at all once a session exists,
 * so this and the server-rendered rows never both show up at once, and
 * nothing here runs for a page load with no history yet (no flash of empty
 * carousels while the batch/similar requests are in flight).
 */
export function AnonymousHistoryRows() {
  const user = useSession();
  const [loaded, setLoaded] = useState(false);
  const [continueItems, setContinueItems] = useState<HistoryItem[]>([]);
  const [seedRows, setSeedRows] = useState<SeedRow[]>([]);
  // Guards against refetching on every remount (e.g. React Strict Mode's
  // double-invoke in dev, or a sibling `router.refresh()`) when the
  // underlying localStorage snapshot has not actually changed.
  const lastSignatureRef = useRef<string | null>(null);

  useEffect(() => {
    if (user) return; // signed-in viewers use the server-rendered rows instead

    const history = getLocalHistory();
    const signature = history
      .map((entry) => `${entry.row_index}:${entry.position_seconds.toFixed(0)}`)
      .join(",");
    // Only skip a *second* effect run for the same snapshot once the first
    // one actually finished. Recording the signature up front (rather than
    // here) meant Strict Mode's dev-only mount -> cleanup -> mount cycle
    // could cancel the first run and then have the second bail out early
    // because the signature already "matched" -- leaving `loaded` stuck at
    // false and the whole component permanently rendering nothing.
    let cancelled = false;

    async function load() {
      if (history.length === 0) {
        if (!cancelled) {
          setLoaded(true);
          lastSignatureRef.current = signature;
        }
        return;
      }

      const resumable = resumableEntries(history);
      const seedCandidates = history.slice(0, 3);

      const [resumableMovies, seedMovies] = await Promise.all([
        resolveMovies(resumable.map((entry) => entry.row_index)),
        resolveMovies(seedCandidates.map((entry) => entry.row_index)),
      ]);
      if (cancelled) return;

      const byRowIndex = new Map(resumableMovies.map((m) => [m.row_index, m]));
      const nextContinue = resumable
        .map((entry) => {
          const movie = byRowIndex.get(entry.row_index);
          return movie ? { entry, movie } : null;
        })
        .filter((item): item is HistoryItem => item !== null);

      const seedByRowIndex = new Map(seedMovies.map((m) => [m.row_index, m]));
      const similarLists = await Promise.all(
        seedCandidates.map((entry) => fetchSimilar(entry.row_index, 12)),
      );
      if (cancelled) return;

      const watchedIds = new Set(history.map((entry) => entry.row_index));
      const nextSeedRows: SeedRow[] = [];
      seedCandidates.forEach((entry, index) => {
        const seed = seedByRowIndex.get(entry.row_index);
        const items = similarLists[index]?.filter(
          (movie) => !watchedIds.has(movie.row_index),
        );
        if (seed && items && items.length > 0) {
          nextSeedRows.push({ key: `because-${entry.row_index}`, seed, items });
        }
      });

      if (!cancelled) {
        setContinueItems(nextContinue);
        setSeedRows(nextSeedRows);
        setLoaded(true);
        // Recorded only on a run that actually completed, so a future
        // genuine change to localStorage (a new title watched) still
        // triggers a refetch instead of being permanently skipped.
        lastSignatureRef.current = signature;
      }
    }

    if (signature === lastSignatureRef.current) return;
    void load();
    return () => {
      cancelled = true;
    };
  }, [user]);

  if (user || !loaded) return null;
  if (continueItems.length === 0 && seedRows.length === 0) return null;

  return (
    <div className="space-y-12">
      {continueItems.length > 0 && (
        <section aria-labelledby="anon-continue-heading">
          <h2
            id="anon-continue-heading"
            className="mb-5 text-xl font-semibold tracking-tight"
          >
            Continue watching
          </h2>
          <Carousel label="Continue watching">
            {continueItems.map(({ movie }) => (
              <CarouselItem key={movie.row_index}>
                <MovieCard movie={movie} />
              </CarouselItem>
            ))}
          </Carousel>
        </section>
      )}

      {seedRows.map((row) => (
        <section key={row.key} aria-labelledby={row.key}>
          <h2 id={row.key} className="mb-5 text-xl font-semibold tracking-tight">
            Because you watched {row.seed.title}
          </h2>
          <Carousel label={`Because you watched ${row.seed.title}`}>
            {row.items.map((movie) => (
              <CarouselItem key={`${row.key}-${movie.row_index}`}>
                <MovieCard movie={movie} />
              </CarouselItem>
            ))}
          </Carousel>
        </section>
      ))}

      <p className="text-xs text-vault-faint">
        Based on titles you watched on this device.{" "}
        <a href="/login" className="underline hover:text-vault-text">
          Sign in
        </a>{" "}
        to keep this history across devices.
      </p>
    </div>
  );
}
