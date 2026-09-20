import { formatRating } from "@/lib/format";

/** Small rating pill. Renders nothing when a title has never been rated. */
export function RatingBadge({
  rating,
  className = "",
}: {
  rating: number | null;
  className?: string;
}) {
  const value = formatRating(rating);
  if (!value) return null;

  const numeric = Number(value);
  const tone =
    numeric >= 7.5
      ? "text-positive"
      : numeric >= 6
        ? "text-warning"
        : "text-negative";

  return (
    <span
      className={`inline-flex items-center gap-1 text-xs font-semibold tabular-nums ${tone} ${className}`}
    >
      <svg aria-hidden="true" viewBox="0 0 20 20" fill="currentColor" className="size-3.5">
        <path d="M10 1.8l2.5 5.1 5.6.8-4 3.9.9 5.6-5-2.6-5 2.6.9-5.6-4-3.9 5.6-.8z" />
      </svg>
      <span>
        {value}
        <span className="sr-only"> out of 10</span>
      </span>
    </span>
  );
}
