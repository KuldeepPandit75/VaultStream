/** Display formatting helpers. All tolerate null so sparse records render cleanly. */

export function formatRuntime(minutes: number | null): string | null {
  if (!minutes || minutes <= 0) return null;
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  if (hours === 0) return `${remainder}m`;
  if (remainder === 0) return `${hours}h`;
  return `${hours}h ${remainder}m`;
}

export function formatRating(rating: number | null): string | null {
  // The dataset uses 0.0 for "never rated", which should read as unrated.
  if (rating === null || rating === undefined || rating <= 0) return null;
  return rating.toFixed(1);
}

export function formatVoteCount(votes: number | null): string | null {
  if (!votes || votes <= 0) return null;
  if (votes < 1000) return String(votes);
  if (votes < 1_000_000) return `${(votes / 1000).toFixed(votes < 10_000 ? 1 : 0)}k`;
  return `${(votes / 1_000_000).toFixed(1)}M`;
}

export function formatYear(year: number | null): string {
  return year ? String(year) : "—";
}

export function formatCurrency(amount: number | null): string | null {
  if (!amount || amount <= 0) return null;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(amount);
}

const LANGUAGE_NAMES = new Intl.DisplayNames(["en"], { type: "language" });

export function formatLanguage(code: string | null): string | null {
  if (!code) return null;
  try {
    return LANGUAGE_NAMES.of(code) ?? code.toUpperCase();
  } catch {
    return code.toUpperCase();
  }
}

/** Percentage 0-100 for the rating meter, or null when unrated. */
export function ratingPercent(rating: number | null): number | null {
  if (rating === null || rating === undefined || rating <= 0) return null;
  return Math.round((rating / 10) * 100);
}
