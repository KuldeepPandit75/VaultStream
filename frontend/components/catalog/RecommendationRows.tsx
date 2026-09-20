import { Carousel, CarouselItem } from "@/components/catalog/Carousel";
import { MovieCard } from "@/components/catalog/MovieCard";
import { getRecommendationFeed } from "@/lib/session";

/**
 * The personalised block: "Top picks for you" and "Because you watched X".
 *
 * Renders nothing for anonymous visitors. A cold-start row is labelled honestly
 * rather than presenting popularity as personalisation.
 */
export async function RecommendationRows() {
  const feed = await getRecommendationFeed();
  if (!feed) return null;

  const rows = feed.rows.filter((row) => row.items.length > 0);
  if (rows.length === 0) return null;

  return (
    <div className="space-y-12">
      {rows.map((row) => (
        <section key={row.key} aria-labelledby={`rec-${row.key}`}>
          <div className="mb-4 flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <h2
              id={`rec-${row.key}`}
              className="text-xl font-semibold tracking-tight"
            >
              {row.title}
            </h2>
            {row.reason && (
              <p className="text-sm text-vault-faint">{row.reason}</p>
            )}
          </div>

          <Carousel label={row.title}>
            {row.items.map((movie) => (
              <CarouselItem key={`${row.key}-${movie.row_index}`}>
                <MovieCard movie={movie} />
              </CarouselItem>
            ))}
          </Carousel>
        </section>
      ))}
    </div>
  );
}
