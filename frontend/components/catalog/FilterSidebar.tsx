"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useId, useMemo, useState } from "react";

import { formatLanguage } from "@/lib/format";
import type { FilterBounds } from "@/lib/types";

const RATING_STEPS = [0, 5, 6, 7, 8, 9] as const;

export function FilterSidebar({ bounds }: { bounds: FilterBounds }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const groupId = useId();
  const [isOpen, setIsOpen] = useState(false);

  const selectedGenres = useMemo(
    () => new Set(searchParams.getAll("genre")),
    [searchParams],
  );
  const matchAll = searchParams.get("genre_match_all") === "true";
  const yearFrom = searchParams.get("year_from") ?? "";
  const yearTo = searchParams.get("year_to") ?? "";
  const language = searchParams.get("language") ?? "";
  const minRating = searchParams.get("min_rating") ?? "";

  const activeCount =
    selectedGenres.size +
    (yearFrom ? 1 : 0) +
    (yearTo ? 1 : 0) +
    (language ? 1 : 0) +
    (minRating ? 1 : 0);

  /** Every change resets to page 1, since the result set changed. */
  const commit = useCallback(
    (mutate: (params: URLSearchParams) => void) => {
      const params = new URLSearchParams(searchParams.toString());
      mutate(params);
      params.delete("page");
      router.push(`/browse?${params.toString()}`, { scroll: false });
    },
    [router, searchParams],
  );

  const toggleGenre = (name: string) =>
    commit((params) => {
      const current = params.getAll("genre");
      params.delete("genre");
      const next = current.includes(name)
        ? current.filter((item) => item !== name)
        : [...current, name];
      for (const item of next) params.append("genre", item);
    });

  const setParam = (key: string, value: string) =>
    commit((params) => {
      if (value) params.set(key, value);
      else params.delete(key);
    });

  const clearAll = () => router.push("/browse", { scroll: false });

  return (
    <div className="lg:sticky lg:top-24">
      {/* Collapsed into a disclosure on small screens where space is scarce. */}
      <button
        type="button"
        onClick={() => setIsOpen((open) => !open)}
        aria-expanded={isOpen}
        aria-controls={groupId}
        className="mb-4 flex w-full items-center justify-between rounded-lg border border-vault-700 bg-vault-850 px-4 py-2.5 text-sm font-semibold lg:hidden"
      >
        <span>
          Filters
          {activeCount > 0 && (
            <span className="ml-2 rounded-full bg-brand-500 px-2 py-0.5 text-xs text-vault-950">
              {activeCount}
            </span>
          )}
        </span>
        <svg
          aria-hidden="true"
          viewBox="0 0 20 20"
          fill="none"
          className={`size-4 transition-transform ${isOpen ? "rotate-180" : ""}`}
        >
          <path d="m5 8 5 5 5-5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
        </svg>
      </button>

      <div id={groupId} className={`${isOpen ? "block" : "hidden"} space-y-7 lg:block`}>
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-vault-muted">
            Filters
          </h2>
          {activeCount > 0 && (
            <button
              type="button"
              onClick={clearAll}
              className="text-xs font-medium text-brand-400 transition-colors hover:text-brand-300"
            >
              Clear all
            </button>
          )}
        </div>

        <fieldset className="space-y-3">
          <legend className="mb-2 text-xs font-semibold uppercase tracking-wide text-vault-faint">
            Genre
          </legend>
          <div className="flex flex-wrap gap-2">
            {bounds.genres.map((genre) => {
              const isSelected = selectedGenres.has(genre.name);
              return (
                <button
                  key={genre.id}
                  type="button"
                  onClick={() => toggleGenre(genre.name)}
                  aria-pressed={isSelected}
                  className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
                    isSelected
                      ? "border-brand-500 bg-brand-500 text-vault-950"
                      : "border-vault-700 bg-vault-850 text-vault-muted hover:border-vault-600 hover:text-vault-text"
                  }`}
                >
                  {genre.name}
                </button>
              );
            })}
          </div>

          {selectedGenres.size > 1 && (
            <label className="mt-3 flex cursor-pointer items-center gap-2 text-xs text-vault-muted">
              <input
                type="checkbox"
                checked={matchAll}
                onChange={(event) =>
                  setParam("genre_match_all", event.target.checked ? "true" : "")
                }
                className="size-4 rounded border-vault-600 bg-vault-850 accent-brand-500"
              />
              Must match every selected genre
            </label>
          )}
        </fieldset>

        <fieldset>
          <legend className="mb-2 text-xs font-semibold uppercase tracking-wide text-vault-faint">
            Release year
          </legend>
          <div className="flex items-center gap-2">
            <label className="flex-1">
              <span className="sr-only">Year from</span>
              <input
                type="number"
                inputMode="numeric"
                min={bounds.min_year ?? 1870}
                max={bounds.max_year ?? 2100}
                placeholder={String(bounds.min_year ?? 1874)}
                defaultValue={yearFrom}
                onBlur={(event) => setParam("year_from", event.target.value)}
                className="w-full rounded-md border border-vault-700 bg-vault-850 px-3 py-2 text-sm tabular-nums placeholder:text-vault-faint"
              />
            </label>
            <span aria-hidden="true" className="text-vault-faint">
              –
            </span>
            <label className="flex-1">
              <span className="sr-only">Year to</span>
              <input
                type="number"
                inputMode="numeric"
                min={bounds.min_year ?? 1870}
                max={bounds.max_year ?? 2100}
                placeholder={String(bounds.max_year ?? 2020)}
                defaultValue={yearTo}
                onBlur={(event) => setParam("year_to", event.target.value)}
                className="w-full rounded-md border border-vault-700 bg-vault-850 px-3 py-2 text-sm tabular-nums placeholder:text-vault-faint"
              />
            </label>
          </div>
        </fieldset>

        <div>
          <label
            htmlFor={`${groupId}-rating`}
            className="mb-2 block text-xs font-semibold uppercase tracking-wide text-vault-faint"
          >
            Minimum rating
          </label>
          <select
            id={`${groupId}-rating`}
            value={minRating}
            onChange={(event) => setParam("min_rating", event.target.value)}
            className="w-full rounded-md border border-vault-700 bg-vault-850 px-3 py-2 text-sm"
          >
            {RATING_STEPS.map((step) => (
              <option key={step} value={step === 0 ? "" : String(step)}>
                {step === 0 ? "Any rating" : `${step}+`}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label
            htmlFor={`${groupId}-language`}
            className="mb-2 block text-xs font-semibold uppercase tracking-wide text-vault-faint"
          >
            Language
          </label>
          <select
            id={`${groupId}-language`}
            value={language}
            onChange={(event) => setParam("language", event.target.value)}
            className="w-full rounded-md border border-vault-700 bg-vault-850 px-3 py-2 text-sm"
          >
            <option value="">Any language</option>
            {bounds.languages.map((entry) => (
              <option key={entry.code} value={entry.code}>
                {formatLanguage(entry.code)} ({entry.count.toLocaleString()})
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}
