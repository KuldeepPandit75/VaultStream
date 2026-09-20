"use client";

import Image from "next/image";
import { useState } from "react";

/**
 * Poster image with a graceful fallback.
 *
 * The catalogue metadata dates from 2017 and TMDB has since removed some
 * artwork, so a fraction of `poster_path` values now 404 on their CDN. Without
 * this, those cards render as broken images and the optimizer logs upstream
 * errors on every request.
 */
export function Poster({
  src,
  title,
  width,
  height,
  sizes,
  priority = false,
  className = "",
}: {
  src: string | null;
  title: string;
  width: number;
  height: number;
  sizes?: string;
  priority?: boolean;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);

  if (!src || failed) {
    return <PosterFallback title={title} />;
  }

  return (
    <Image
      src={src}
      // Decorative: the enclosing link already carries the accessible name.
      alt=""
      width={width}
      height={height}
      sizes={sizes}
      priority={priority}
      onError={() => setFailed(true)}
      className={className}
    />
  );
}

/** Typographic placeholder so a missing poster still looks deliberate. */
export function PosterFallback({ title }: { title: string }) {
  const initials = title
    .replace(/^(the|a|an)\s+/i, "")
    .split(/\s+/)
    .slice(0, 2)
    .map((word) => word[0])
    .join("")
    .toUpperCase();

  return (
    <div className="flex size-full flex-col items-center justify-center gap-2 bg-gradient-to-br from-vault-800 to-vault-700 p-3 text-center">
      <span aria-hidden="true" className="font-mono text-2xl font-bold text-vault-500">
        {initials || "?"}
      </span>
      <span className="line-clamp-3 text-[0.6875rem] leading-tight text-vault-faint">
        {title}
      </span>
    </div>
  );
}
