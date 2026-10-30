/**
 * The debug pause marker of the 3D playback bar (DEC-M4-1, plan 7.9): while the shown run is paused, the bar
 * marks the pause time on the time slider and says so, and the playback ends at that time (the controller
 * holds the head there, see `ViewerPlayback.setPauseTime`).
 */

import { useEffect, type ReactElement } from "react";

import { usePauseTime } from "../plot/pauseState";
import { markerFraction } from "./pauseClamp";
import type { ViewerPlayback } from "./playbackController";

/** Tell the playback about the pause time of the shown run (null on resume and when the run ends). */
export function usePlaybackPause(playback: ViewerPlayback | null): number | null {
  const pauseTime = usePauseTime();
  useEffect(() => {
    playback?.setPauseTime(pauseTime);
    return () => {
      playback?.setPauseTime(null);
    };
  }, [playback, pauseTime]);
  return pauseTime;
}

export interface PauseMarkerProps {
  readonly pauseTime: number | null;
  readonly start: number;
  readonly end: number;
}

/** The dashed marker on the slider track; renders nothing when not paused. */
export function PauseMarker({ pauseTime, start, end }: PauseMarkerProps): ReactElement | null {
  const fraction = markerFraction(pauseTime, start, end);
  if (pauseTime === null || fraction === null) {
    return null;
  }
  return (
    <span
      className="playback__pause-marker"
      data-testid="playback-pause-marker"
      data-pause-time={pauseTime}
      style={{ left: `${(fraction * 100).toFixed(2)}%` }}
      title={`Paused at t = ${pauseTime.toFixed(4)} s`}
      aria-hidden="true"
    />
  );
}

/** The "Paused at t" chip next to the readout; renders nothing when not paused. */
export function PauseChip({ pauseTime }: { readonly pauseTime: number | null }): ReactElement | null {
  if (pauseTime === null) {
    return null;
  }
  return (
    <span className="playback__chip playback__chip--paused" data-testid="playback-paused">
      Paused at {pauseTime.toFixed(3)} s
    </span>
  );
}
