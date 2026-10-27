/**
 * One uPlot instance of a plot panel (plan 7.5).
 *
 * uPlot is used directly, not through a wrapper. The chart owns its canvas and
 * cursor; the React parent owns the run, the zoom window and the data, so
 * remounting the dock tab or resizing the splitter never loses the view.
 *
 * Interactions:
 *  * drag horizontally selects a time range and zooms (uPlot's built-in drag);
 *  * the wheel zooms around the pointer;
 *  * double-click resets to "show all"; Escape clears an in-progress drag;
 *  * every zoom reports `{t0, t1, px}` to the parent, which re-requests `/data`.
 *
 * The cursor is linked to the other panels through a shared `uPlot.sync` key.
 * Its time is the global inspect time, and each chart renders a custom legend
 * with the values at the cursor (the engineering number formatting lives in
 * `format.ts`).
 */

import { useEffect, useRef, useState } from "react";
import "./uplotSetup";
import uPlot from "uplot";

import type { RunSignalKind, ValueType } from "../contracts/run-manifest";
import {
  formatAxisTime,
  formatCursorTime,
  formatLegendValue,
} from "./format";
import type { ChartSeriesData } from "./runStore";
import type { SeriesWindow } from "./runCache";

/** Height of one chart in CSS pixels; the dock scrolls stacked panels. */
export const CHART_HEIGHT = 160;
const MIN_CHART_WIDTH = 320;
const FALLBACK_CHART_WIDTH = 640;
const AXIS_COLOR = "#8a95a3";
const GRID_COLOR = "rgba(128, 140, 156, 0.22)";
const AXIS_FONT = '11px "Inter Variable", "Inter", system-ui, sans-serif';

/** One plotted signal; compare signals are the same id in the pinned run. */
export interface ChartSeriesConfig {
  id: string;
  label: string;
  unit: string | null;
  type: ValueType;
  kind: RunSignalKind;
  color: string;
  axis: "y" | "y2";
  compare: boolean;
}

export interface UPlotChartProps {
  signals: ChartSeriesConfig[];
  compareSignals: ChartSeriesConfig[];
  data: ChartSeriesData | null;
  compare: ChartSeriesData | null;
  view: SeriesWindow | null;
  /** The full run window, used to clamp zooming. */
  fullRange: SeriesWindow;
  /** The uPlot sync key shared by every chart in the dock. */
  syncKey: string;
  /** The global inspect time (seconds); null before the first pointer move. */
  cursorTime: number | null;
  onZoom: (view: SeriesWindow | null, px: number) => void;
  onReset: () => void;
  onCursorTime: (time: number | null) => void;
}

const EMPTY_TIME = new Float64Array(0);

type SeriesTable = ReadonlyArray<ArrayLike<number | null | undefined>>;

function seriesKey(signals: readonly ChartSeriesConfig[]): string {
  return signals
    .map(
      (signal) =>
        `${signal.id}:${signal.axis}:${signal.compare ? "p" : "c"}:` +
        `${signal.unit ?? ""}:${signal.type}`,
    )
    .join("|");
}

function axisLabel(
  signals: readonly ChartSeriesConfig[],
  axis: "y" | "y2",
): string {
  const first = signals.find((signal) => signal.axis === axis);
  const unit = first?.unit?.trim() ?? "";
  return unit.length > 0 ? unit : axis === "y" ? "value" : "—";
}

function columnFor(
  source: ArrayLike<number> | undefined,
  length: number,
): ArrayLike<number | null> | Float64Array {
  if (source !== undefined && source.length === length) {
    return source;
  }
  return new Array<number | null>(length).fill(null);
}

function buildChartData(
  signals: readonly ChartSeriesConfig[],
  compareSignals: readonly ChartSeriesConfig[],
  data: ChartSeriesData | null,
  compare: ChartSeriesData | null,
): uPlot.AlignedData {
  const time = data?.time ?? EMPTY_TIME;
  const current: ArrayLike<number | null>[] = [
    time,
    ...signals.map((signal) =>
      columnFor(data?.values[signal.id], time.length),
    ),
  ];
  if (compareSignals.length === 0) {
    return current as uPlot.AlignedData;
  }
  if (compare === null || compare.time.length === 0) {
    // The pinned columns have not arrived yet; keep the series count aligned
    // with the chart options so uPlot can draw the current data.
    return [
      ...current,
      ...compareSignals.map(() => new Array<number | null>(time.length).fill(null)),
    ] as uPlot.AlignedData;
  }
  const compareTable: ArrayLike<number | null>[] = [
    compare.time,
    ...compareSignals.map((signal) =>
      columnFor(compare.values[signal.id], compare.time.length),
    ),
  ];
  return uPlot.join([
    current as uPlot.AlignedData,
    compareTable as uPlot.AlignedData,
  ]);
}

