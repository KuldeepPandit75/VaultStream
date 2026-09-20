import Link from "next/link";

import { Poster } from "@/components/catalog/Poster";
import { RatingBadge } from "@/components/ui/RatingBadge";
import { formatRuntime, formatYear } from "@/lib/format";
import type { MovieSummary } from "@/lib/types";

/** Poster aspect ratio used by TMDB artwork. */
const POSTER_WIDTH = 200;
const POSTER_HEIGHT = 300;

export function MovieCard({
  movie,
  priority = false,
}: {
  movie: MovieSummary;
  priority?: boolean;
}) {
  const year = formatYear(movie.release_year);
  const runtime = formatRuntime(movie.runtime);

  return (
    <article className="group relative">
      <Link
        href={`/movie/${movie.row_index}`}
        // The whole card is one link, so the accessible name must carry the
        // context a sighted user gets from the surrounding layout.
        aria-label={`${movie.title}${movie.release_year ? `, ${movie.release_year}` : ""}`}
        className="block rounded-card focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-brand-400"
      >
        <div className="relative aspect-[2/3] overflow-hidden rounded-card bg-vault-800 shadow-poster">
          <Poster
            src={movie.poster_url}
            title={movie.title}
            width={POSTER_WIDTH}
            height={POSTER_HEIGHT}
            priority={priority}
            sizes="(max-width: 480px) 45vw, (max-width: 768px) 30vw, (max-width: 1280px) 20vw, 200px"
            className="size-full object-cover transition-transform duration-500 ease-out-quart group-hover:scale-[1.04]"
          />

          {/* Gradient scrim so the rating stays legible over bright posters. */}
          <div
            aria-hidden="true"
            className="absolute inset-x-0 bottom-0 h-1/3 bg-gradient-to-t from-vault-950/90 to-transparent opacity-0 transition-opacity duration-300 group-hover:opacity-100"
          />
          <div className="absolute inset-x-2 bottom-2 flex items-center justify-between opacity-0 transition-opacity duration-300 group-hover:opacity-100">
            <RatingBadge rating={movie.vote_average} />
            {runtime && (
              <span className="text-xs font-medium text-vault-muted">{runtime}</span>
            )}
          </div>
        </div>

        <div className="mt-2 space-y-0.5">
          <h3 className="line-clamp-2 text-sm font-medium leading-snug text-vault-text transition-colors group-hover:text-brand-300">
            {movie.title}
          </h3>
          <p className="text-xs text-vault-faint tabular-nums">{year}</p>
        </div>
      </Link>
    </article>
  );
}
