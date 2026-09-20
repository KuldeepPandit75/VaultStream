import Image from "next/image";
import Link from "next/link";

import type { CastMember } from "@/lib/types";

/** Horizontally scrolling billed cast. Keyboard-scrollable via the list itself. */
export function CastStrip({ cast }: { cast: CastMember[] }) {
  if (cast.length === 0) return null;

  return (
    <section aria-labelledby="cast-heading">
      <h2 id="cast-heading" className="mb-4 text-lg font-semibold tracking-tight">
        Top billed cast
      </h2>
      <ul
        // tabIndex makes the overflow container focusable so it can be scrolled
        // with the arrow keys, which a plain div cannot.
        tabIndex={0}
        className="flex gap-4 overflow-x-auto pb-3 [scrollbar-width:thin]"
      >
        {cast.map((member) => (
          <li
            key={`${member.person_id}-${member.character ?? ""}`}
            className="w-28 shrink-0"
          >
            <Link
              href={`/person/${member.person_id}`}
              className="group block rounded-lg focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-brand-400"
              aria-label={
                member.character
                  ? `${member.name}, as ${member.character}`
                  : member.name
              }
            >
              <div className="relative aspect-[2/3] overflow-hidden rounded-lg bg-vault-800">
                {member.profile_url ? (
                  <Image
                    src={member.profile_url}
                    alt=""
                    width={185}
                    height={278}
                    sizes="112px"
                    className="size-full object-cover"
                  />
                ) : (
                  <div className="grid size-full place-items-center">
                    <svg
                      aria-hidden="true"
                      viewBox="0 0 24 24"
                      fill="none"
                      className="size-8 text-vault-600"
                    >
                      <circle
                        cx="12"
                        cy="8"
                        r="4"
                        stroke="currentColor"
                        strokeWidth="1.8"
                      />
                      <path
                        d="M4 21c0-4 3.6-6 8-6s8 2 8 6"
                        stroke="currentColor"
                        strokeWidth="1.8"
                        strokeLinecap="round"
                      />
                    </svg>
                  </div>
                )}
              </div>

              <p className="mt-2 line-clamp-2 text-xs font-medium leading-snug text-vault-text transition-colors group-hover:text-brand-300">
                {member.name}
              </p>
              {member.character && (
                <p className="line-clamp-2 text-xs leading-snug text-vault-faint">
                  {member.character}
                </p>
              )}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
