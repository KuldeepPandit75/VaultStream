import Image from "next/image";
import Link from "next/link";

import { Poster } from "@/components/catalog/Poster";
import { PlayButton } from "@/components/movie/PlayButton";
import { RatingBadge } from "@/components/ui/RatingBadge";
import { formatRuntime, formatVoteCount } from "@/lib/format";
import type { MovieDetail } from "@/lib/types";

export function DetailHero({ movie }: { movie: MovieDetail }) {
  const runtime = formatRuntime(movie.runtime);
  const votes = formatVoteCount(movie.vote_count);

  return (
    <header className="relative">
      {/*
        Backdrop artwork only exists once the TMDB refresh has run. Until then
        this falls back to a tinted gradient so the hero never looks unfinished.
      */}
      <div aria-hidden="true" className="absolute inset-0 -z-10 overflow-hidden">
        {movie.backdrop_url ? (
          <>
            <Image
              src={movie.backdrop_url}
              alt=""
              fill
              priority
              sizes="100vw"
              className="hero-fade object-cover object-top opacity-40"
            />
            <div className="absolute inset-0 bg-gradient-to-t from-vault-950 via-vault-950/80 to-vault-950/40" />
          </>
        ) : (
          <div className="size-full bg-[radial-gradient(ellipse_at_top,var(--color-vault-800),var(--color-vault-950)_70%)]" />
        )}
      </div>

      <div className="mx-auto max-w-[1600px] px-4 pb-10 pt-10 sm:px-6 lg:px-8 lg:pt-16">
        <div className="flex flex-col gap-8 md:flex-row md:gap-10">
          <div className="w-40 shrink-0 sm:w-48 lg:w-60">
            <div className="relative aspect-[2/3] overflow-hidden rounded-card bg-vault-800 shadow-raised">
              <Poster
                src={movie.poster_url}
                title={movie.title}
                width={400}
                height={600}
                priority
                sizes="(max-width: 640px) 160px, (max-width: 1024px) 192px, 240px"
                className="size-full object-cover"
              />
            </div>
          </div>

          <div className="min-w-0 flex-1">
            <h1 className="text-balance-title text-3xl font-bold tracking-tight sm:text-4xl lg:text-5xl">
              {movie.title}
            </h1>

            <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-vault-muted">
              {movie.omdb?.rated && (
                <span className="rounded border border-vault-700 px-1.5 py-0.5 text-xs font-medium text-vault-text">
                  {movie.omdb.rated}
                </span>
              )}
              {movie.release_year && (
                <span className="tabular-nums">{movie.release_year}</span>
              )}
              {runtime && (
                <>
                  <span aria-hidden="true" className="text-vault-600">
                    ·
                  </span>
                  <span>{runtime}</span>
                </>
              )}
              {movie.omdb?.imdb_rating ? (
                <>
                  <span aria-hidden="true" className="text-vault-600">
                    ·
                  </span>
                  <span className="flex items-center gap-1.5">
                    <RatingBadge rating={movie.omdb.imdb_rating} />
                    <span className="text-[11px] font-medium uppercase tracking-wide text-vault-faint">IMDb</span>
                  </span>
                </>
              ) : movie.vote_average !== null && movie.vote_average > 0 ? (
                <>
                  <span aria-hidden="true" className="text-vault-600">
                    ·
                  </span>
                  <span className="flex items-center gap-1.5">
                    <RatingBadge rating={movie.vote_average} />
                    <span className="text-[11px] font-medium uppercase tracking-wide text-vault-faint">TMDB</span>
                    {votes && <span className="text-vault-faint">({votes} votes)</span>}
                  </span>
                </>
              ) : null}
            </div>

            {movie.genres.length > 0 && (
              <ul className="mt-4 flex flex-wrap gap-2" aria-label="Genres">
                {movie.genres.map((genre) => (
                  <li key={genre}>
                    <Link
                      href={`/browse?genre=${encodeURIComponent(genre)}`}
                      className="inline-block rounded-full border border-vault-600 px-3 py-1 text-xs font-medium text-vault-muted transition-colors hover:border-brand-500 hover:text-brand-300"
                    >
                      {genre}
                    </Link>
                  </li>
                ))}
              </ul>
            )}

            {movie.tagline && (
              <p className="mt-5 text-base italic text-vault-muted">
                “{movie.tagline}”
              </p>
            )}

            {movie.overview ? (
              <p className="mt-5 max-w-3xl text-[0.9375rem] leading-relaxed text-vault-text/90">
                {movie.overview}
              </p>
            ) : (
              <p className="mt-5 text-sm italic text-vault-faint">
                No synopsis available for this title.
              </p>
            )}

            {movie.directors.length > 0 && (
              <p className="mt-5 text-sm text-vault-muted">
                <span className="text-vault-faint">
                  {movie.directors.length > 1 ? "Directors" : "Director"}:
                </span>{" "}
                {movie.directors.join(", ")}
              </p>
            )}

            <div className="mt-8 flex flex-wrap items-start gap-3">
              <PlayButton
                rowIndex={movie.row_index}
                hasTrailer={movie.has_trailer}
                title={movie.title}
              />
              {movie.imdb_url && (
                <a
                  href={movie.imdb_url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="inline-flex items-center gap-2 rounded-full border border-vault-700 bg-vault-800 px-6 py-3 text-sm font-semibold text-vault-text transition-all hover:border-brand-500 hover:text-brand-300"
                >
                  <span className="rounded bg-[#F5C518] px-1 py-0.5 text-[10px] font-black tracking-tight text-black">
                    IMDb
                  </span>
                  View on IMDb
                  <span className="sr-only">(opens in a new tab)</span>
                </a>
              )}
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
