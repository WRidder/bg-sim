import { useEffect, useState, type KeyboardEvent, type ReactElement } from "react";

import { PLAYBACK_SPEEDS } from "./playbackClock";
import type { ViewerPlayback, PlaybackSnapshot } from "./playbackController";
import "./playback.css";

export interface PlaybackBarProps {
  readonly playback: ViewerPlayback | null;
  readonly snapshot: PlaybackSnapshot;
  /** A message for the user about the stream, or null. */
  readonly streamError: string | null;
  /** The stream failed and the run was loaded over HTTP instead (W5.5), or absent. */
  readonly streamNote?: string | null;
  /** The model has bindings. */
  readonly hasBindings: boolean;
  /** The binding table is open. */
  readonly bindingsOpen: boolean;
  readonly onToggleBindings: () => void;
}

/** Seconds with 3 significant decimals, e.g. `0.250 s`. */
export function formatTime(t: number | null): string {
  return t === null || !Number.isFinite(t) ? "-" : `${t.toFixed(3)} s`;
}

/**
 * Space toggles play and pause while the 3D view has focus. A focused button, field or list keeps its own
 * use of the key.
 */
export function playbackKeyHandler(playback: ViewerPlayback | null): (event: KeyboardEvent<HTMLElement>) => void {
  return (event) => {
    if (playback === null || (event.key !== " " && event.key !== "Spacebar")) return;
    const el = event.target as HTMLElement;
    if (el.closest("button, input, select, textarea, a, [contenteditable=true]") !== null) return;
    event.preventDefault();
    playback.toggle();
  };
}

/**
 * Rewind, play and pause, speed, loop and the time slider of the 3D View, with the current time. Live runs
 * follow the newest data (the controls wait for the run to finish); `data-*` attributes expose the state:
 * `data-mode`, `data-playing`, `data-time` and `data-applied` (position bindings, JSON) for tests.
 */
export function PlaybackBar({ playback, snapshot, streamError, streamNote = null, hasBindings, bindingsOpen, onToggleBindings }: PlaybackBarProps): ReactElement {
  const { mode, playing, time, start, end, speed, loop, applied } = snapshot;
  // the slider shows what the user just chose until the next frame reports the new head; a controlled range
  // that waited for that frame would snap back under the thumb
  const [scrub, setScrub] = useState<number | null>(null);
  useEffect(() => {
    setScrub(null);
  }, [time]);
  const enabled = playback !== null && mode === "playback";
  const live = mode === "live";
  let note: string | null = null;
  if (streamError !== null) note = streamError;
  else if (!hasBindings) note = "No bindings yet. Open Bindings to connect a signal to the scene.";
  else if (mode === "empty") note = "Run the model to play its signals in 3D.";

  return (
    <div
      className="playback"
      role="group"
      aria-label="Playback"
      data-testid="playback-bar"
      data-mode={mode}
      data-playing={playing ? "true" : "false"}
      data-time={time === null ? "" : String(time)}
      data-applied={JSON.stringify(applied)}
    >
      <div className="playback__row">
        <button
          type="button"
          className="playback__button"
          aria-label="Rewind to start"
          disabled={!enabled}
          data-testid="playback-rewind"
          onClick={() => {
            playback?.seek(start);
          }}
        >
          <span aria-hidden="true">{"⏮"}</span>
        </button>
        <button
          type="button"
          className="playback__button playback__button--primary"
          aria-label={playing ? "Pause" : "Play"}
          aria-pressed={playing}
          disabled={!enabled}
          data-testid="playback-toggle"
          onClick={() => {
            playback?.toggle();
          }}
        >
          <span aria-hidden="true">{playing ? "⏸" : "▶"}</span>
        </button>
        <label className="playback__speed">
          <span className="playback__label">Speed</span>
          <select
            value={String(speed)}
            aria-label="Playback speed"
            disabled={!enabled}
            data-testid="playback-speed"
            onChange={(e) => {
              playback?.setSpeed(Number(e.target.value));
            }}
          >
            {PLAYBACK_SPEEDS.map((s) => (
              <option key={s} value={String(s)}>{`${String(s)}×`}</option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="playback__button"
          aria-label="Loop"
          aria-pressed={loop}
          disabled={!enabled}
          data-testid="playback-loop"
          onClick={() => {
            playback?.setLoop(!loop);
          }}
        >
          <span aria-hidden="true">{"↻"}</span>
        </button>
        <input
          type="range"
          className="playback__slider"
          aria-label="Time"
          aria-valuetext={formatTime(time)}
          min={start}
          max={end > start ? end : start + 1}
          step="any"
          value={scrub ?? time ?? start}
          disabled={!enabled}
          data-testid="playback-time"
          onChange={(e) => {
            const v = Number(e.target.value);
            setScrub(v);
            playback?.seek(v);
          }}
        />
        <span className="playback__readout" data-testid="playback-readout" aria-live="off">
          {formatTime(time)} / {formatTime(end)}
        </span>
        {live ? (
          <span className="playback__chip" data-testid="playback-live">
            Live
          </span>
        ) : null}
        <button
          type="button"
          className="playback__button playback__button--text"
          aria-pressed={bindingsOpen}
          aria-label="Bindings"
          data-testid="bindings-toggle"
          onClick={onToggleBindings}
        >
          Bindings
        </button>
      </div>
      {streamNote !== null && streamError === null ? (
        <p className="playback__note" role="status" data-testid="playback-fallback-note">
          {streamNote}
        </p>
      ) : null}
      {note !== null ? (
        <p className="playback__note" role={streamError !== null ? "alert" : undefined} data-testid="playback-note">
          {note}
        </p>
      ) : null}
    </div>
  );
}
