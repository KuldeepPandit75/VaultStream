import Link from "next/link";

/**
 * Primary call to action.
 *
 * When no trailer is known, this renders a disabled control with an explicit
 * reason rather than a link that would dead-end on the player page.
 */
export function PlayButton({
  rowIndex,
  hasTrailer,
  title,
}: {
  rowIndex: number;
  hasTrailer: boolean;
  title: string;
}) {
  const icon = (
    <svg aria-hidden="true" viewBox="0 0 20 20" fill="currentColor" className="size-5">
      <path d="M6 4.5v11l9-5.5-9-5.5z" />
    </svg>
  );

  if (!hasTrailer) {
    return (
      <div className="flex flex-col gap-1.5">
        <button
          type="button"
          disabled
          aria-describedby="no-trailer-reason"
          className="inline-flex cursor-not-allowed items-center gap-2 rounded-full bg-vault-700 px-7 py-3 text-sm font-semibold text-vault-faint"
        >
          {icon}
          Play trailer
        </button>
        <p id="no-trailer-reason" className="text-xs text-vault-faint">
          No trailer available for this title.
        </p>
      </div>
    );
  }

  return (
    <Link
      href={`/watch/${rowIndex}`}
      className="inline-flex items-center gap-2 rounded-full bg-brand-500 px-7 py-3 text-sm font-semibold text-vault-950 transition-colors hover:bg-brand-400"
    >
      {icon}
      Play trailer
      <span className="sr-only"> for {title}</span>
    </Link>
  );
}
