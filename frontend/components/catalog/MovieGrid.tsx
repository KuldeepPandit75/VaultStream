import { MovieCard } from "@/components/catalog/MovieCard";
import type { MovieSummary } from "@/lib/types";

const GRID_CLASS =
  "grid grid-cols-2 gap-x-4 gap-y-7 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 2xl:grid-cols-7";

export function MovieGrid({
  movies,
  label,
}: {
  movies: MovieSummary[];
  label: string;
}) {
  return (
    <ul className={GRID_CLASS} aria-label={label}>
      {movies.map((movie, index) => (
        <li key={movie.row_index}>
          {/* Eagerly load the first row so the largest contentful paint is fast. */}
          <MovieCard movie={movie} priority={index < 7} />
        </li>
      ))}
    </ul>
  );
}

export function MovieGridSkeleton({ count = 21 }: { count?: number }) {
  return (
    <div className={GRID_CLASS} aria-hidden="true">
      {Array.from({ length: count }, (_, index) => (
        <div key={index} className="space-y-2">
          <div className="shimmer aspect-[2/3] rounded-card bg-vault-850" />
          <div className="shimmer h-3.5 w-11/12 rounded bg-vault-850" />
          <div className="shimmer h-3 w-1/3 rounded bg-vault-850" />
        </div>
      ))}
    </div>
  );
}
