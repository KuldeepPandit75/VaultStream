"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { PlayerControls } from "@/components/player/PlayerControls";
import {
  YT_PLAYER_STATE,
  loadYouTubeApi,
  type YouTubePlayer,
} from "@/lib/youtube";

/** How often the UI reads the player clock. */
const TICK_MS = 250;
/** How often progress is reported upward (Task 12 persists it). */
const PROGRESS_REPORT_MS = 5_000;
/** Idle delay before the chrome fades while playing. */
const IDLE_HIDE_MS = 2_800;

export interface TrailerPlayerProps {
  videoKey: string;
  title: string;
  rowIndex: number;
  /** Seconds to resume from. */
  startAt?: number;
  /** Called periodically while playing, and once on pause/end. */
  onProgress?: (positionSeconds: number, durationSeconds: number) => void;
}

export function TrailerPlayer({
  videoKey,
  title,
  rowIndex,
  startAt = 0,
  onProgress,
}: TrailerPlayerProps) {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const playerRef = useRef<YouTubePlayer | null>(null);
  const shellRef = useRef<HTMLDivElement | null>(null);
  const idleTimerRef = useRef<number | null>(null);
  const lastReportRef = useRef(0);

  // Held in a ref so the polling effect never needs to re-subscribe when the
  // parent passes a new closure. Synced in an effect because mutating a ref
  // during render is not allowed.
  const onProgressRef = useRef(onProgress);
  useEffect(() => {
    onProgressRef.current = onProgress;
  }, [onProgress]);

  const [isReady, setIsReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [hasEnded, setHasEnded] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [bufferedFraction, setBufferedFraction] = useState(0);
  const [volume, setVolume] = useState(100);
  const [isMuted, setIsMuted] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showChrome, setShowChrome] = useState(true);

  // --- create the player ---------------------------------------------------
  useEffect(() => {
    let cancelled = false;
    const mount = mountRef.current;
    if (!mount) return;

    loadYouTubeApi()
      .then((YT) => {
        if (cancelled || !mountRef.current) return;

        // Autoplay is suppressed for users who ask for reduced motion; a
        // trailer starting itself is exactly the kind of movement they opt out
        // of. Everyone else gets the expected OTT behaviour.
        const prefersReducedMotion = window.matchMedia(
          "(prefers-reduced-motion: reduce)",
        ).matches;

        playerRef.current = new YT.Player(mountRef.current, {
          videoId: videoKey,
          playerVars: {
            // Custom chrome, so YouTube's own controls stay hidden.
            controls: 0,
            modestbranding: 1,
            rel: 0,
            playsinline: 1,
            iv_load_policy: 3,
            enablejsapi: 1,
            autoplay: prefersReducedMotion ? 0 : 1,
            start: Math.max(0, Math.floor(startAt)),
            origin: window.location.origin,
          },
          events: {
            onReady: (event) => {
              if (cancelled) return;
              setIsReady(true);
              setDuration(event.target.getDuration());
              setVolume(event.target.getVolume());
              setIsMuted(event.target.isMuted());
            },
            onStateChange: (event) => {
              if (cancelled) return;
              const state = event.data;
              setIsPlaying(state === YT_PLAYER_STATE.PLAYING);

              if (state === YT_PLAYER_STATE.PLAYING) {
                setHasEnded(false);
                // Duration is only reliable once playback starts.
                setDuration(event.target.getDuration());
              }
              if (state === YT_PLAYER_STATE.ENDED) {
                setHasEnded(true);
                setShowChrome(true);
                onProgressRef.current?.(
                  event.target.getDuration(),
                  event.target.getDuration(),
                );
              }
              if (state === YT_PLAYER_STATE.PAUSED) {
                setShowChrome(true);
                onProgressRef.current?.(
                  event.target.getCurrentTime(),
                  event.target.getDuration(),
                );
              }
            },
            onError: () => {
              if (!cancelled) {
                setError(
                  "This trailer cannot be played. It may have been removed or " +
                    "restricted by its owner.",
                );
              }
            },
          },
        });
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setError(
            cause instanceof Error ? cause.message : "The player failed to load.",
          );
        }
      });

    return () => {
      cancelled = true;
      try {
        playerRef.current?.destroy();
      } catch {
        // The iframe may already be gone during fast navigation.
      }
      playerRef.current = null;
    };
  }, [videoKey, startAt]);

  // --- clock + progress reporting -----------------------------------------
  useEffect(() => {
    if (!isReady) return;

    const id = window.setInterval(() => {
      const player = playerRef.current;
      if (!player) return;

      const position = player.getCurrentTime();
      const total = player.getDuration();
      setCurrentTime(position);
      if (total > 0) setDuration(total);
      setBufferedFraction(player.getVideoLoadedFraction());

      // YouTube exposes no timeupdate event, so the clock must be polled.
      if (
        onProgressRef.current &&
        player.getPlayerState() === YT_PLAYER_STATE.PLAYING &&
        Date.now() - lastReportRef.current >= PROGRESS_REPORT_MS
      ) {
        lastReportRef.current = Date.now();
        onProgressRef.current(position, total);
      }
    }, TICK_MS);

    return () => window.clearInterval(id);
  }, [isReady]);

  // --- controls ------------------------------------------------------------
  const togglePlay = useCallback(() => {
    const player = playerRef.current;
    if (!player) return;
    if (player.getPlayerState() === YT_PLAYER_STATE.PLAYING) player.pauseVideo();
    else player.playVideo();
  }, []);

  const seek = useCallback((seconds: number) => {
    const player = playerRef.current;
    if (!player) return;
    const clamped = Math.max(0, Math.min(seconds, player.getDuration() || seconds));
    player.seekTo(clamped, true);
    setCurrentTime(clamped);
  }, []);

  const nudge = useCallback(
    (delta: number) => {
      const player = playerRef.current;
      if (!player) return;
      seek(player.getCurrentTime() + delta);
    },
    [seek],
  );

  const changeVolume = useCallback((next: number) => {
    const player = playerRef.current;
    if (!player) return;
    player.setVolume(next);
    setVolume(next);
    if (next === 0) {
      player.mute();
      setIsMuted(true);
    } else if (player.isMuted()) {
      player.unMute();
      setIsMuted(false);
    }
  }, []);

  const toggleMute = useCallback(() => {
    const player = playerRef.current;
    if (!player) return;
    if (player.isMuted()) {
      player.unMute();
      setIsMuted(false);
    } else {
      player.mute();
      setIsMuted(true);
    }
  }, []);

  const toggleFullscreen = useCallback(() => {
    const shell = shellRef.current;
    if (!shell) return;
    if (document.fullscreenElement) void document.exitFullscreen();
    else void shell.requestFullscreen().catch(() => undefined);
  }, []);

  useEffect(() => {
    const onChange = () => setIsFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  // --- keyboard shortcuts --------------------------------------------------
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      // Don't hijack keys aimed at the seek/volume sliders or any input.
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable)
      ) {
        return;
      }

      switch (event.key) {
        case " ":
        case "k":
          event.preventDefault();
          togglePlay();
          break;
        case "ArrowRight":
          event.preventDefault();
          nudge(5);
          break;
        case "ArrowLeft":
          event.preventDefault();
          nudge(-5);
          break;
        case "ArrowUp":
          event.preventDefault();
          changeVolume(Math.min(100, volume + 10));
          break;
        case "ArrowDown":
          event.preventDefault();
          changeVolume(Math.max(0, volume - 10));
          break;
        case "m":
          toggleMute();
          break;
        case "f":
          toggleFullscreen();
          break;
        default:
          return;
      }
      setShowChrome(true);
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [togglePlay, nudge, changeVolume, toggleMute, toggleFullscreen, volume]);

  // --- auto-hide chrome ----------------------------------------------------
  /** Arms the idle timer. Sets no state synchronously, so it is effect-safe. */
  const scheduleHide = useCallback(() => {
    if (idleTimerRef.current) window.clearTimeout(idleTimerRef.current);
    idleTimerRef.current = window.setTimeout(() => {
      // Never hide while paused: the user is looking at the controls.
      if (playerRef.current?.getPlayerState() === YT_PLAYER_STATE.PLAYING) {
        setShowChrome(false);
      }
    }, IDLE_HIDE_MS);
  }, []);

  const wakeChrome = useCallback(() => {
    setShowChrome(true);
    scheduleHide();
  }, [scheduleHide]);

  useEffect(() => {
    // Only arm the timer here; showing the chrome is driven by real interaction.
    if (isPlaying) scheduleHide();
    return () => {
      if (idleTimerRef.current) window.clearTimeout(idleTimerRef.current);
    };
  }, [isPlaying, scheduleHide]);

  // --- render --------------------------------------------------------------
  if (error) {
    return (
      <div className="grid aspect-video w-full place-items-center rounded-xl border border-vault-800 bg-vault-900 p-8 text-center">
        <div>
          <p className="text-sm text-vault-muted">{error}</p>
          <Link
            href={`/movie/${rowIndex}`}
            className="mt-4 inline-block rounded-full border border-vault-700 px-5 py-2 text-sm font-semibold transition-colors hover:border-brand-500 hover:text-brand-300"
          >
            Back to {title}
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={shellRef}
      onMouseMove={wakeChrome}
      onFocus={wakeChrome}
      className={`group relative w-full overflow-hidden bg-black ${
        isFullscreen ? "h-screen" : "aspect-video rounded-xl"
      } ${showChrome || !isPlaying ? "cursor-auto" : "cursor-none"}`}
    >
      {/* The API replaces this node with the iframe. */}
      <div className="absolute inset-0">
        <div ref={mountRef} className="size-full" />
      </div>

      {!isReady && (
        <div className="absolute inset-0 grid place-items-center bg-vault-950">
          <div className="flex flex-col items-center gap-3">
            <div className="size-8 animate-spin rounded-full border-2 border-vault-600 border-t-brand-500" />
            <p className="text-sm text-vault-muted">Loading trailer…</p>
          </div>
        </div>
      )}

      {/* Click-to-toggle surface, sized to leave the control bar clickable. */}
      <button
        type="button"
        onClick={togglePlay}
        onDoubleClick={toggleFullscreen}
        aria-label={isPlaying ? "Pause" : "Play"}
        className="absolute inset-x-0 top-0 bottom-24 [cursor:inherit]"
        // Excluded from the tab order: the control bar's Play button is the
        // keyboard-accessible equivalent, so this would be a duplicate stop.
        tabIndex={-1}
      />

      {hasEnded && (
        <div className="absolute inset-0 grid place-items-center bg-vault-950/80">
          <button
            type="button"
            onClick={() => {
              seek(0);
              playerRef.current?.playVideo();
            }}
            className="rounded-full bg-brand-500 px-6 py-3 text-sm font-semibold text-vault-950 transition-colors hover:bg-brand-400"
          >
            Watch again
          </button>
        </div>
      )}

      <div
        className={`pointer-events-none absolute inset-0 flex flex-col justify-between transition-opacity duration-300 ${
          showChrome || !isPlaying ? "opacity-100" : "opacity-0"
        }`}
      >
        <div className="pointer-events-auto flex items-start gap-3 bg-gradient-to-b from-black/80 to-transparent p-4">
          <Link
            href={`/movie/${rowIndex}`}
            className="grid place-items-center rounded-full p-2 text-white transition-colors hover:bg-white/15"
            aria-label={`Back to ${title}`}
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
          </Link>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-white sm:text-base">
              {title}
            </p>
            <p className="text-xs text-white/60">Official trailer</p>
          </div>
        </div>

        <div className="pointer-events-auto bg-gradient-to-t from-black/85 to-transparent px-4 pb-4 pt-10">
          <PlayerControls
            isPlaying={isPlaying}
            currentTime={currentTime}
            duration={duration}
            bufferedFraction={bufferedFraction}
            volume={volume}
            isMuted={isMuted}
            isFullscreen={isFullscreen}
            onTogglePlay={togglePlay}
            onSeek={seek}
            onVolumeChange={changeVolume}
            onToggleMute={toggleMute}
            onToggleFullscreen={toggleFullscreen}
          />
        </div>
      </div>
    </div>
  );
}
