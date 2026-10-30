/**
 * The 3D playback at a debug pause (DEC-M4-1, plan 7.9): the head cannot go beyond the pause time. Pure
 * helpers shared by the controller (`playbackController.ts`) and the marker on the playback bar.
 */

/** `t` held at the pause time; unchanged when the run is not paused. */
export function clampToPause(t: number, pauseTime: number | null): number {
  return pauseTime !== null && t > pauseTime ? pauseTime : t;
}

/**
 * The head of a paused live run: the pause time itself (not the delayed live head), but never past the
 * newest sample that has arrived. Null while there is no sample.
 */
export function pausedHead(
  span: { readonly t0: number; readonly t1: number } | null,
  pauseTime: number,
): number | null {
  if (span === null) {
    return null;
  }
  return Math.max(span.t0, Math.min(pauseTime, span.t1));
}

/** The marker's position on a slider from `start` to `end` as a fraction in [0, 1], or null when it has none. */
export function markerFraction(pauseTime: number | null, start: number, end: number): number | null {
  if (pauseTime === null || !Number.isFinite(pauseTime) || !(end > start)) {
    return null;
  }
  return Math.min(1, Math.max(0, (pauseTime - start) / (end - start)));
}
