"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";

/**
 * Debounced search that writes to the URL rather than holding local state, so
 * results stay shareable, bookmarkable, and survive a refresh.
 */
export function SearchBox({ className = "" }: { className?: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const inputId = useId();

  const urlQuery = searchParams.get("q") ?? "";
  const [value, setValue] = useState(urlQuery);
  const [syncedQuery, setSyncedQuery] = useState(urlQuery);
  const isFirstRender = useRef(true);

  // Keep the input in sync when navigation changes the URL (back button, links).
  // Adjusted during render rather than in an effect: an effect here would cause
  // a cascading re-render on every navigation.
  if (urlQuery !== syncedQuery) {
    setSyncedQuery(urlQuery);
    setValue(urlQuery);
  }

  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }
    if (value === urlQuery) return;

    const timer = setTimeout(() => {
      const params = new URLSearchParams(searchParams.toString());
      if (value.trim()) {
        params.set("q", value.trim());
      } else {
        params.delete("q");
      }
      // A new query means a new result set; never keep the old page offset.
      params.delete("page");
      router.push(`/browse?${params.toString()}`);
    }, 350);

    return () => clearTimeout(timer);
  }, [value, urlQuery, router, searchParams]);

  return (
    <search className={className}>
      <label htmlFor={inputId} className="sr-only">
        Search movies by title
      </label>
      <div className="relative">
        <svg
          aria-hidden="true"
          viewBox="0 0 20 20"
          fill="none"
          className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-vault-faint"
        >
          <circle cx="9" cy="9" r="6" stroke="currentColor" strokeWidth="1.6" />
          <path d="m13.5 13.5 3.5 3.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
        <input
          id={inputId}
          type="search"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder="Search movies…"
          autoComplete="off"
          className="w-full rounded-full border border-vault-700 bg-vault-850/80 py-2 pl-9 pr-4 text-sm text-vault-text placeholder:text-vault-faint transition-colors hover:border-vault-600 focus:border-brand-500 focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-400"
        />
      </div>
    </search>
  );
}
