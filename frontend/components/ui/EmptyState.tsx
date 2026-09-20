import Link from "next/link";
import type { ReactNode } from "react";

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-vault-800 bg-vault-900/60 px-6 py-16 text-center">
      <svg
        aria-hidden="true"
        viewBox="0 0 48 48"
        fill="none"
        className="mx-auto size-12 text-vault-600"
      >
        <rect x="7" y="11" width="34" height="26" rx="3" stroke="currentColor" strokeWidth="2" />
        <path d="M7 19h34M17 11v8M31 11v8" stroke="currentColor" strokeWidth="2" />
      </svg>
      <h2 className="mt-4 text-lg font-semibold text-vault-text">{title}</h2>
      <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-vault-muted">
        {description}
      </p>
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}

export function ClearFiltersLink() {
  return (
    <Link
      href="/browse"
      className="inline-flex items-center rounded-full bg-brand-500 px-5 py-2 text-sm font-semibold text-vault-950 transition-colors hover:bg-brand-400"
    >
      Clear all filters
    </Link>
  );
}
