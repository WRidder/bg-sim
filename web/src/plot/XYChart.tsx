/**
 * An XY plot: every listed signal drawn against one x signal, sample by sample (a phase portrait,
 * a Lissajous figure, a force-deflection loop). The time panels use `UPlotChart`; this chart is
 * the same uPlot, in its `mode: 2` (one `[xs, ys]` pair per series) with its own path builder.
 *
 * Data: the rows of the shared time window (the time zoom of the other panels, or the whole run),
 * from whole recorded rows (the run store requests raw `/data` and an exact live tail while an XY
 * plot is open). The path builder thins them in screen space (`thinXYPath`), so the line stays
 * sharp at full resolution at any zoom and while a run streams.
 *
 * Interactions: drag a box to zoom (both axes), the wheel zooms about the pointer, double-click
 * fits the data again. The zoom is this panel's own: the x axis is not time, so it does not join
 * the shared time zoom. Hovering moves the global inspect time to the nearest drawn sample; every
 * series marks its point at the inspect time (at the newest sample when there is none), and the
 * legend shows t, x and each y there. `equalAspect` keeps one unit equally long on both axes.
 */

import { useEffect, useRef, useState } from "react";
import "./uplotSetup";
import uPlot from "uplot";

import { formatCursorTime, formatLegendValue } from "./format";
import type { ChartSeriesData } from "./runStore";
import type { SeriesWindow } from "./runCache";
import type { ChartSeriesConfig } from "./UPlotChart";
import {
  axisMap,
  equalAspectRanges,
  extendExtent,
  nearestDrawnPoint,
  paddedRange,
  pointAtTime,
  thinXYPath,
  windowIndices,
  xyAxisLabel,
  type Extent,
  type ThinnedPath,
} from "./xy";

/** Default height of an XY chart in the dock, in CSS pixels (a phase portrait wants room). */
export const XY_CHART_HEIGHT = 240;
const MIN_CHART_WIDTH = 240;
const MIN_CHART_HEIGHT = 120;
const AXIS_COLOR = "#8a95a3";
const GRID_COLOR = "rgba(128, 140, 156, 0.22)";
const AXIS_FONT = '11px "Inter Variable", "Inter", system-ui, sans-serif';

export interface XYChartProps {
  /** The signal on the horizontal axis. */
  xSignal: ChartSeriesConfig;
  /** The signals drawn against it (each on the y or y2 scale). */
  signals: ChartSeriesConfig[];
  /** Pinned-run overlays of the same signals (dashed). */
  compareSignals: ChartSeriesConfig[];
  data: ChartSeriesData | null;
  compare: ChartSeriesData | null;
  /** The shared time window; null is the whole run. */
  view: SeriesWindow | null;
  cursorTime: number | null;
  equalAspect: boolean;
  onCursorTime: (time: number | null) => void;
}

interface SeriesSource {
  table: ChartSeriesData | null;
  range: [number, number] | null;
  xs: ArrayLike<number> | undefined;
  ys: ArrayLike<number> | undefined;
}

function seriesKey(xSignal: ChartSeriesConfig, signals: readonly ChartSeriesConfig[]): string {
  return [
    `x=${xSignal.id}:${xSignal.unit ?? ""}`,
    ...signals.map((s) => `${s.id}:${s.axis}:${s.compare ? "p" : "c"}:${s.unit ?? ""}:${s.color}`),
  ].join("|");
}

/** The x/y columns and the window rows of every series (current run first, then pinned). */
function seriesSources(
  xId: string,
  signals: readonly ChartSeriesConfig[],
  data: ChartSeriesData | null,
  compare: ChartSeriesData | null,
  view: SeriesWindow | null,
): SeriesSource[] {
  const mainRange = data === null ? null : windowIndices(data.time, view);
  const compareRange = compare === null ? null : windowIndices(compare.time, view);
  return signals.map((signal) => {
    const table = signal.compare ? compare : data;
    return {
      table,
      range: signal.compare ? compareRange : mainRange,
      xs: table?.values[xId],
      ys: table?.values[signal.id],
    };
  });
}

