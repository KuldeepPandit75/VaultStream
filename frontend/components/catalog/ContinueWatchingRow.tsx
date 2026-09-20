import { Carousel, CarouselItem } from "@/components/catalog/Carousel";
import { ContinueWatchingCard } from "@/components/catalog/ContinueWatchingCard";
import { getContinueWatching } from "@/lib/session";
import type { WatchProgress } from "@/lib/types";

/**
 * "Continue watching" row.
 *
 * Renders nothing for anonymous visitors or users with nothing to resume, so the
 * home page has no empty placeholder.
 */
export async function ContinueWatchingRow() {
  const entries = (await getContinueWatching(14)) as WatchProgress[];

  const resumable = entries.filter(
    (entry) => entry?.movie && typeof entry.movie.row_index === "number",
  );
  if (resumable.length === 0) return null;

  return (
    <section aria-labelledby="continue-heading">
      <h2
        id="continue-heading"
        className="mb-5 text-xl font-semibold tracking-tight"
      >
        Continue watching
      </h2>
      <Carousel label="Continue watching">
        {resumable.map((entry) => (
          <CarouselItem key={entry.movie.row_index}>
            <ContinueWatchingCard entry={entry} />
          </CarouselItem>
        ))}
      </Carousel>
    </section>
  );
}
