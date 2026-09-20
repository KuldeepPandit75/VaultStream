"use client";

import { formatTime } from "@/lib/youtube";

interface PlayerControlsProps {
  isPlaying: boolean;
  currentTime: number;
  duration: number;
  bufferedFraction: number;
  volume: number;
  isMuted: boolean;
  isFullscreen: boolean;
  onTogglePlay: () => void;
  onSeek: (seconds: number) => void;
  onVolumeChange: (volume: number) => void;
  onToggleMute: () => void;
  onToggleFullscreen: () => void;
}

const Icon = {
  Play: () => (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="currentColor" className="size-6">
      <path d="M7 5v14l12-7z" />
    </svg>
  ),
  Pause: () => (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="currentColor" className="size-6">
      <path d="M7 5h4v14H7zM13 5h4v14h-4z" />
    </svg>
  ),
  VolumeHigh: () => (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="currentColor" className="size-5">
      <path d="M4 9v6h3l5 4V5L7 9H4z" />
      <path
        d="M16 8.5a4 4 0 0 1 0 7M18.5 6a7 7 0 0 1 0 12"
        stroke="currentColor"
        strokeWidth="1.6"
        fill="none"
        strokeLinecap="round"
      />
    </svg>
  ),
  VolumeMuted: () => (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="currentColor" className="size-5">
      <path d="M4 9v6h3l5 4V5L7 9H4z" />
      <path
        d="m16 9.5 5 5m0-5-5 5"
        stroke="currentColor"
        strokeWidth="1.8"
        fill="none"
        strokeLinecap="round"
      />
    </svg>
  ),
  Expand: () => (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" className="size-5">
      <path
        d="M4 9V4h5M20 15v5h-5M20 9V4h-5M4 15v5h5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  ),
  Collapse: () => (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" className="size-5">
      <path
        d="M9 4v5H4M15 20v-5h5M15 4v5h5M9 20v-5H4"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  ),
};

export function PlayerControls({
  isPlaying,
  currentTime,
  duration,
  bufferedFraction,
  volume,
  isMuted,
  isFullscreen,
  onTogglePlay,
  onSeek,
  onVolumeChange,
  onToggleMute,
  onToggleFullscreen,
}: PlayerControlsProps) {
  const progress = duration > 0 ? (currentTime / duration) * 100 : 0;

  const buttonClass =
    "grid place-items-center rounded-full p-2 text-white transition-colors hover:bg-white/15 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-400";

  return (
    <div className="space-y-2">
      {/*
        A range input rather than a custom div: it is natively keyboard
        operable (arrows, Home/End), announced correctly by screen readers, and
        works with assistive pointing devices.
      */}
      <div className="relative flex h-4 items-center">
        <div className="absolute inset-x-0 h-1 rounded-full bg-white/25">
          <div
            className="h-full rounded-full bg-white/40"
            style={{ width: `${Math.min(bufferedFraction * 100, 100)}%` }}
          />
        </div>
        <div
          className="pointer-events-none absolute left-0 h-1 rounded-full bg-brand-500"
          style={{ width: `${progress}%` }}
        />
        <input
          type="range"
          min={0}
          max={Math.max(duration, 0.1)}
          step={0.1}
          value={Math.min(currentTime, duration || 0)}
          onChange={(event) => onSeek(Number(event.target.value))}
          aria-label="Seek"
          aria-valuetext={`${formatTime(currentTime)} of ${formatTime(duration)}`}
          className="absolute inset-x-0 h-4 w-full cursor-pointer appearance-none bg-transparent [&::-webkit-slider-thumb]:size-3.5 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-brand-500 [&::-moz-range-thumb]:size-3.5 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border-0 [&::-moz-range-thumb]:bg-brand-500"
        />
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onTogglePlay}
          className={buttonClass}
          aria-label={isPlaying ? "Pause" : "Play"}
        >
          {isPlaying ? <Icon.Pause /> : <Icon.Play />}
        </button>

        <div className="group/volume flex items-center gap-1">
          <button
            type="button"
            onClick={onToggleMute}
            className={buttonClass}
            aria-label={isMuted ? "Unmute" : "Mute"}
          >
            {isMuted || volume === 0 ? <Icon.VolumeMuted /> : <Icon.VolumeHigh />}
          </button>
          <input
            type="range"
            min={0}
            max={100}
            value={isMuted ? 0 : volume}
            onChange={(event) => onVolumeChange(Number(event.target.value))}
            aria-label="Volume"
            className="w-0 cursor-pointer appearance-none opacity-0 transition-all duration-200 focus-visible:w-20 focus-visible:opacity-100 group-hover/volume:w-20 group-hover/volume:opacity-100 [&::-webkit-slider-runnable-track]:h-1 [&::-webkit-slider-runnable-track]:rounded-full [&::-webkit-slider-runnable-track]:bg-white/30 [&::-webkit-slider-thumb]:size-3 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-white"
          />
        </div>

        <p className="ml-1 font-mono text-xs tabular-nums text-white/80">
          {formatTime(currentTime)}
          <span className="text-white/40"> / {formatTime(duration)}</span>
        </p>

        <button
          type="button"
          onClick={onToggleFullscreen}
          className={`${buttonClass} ml-auto`}
          aria-label={isFullscreen ? "Exit full screen" : "Full screen"}
        >
          {isFullscreen ? <Icon.Collapse /> : <Icon.Expand />}
        </button>
      </div>
    </div>
  );
}
