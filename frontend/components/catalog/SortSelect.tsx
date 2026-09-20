"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useId } from "react";

/** Sort presets, each encoding both the field and a sensible direction. */
const OPTIONS = [
  { value: "popularity:desc", label: "Most popular" },
  { value: "rating:desc", label: "Highest rated" },
  { value: "vote_count:desc", label: "Most voted" },
  { value: "release_date:desc", label: "Newest first" },
  { value: "release_date:asc", label: "Oldest first" },
  { value: "title:asc", label: "Title A–Z" },
] as const;

export function SortSelect() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const selectId = useId();

  const current = `${searchParams.get("sort") ?? "popularity"}:${
    searchParams.get("order") ?? "desc"
  }`;

  const onChange = (value: string) => {
    const [sort, order] = value.split(":");
    const params = new URLSearchParams(searchParams.toString());
    params.set("sort", sort);
    params.set("order", order);
    params.delete("page");
    router.push(`/browse?${params.toString()}`, { scroll: false });
  };

  return (
    <div className="flex items-center gap-2">
      <label htmlFor={selectId} className="text-sm text-vault-muted">
        Sort
      </label>
      <select
        id={selectId}
        value={OPTIONS.some((option) => option.value === current) ? current : "popularity:desc"}
        onChange={(event) => onChange(event.target.value)}
        className="rounded-md border border-vault-700 bg-vault-850 px-3 py-1.5 text-sm text-vault-text"
      >
        {OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}
