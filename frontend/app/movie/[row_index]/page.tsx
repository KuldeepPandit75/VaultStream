import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { CastStrip } from "@/components/movie/CastStrip";
import { DetailHero } from "@/components/movie/DetailHero";
import { FactList } from "@/components/movie/FactList";
import { FranchiseRow } from "@/components/movie/FranchiseRow";
import { EmptyState } from "@/components/ui/EmptyState";
import { ApiError, getMovie } from "@/lib/api";
import type { MovieDetail } from "@/lib/types";

type LoadResult =
  | { ok: true; movie: MovieDetail }
  | { ok: false; status: number; message: string };

/** No JSX inside the try, so the catch governs only the fetch. */
async function loadMovie(rowIndex: number): Promise<LoadResult> {
  try {
    return { ok: true, movie: await getMovie(rowIndex) };
  } catch (error) {
    if (error instanceof ApiError) {
      return { ok: false, status: error.status, message: error.message };
    }
    return { ok: false, status: 500, message: "Could not load this title." };
  }
}

function parseRowIndex(raw: string): number | null {
  // Reject "01", "1.5", "abc" so each title has exactly one canonical URL.
  if (!/^\d+$/.test(raw)) return null;
  const parsed = Number(raw);
  return Number.isSafeInteger(parsed) ? parsed : null;
}

export async function generateMetadata({
  params,
}: PageProps<"/movie/[row_index]">): Promise<Metadata> {
  const { row_index } = await params;
  const rowIndex = parseRowIndex(row_index);
  if (rowIndex === null) return { title: "Not found" };

  const result = await loadMovie(rowIndex);
  if (!result.ok) return { title: "Not found" };

  const { movie } = result;
  const year = movie.release_year ? ` (${movie.release_year})` : "";
  const description =
    movie.overview?.slice(0, 160) ??
    `Details, cast and crew for ${movie.title}${year}.`;

  return {
    title: `${movie.title}${year}`,
    description,
    openGraph: {
      title: `${movie.title}${year} · VaultStream`,
      description,
      images: movie.backdrop_url
        ? [{ url: movie.backdrop_url }]
        : movie.poster_url
          ? [{ url: movie.poster_url }]
          : undefined,
    },
  };
}

export default async function MovieDetailPage({
  params,
}: PageProps<"/movie/[row_index]">) {
  // Next.js 16: params is a Promise.
  const { row_index } = await params;
  const rowIndex = parseRowIndex(row_index);
  if (rowIndex === null) notFound();

  const result = await loadMovie(rowIndex);

  if (!result.ok) {
    if (result.status === 404) notFound();
    return (
      <div className="mx-auto max-w-3xl px-4 py-20">
        <EmptyState title="Could not load this title" description={result.message} />
      </div>
    );
  }

  const { movie } = result;

  return (
    <article>
      <DetailHero movie={movie} />

      <div className="mx-auto max-w-[1600px] space-y-12 px-4 pb-20 sm:px-6 lg:px-8">
        <CastStrip cast={movie.cast} />

        <Suspense fallback={null}>
          <FranchiseRow
            rowIndex={movie.row_index}
            collectionName={movie.collection?.name ?? null}
          />
        </Suspense>

        {movie.crew.length > 0 && (
          <section aria-labelledby="crew-heading">
            <h2 id="crew-heading" className="mb-4 text-lg font-semibold tracking-tight">
              Crew
            </h2>
            <ul className="grid gap-x-8 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
              {movie.crew.map((member) => (
                <li
                  key={`${member.person_id}-${member.job}`}
                  className="flex items-baseline justify-between gap-4 border-b border-vault-850 pb-2"
                >
                  <Link
                    href={`/person/${member.person_id}`}
                    className="text-sm text-vault-text transition-colors hover:text-brand-300"
                  >
                    {member.name}
                  </Link>
                  <span className="shrink-0 text-xs uppercase tracking-wide text-vault-faint">
                    {member.job}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}

        <FactList movie={movie} />

        {movie.keywords.length > 0 && (
          <section aria-labelledby="keywords-heading">
            <h2
              id="keywords-heading"
              className="mb-3 text-sm font-semibold uppercase tracking-wide text-vault-muted"
            >
              Keywords
            </h2>
            <ul className="flex flex-wrap gap-2">
              {movie.keywords.map((keyword) => (
                <li key={keyword.id}>
                  <span className="inline-block rounded-md bg-vault-850 px-2.5 py-1 text-xs text-vault-muted">
                    {keyword.name}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}

        <p>
          <Link
            href="/browse"
            className="text-sm font-medium text-brand-400 transition-colors hover:text-brand-300"
          >
            ← Back to browse
          </Link>
        </p>
      </div>
    </article>
  );
}
