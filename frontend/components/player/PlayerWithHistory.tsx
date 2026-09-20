"use client";

import { useCallback, useRef } from "react";

import { TrailerPlayer } from "@/components/player/TrailerPlayer";
import { reportProgress } from "@/lib/history-client";

/**
 * Wires the player's progress callback to the history API.
 *
 * Kept separate from TrailerPlayer so the player stays a pure playback
 * component with no knowledge of persistence, and so anonymous viewers can use
 * the same player with reporting simply switched off.
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
  /** False for anonymous viewers: nothing to attribute progress to. */
  enabled: boolean;
}) {
  // Skip a POST when the position has barely moved, e.g. repeated pause events.
  const lastSentRef = useRef(-Infinity);

  const onProgress = useCallback(
    (position: number, duration: number) => {
      if (Math.abs(position - lastSentRef.current) < 1) return;
      lastSentRef.current = position;
      void reportProgress(rowIndex, position, duration || null);
    },
    [rowIndex],
  );

  return (
    <TrailerPlayer
      videoKey={videoKey}
      title={title}
      rowIndex={rowIndex}
      startAt={startAt}
      onProgress={enabled ? onProgress : undefined}
    />
  );
}
