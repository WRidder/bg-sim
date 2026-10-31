/**
 * The recorded data the dashboard's display cards read (DASHBOARD_PLAN.md).
 *
 * The same source as the plot dock and the probe windows: the live tail while a run is
 * followed, else the `/data` answer, cut at the pause time while a debug run is paused. The
 * card value is taken at the global inspect time (`cursorTime`: the plot cursor, the 3D
 * playback head, a pause) and at the latest row when there is none, so a live run shows the
 * newest value and scrubbing or playback shows the value under the cursor.
 */

import { useEffect, useMemo } from "react";

import type { ModelDashboard } from "../contracts/model";
import type { RunManifest, RunSignal } from "../contracts/run-manifest";
import { usePausedSeries } from "../plot/pauseState";
import {
  liveSeriesFor,
  useRunStore,
  type ChartSeriesData,
  type RunUiStatus,
} from "../plot/runStore";
import { dashboardSignalIds } from "./model";

export interface RunSeries {
  manifest: RunManifest | null;
  status: RunUiStatus;
  data: ChartSeriesData | null;
  signalsById: ReadonlyMap<string, RunSignal>;
  /** The inspect time, or null for "latest". */
  cursorTime: number | null;
  /** The run's time window (growing while it runs). */
  range: { t0: number; t1: number };
}

export function useRunSeries(): RunSeries {
  const manifest = useRunStore((state) => state.manifest);
  const status = useRunStore((state) => state.status);
  const progress = useRunStore((state) => state.progress);
  const fetched = useRunStore((state) => state.data);
  const view = useRunStore((state) => state.view);
  const cursorTime = useRunStore((state) => state.cursorTime);
  const liveVersion = useRunStore((state) => state.liveVersion);

  const live = useMemo(() => {
    if (status === "running") {
      return view === null ? liveSeriesFor(manifest?.id) : null;
    }
    if (status !== "done" && status !== "cancelled" && status !== "failed") {
      return null;
    }
    return fetched === null || fetched.time.length === 0 ? liveSeriesFor(manifest?.id) : null;
    // liveVersion is the live tail's change counter.
  }, [status, view, manifest?.id, liveVersion, fetched]);
  const data = usePausedSeries(live, fetched);

  const signalsById = useMemo(() => {
    const map = new Map<string, RunSignal>();
    for (const signal of manifest?.signals ?? []) {
      map.set(signal.id, signal);
    }
    return map;
  }, [manifest]);

  const range = useMemo(() => {
    const t0 = manifest?.time.t0 ?? manifest?.settings.t_start ?? 0;
    let t1 = manifest?.time.t1 ?? t0 + 1;
    if (status === "running" || status === "starting") {
      t1 = Math.max(t1, progress?.t ?? t0);
    }
    if (manifest !== null && (status === "running" || status === "paused")) {
      t1 = Math.max(t1, manifest.settings.t_end);
    }
    return { t0, t1: t1 > t0 ? t1 : t0 + 1 };
  }, [manifest, status, progress?.t]);

  return { manifest, status, data, signalsById, cursorTime, range };
}

/**
 * Register the dashboard's display signals with the run store while the dashboard is shown, so
 * `/data` and the live tail include them (like the probe windows do).
 */
export function useDashboardSignalSubscription(dashboard: ModelDashboard | undefined): void {
  const manifestId = useRunStore((state) => state.manifest?.id ?? null);
  const ids = useMemo(() => dashboardSignalIds(dashboard), [dashboard]);
  const key = ids.join(",");
  useEffect(() => {
    useRunStore.getState().setDashboardSignals(ids);
    if (manifestId !== null) {
      void useRunStore.getState().ensureData();
    }
    // `key` stands for `ids`.
  }, [key, manifestId]);
  useEffect(
    () => () => {
      useRunStore.getState().setDashboardSignals([]);
    },
    [],
  );
}
