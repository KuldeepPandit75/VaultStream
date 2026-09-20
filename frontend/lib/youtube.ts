/**
 * Promise-based loader for the YouTube IFrame Player API.
 *
 * The API is loaded on demand rather than in the document head, so the catalogue
 * pages never pay for it. Types are declared locally instead of adding
 * `@types/youtube`, since only this small surface is used.
 */

export const YT_PLAYER_STATE = {
  UNSTARTED: -1,
  ENDED: 0,
  PLAYING: 1,
  PAUSED: 2,
  BUFFERING: 3,
  CUED: 5,
} as const;

export interface YouTubePlayer {
  playVideo(): void;
  pauseVideo(): void;
  seekTo(seconds: number, allowSeekAhead: boolean): void;
  getCurrentTime(): number;
  getDuration(): number;
  getPlayerState(): number;
  getVolume(): number;
  setVolume(volume: number): void;
  mute(): void;
  unMute(): void;
  isMuted(): boolean;
  getVideoLoadedFraction(): number;
  destroy(): void;
}

interface YouTubePlayerEvent {
  target: YouTubePlayer;
  data: number;
}

export interface YouTubePlayerOptions {
  videoId: string;
  playerVars?: Record<string, string | number>;
  events?: {
    onReady?: (event: YouTubePlayerEvent) => void;
    onStateChange?: (event: YouTubePlayerEvent) => void;
    onError?: (event: YouTubePlayerEvent) => void;
  };
}

interface YouTubeApi {
  Player: new (
    element: HTMLElement | string,
    options: YouTubePlayerOptions,
  ) => YouTubePlayer;
}

declare global {
  interface Window {
    YT?: YouTubeApi;
    onYouTubeIframeAPIReady?: () => void;
  }
}

const SCRIPT_SRC = "https://www.youtube.com/iframe_api";

let loader: Promise<YouTubeApi> | null = null;

/** Resolves once `window.YT.Player` is constructible. Safe to call repeatedly. */
export function loadYouTubeApi(): Promise<YouTubeApi> {
  if (typeof window === "undefined") {
    return Promise.reject(new Error("loadYouTubeApi must run in the browser"));
  }

  // Already available, e.g. a second player on the same page.
  if (window.YT?.Player) return Promise.resolve(window.YT);
  if (loader) return loader;

  loader = new Promise<YouTubeApi>((resolve, reject) => {
    const timeout = setTimeout(() => {
      reject(new Error("The YouTube player failed to load."));
    }, 15_000);

    // The API calls this global exactly once when it finishes initialising.
    const previous = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => {
      previous?.();
      clearTimeout(timeout);
      if (window.YT?.Player) resolve(window.YT);
      else reject(new Error("The YouTube player failed to initialise."));
    };

    const existing = document.querySelector<HTMLScriptElement>(
      `script[src="${SCRIPT_SRC}"]`,
    );
    if (existing) return; // another caller already injected it

    const script = document.createElement("script");
    script.src = SCRIPT_SRC;
    script.async = true;
    script.onerror = () => {
      clearTimeout(timeout);
      reject(new Error("The YouTube player could not be reached."));
    };
    document.head.appendChild(script);
  });

  // Allow a later retry if this attempt failed.
  loader.catch(() => {
    loader = null;
  });

  return loader;
}

/** mm:ss, or h:mm:ss past an hour. Returns "0:00" for unknown values. */
export function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";

  const total = Math.floor(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;

  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  }
  return `${minutes}:${String(secs).padStart(2, "0")}`;
}
