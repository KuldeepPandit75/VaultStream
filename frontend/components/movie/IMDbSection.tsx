import type { OmdbData } from "@/lib/types";

function getMetacriticColor(scoreStr: string) {
  const score = parseInt(scoreStr, 10);
  if (isNaN(score)) return "bg-vault-800 text-vault-text";
  if (score >= 61) return "bg-[var(--color-mc-green)] text-white";
  if (score >= 40) return "bg-[var(--color-mc-yellow)] text-white";
  return "bg-[var(--color-mc-red)] text-white";
}

function getRottenTomatoesIcon(scoreStr: string) {
  const score = parseInt(scoreStr, 10);
  if (isNaN(score)) return null;
  // Fresh >= 60, Rotten < 60
  if (score >= 60) {
    return (
      <svg viewBox="0 0 32 32" className="size-6 shrink-0" aria-label="Fresh Tomato">
        <path fill="#FA320A" d="M16 2.5c-7.5 0-14.5 4.5-14.5 13.5 0 9 7.5 13.5 14.5 13.5s14.5-4.5 14.5-13.5S23.5 2.5 16 2.5z" />
        <path fill="#42B029" d="M18.5 7.5c-1-1.5-3-2.5-5-2.5-3.5 0-6 2.5-6 6 0 2.5 1.5 4.5 3.5 5.5.5.5 1.5.5 2-.5.5-1-1-2.5-2.5-3-2.5-1-1.5-4 1.5-4 2 0 4 1.5 5.5 3.5.5.5 1.5 1 2 .5.5-.5 0-1.5-.5-2.5-1-2-1.5-3.5-.5-3z" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 32 32" className="size-6 shrink-0" aria-label="Rotten Splat">
      <path fill="#78B928" d="M19.5 22.5c2 1 4-1 3.5-3.5-.5-2.5-2-4-4.5-3.5-1 .5-2 1.5-2.5 3-.5 1-1 3.5 3.5 4z" />
      <path fill="#78B928" d="M12.5 24.5c2 1 4.5 0 5-2.5.5-2.5-1-4.5-3.5-4-1.5.5-3 1.5-3.5 3-.5 1.5 0 3.5 2 3.5z" />
      <path fill="#78B928" d="M8.5 19.5c1.5 1.5 4 .5 4.5-1.5.5-2-1-4-3-4-1.5 0-2.5 1-3 2.5-.5 1.5 0 3.5 1.5 3z" />
      <path fill="#78B928" d="M11 12.5c1.5 1 3.5 0 4-2 .5-2-1.5-4-3.5-3.5-1.5.5-3 1.5-3 3 0 1.5.5 3 2.5 2.5z" />
      <path fill="#78B928" d="M18 10.5c2 1 4.5.5 5-1.5.5-2-1.5-4.5-4-4-1.5.5-3 1.5-3 3 0 1.5.5 3 2 2.5z" />
      <path fill="#78B928" d="M24 16.5c1.5 1.5 4 .5 4-1.5 0-2-1.5-4-3.5-3.5-1.5.5-2.5 2-2.5 3.5 0 1 1 2 2 1.5z" />
    </svg>
  );
}

export function IMDbSection({ omdb }: { omdb: OmdbData }) {
  const rtRating = omdb.ratings?.find((r) => r.source === "Rotten Tomatoes")?.value;
  
  if (!omdb.imdb_rating && !rtRating && !omdb.metascore && !omdb.awards) {
    return null;
  }

  return (
    <section className="mt-8 rounded-card border border-vault-800 bg-vault-900/50 p-6 shadow-sm backdrop-blur-sm sm:p-8">
      <h2 className="sr-only">External Ratings and Awards</h2>
      
      <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
        {/* Ratings Trio */}
        <div className="flex flex-wrap items-center gap-6 sm:gap-10">
          {/* IMDb */}
          {omdb.imdb_rating && (
            <div className="flex items-center gap-3">
              <span className="rounded bg-[#F5C518] px-1.5 py-0.5 text-xs font-black tracking-tight text-black">
                IMDb
              </span>
              <div className="flex flex-col">
                <span className="text-lg font-bold tabular-nums leading-none">
                  <span className="text-white">{omdb.imdb_rating.toFixed(1)}</span>
                  <span className="text-vault-muted text-sm font-normal">/10</span>
                </span>
                {omdb.imdb_votes && (
                  <span className="text-[11px] uppercase tracking-wide text-vault-faint">
                    {omdb.imdb_votes} votes
                  </span>
                )}
              </div>
            </div>
          )}

          {/* Rotten Tomatoes */}
          {rtRating && (
            <div className="flex items-center gap-3">
              {getRottenTomatoesIcon(rtRating)}
              <div className="flex flex-col">
                <span className="text-lg font-bold tabular-nums leading-none text-white">
                  {rtRating}
                </span>
                <span className="text-[11px] uppercase tracking-wide text-vault-faint">
                  Tomatometer
                </span>
              </div>
            </div>
          )}

          {/* Metacritic */}
          {omdb.metascore && (
            <div className="flex items-center gap-3">
              <div
                className={`grid size-9 place-items-center rounded ${getMetacriticColor(
                  omdb.metascore
                )} text-base font-bold tabular-nums leading-none`}
              >
                {omdb.metascore}
              </div>
              <div className="flex flex-col">
                <span className="text-[11px] font-semibold uppercase tracking-wide text-vault-text">
                  Metascore
                </span>
                <span className="text-[11px] uppercase tracking-wide text-vault-faint">
                  Critic Reviews
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Awards */}
        {omdb.awards && (
          <div className="flex items-start gap-3 md:max-w-sm lg:max-w-md">
            <svg
              className="mt-0.5 size-5 shrink-0 text-brand-400"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={1.5}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M16.5 18.75h-9m9 0a3 3 0 013 3h-15a3 3 0 013-3m9 0v-3.375c0-.621-.503-1.125-1.125-1.125h-.871M7.5 18.75v-3.375c0-.621.504-1.125 1.125-1.125h.872m5.007 0H9.497m5.007 0a7.454 7.454 0 01-.982-3.172M9.497 14.25a7.454 7.454 0 00.981-3.172M5.25 4.236c-.982.143-1.954.317-2.916.52A6.003 6.003 0 007.73 9.728M5.25 4.236V4.5c0 2.108.966 3.99 2.48 5.228M5.25 4.236V2.721C7.456 2.41 9.71 2.25 12 2.25c2.291 0 4.545.16 6.75.47v1.516M7.73 9.728a6.726 6.726 0 002.748 1.35m8.272-6.842V4.5c0 2.108-.966 3.99-2.48 5.228m2.48-5.492a46.32 46.32 0 012.916.52 6.003 6.003 0 01-5.395 4.972m0 0a6.726 6.726 0 01-2.749 1.35m0 0a6.772 6.772 0 01-3.044 0"
              />
            </svg>
            <p className="text-sm font-medium leading-snug text-vault-text">
              {omdb.awards}
            </p>
          </div>
        )}
      </div>
    </section>
  );
}
