"use client";

import Image from "next/image";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import type { MovieSummary } from "@/lib/types";

/** Auto-advance interval in milliseconds. */
const AUTO_ADVANCE_MS = 6_000;
/** Crossfade transition duration in milliseconds. */
const TRANSITION_MS = 700;

export function HeroCarousel({ movies }: { movies: MovieSummary[] }) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [isPaused, setIsPaused] = useState(false);
  const activeRef = useRef(0);
  const count = movies.length;

  const goTo = useCallback(
    (index: number) => {
      const next = ((index % count) + count) % count;
      activeRef.current = next;
      setActiveIndex(next);
    },
    [count],
  );

  // Auto-advance timer — restarts when activeIndex changes
  // so manual navigation resets the progress bar timer.
  useEffect(() => {
    if (isPaused || count <= 1) return;

    const id = setInterval(() => {
      goTo(activeRef.current + 1);
    }, AUTO_ADVANCE_MS);
    return () => clearInterval(id);
  }, [isPaused, count, goTo, activeIndex]);

  if (count === 0) return null;

  const active = movies[activeIndex];
  const genres = active.genres.slice(0, 3);

  return (
    <section
      aria-label="Featured movies"
      onMouseEnter={() => setIsPaused(true)}
      onMouseLeave={() => setIsPaused(false)}
      onFocus={() => setIsPaused(true)}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) setIsPaused(false);
      }}
      className="relative w-full overflow-hidden"
      style={{ height: "clamp(400px, 60vh, 700px)" }}
    >
      {/* Backdrop images — only these crossfade */}
      {movies.map((movie, index) => (
        <div
          key={movie.row_index}
          className="absolute inset-0 transition-opacity ease-out"
          style={{
            transitionDuration: `${TRANSITION_MS}ms`,
            opacity: index === activeIndex ? 1 : 0,
            zIndex: index === activeIndex ? 1 : 0,
          }}
          aria-hidden={index !== activeIndex}
        >
          {movie.backdrop_url ? (
            <Image
              src={movie.backdrop_url}
              alt=""
              fill
              priority={index === 0}
              sizes="100vw"
              className="object-cover object-[50%_20%]"
            />
          ) : (
            <div className="absolute inset-0 bg-gradient-to-br from-vault-800 to-vault-950" />
          )}
        </div>
      ))}

      {/* Dark overlays for text legibility */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 z-[2] bg-gradient-to-r from-vault-950/90 via-vault-950/50 to-transparent"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 z-[2] bg-gradient-to-t from-vault-950/70 via-transparent to-vault-950/30"
      />

      {/* Bottom fade into page background */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 bottom-0 z-[2] h-1/3 bg-gradient-to-t from-vault-950 via-vault-950/60 to-transparent"
      />

      {/* Static content overlay — animated with key to trigger on slide change */}
      <div className="relative z-10 flex h-full items-end px-4 pb-20 sm:px-6 lg:px-8">
        <div className="mx-auto w-full max-w-[1600px]">
          <div key={activeIndex} className="max-w-xl animate-fade-in-up">
            {/* Genre pills */}
            {genres.length > 0 && (
              <div className="mb-3 flex flex-wrap gap-2">
                {genres.map((genre) => (
                  <span
                    key={genre}
                    className="rounded-full border border-white/20 bg-white/10 px-3 py-0.5 text-xs font-medium text-white/80 backdrop-blur-sm"
                  >
                    {genre}
                  </span>
                ))}
              </div>
            )}

            <h2 className="text-3xl font-bold tracking-tight text-white sm:text-4xl lg:text-5xl">
              {active.title}
            </h2>

            {/* Meta line */}
            <div className="mt-2.5 flex items-center gap-3 text-sm text-white/70">
              {active.release_year && <span>{active.release_year}</span>}
              {active.vote_average != null && active.vote_average > 0 && (
                <>
                  <span className="text-white/30">•</span>
                  <span className="flex items-center gap-1">
                    <svg
                      aria-hidden="true"
                      viewBox="0 0 20 20"
                      fill="currentColor"
                      className="size-3.5 text-brand-400"
                    >
                      <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                    </svg>
                    {active.vote_average.toFixed(1)}
                  </span>
                </>
              )}
            </div>

            {/* CTAs — static buttons, only href updates */}
            <div className="mt-6 flex flex-wrap gap-3">
              <Link
                href={`/watch/${active.row_index}`}
                className="inline-flex items-center gap-2 rounded-full bg-brand-500 px-6 py-3 text-sm font-semibold text-vault-950 transition-colors hover:bg-brand-400"
              >
                <svg
                  aria-hidden="true"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                  className="size-5"
                >
                  <path d="M6 4.5v11l9-5.5-9-5.5z" />
                </svg>
                Play trailer
              </Link>
              <Link
                href={`/movie/${active.row_index}`}
                className="inline-flex items-center gap-2 rounded-full border border-white/25 bg-white/10 px-6 py-3 text-sm font-semibold text-white backdrop-blur-sm transition-colors hover:border-white/40 hover:bg-white/20"
              >
                <svg
                  aria-hidden="true"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                  className="size-4"
                >
                  <path
                    fillRule="evenodd"
                    d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.253a.25.25 0 01.244.304l-.459 2.066A1.75 1.75 0 0010.747 15H11a.75.75 0 000-1.5h-.253a.25.25 0 01-.244-.304l.459-2.066A1.75 1.75 0 009.253 9H9z"
                    clipRule="evenodd"
                  />
                </svg>
                More info
              </Link>
            </div>
          </div>
        </div>
      </div>

      {/* Dot indicators */}
      {count > 1 && (
        <div className="absolute inset-x-0 bottom-6 z-20 flex justify-center gap-2.5">
          {movies.map((movie, index) => (
            <button
              key={movie.row_index}
              type="button"
              onClick={() => goTo(index)}
              aria-label={`Show ${movie.title}`}
              className={`group relative h-2.5 overflow-hidden rounded-full transition-all duration-300 ${
                index === activeIndex
                  ? "w-8 bg-white/30"
                  : "w-2.5 bg-white/30 hover:bg-white/50"
              }`}
            >
              <span
                className={`absolute inset-y-0 left-0 rounded-full bg-brand-500 transition-opacity duration-200 force-motion ${
                  index === activeIndex ? "opacity-100" : "opacity-0"
                }`}
                style={{
                  width: 0,
                  animation: index === activeIndex
                    ? `hero-progress ${AUTO_ADVANCE_MS}ms linear forwards`
                    : "none",
                  animationPlayState: isPaused ? "paused" : "running",
                }}
              />
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
