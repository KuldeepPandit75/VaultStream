import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";

import { RatingBadge } from "@/components/ui/RatingBadge";
import { EmptyState } from "@/components/ui/EmptyState";
import { ApiError, getPerson } from "@/lib/api";
import type { PersonCredit, PersonDetail } from "@/lib/types";

type LoadResult =
  | { ok: true; person: PersonDetail }
  | { ok: false; status: number; message: string };

async function loadPerson(personId: number): Promise<LoadResult> {
  try {
    return { ok: true, person: await getPerson(personId) };
  } catch (error) {
    if (error instanceof ApiError) {
      return { ok: false, status: error.status, message: error.message };
    }
    return { ok: false, status: 500, message: "Could not load this person." };
  }
}

function parseId(raw: string): number | null {
  if (!/^\d+$/.test(raw)) return null;
  const parsed = Number(raw);
  return Number.isSafeInteger(parsed) ? parsed : null;
}

export async function generateMetadata({
  params,
}: PageProps<"/person/[person_id]">): Promise<Metadata> {
  const { person_id } = await params;
  const id = parseId(person_id);
  if (id === null) return { title: "Not found" };

  const result = await loadPerson(id);
  if (!result.ok) return { title: "Not found" };

  const { person } = result;
  const total = person.cast_count + person.crew_count;
  return {
    title: person.name,
    description: `${person.name} — ${total} credit${total === 1 ? "" : "s"} in the VaultStream catalogue.`,
  };
}

function CreditList({
  heading,
  credits,
  roleLabel,
}: {
  heading: string;
  credits: PersonCredit[];
  roleLabel: string;
}) {
  if (credits.length === 0) return null;

  const headingId = heading.toLowerCase().replace(/\s+/g, "-");

  return (
    <section aria-labelledby={headingId}>
      <h2 id={headingId} className="mb-4 text-lg font-semibold tracking-tight">
        {heading}{" "}
        <span className="text-sm font-normal text-vault-faint tabular-nums">
          ({credits.length})
        </span>
      </h2>
      <ul className="divide-y divide-vault-850">
        {credits.map((credit, index) => (
          <li key={`${credit.row_index}-${credit.role ?? index}`}>
            <Link
              href={`/movie/${credit.row_index}`}
              className="flex items-center gap-4 py-3 transition-colors hover:bg-vault-900/60"
            >
              <span className="w-12 shrink-0 text-right text-sm text-vault-faint tabular-nums">
                {credit.release_year ?? "—"}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-vault-text">
                  {credit.title}
                </span>
                {credit.role && (
                  <span className="block truncate text-xs text-vault-faint">
                    <span className="sr-only">{roleLabel}: </span>
                    {credit.role}
                  </span>
                )}
              </span>
              <RatingBadge rating={credit.vote_average} className="shrink-0" />
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default async function PersonPage({
  params,
}: PageProps<"/person/[person_id]">) {
  const { person_id } = await params;
  const id = parseId(person_id);
  if (id === null) notFound();

  const result = await loadPerson(id);
  if (!result.ok) {
    if (result.status === 404) notFound();
    return (
      <div className="mx-auto max-w-3xl px-4 py-20">
        <EmptyState title="Could not load this person" description={result.message} />
      </div>
    );
  }

  const { person } = result;
  const total = person.cast_count + person.crew_count;

  return (
    <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6 lg:px-8">
      <header className="flex flex-col gap-6 sm:flex-row sm:items-start sm:gap-8">
        <div className="w-32 shrink-0 sm:w-40">
          <div className="relative aspect-[2/3] overflow-hidden rounded-card bg-vault-800 shadow-poster">
            {person.profile_url ? (
              <Image
                src={person.profile_url}
                alt=""
                width={185}
                height={278}
                priority
                sizes="(max-width: 640px) 128px, 160px"
                className="size-full object-cover"
              />
            ) : (
              <div className="grid size-full place-items-center">
                <svg
                  aria-hidden="true"
                  viewBox="0 0 24 24"
                  fill="none"
                  className="size-12 text-vault-600"
                >
                  <circle cx="12" cy="8" r="4" stroke="currentColor" strokeWidth="1.6" />
                  <path
                    d="M4 21c0-4 3.6-6 8-6s8 2 8 6"
                    stroke="currentColor"
                    strokeWidth="1.6"
                    strokeLinecap="round"
                  />
                </svg>
              </div>
            )}
          </div>
        </div>

        <div className="min-w-0">
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
            {person.name}
          </h1>
          <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-sm text-vault-muted">
            {person.known_for && (
              <div className="flex gap-2">
                <dt className="text-vault-faint">Known for</dt>
                <dd>{person.known_for}</dd>
              </div>
            )}
            {person.gender && (
              <div className="flex gap-2">
                <dt className="text-vault-faint">Gender</dt>
                <dd>{person.gender}</dd>
              </div>
            )}
            <div className="flex gap-2">
              <dt className="text-vault-faint">Credits</dt>
              <dd className="tabular-nums">{total}</dd>
            </div>
          </dl>
          {/*
            The source dataset has no biographies, so this is stated plainly
            rather than leaving an empty region that looks like a loading bug.
          */}
          <p className="mt-4 max-w-prose text-sm leading-relaxed text-vault-faint">
            Biographical details are not included in this catalogue. Credits below
            are limited to top-billed cast and principal crew.
          </p>
        </div>
      </header>

      <div className="mt-12 space-y-12">
        {total === 0 ? (
          <EmptyState
            title="No credits found"
            description="This person has no cast or crew credits in the catalogue."
          />
        ) : (
          <>
            <CreditList
              heading="Acting"
              credits={person.cast_credits}
              roleLabel="Character"
            />
            <CreditList heading="Crew" credits={person.crew_credits} roleLabel="Job" />
          </>
        )}

        <p>
          <Link
            href="/browse"
            className="text-sm font-medium text-brand-400 transition-colors hover:text-brand-300"
          >
            ← Back to browse
          </Link>
        </p>
      </div>
    </div>
  );
}
