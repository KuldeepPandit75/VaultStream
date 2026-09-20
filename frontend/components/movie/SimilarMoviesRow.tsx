import { MovieCard } from "@/components/catalog/MovieCard";
import { getSimilarMovies } from "@/lib/api";

export async function SimilarMoviesRow({ rowIndex }: { rowIndex: number }) {
  const similar = await getSimilarMovies(rowIndex).catch(() => []);
  if (similar.length === 0) return null;

  return (
    <section aria-labelledby="similar-heading">
      <h2 id="similar-heading" className="mb-4 text-lg font-semibold tracking-tight">
        Similar Movies
      </h2>
      <ul className="grid grid-cols-2 gap-x-4 gap-y-7 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 xl:grid-cols-7">
        {similar.map((movie) => (
          <li key={movie.row_index}>
            <MovieCard movie={movie} />
          </li>
        ))}
      </ul>
    </section>
  );
}
