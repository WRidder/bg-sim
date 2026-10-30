/**
 * The pause time the plots follow (plan 7.9, "At a pause"), and the reaction to a pause: the inspect time
 * jumps to the pause time and the plotted series are refreshed so they end exactly there.
 */

import { useMemo } from "react";

import type { PausedInfo } from "../contracts/debug";
import { subscribePaused, useDebugStore, type DebugStatus } from "../debug/debugStore";
import { chooseSeries } from "./pauseMarker";
import { useRunStore, type ChartSeriesData } from "./runStore";

/** The pause time of the run `runId`, or null when that run is not paused. */
export function pauseTimeOf(
  debug: { status: DebugStatus; runId: string | null; pausedInfo: PausedInfo | null },
  runId: string | null,
): number | null {
  if (debug.status !== "paused" || debug.runId === null || debug.runId !== runId) {
    return null;
  }
  const t = debug.pausedInfo?.t;
  return typeof t === "number" && Number.isFinite(t) ? t : null;
}

/** The pause time while the shown run is paused, else null. */
export function usePauseTime(): number | null {
  const runId = useRunStore((state) => state.runId);
  const status = useDebugStore((state) => state.status);
  const debugRunId = useDebugStore((state) => state.runId);
  const pausedInfo = useDebugStore((state) => state.pausedInfo);
  return pauseTimeOf({ status, runId: debugRunId, pausedInfo }, runId);
}

/** The series a panel plots: its live tail or fetched data, ending at the pause time while paused. */
export function usePausedSeries(
  live: ChartSeriesData | null,
  data: ChartSeriesData | null,
): ChartSeriesData | null {
  const pauseTime = usePauseTime();
  return useMemo(() => chooseSeries(live, data, pauseTime), [live, data, pauseTime]);
}

/** What a pause does to the plots; exported for tests. */
export function applyPauseToPlots(info: PausedInfo): void {
  const store = useRunStore.getState();
  if (store.runId !== info.runId) {
    return;
  }
  store.setCursorTime(info.t);
  void store.ensureData(undefined, true);
}

let wired = false;

/** Subscribe the plots to pauses. Idempotent; runs when this module is first imported. */
export function wirePauseSync(): void {
  if (wired) {
    return;
  }
  wired = true;
  subscribePaused(applyPauseToPlots);
}

wirePauseSync();
