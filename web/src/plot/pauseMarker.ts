/**
 * Pause-aware plots (plan 7.9, "At a pause"): the vertical "paused" marker, the clipping of the shown series
 * at the pause time, and the choice between the live tail and the fetched `/data` while paused.
 *
 * The marker is a uPlot plugin that draws a dashed line and a label at the pause time with the warning token
 * (`--color-warning-text`), so it cannot be mistaken for the plot cursor. It also publishes the pause time and
 * its x position on the chart host (`data-pause-time`, `data-pause-x`) for tests, and removes both on resume.
 */

import type uPlot from "uplot";

import type { ChartSeriesData } from "./runStore";

const FALLBACK_COLOR = "#b54708";
const LABEL = "paused";

/** Tolerance when comparing sample times to the pause time (s). */
const TIME_EPS = 1e-9;

/** Index after the last sample with time <= `t` (binary search; `time` ascending). */
export function countUpTo(time: ArrayLike<number>, t: number): number {
  let lo = 0;
  let hi = time.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if ((time[mid] ?? Number.POSITIVE_INFINITY) <= t + TIME_EPS) {
      lo = mid + 1;
    } else {
      hi = mid;
    }
  }
  return lo;
}

/**
 * The series up to the pause time. A paused run writes nothing further, so this only matters for a stale
 * answer (a tail or a fetch that ran past the pause on an earlier resume). Returns the same object when
 * nothing is cut.
 */
export function clipSeriesAtPause(
  series: ChartSeriesData | null,
  pauseTime: number | null,
): ChartSeriesData | null {
  if (series === null || pauseTime === null) {
    return series;
  }
  const count = countUpTo(series.time, pauseTime);
  if (count >= series.time.length) {
    return series;
  }
  const values: Record<string, ArrayLike<number>> = {};
  for (const [id, column] of Object.entries(series.values)) {
    values[id] = Array.prototype.slice.call(column, 0, count) as number[];
  }
  return { time: Array.prototype.slice.call(series.time, 0, count) as number[], values };
}

function reaches(series: ChartSeriesData | null, t: number): boolean {
  if (series === null || series.time.length === 0) {
    return false;
  }
  return (series.time[series.time.length - 1] ?? Number.NEGATIVE_INFINITY) >= t - TIME_EPS;
}

/**
 * The series to plot. Not paused: the live tail when there is one, else the fetched data. Paused: the
 * fetched `/data` (which the pause refresh requested and which ends at the pause row) once it reaches the
 * pause time, otherwise the live tail; both are clipped at the pause time.
 */
export function chooseSeries(
  live: ChartSeriesData | null,
  data: ChartSeriesData | null,
  pauseTime: number | null,
): ChartSeriesData | null {
  if (pauseTime === null) {
    return live ?? data;
  }
  const chosen = reaches(data, pauseTime) ? data : reaches(live, pauseTime) ? live : (live ?? data);
  return clipSeriesAtPause(chosen, pauseTime);
}

export interface PauseMarkerOptions {
  /** The pause time in seconds, or null while the run is not paused. */
  readonly getTime: () => number | null;
}

function markerColor(u: uPlot): string {
  const value = getComputedStyle(u.root).getPropertyValue("--color-warning-text").trim();
  return value.length > 0 ? value : FALLBACK_COLOR;
}

function publish(host: HTMLElement | null, time: number | null, x: number | null): void {
  if (host === null) {
    return;
  }
  if (time === null) {
    delete host.dataset.pauseTime;
    delete host.dataset.pauseX;
    return;
  }
  host.dataset.pauseTime = String(time);
  if (x === null) {
    delete host.dataset.pauseX;
  } else {
    host.dataset.pauseX = x.toFixed(1);
  }
}

/** The uPlot plugin that draws the pause marker; call `chart.redraw()` after the pause time changes. */
export function pauseMarkerPlugin(options: PauseMarkerOptions): uPlot.Plugin {
  return {
    hooks: {
      draw: (u: uPlot) => {
        const host = u.root.parentElement;
        const time = options.getTime();
        if (time === null) {
          publish(host, null, null);
          return;
        }
        const dpr = typeof window === "undefined" ? 1 : window.devicePixelRatio || 1;
        const css = u.valToPos(time, "x", false);
        const x = u.valToPos(time, "x", true);
        const { left, top, width, height } = u.bbox;
        const inside = Number.isFinite(x) && x >= left - 1 && x <= left + width + 1;
        publish(host, time, inside && Number.isFinite(css) ? css : null);
        if (!inside) {
          return;
        }
        const ctx = u.ctx;
        const color = markerColor(u);
        ctx.save();
        ctx.beginPath();
        ctx.rect(left - 1, top, width + 2, height);
        ctx.clip();
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.5 * dpr;
        ctx.setLineDash([6 * dpr, 4 * dpr]);
        ctx.beginPath();
        ctx.moveTo(x, top);
        ctx.lineTo(x, top + height);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = color;
        ctx.font = `${11 * dpr}px "Inter Variable", "Inter", system-ui, sans-serif`;
        ctx.textBaseline = "top";
        const labelWidth = ctx.measureText(LABEL).width;
        const flip = x + 4 * dpr + labelWidth > left + width;
        ctx.textAlign = flip ? "right" : "left";
        ctx.fillText(LABEL, flip ? x - 4 * dpr : x + 4 * dpr, top + 2 * dpr);
        ctx.restore();
      },
    },
  };
}