/** Fitted (padded, optionally equal-aspect) ranges of the x, y and y2 scales. */
function fittedRanges(
  sources: readonly SeriesSource[],
  signals: readonly ChartSeriesConfig[],
  equalAspect: boolean,
  width: number,
  height: number,
): { x: Extent; y: Extent; y2: Extent } {
  let x: Extent | null = null;
  let y: Extent | null = null;
  let y2: Extent | null = null;
  sources.forEach((source, index) => {
    if (source.range === null || source.xs === undefined || source.ys === undefined) {
      return;
    }
    const [i0, i1] = source.range;
    x = extendExtent(x, source.xs, i0, i1);
    if (signals[index]?.axis === "y2") {
      y2 = extendExtent(y2, source.ys, i0, i1);
    } else {
      y = extendExtent(y, source.ys, i0, i1);
    }
  });
  let rx = paddedRange(x);
  let ry = paddedRange(y);
  if (equalAspect) {
    ({ x: rx, y: ry } = equalAspectRanges(rx, ry, width, height));
  }
  return { x: rx, y: ry, y2: paddedRange(y2) };
}

export function XYChart({
  xSignal,
  signals,
  compareSignals,
  data,
  compare,
  view,
  cursorTime,
  equalAspect,
  onCursorTime,
}: XYChartProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<uPlot | null>(null);
  const markersRef = useRef<HTMLDivElement[]>([]);
  const pathsRef = useRef<(ThinnedPath | null)[]>([]);
  const sourcesRef = useRef<SeriesSource[]>([]);
  const zoomedRef = useRef(false);
  const programmaticRef = useRef(0);
  const renderSeqRef = useRef(0);
  const allSignals = [...signals, ...compareSignals];
  const allSignalsRef = useRef(allSignals);
  allSignalsRef.current = allSignals;
  const cursorTimeRef = useRef(cursorTime);
  cursorTimeRef.current = cursorTime;
  const equalAspectRef = useRef(equalAspect);
  equalAspectRef.current = equalAspect;
  const onCursorTimeRef = useRef(onCursorTime);
  onCursorTimeRef.current = onCursorTime;
  const [chartEpoch, setChartEpoch] = useState(0);
  const [zoomed, setZoomed] = useState(false);

  const key = seriesKey(xSignal, allSignals);
  const hasRightAxis = allSignals.some((signal) => signal.axis === "y2");

  // ------------------------------------------------------------- helpers on the live chart
  const placeMarkers = (chart: uPlot): void => {
    const markers = markersRef.current;
    const sources = sourcesRef.current;
    const list = allSignalsRef.current;
    let shownT: number | null = null;
    markers.forEach((marker, index) => {
      const source = sources[index];
      const signal = list[index];
      const point =
        source === undefined || signal === undefined || source.table === null || source.range === null ||
        source.xs === undefined || source.ys === undefined
          ? null
          : pointAtTime(source.table.time, source.xs, source.ys, cursorTimeRef.current, source.range[0], source.range[1]);
      if (point === null || signal === undefined) {
        marker.style.display = "none";
        return;
      }
      const left = chart.valToPos(point.x, "x");
      const top = chart.valToPos(point.y, signal.axis);
      const width = chart.over.clientWidth;
      const height = chart.over.clientHeight;
      if (!Number.isFinite(left) || !Number.isFinite(top) || left < 0 || top < 0 || left > width || top > height) {
        marker.style.display = "none";
        return;
      }
      marker.style.display = "block";
      marker.style.transform = `translate(${left}px, ${top}px)`;
      if (!signal.compare && shownT === null) {
        shownT = point.t;
      }
    });
    const host = hostRef.current;
    if (host !== null) {
      host.dataset.markerT = shownT === null ? "" : String(shownT);
    }
  };

  /** Set the fitted ranges; call inside `chart.batch` (one commit, one draw). */
  const applyFit = (chart: uPlot): void => {
    const ranges = fittedRanges(
      sourcesRef.current,
      allSignalsRef.current,
      equalAspectRef.current,
      chart.over.clientWidth,
      chart.over.clientHeight,
    );
    chart.setScale("x", ranges.x);
    chart.setScale("y", ranges.y);
    if (chart.scales.y2 !== undefined) {
      chart.setScale("y2", ranges.y2);
    }
  };
  const fit = (chart: uPlot): void => {
    programmaticRef.current += 1;
    chart.batch(() => applyFit(chart));
    programmaticRef.current -= 1;
  };

  // ------------------------------------------------------------------------- chart create
  useEffect(() => {
    const host = hostRef.current;
    if (host === null) {
      return;
    }
    const size = (): { width: number; height: number } => ({
      width: Math.max(MIN_CHART_WIDTH, Math.floor(host.clientWidth || 480)),
      height: Math.max(MIN_CHART_HEIGHT, Math.floor(host.clientHeight || XY_CHART_HEIGHT)),
    });
    const list = allSignalsRef.current;

    const buildPath: uPlot.Series.PathBuilder = (u, seriesIdx) => {
      const index = seriesIdx - 1;
      const source = sourcesRef.current[index];
      const signal = allSignalsRef.current[index];
      const xScale = u.scales.x;
      const yScale = signal === undefined ? undefined : u.scales[signal.axis];
      if (
        source === undefined || signal === undefined || source.range === null || source.xs === undefined ||
        source.ys === undefined || yScale === undefined || typeof xScale.min !== "number" ||
        typeof xScale.max !== "number" || typeof yScale.min !== "number" || typeof yScale.max !== "number"
      ) {
        pathsRef.current[index] = null;
        return null;
      }
      const { left, top, width, height } = u.bbox;
      const thinned = thinXYPath(
        source.xs,
        source.ys,
        source.range[0],
        source.range[1],
        axisMap(xScale.min, xScale.max, left, width, false),
        axisMap(yScale.min, yScale.max, top, height, true),
        0.5,
      );
      pathsRef.current[index] = thinned;
      const stroke = new Path2D();
      for (let k = 0; k < thinned.count; k += 1) {
        const px = thinned.px[k] as number;
        const py = thinned.py[k] as number;
        if (thinned.breaks[k] === 1) {
          stroke.moveTo(px, py);
          // A lone sample (a run of one point) still shows as a dot-sized segment.
          const next = k + 1 < thinned.count ? thinned.breaks[k + 1] : 1;
          if (next === 1) stroke.lineTo(px + 0.01, py);
        } else {
          stroke.lineTo(px, py);
        }
      }
      return { stroke, fill: null, clip: null, flags: 0 } as uPlot.Series.Paths;
    };

    const series: uPlot.Series[] = [{}];
    for (const signal of list) {
      series.push({
        label: signal.compare ? `${signal.label} (pinned)` : signal.label,
        stroke: signal.color,
        width: signal.compare ? 1 : 1.5,
        dash: signal.compare ? [5, 3] : undefined,
        alpha: signal.compare ? 0.8 : 1,
        facets: [
          { scale: "x", auto: false },
          { scale: signal.axis, auto: false },
        ],
        paths: buildPath,
        points: { show: false },
      });
    }
    const current = list.filter((signal) => !signal.compare);
    const axes: uPlot.Axis[] = [
      {
        scale: "x",
        side: 2,
        size: 24,
        stroke: AXIS_COLOR,
        font: AXIS_FONT,
        label: xyAxisLabel([xSignal], "x"),
        labelSize: 14,
        labelFont: AXIS_FONT,
        grid: { stroke: GRID_COLOR, width: 1 },
        ticks: { stroke: AXIS_COLOR, width: 1, size: 4 },
      },
      {
        scale: "y",
        side: 3,
        size: 48,
        stroke: AXIS_COLOR,
        font: AXIS_FONT,
        label: xyAxisLabel(current.filter((signal) => signal.axis === "y"), "value"),
        labelSize: 14,
        labelFont: AXIS_FONT,
        grid: { stroke: GRID_COLOR, width: 1 },
        ticks: { stroke: AXIS_COLOR, width: 1, size: 4 },
      },
    ];
    const scales: uPlot.Scales = {
      x: { time: false, auto: false },
      y: { auto: false },
    };
    if (hasRightAxis) {
      scales.y2 = { auto: false };
      axes.push({
        scale: "y2",
        side: 1,
        size: 48,
        stroke: AXIS_COLOR,
        font: AXIS_FONT,
        label: xyAxisLabel(current.filter((signal) => signal.axis === "y2"), "—"),
        labelSize: 14,
        labelFont: AXIS_FONT,
        grid: { show: false },
        ticks: { stroke: AXIS_COLOR, width: 1, size: 4 },
      });
    }

    let equalizeQueued = false;
    const options: uPlot.Options = {
      mode: 2,
      ...size(),
      padding: [8, 8, 0, 0],
      series,
      axes,
      scales,
      legend: { show: false },
      cursor: {
        show: true,
        x: false,
        y: false,
        points: { show: false },
        drag: { setScale: true, x: true, y: true, dist: 6 },
        dataIdx: () => null as unknown as number,
      },
      hooks: {
        // uPlot invalidates mode-2 paths only when the y scale changes; rebuild them on every draw
        // (draws follow data, zoom and resize, not pointer moves).
        drawClear: [
          (u) => {
            u.series.forEach((s, i) => {
              if (i > 0) {
                (s as { _paths?: unknown })._paths = null;
              }
            });
          },
        ],
        draw: [(u) => placeMarkers(u)],
        setScale: [
          (u) => {
            if (programmaticRef.current > 0) {
              return;
            }
            // A drag box or the wheel: this panel keeps its own zoom until a double-click.
            if (!zoomedRef.current) {
              zoomedRef.current = true;
              setZoomed(true);
            }
            if (equalAspectRef.current && !equalizeQueued) {
              equalizeQueued = true;
              queueMicrotask(() => {
                equalizeQueued = false;
                const xs = u.scales.x;
                const ys = u.scales.y;
                if (typeof xs.min !== "number" || typeof xs.max !== "number" || typeof ys.min !== "number" || typeof ys.max !== "number") {
                  return;
                }
                const ranges = equalAspectRanges(
                  { min: xs.min, max: xs.max },
                  { min: ys.min, max: ys.max },
                  u.over.clientWidth,
                  u.over.clientHeight,
                );
                programmaticRef.current += 1;
                u.batch(() => {
                  u.setScale("x", ranges.x);
                  u.setScale("y", ranges.y);
                });
                programmaticRef.current -= 1;
              });
            }
          },
        ],
      },
    };

    const detachedHost = typeof document !== "undefined" && host.ownerDocument !== document;
    const target = (
      detachedHost
        ? (chart: uPlot, init: () => void) => {
            host.appendChild(chart.root);
            init();
          }
        : host
    ) as unknown as HTMLElement;
    const empty = [null, ...list.map(() => [[], []])] as unknown as uPlot.AlignedData;
    const chart = new uPlot(options, empty, target);
    chartRef.current = chart;
    zoomedRef.current = false;
    setZoomed(false);

    markersRef.current = list.map((signal) => {
      const marker = host.ownerDocument.createElement("div");
      marker.className = `plot-xy__marker${signal.compare ? " plot-xy__marker--compare" : ""}`;
      marker.style.borderColor = signal.color;
      marker.style.display = "none";
      marker.setAttribute("aria-hidden", "true");
      marker.dataset.testid = "xy-marker";
      chart.over.appendChild(marker);
      return marker;
    });

    // Hover: the nearest drawn sample of the current run sets the global inspect time.
    let frame: number | null = null;
    let pointer: { x: number; y: number } | null = null;
    const report = (): void => {
      frame = null;
      const live = chartRef.current;
      if (live === null || pointer === null) {
        return;
      }
      const ratio = uPlot.pxRatio || 1;
      const x = live.bbox.left + pointer.x * ratio;
      const y = live.bbox.top + pointer.y * ratio;
      const candidates = pathsRef.current.map((path, index) =>
        allSignalsRef.current[index]?.compare === true ? null : path,
      );
      const nearest = nearestDrawnPoint(candidates, x, y);
      if (nearest === null) {
        return;
      }
      const source = sourcesRef.current[nearest.path];
      const row = pathsRef.current[nearest.path]?.rows[nearest.point];
      const time = row === undefined ? undefined : source?.table?.time[row];
      if (typeof time === "number" && Number.isFinite(time)) {
        onCursorTimeRef.current(time);
      }
    };
    const onMouseMove = (event: MouseEvent): void => {
      const rect = chart.over.getBoundingClientRect();
      pointer = { x: event.clientX - rect.left, y: event.clientY - rect.top };
      if (frame === null) {
        frame = requestAnimationFrame(report);
      }
    };
    const onDoubleClick = (): void => {
      chart.setSelect({ left: 0, top: 0, width: 0, height: 0 }, false);
      zoomedRef.current = false;
      setZoomed(false);
      fit(chart);
    };
    const onWheel = (event: WheelEvent): void => {
      const xs = chart.scales.x;
      const ys = chart.scales.y;
      if (typeof xs.min !== "number" || typeof xs.max !== "number" || typeof ys.min !== "number" || typeof ys.max !== "number") {
        return;
      }
      event.preventDefault();
      const rect = chart.over.getBoundingClientRect();
      const fx = chart.posToVal(event.clientX - rect.left, "x");
      const delta = event.deltaMode === 1 ? event.deltaY * 16 : event.deltaY;
      const factor = Math.exp(Math.max(-4, Math.min(4, delta * 0.0015)));
      const scaled = (min: number, max: number, focus: number): Extent => ({
        min: focus - (focus - min) * factor,
        max: focus + (max - focus) * factor,
      });
      zoomedRef.current = true;
      setZoomed(true);
      programmaticRef.current += 1;
      chart.batch(() => {
        chart.setScale("x", scaled(xs.min as number, xs.max as number, fx));
        for (const scaleKey of ["y", "y2"]) {
          const sc = chart.scales[scaleKey];
          if (sc !== undefined && typeof sc.min === "number" && typeof sc.max === "number") {
            chart.setScale(scaleKey, scaled(sc.min, sc.max, chart.posToVal(event.clientY - rect.top, scaleKey)));
          }
        }
      });
      programmaticRef.current -= 1;
    };
    chart.over.addEventListener("mousemove", onMouseMove);
    chart.over.addEventListener("dblclick", onDoubleClick);
    chart.over.addEventListener("wheel", onWheel, { passive: false });

    const observer = new ResizeObserver(() => {
      const next = size();
      if (next.width === chart.width && next.height === chart.height) {
        return;
      }
      chart.setSize(next);
      if (!zoomedRef.current) {
        // The plot area changed: an equal-aspect fit depends on it.
        queueMicrotask(() => {
          if (chartRef.current === chart) fit(chart);
        });
      }
    });
    observer.observe(host);
    setChartEpoch((epoch) => epoch + 1);

    return () => {
      chart.over.removeEventListener("mousemove", onMouseMove);
      chart.over.removeEventListener("dblclick", onDoubleClick);
      chart.over.removeEventListener("wheel", onWheel);
      if (frame !== null) {
        cancelAnimationFrame(frame);
      }
      observer.disconnect();
      chart.destroy();
      markersRef.current = [];
      pathsRef.current = [];
      if (chartRef.current === chart) {
        chartRef.current = null;
      }
    };
    // `key` covers the series list and the x signal; the callbacks read refs.
  }, [key, hasRightAxis]);

  // -------------------------------------------------------------------------------- data
  useEffect(() => {
    const chart = chartRef.current;
    const host = hostRef.current;
    if (chart === null || host === null) {
      return;
    }
    const list = allSignalsRef.current;
    const sources = seriesSources(xSignal.id, list, data, compare, view);
    sourcesRef.current = sources;
    const table = [
      null,
      ...sources.map((source) => [source.xs ?? [], source.ys ?? []]),
    ] as unknown as uPlot.AlignedData;
    const seq = renderSeqRef.current + 1;
    renderSeqRef.current = seq;
    const started = performance.now();
    programmaticRef.current += 1;
    chart.batch(() => {
      chart.setData(table, false);
      if (!zoomedRef.current) {
        applyFit(chart);
      }
    });
    programmaticRef.current -= 1;
    const rows = sources.find((source, index) => !list[index]?.compare && source.range !== null)?.range;
    // The draw runs in uPlot's commit microtask; this one is queued after it.
    queueMicrotask(() => {
      if (renderSeqRef.current !== seq) {
        return;
      }
      const drawn = pathsRef.current.reduce((sum, path) => sum + (path?.count ?? 0), 0);
      host.dataset.renderMs = (performance.now() - started).toFixed(2);
      host.dataset.renderSeq = String(seq);
      host.dataset.points = String(rows === undefined || rows === null ? 0 : rows[1] - rows[0] + 1);
      host.dataset.drawnPoints = String(drawn);
    });
  }, [data, compare, view, key, chartEpoch, equalAspect, xSignal.id]);

  // ----------------------------------------------------------------------- inspect cursor
  useEffect(() => {
    const chart = chartRef.current;
    if (chart !== null) {
      placeMarkers(chart);
    }
    // placeMarkers reads refs only.
  }, [cursorTime, chartEpoch]);

  // ------------------------------------------------------------------------------ legend
  const sources = seriesSources(xSignal.id, allSignals, data, compare, view);
  const points = sources.map((source) =>
    source.table === null || source.range === null || source.xs === undefined || source.ys === undefined
      ? null
      : pointAtTime(source.table.time, source.xs, source.ys, cursorTime, source.range[0], source.range[1]),
  );
  const head = points.find((point, index) => point !== null && allSignals[index]?.compare !== true) ?? null;

  return (
    <div className="plot-chart__body plot-xy">
      <div
        className="plot-chart__canvas plot-xy__canvas"
        ref={hostRef}
        data-testid="plot-chart"
        data-mode="xy"
        data-x-signal={xSignal.id}
        data-series-count={allSignals.length}
        data-compare-count={compareSignals.length}
        data-equal-aspect={equalAspect ? "true" : "false"}
        data-zoomed={zoomed ? "true" : "false"}
        role="img"
        aria-label={`XY plot of ${signals.map((signal) => signal.id).join(", ")} against ${xSignal.id}`}
      />
      <div className="plot-legend" data-testid="plot-legend">
        <span className="plot-legend__time" data-testid="legend-time">
          {head === null ? "t —" : `t = ${formatCursorTime(head.t)}`}
        </span>
        <ul className="plot-legend__items">
          <li
            className="plot-legend__item plot-legend__item--x"
            data-testid="legend-x"
            data-signal-id={xSignal.id}
            title={`${xSignal.id} (x axis)`}
          >
            <span className="plot-legend__axis">x</span>
            <span className="plot-legend__label">{xSignal.label}</span>
            <span className="plot-legend__value">
              {formatLegendValue(head?.x ?? null, xSignal.unit, xSignal.type)}
            </span>
          </li>
          {allSignals.map((signal, index) => (
            <li
              className={`plot-legend__item${signal.compare ? " plot-legend__item--compare" : ""}`}
              key={`${signal.compare ? "p" : "c"}:${signal.id}`}
              data-testid="legend-item"
              data-signal-id={signal.id}
              data-compare={signal.compare ? "true" : "false"}
              title={`${signal.id} against ${xSignal.id}${signal.compare ? " (pinned run)" : ""}`}
            >
              <span
                className={`plot-legend__swatch${signal.compare ? " plot-legend__swatch--dashed" : ""}`}
                style={{ color: signal.color }}
                aria-hidden="true"
              />
              <span className="plot-legend__label">{signal.label}</span>
              <span className="plot-legend__value">
                {formatLegendValue(points[index]?.y ?? null, signal.unit, signal.type)}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
