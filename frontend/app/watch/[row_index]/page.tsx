import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { PlayerWithHistory } from "@/components/player/PlayerWithHistory";
import { EmptyState } from "@/components/ui/EmptyState";
import { ApiError, getMovie, getStreamSource } from "@/lib/api";
import { formatRuntime } from "@/lib/format";
import { getCurrentUser, getResumePosition } from "@/lib/session";
import type { MovieDetail } from "@/lib/types";

function parseRowIndex(raw: string): number | null {
  if (!/^\d+$/.test(raw)) return null;
  const parsed = Number(raw);
  return Number.isSafeInteger(parsed) ? parsed : null;
}

type MovieResult =
  | { ok: true; movie: MovieDetail }
  | { ok: false; status: number };

async function loadMovie(rowIndex: number): Promise<MovieResult> {
  try {
    return { ok: true, movie: await getMovie(rowIndex) };
  } catch (error) {
    return { ok: false, status: error instanceof ApiError ? error.status : 500 };
  }
}

export async function generateMetadata({
  params,
}: PageProps<"/watch/[row_index]">): Promise<Metadata> {
  const { row_index } = await params;
  const rowIndex = parseRowIndex(row_index);
  if (rowIndex === null) return { title: "Not found" };

  const result = await loadMovie(rowIndex);
  if (!result.ok) return { title: "Not found" };

  return {
    title: `Watch ${result.movie.title}`,
    description: `Official trailer for ${result.movie.title}.`,
    // A player page has no standalone value in search results.
    robots: { index: false },
  };
}

export default async function WatchPage({
  params,
}: PageProps<"/watch/[row_index]">) {
  const { row_index } = await params;
  const rowIndex = parseRowIndex(row_index);
  if (rowIndex === null) notFound();

  const result = await loadMovie(rowIndex);
  if (!result.ok) {
    if (result.status === 404) notFound();
    return (
      <div className="mx-auto max-w-3xl px-4 py-20">
        <EmptyState
          title="Could not load this title"
          description="The catalogue service is unavailable. Please try again shortly."
        />
      </div>
    );
  }

  const { movie } = result;
  const source = await getStreamSource(rowIndex);

  if ("unavailable" in source) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-20">
        <EmptyState
          title="No trailer available"
          description={source.reason}
          action={
            <Link
              href={`/movie/${rowIndex}`}
              className="inline-flex items-center rounded-full bg-brand-500 px-5 py-2 text-sm font-semibold text-vault-950 transition-colors hover:bg-brand-400"
            >
              Back to {movie.title}
            </Link>
          }
        />
      </div>
    );
  }

  const runtime = formatRuntime(movie.runtime);

  // Resume where the user left off, and only record progress when signed in.
  const user = await getCurrentUser();
  const startAt = user ? await getResumePosition(rowIndex) : 0;

  return (
    <div className="mx-auto max-w-[1400px] px-0 py-0 sm:px-6 sm:py-8 lg:px-8">
      <PlayerWithHistory
        videoKey={source.key}
        title={movie.title}
        rowIndex={movie.row_index}
        startAt={startAt}
        enabled={Boolean(user)}
      />

      <div className="px-4 py-8 sm:px-0">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
              {movie.title}
            </h1>
            <p className="mt-1.5 flex flex-wrap items-center gap-x-3 text-sm text-vault-muted">
              {movie.release_year && <span>{movie.release_year}</span>}
              {runtime && <span>{runtime}</span>}
              {movie.genres.length > 0 && <span>{movie.genres.join(", ")}</span>}
            </p>
          </div>
          <Link
            href={`/movie/${movie.row_index}`}
            className="rounded-full border border-vault-700 px-5 py-2.5 text-sm font-semibold transition-colors hover:border-brand-500 hover:text-brand-300"
          >
            Title details
          </Link>
        </div>

        {movie.overview && (
          <p className="mt-5 max-w-3xl text-[0.9375rem] leading-relaxed text-vault-text/90">
            {movie.overview}
          </p>
        )}

        <p className="mt-6 text-xs text-vault-faint">
          Playback is limited to the official trailer supplied by TMDB.
          {source.name ? ` Now playing: ${source.name}.` : ""}
        </p>
      </div>
    </div>
  );
}
