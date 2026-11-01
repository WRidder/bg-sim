import { useEffect, useState, type KeyboardEvent, type ReactElement } from "react";

import { useRunStore } from "../plot/runStore";
import { useDocumentStore } from "../state/documentStore";
import { PauseChip, PauseMarker, usePlaybackPause } from "./pauseMarker";
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

/** A model is open and no run is starting or running: Play may start one. */
function canStartRun(): boolean {
  const run = useRunStore.getState();
  const doc = useDocumentStore.getState();
  return doc.doc !== null && doc.project !== null && run.status !== "starting" && run.status !== "running" && !run.stopping;
}

/**
 * Play with nothing to play yet starts a run (as Run in the top bar); the view follows it live and plays it
 * from the start once it is done. Returns whether a run was started.
 */
export function startRunFromPlayback(playback: ViewerPlayback | null = null): boolean {
  if (!canStartRun()) return false;
  playback?.playWhenDone();
  void useRunStore.getState().startRun();
  return true;
}

/**
 * Space toggles play and pause while the 3D view has focus, or starts a run when there is none to play.
 * A focused button, field or list keeps its own use of the key.
 */
export function playbackKeyHandler(playback: ViewerPlayback | null): (event: KeyboardEvent<HTMLElement>) => void {
  return (event) => {
    if (playback === null || (event.key !== " " && event.key !== "Spacebar")) return;
    const el = event.target as HTMLElement;
    if (el.closest("button, input, select, textarea, a, [contenteditable=true]") !== null) return;
    event.preventDefault();
    if (playback.snapshot().mode === "empty") startRunFromPlayback(playback);
    else playback.toggle();
  };
}

/**
 * Rewind, play and pause, speed, loop and the time slider of the 3D View, with the current time. Live runs
 * follow the newest data (the controls wait for the run to finish); `data-*` attributes expose the state:
 * `data-mode`, `data-playing`, `data-time` and `data-applied` (position bindings, JSON) for tests.
 */
export function PlaybackBar({ playback, snapshot, streamError, streamNote = null, hasBindings, bindingsOpen, onToggleBindings }: PlaybackBarProps): ReactElement {
  const { mode, playing, time, start, end, speed, loop, applied } = snapshot;
  // M4 debug (DEC-M4-1): at a pause the bar marks the pause time and the playback ends there
  const pauseTime = usePlaybackPause(playback);
  // the slider shows what the user just chose until the next frame reports the new head; a controlled range
  // that waited for that frame would snap back under the thumb
  const [scrub, setScrub] = useState<number | null>(null);
  useEffect(() => {
    setScrub(null);
  }, [time]);
  const enabled = playback !== null && mode === "playback";
  // nothing to play yet: Play runs the model
  const runnable = useRunStore((r) => r.status !== "starting" && r.status !== "running" && !r.stopping);
  const hasModel = useDocumentStore((d) => d.doc !== null && d.project !== null);
  const playRuns = mode === "empty" && runnable && hasModel;
  const live = mode === "live";
  let note: string | null = null;
  if (streamError !== null) note = streamError;
  else if (!hasBindings) note = "No bindings yet. Open Bindings to connect a signal to the scene.";
  else if (mode === "empty") note = "Press Play to run the model: the view follows the run and plays it back when it is done.";

  return (
    <div
      className="playback"
      role="group"
      aria-label="Playback"
      data-testid="playback-bar"
      data-mode={mode}
      data-playing={playing ? "true" : "false"}
      data-time={time === null ? "" : String(time)}
      data-pause-time={pauseTime === null ? "" : String(pauseTime)}
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
          disabled={!enabled && !playRuns}
          data-testid="playback-toggle"
          data-runs={playRuns ? "true" : "false"}
          title={playRuns ? "Run the model and follow it in 3D (Space)" : undefined}
          onClick={() => {
            if (playRuns) startRunFromPlayback(playback);
            else playback?.toggle();
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
        <div className="playback__track">
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
          <PauseMarker pauseTime={pauseTime} start={start} end={end} />
        </div>
        <span className="playback__readout" data-testid="playback-readout" aria-live="off">
          {formatTime(time)} / {formatTime(end)}
        </span>
        <PauseChip pauseTime={pauseTime} />
        {live && pauseTime === null ? (
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
