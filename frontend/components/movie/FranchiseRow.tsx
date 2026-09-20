import { MovieCard } from "@/components/catalog/MovieCard";
import { getCollectionSiblings } from "@/lib/api";

/**
 * Other titles in the same franchise.
 *
 * Renders nothing when the film has no collection, which is the common case:
 * only about 10% of the catalogue belongs to one.
 */
export async function FranchiseRow({
  rowIndex,
  collectionName,
}: {
  rowIndex: number;
  collectionName: string | null;
}) {
  const siblings = await getCollectionSiblings(rowIndex).catch(() => []);
  if (siblings.length === 0) return null;

  return (
    <section aria-labelledby="franchise-heading">
      <h2 id="franchise-heading" className="mb-4 text-lg font-semibold tracking-tight">
        {collectionName ?? "More in this collection"}
      </h2>
      <ul className="grid grid-cols-2 gap-x-4 gap-y-7 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 xl:grid-cols-7">
        {siblings.map((movie) => (
          <li key={movie.row_index}>
            <MovieCard movie={movie} />
          </li>
        ))}
      </ul>
    </section>
  );
}
