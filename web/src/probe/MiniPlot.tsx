/**
 * The small plot inside a probe window on the canvas.
 *
 * Deliberately simple: automatic limits (time over the run, or over the dock's
 * zoom window when one is set; values over what is drawn), no zoom, no cursor.
 * Each signal is decimated to one min/max pair per pixel column, so a long run
 * keeps its peaks at any window width. The full plot of the same signals is the
 * Auto Plot tab, which shows the probe when its window is selected.
 */

import { useEffect, useRef, useState } from "react";

import type { ChartSeriesData } from "../plot/runStore";

export interface MiniPlotSeries {
  id: string;
  label: string;
  color: string;
}

const PAD_LEFT = 44;
const PAD_RIGHT = 6;
const PAD_TOP = 4;
const PAD_BOTTOM = 14;

/** Three significant digits, without trailing zeros; exponent form at the extremes. */
export function compactNumber(value: number): string {
  if (!Number.isFinite(value)) {
    return "";
  }
  if (value === 0) {
    return "0";
  }
  const magnitude = Math.abs(value);
  if (magnitude >= 1e5 || magnitude < 1e-3) {
    return value.toExponential(1);
  }
  return String(Number(value.toPrecision(3)));
}

/** The value range of the series inside `[t0, t1]`, padded by 5 %; never empty. */
export function autoLimits(
  data: ChartSeriesData,
  ids: readonly string[],
  t0: number,
  t1: number,
): { lo: number; hi: number } {
  let lo = Infinity;
  let hi = -Infinity;
  const time = data.time;
  for (const id of ids) {
    const values = data.values[id];
    if (values === undefined) {
      continue;
    }
    for (let k = 0; k < time.length; k += 1) {
      const t = time[k] ?? NaN;
      const v = values[k] ?? NaN;
      if (t < t0 || t > t1 || !Number.isFinite(v)) {
        continue;
      }
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
  }
  if (!Number.isFinite(lo)) {
    return { lo: -1, hi: 1 };
  }
  if (hi - lo <= 1e-12 * Math.max(1, Math.abs(lo))) {
    const half = Math.abs(lo) > 0 ? Math.abs(lo) * 0.1 : 1;
    return { lo: lo - half, hi: hi + half };
  }
  const pad = 0.05 * (hi - lo);
  return { lo: lo - pad, hi: hi + pad };
}

/**
 * An SVG path for one series: per pixel column the first, min, max and last
 * value, so steps and spikes survive decimation. Gaps (NaN) break the line.
 */
export function decimatedPath(
  time: ArrayLike<number>,
  values: ArrayLike<number>,
  t0: number,
  t1: number,
  lo: number,
  hi: number,
  width: number,
  height: number,
): string {
  const columns = Math.max(1, Math.floor(width));
  const sx = width / (t1 - t0 || 1);
  const sy = height / (hi - lo || 1);
  const y = (v: number): string => (height - (v - lo) * sy).toFixed(1);
  let path = "";
  let pen = false;
  let column = -1;
  let first = 0;
  let min = 0;
  let max = 0;
  let last = 0;
  const flush = (): void => {
    if (column < 0) {
      return;
    }
    const x = (column + 0.5).toFixed(1);
    path += `${pen ? "L" : "M"}${x} ${y(first)}`;
    if (min !== first) path += `L${x} ${y(min)}`;
    if (max !== min) path += `L${x} ${y(max)}`;
    if (last !== max) path += `L${x} ${y(last)}`;
    pen = true;
  };
  for (let k = 0; k < time.length; k += 1) {
    const t = time[k] ?? NaN;
    const v = values[k] ?? NaN;
    if (!(t >= t0 && t <= t1)) {
      continue;
    }
    if (!Number.isFinite(v)) {
      flush();
      column = -1;
      pen = false;
      continue;
    }
    const c = Math.min(columns - 1, Math.floor((t - t0) * sx));
    if (c !== column) {
      flush();
      column = c;
      first = min = max = last = v;
    } else {
      if (v < min) min = v;
      if (v > max) max = v;
      last = v;
    }
  }
  flush();
  return path;
}

export function MiniPlot({
  series,
  data,
  t0,
  t1,
}: {
  series: readonly MiniPlotSeries[];
  data: ChartSeriesData | null;
  t0: number;
  t1: number;
}) {
  const boxRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const box = boxRef.current;
    if (box === null) {
      return;
    }
    const measure = (): void =>
      setSize({ width: box.clientWidth, height: box.clientHeight });
    measure();
    if (typeof ResizeObserver === "undefined") {
      return;
    }
    const observer = new ResizeObserver(measure);
    observer.observe(box);
    return () => observer.disconnect();
  }, []);

  const plotWidth = Math.max(0, size.width - PAD_LEFT - PAD_RIGHT);
  const plotHeight = Math.max(0, size.height - PAD_TOP - PAD_BOTTOM);
  const ids = series.map((entry) => entry.id);
  const limits =
    data === null ? { lo: -1, hi: 1 } : autoLimits(data, ids, t0, t1);

  return (
    <div className="mini-plot" data-testid="mini-plot">
      <div className="mini-plot__area" ref={boxRef}>
        {plotWidth > 0 && plotHeight > 0 ? (
          <svg
            width={size.width}
            height={size.height}
            className="mini-plot__svg"
            aria-hidden="true"
          >
            <g transform={`translate(${PAD_LEFT} ${PAD_TOP})`}>
              <rect
                className="mini-plot__frame"
                width={plotWidth}
                height={plotHeight}
              />
              {limits.lo < 0 && limits.hi > 0 ? (
                <line
                  className="mini-plot__zero"
                  x1={0}
                  x2={plotWidth}
                  y1={
                    plotHeight -
                    ((0 - limits.lo) / (limits.hi - limits.lo)) * plotHeight
                  }
                  y2={
                    plotHeight -
                    ((0 - limits.lo) / (limits.hi - limits.lo)) * plotHeight
                  }
                />
              ) : null}
              {data === null
                ? null
                : series.map((entry) => {
                    const values = data.values[entry.id];
                    if (values === undefined) {
                      return null;
                    }
                    return (
                      <path
                        key={entry.id}
                        d={decimatedPath(
                          data.time,
                          values,
                          t0,
                          t1,
                          limits.lo,
                          limits.hi,
                          plotWidth,
                          plotHeight,
                        )}
                        stroke={entry.color}
                        data-signal={entry.id}
                        className="mini-plot__line"
                      />
                    );
                  })}
            </g>
            <text
              className="mini-plot__tick"
              x={PAD_LEFT - 3}
              y={PAD_TOP + 8}
              textAnchor="end"
            >
              {compactNumber(limits.hi)}
            </text>
            <text
              className="mini-plot__tick"
              x={PAD_LEFT - 3}
              y={PAD_TOP + plotHeight}
              textAnchor="end"
            >
              {compactNumber(limits.lo)}
            </text>
            <text className="mini-plot__tick" x={PAD_LEFT} y={size.height - 2}>
              {compactNumber(t0)} s
            </text>
            <text
              className="mini-plot__tick"
              x={PAD_LEFT + plotWidth}
              y={size.height - 2}
              textAnchor="end"
            >
              {compactNumber(t1)} s
            </text>
          </svg>
        ) : null}
      </div>
      <ul className="mini-plot__legend">
        {series.map((entry) => (
          <li key={entry.id} title={entry.id}>
            <span
              className="mini-plot__swatch"
              style={{ background: entry.color }}
            />
            {entry.label}
          </li>
        ))}
      </ul>
    </div>
  );
}
