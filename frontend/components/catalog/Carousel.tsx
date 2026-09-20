"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { ReactNode } from "react";

/**
 * Horizontally scrolling row with arrow controls.
 *
 * The track is a real focusable, scrollable list so keyboard users can move
 * through it with the arrow keys; the buttons are an addition for pointer users,
 * not the only way to operate it. Arrows hide when there is nothing further to
 * scroll, which is how a native OTT row behaves.
 */
export function Carousel({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  const trackRef = useRef<HTMLUListElement | null>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);

  const measure = useCallback(() => {
    const track = trackRef.current;
    if (!track) return;
    const maxScroll = track.scrollWidth - track.clientWidth;
    setCanScrollLeft(track.scrollLeft > 8);
    setCanScrollRight(track.scrollLeft < maxScroll - 8);
  }, []);

  useEffect(() => {
    const track = trackRef.current;
    if (!track) return;

    measure();
    track.addEventListener("scroll", measure, { passive: true });

    // Recompute when the row resizes, e.g. a window resize or font load.
    const observer = new ResizeObserver(measure);
    observer.observe(track);

    return () => {
      track.removeEventListener("scroll", measure);
      observer.disconnect();
    };
  }, [measure]);

  const scrollByPage = (direction: -1 | 1) => {
    const track = trackRef.current;
    if (!track) return;
    // Leave a sliver of the adjacent card visible so the row reads as continuous.
    track.scrollBy({ left: direction * track.clientWidth * 0.85, behavior: "smooth" });
  };

  const arrowClass =
    "absolute top-1/2 z-10 hidden -translate-y-1/2 place-items-center rounded-full bg-vault-950/80 p-2.5 text-vault-text backdrop-blur transition-colors hover:bg-vault-800 md:grid";

  return (
    <div className="group/carousel relative">
      {canScrollLeft && (
        <button
          type="button"
          onClick={() => scrollByPage(-1)}
          aria-label={`Scroll ${label} left`}
          className={`${arrowClass} -left-3`}
        >
          <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" className="size-5">
            <path
              d="M15 5l-7 7 7 7"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
      )}

      <ul
        ref={trackRef}
        // Focusable so the row can be scrolled with the keyboard alone.
        tabIndex={0}
        aria-label={label}
        className="flex snap-x snap-mandatory gap-4 overflow-x-auto scroll-smooth pb-2 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {children}
      </ul>

      {canScrollRight && (
        <button
          type="button"
          onClick={() => scrollByPage(1)}
          aria-label={`Scroll ${label} right`}
          className={`${arrowClass} -right-3`}
        >
          <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" className="size-5">
            <path
              d="M9 5l7 7-7 7"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
      )}
    </div>
  );
}

/** Fixed-width slide sized so ~7 fit on a wide screen. */
export function CarouselItem({ children }: { children: ReactNode }) {
  return (
    <li className="w-[8.5rem] shrink-0 snap-start sm:w-[9.5rem] lg:w-[10.5rem]">
      {children}
    </li>
  );
}
