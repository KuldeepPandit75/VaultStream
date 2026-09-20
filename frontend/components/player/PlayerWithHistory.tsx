"use client";

import { useCallback, useRef } from "react";

import { TrailerPlayer } from "@/components/player/TrailerPlayer";
import { reportProgress } from "@/lib/history-client";
import { recordLocalProgress } from "@/lib/local-history";

/**
 * Wires the player's progress callback to the history API.
 *
 * Kept separate from TrailerPlayer so the player stays a pure playback
 * component with no knowledge of persistence. Anonymous viewers still get
 * progress tracking, just written to localStorage instead of the backend,
 * since there is no account to attach server-side history to.
 */
export function PlayerWithHistory({
  videoKey,
  title,
  rowIndex,
  startAt,
  enabled,
}: {
  videoKey: string;
  title: string;
  rowIndex: number;
  startAt: number;
  /** False for anonymous viewers: progress goes to localStorage instead. */
  enabled: boolean;
}) {
  // Skip a write when the position has barely moved, e.g. repeated pause events.
  const lastSentRef = useRef(-Infinity);

  const onProgress = useCallback(
    (position: number, duration: number) => {
      if (Math.abs(position - lastSentRef.current) < 1) return;
      lastSentRef.current = position;
      if (enabled) {
        void reportProgress(rowIndex, position, duration || null);
      } else {
        recordLocalProgress(rowIndex, position, duration || null);
      }
    },
    [rowIndex, enabled],
  );

  return (
    <TrailerPlayer
      videoKey={videoKey}
      title={title}
      rowIndex={rowIndex}
      startAt={startAt}
      onProgress={onProgress}
    />
  );
}