function valueAt(
  table: uPlot.AlignedData | null,
  column: number,
  index: number,
): number | null {
  const values = (table as SeriesTable | null)?.[column];
  if (values === undefined || index < 0 || index >= values.length) {
    return null;
  }
  const value = values[index];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function UPlotChart({
  signals,
  compareSignals,
  data,
  compare,
  view,
  fullRange,
  syncKey,
  cursorTime,
  onZoom,
  onReset,
  onCursorTime,
}: UPlotChartProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<uPlot | null>(null);
  const dataRef = useRef<uPlot.AlignedData | null>(null);
  const legendIndexRef = useRef<number | null>(null);
  const wheelTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const dragTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const programmaticScaleRef = useRef(false);
  const scaleTokenRef = useRef(0);
  const readyRef = useRef(false);
  const fullRangeRef = useRef(fullRange);
  const viewRef = useRef(view);
  const onZoomRef = useRef(onZoom);
  const onResetRef = useRef(onReset);
  const onCursorTimeRef = useRef(onCursorTime);
  const cursorTimeRef = useRef(cursorTime);
  const renderSeqRef = useRef(0);

  const [chartEpoch, setChartEpoch] = useState(0);
  const [legendIndex, setLegendIndex] = useState<number | null>(null);
  const [legendTick, setLegendTick] = useState(0);

  fullRangeRef.current = fullRange;
  viewRef.current = view;
  onZoomRef.current = onZoom;
  onResetRef.current = onReset;
  onCursorTimeRef.current = onCursorTime;
  cursorTimeRef.current = cursorTime;

  const allSignals = [...signals, ...compareSignals];
  const chartSeriesKey = seriesKey(allSignals);
  const hasRightAxis = allSignals.some((signal) => signal.axis === "y2");

  // ------------------------------------------------------------- chart create
  useEffect(() => {
    const host = hostRef.current;
    if (host === null) {
      return;
    }
    const width = Math.max(
      MIN_CHART_WIDTH,
      Math.floor(host.clientWidth || FALLBACK_CHART_WIDTH),
    );

    const plotPixelWidth = (): number => {
      const hostWidth = host.clientWidth || width;
      const ratio =
        typeof window === "undefined" ? 1 : window.devicePixelRatio || 1;
      return Math.max(1, Math.round(hostWidth * ratio));
    };

    const reportZoom = (
      min: number,
      max: number,
      delay: number,
      timer: typeof wheelTimerRef,
    ): void => {
      if (timer.current !== null) {
        clearTimeout(timer.current);
      }
      timer.current = setTimeout(() => {
        timer.current = null;
        const full = fullRangeRef.current;
        const span = full.t1 - full.t0;
        const epsilon = Math.max(Math.abs(span) * 1e-9, 1e-12);
        const px = plotPixelWidth();
        if (min <= full.t0 + epsilon && max >= full.t1 - epsilon) {
          onZoomRef.current(null, px);
        } else {
          onZoomRef.current({ t0: min, t1: max }, px);
        }
      }, delay);
    };

    const series: uPlot.Series[] = [{ label: "t" }];
    for (const signal of allSignals) {
      series.push({
        label: signal.compare ? `${signal.label} (pinned)` : signal.label,
        scale: signal.axis,
        stroke: signal.color,
        width: signal.compare ? 1 : 1.5,
        dash: signal.compare ? [5, 3] : undefined,
        alpha: signal.compare ? 0.8 : 1,
        spanGaps: true,
        points: { show: false },
      });
    }

    const axes: uPlot.Axis[] = [
      {
        scale: "x",
        side: 2,
        size: 24,
        stroke: AXIS_COLOR,
        font: AXIS_FONT,
        label: "t [s]",
        labelSize: 14,
        labelFont: AXIS_FONT,
        values: (_self, splits) => splits.map((value) => formatAxisTime(value)),
        grid: { stroke: GRID_COLOR, width: 1 },
        ticks: { stroke: AXIS_COLOR, width: 1, size: 4 },
      },
      {
        scale: "y",
        side: 3,
        size: 44,
        stroke: AXIS_COLOR,
        font: AXIS_FONT,
        label: axisLabel(allSignals, "y"),
        labelSize: 14,
        labelFont: AXIS_FONT,
        grid: { stroke: GRID_COLOR, width: 1 },
        ticks: { stroke: AXIS_COLOR, width: 1, size: 4 },
      },
    ];
    if (hasRightAxis) {
      axes.push({
        scale: "y2",
        side: 1,
        size: 44,
        stroke: AXIS_COLOR,
        font: AXIS_FONT,
        label: axisLabel(allSignals, "y2"),
        labelSize: 14,
        labelFont: AXIS_FONT,
        grid: { show: false },
        ticks: { stroke: AXIS_COLOR, width: 1, size: 4 },
      });
    }

    const options: uPlot.Options = {
      width,
      height: CHART_HEIGHT,
      padding: [6, 8, 0, 0],
      series,
      axes,
      scales: {
        x: { time: false },
        y: { auto: true },
        y2: { auto: true },
      },
      legend: { show: false },
      cursor: {
        show: true,
        x: true,
        y: false,
        drag: { setScale: true, x: true, y: false, dist: 4 },
        points: { show: false },
        sync: { key: syncKey, setSeries: false, scales: ["x", null] },
      },
      hooks: {
        ready: [
          (self) => {
            readyRef.current = true;
            self.syncRect();
          },
        ],
        setScale: [
          (self, key) => {
            if (key !== "x" || !readyRef.current) {
              return;
            }
            if (programmaticScaleRef.current) {
              return;
            }
            const min = self.scales.x.min;
            const max = self.scales.x.max;
            if (typeof min !== "number" || typeof max !== "number" || !(max > min)) {
              return;
            }
            reportZoom(min, max, 30, dragTimerRef);
          },
        ],
        setCursor: [
          (self) => {
            const index = self.cursor.idx;
            if (index === null || index === undefined) {
              return;
            }
            // A synced or programmatic cursor must not write the store; the
            // mousemove listener below is the only writer of inspect time.
            if (index !== legendIndexRef.current) {
              legendIndexRef.current = index;
              setLegendIndex(index);
            }
          },
        ],
      },
    };

    // uPlot checks `target instanceof HTMLElement` against the *main* window,
    // so a host inside the detached window is mistaken for a callback. Pass the
    // callback form there: uPlot builds its root in this document and the host
    // adopts it when it is appended.
    const detachedHost =
      typeof document !== "undefined" && host.ownerDocument !== document;
    const target = (
      detachedHost
        ? (chart: uPlot, init: () => void) => {
            host.appendChild(chart.root);
            init();
          }
        : host
    ) as unknown as HTMLElement;
    const chart = new uPlot(
      options,
      [[], ...allSignals.map(() => [])],
      target,
    );
    chartRef.current = chart;
    readyRef.current = false;
    chart.setSize({ width, height: CHART_HEIGHT });

    const onWheel = (event: WheelEvent): void => {
      const current = chartRef.current;
      if (current === null) {
        return;
      }
      const xScale = current.scales.x;
      if (
        typeof xScale.min !== "number" ||
        typeof xScale.max !== "number" ||
        !(xScale.max > xScale.min)
      ) {
        return;
      }
      event.preventDefault();
      const rect = current.over.getBoundingClientRect();
      const left = Math.min(
        Math.max(event.clientX - rect.left, 0),
        Math.max(rect.width, 1),
      );
      const focus = current.posToVal(left, "x");
      if (!Number.isFinite(focus)) {
        return;
      }
      const delta =
        event.deltaMode === 1 ? event.deltaY * 16 : event.deltaY;
      const factor = Math.exp(Math.max(-4, Math.min(4, delta * 0.0015)));
      const full = fullRangeRef.current;
      let min = focus - (focus - xScale.min) * factor;
      let max = focus + (xScale.max - focus) * factor;
      min = Math.max(full.t0, min);
      max = Math.min(full.t1, max);
      if (!(max > min)) {
        return;
      }
      const token = ++scaleTokenRef.current;
      programmaticScaleRef.current = true;
      current.batch(() => current.setScale("x", { min, max }));
      if (scaleTokenRef.current === token) {
        programmaticScaleRef.current = false;
      }
      reportZoom(min, max, 120, wheelTimerRef);
    };

    const onDoubleClick = (): void => {
      if (wheelTimerRef.current !== null) {
        clearTimeout(wheelTimerRef.current);
        wheelTimerRef.current = null;
      }
      if (dragTimerRef.current !== null) {
        clearTimeout(dragTimerRef.current);
        dragTimerRef.current = null;
      }
      chart.setSelect({ left: 0, top: 0, width: 0, height: 0 }, false);
      onResetRef.current();
    };

    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key !== "Escape") {
        return;
      }
      // Cancel a drag: drop its selection and any pending re-request, and put
      // the scale back where the committed view says it is.
      if (wheelTimerRef.current !== null) {
        clearTimeout(wheelTimerRef.current);
        wheelTimerRef.current = null;
      }
      if (dragTimerRef.current !== null) {
        clearTimeout(dragTimerRef.current);
        dragTimerRef.current = null;
      }
      chart.setSelect({ left: 0, top: 0, width: 0, height: 0 }, false);
      const token = ++scaleTokenRef.current;
      programmaticScaleRef.current = true;
      const active = viewRef.current;
      if (active === null) {
        chart.setData(chart.data, true);
      } else {
        chart.setScale("x", { min: active.t0, max: active.t1 });
      }
      queueMicrotask(() => {
        if (scaleTokenRef.current === token) {
          programmaticScaleRef.current = false;
        }
      });
    };

    // The pointer is the only writer of the global inspect time. uPlot's own
    // mousemove handler runs first and sets `cursor.idx`; a rAF throttle keeps
    // a fast mouse from re-rendering every panel more than once per frame.
    let cursorFrame: number | null = null;
    const reportCursor = (): void => {
      cursorFrame = null;
      const current = chartRef.current;
      if (current === null) {
        return;
      }
      const index = current.cursor.idx;
      if (index === null || index === undefined) {
        return;
      }
      const time = current.data[0]?.[index];
      if (typeof time !== "number" || !Number.isFinite(time)) {
        return;
      }
      onCursorTimeRef.current(time);    };
    const onMouseMove = (): void => {
      if (cursorFrame !== null) {
        return;
      }
      cursorFrame = requestAnimationFrame(reportCursor);
    };

    chart.over.addEventListener("wheel", onWheel, { passive: false });
    chart.over.addEventListener("dblclick", onDoubleClick);
    chart.over.addEventListener("mousemove", onMouseMove);
    window.addEventListener("keydown", onKeyDown);

    const observer = new ResizeObserver(() => {
      const nextWidth = Math.max(
        MIN_CHART_WIDTH,
        Math.floor(host.clientWidth || FALLBACK_CHART_WIDTH),
      );
      chart.setSize({ width: nextWidth, height: CHART_HEIGHT });
    });
    observer.observe(host);

    setChartEpoch((epoch) => epoch + 1);

    return () => {
      window.removeEventListener("keydown", onKeyDown);
      chart.over.removeEventListener("wheel", onWheel);
      chart.over.removeEventListener("dblclick", onDoubleClick);
      chart.over.removeEventListener("mousemove", onMouseMove);
      if (cursorFrame !== null) {
        cancelAnimationFrame(cursorFrame);
        cursorFrame = null;
      }
      observer.disconnect();
      if (wheelTimerRef.current !== null) {
        clearTimeout(wheelTimerRef.current);
        wheelTimerRef.current = null;
      }
      if (dragTimerRef.current !== null) {
        clearTimeout(dragTimerRef.current);
        dragTimerRef.current = null;
      }
      readyRef.current = false;
      chart.destroy();
      if (chartRef.current === chart) {
        chartRef.current = null;
      }
    };
  }, [chartSeriesKey, hasRightAxis, syncKey]);

  // -------------------------------------------------------------- chart data
  useEffect(() => {
    const chart = chartRef.current;
    if (chart === null) {
      return;
    }
    const table = buildChartData(signals, compareSignals, data, compare);
    dataRef.current = table;
    const scaleToken = ++scaleTokenRef.current;
    programmaticScaleRef.current = true;
    const seq = renderSeqRef.current + 1;
    renderSeqRef.current = seq;
    const started =
      typeof performance === "undefined" ? 0 : performance.now();
    chart.setData(table, view === null);
    if (view !== null) {
      chart.setScale("x", { min: view.t0, max: view.t1 });
    }
    const points = (table[0] as ArrayLike<number> | undefined)?.length ?? 0;
    // While the pointer is on the plot, keep its index (clamped) so a live
    // tail does not yank the legend away; otherwise follow the newest point.
    const previous = legendIndexRef.current;
    const nextIndex =
      points === 0
        ? null
        : cursorTimeRef.current !== null && previous !== null
          ? Math.min(previous, points - 1)
          : points - 1;
    legendIndexRef.current = nextIndex;
    setLegendIndex(nextIndex);
    setLegendTick((tick) => tick + 1);

    // uPlot's setData defers its draw to a microtask; this one is queued after
    // it, so the measured time covers scale calculation, path building and the
    // canvas draw. The result is the plot performance contract of plan 7.5 and
    // the Playwright perf test reads it back from data-render-ms.
    const host = hostRef.current;
    queueMicrotask(() => {
      if (scaleTokenRef.current === scaleToken) {
        programmaticScaleRef.current = false;
      }
      if (host === null || renderSeqRef.current !== seq) {
        return;
      }
      const finished =
        typeof performance === "undefined" ? started : performance.now();
      host.dataset.renderMs = (finished - started).toFixed(2);
      host.dataset.renderSeq = String(seq);
      host.dataset.renderAt = finished.toFixed(2);
      host.dataset.points = String(points);
      const xScale = chart.scales.x;
      if (typeof xScale.min === "number") {
        host.dataset.xMin = String(xScale.min);
      }
      if (typeof xScale.max === "number") {
        host.dataset.xMax = String(xScale.max);
      }
    });
  }, [
    data,
    compare,
    chartSeriesKey,
    view,
    chartEpoch,
  ]);

  // --------------------------------------------------- global inspect cursor
  // Any module can set the inspect time; every panel then shows the cursor at
  // that time. Applying it programmatically does not call onCursorTime (only a
  // real pointer move does), so synced panels cannot feed back into the store.
  useEffect(() => {
    const chart = chartRef.current;
    if (chart === null || cursorTime === null) {
      return;
    }
    const apply = (): void => {
      const current = chartRef.current;
      if (current === null) {
        return;
      }
      const times = current.data[0] as ArrayLike<number> | undefined;
      if (times === undefined || times.length === 0) {
        return;
      }
      const left = current.valToPos(cursorTime, "x");
      if (
        !Number.isFinite(left) ||
        left < 0 ||
        left > current.over.clientWidth
      ) {
        return;
      }
      current.setCursor({ left, top: 0 });
    };
    queueMicrotask(apply);
  }, [cursorTime, data, view, chartEpoch]);


  const legendTime = valueAt(dataRef.current, 0, legendIndex ?? -1);

  return (
    <div className="plot-chart__body">
      <div
        className="plot-chart__canvas"
        ref={hostRef}
        data-testid="plot-chart"
        data-series-count={allSignals.length}
        data-compare-count={compareSignals.length}
        data-points={data?.time.length ?? 0}
        data-autoscroll={view === null ? "true" : "false"}
        data-legend-tick={legendTick}
      />
      <div className="plot-legend" data-testid="plot-legend">
        <span className="plot-legend__time" data-testid="legend-time">
          {legendIndex === null ? "t —" : `t = ${formatCursorTime(legendTime)}`}
        </span>
        <ul className="plot-legend__items">
          {allSignals.map((signal, index) => (
            <li
              className={`plot-legend__item${signal.compare ? " plot-legend__item--compare" : ""}`}
              key={`${signal.compare ? "p" : "c"}:${signal.id}`}
              data-testid="legend-item"
              data-signal-id={signal.id}
              data-compare={signal.compare ? "true" : "false"}
              title={`${signal.id}${signal.compare ? " (pinned run)" : ""}`}
            >
              <span
                className={`plot-legend__swatch${signal.compare ? " plot-legend__swatch--dashed" : ""}`}
                style={{ color: signal.color }}
                aria-hidden="true"
              />
              <span className="plot-legend__label">{signal.label}</span>
              <span className="plot-legend__value">
                {formatLegendValue(
                  valueAt(dataRef.current, index + 1, legendIndex ?? -1),
                  signal.unit,
                  signal.type,
                )}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
