/**
 * The display cards of the dashboard (DASHBOARD_PLAN.md): Value, Gauge, Bar, Indicator, Plot
 * and Text. Each shows its bound signal at the inspect time (`useRunSeries`), so a live run
 * shows the newest value and scrubbing or playback the value under the cursor.
 */

import { useCallback, useMemo } from "react";
import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";

import type { ModelDashboardCard } from "../contracts/model";
import type { RunSignal } from "../contracts/run-manifest";
import { formatNumber } from "../plot/format";
import { panelConfiguration, PLOT_SYNC_KEY } from "../plot/PlotPanel";
import { useRunStore } from "../plot/runStore";
import { UPlotChart } from "../plot/UPlotChart";
import { autoLimits, decimatedPath } from "../probe/MiniPlot";
import {
  formatCardValue,
  fractionOf,
  valueAt,
  zoneOf,
} from "./model";
import type { RunSeries } from "./useRunSeries";

export interface DisplayCardProps {
  card: ModelDashboardCard;
  series: RunSeries;
  titleId: string;
}

interface Sample {
  id: string | null;
  signal: RunSignal | null;
  value: number | null;
  unit: string;
  text: string;
}

function sampleOf(card: ModelDashboardCard, series: RunSeries): Sample {
  const id = card.signals?.[0] ?? null;
  const signal = id === null ? null : (series.signalsById.get(id) ?? null);
  const hold = signal !== null && signal.type !== "Real";
  const value =
    id === null || series.data === null
      ? null
      : valueAt(series.data.time, series.data.values[id], series.cursorTime, hold);
  const unit = card.options?.unit ?? signal?.unit ?? "";
  let text: string;
  if (value !== null && signal?.type === "Bool") {
    text = value !== 0 ? "true" : "false";
  } else if (value !== null && signal?.type === "Int") {
    text = String(Math.round(value));
  } else {
    text = formatCardValue(value, card.options?.decimals, formatNumber);
  }
  return { id, signal, value, unit, text };
}

function EmptyBinding({ card, series }: { card: ModelDashboardCard; series: RunSeries }) {
  const id = card.signals?.[0];
  if (id === undefined) {
    return (
      <p className="dash-card__hint">
        Drag a signal here from the Signals tab, or pick one in the card settings.
      </p>
    );
  }
  if (series.manifest === null) {
    return <p className="dash-card__hint">Run the model to see {id}.</p>;
  }
  if (!series.signalsById.has(id)) {
    return <p className="dash-card__hint">This run has no signal {id}.</p>;
  }
  return null;
}

function needsBinding(card: ModelDashboardCard, series: RunSeries): boolean {
  const id = card.signals?.[0];
  return id === undefined || series.manifest === null || !series.signalsById.has(id);
}

function at(series: RunSeries): string {
  return series.cursorTime === null ? "latest" : `t = ${formatNumber(series.cursorTime)} s`;
}

// ------------------------------------------------------------------- value

const TONE_LABEL: Record<string, string> = { good: "good", warn: "warning", bad: "alarm", info: "info" };
const TONE_GLYPH: Record<string, string> = { good: "✓", warn: "!", bad: "✕", info: "i" };

/** A zone is a status: a coloured mark plus a word, never colour alone. */
function ToneChip({ tone }: { tone: string }) {
  return (
    <span className={`dash-tone-chip dash-zone--${tone}`}>
      <span className="dash-tone-chip__glyph" aria-hidden="true">
        {TONE_GLYPH[tone] ?? "•"}
      </span>
      {TONE_LABEL[tone] ?? tone}
    </span>
  );
}

function Sparkline({ id, series }: { id: string; series: RunSeries }) {
  const data = series.data;
  if (data === null || data.values[id] === undefined) {
    return null;
  }
  const width = 160;
  const height = 28;
  const { t0, t1 } = series.range;
  const limits = autoLimits(data, [id], t0, t1);
  const path = decimatedPath(data.time, data.values[id]!, t0, t1, limits.lo, limits.hi, width, height);
  const cursor =
    series.cursorTime === null ? null : ((series.cursorTime - t0) / (t1 - t0)) * width;
  return (
    <svg
      className="dash-sparkline"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <path d={path} className="dash-sparkline__line" />
      {cursor !== null && cursor >= 0 && cursor <= width ? (
        <line x1={cursor} x2={cursor} y1={0} y2={height} className="dash-sparkline__cursor" />
      ) : null}
    </svg>
  );
}

export function ValueCard({ card, series }: DisplayCardProps) {
  if (needsBinding(card, series)) {
    return <EmptyBinding card={card} series={series} />;
  }
  const sample = sampleOf(card, series);
  const tone = zoneOf(sample.value, card.options?.zones);
  return (
    <div className="dash-value" data-testid={`dash-value-${card.id}`}>
      <output className="dash-value__number" aria-label={`${sample.id} at ${at(series)}`}>
        {sample.text}
        {sample.unit.length > 0 ? <span className="dash-value__unit"> {sample.unit}</span> : null}
      </output>
      {tone !== null ? <ToneChip tone={tone} /> : null}
      {card.options?.sparkline === true && sample.id !== null ? (
        <Sparkline id={sample.id} series={series} />
      ) : null}
    </div>
  );
}

// ------------------------------------------------------------------- gauge

/** The display range: the options, else the series' own range in the run window. */
function displayRange(card: ModelDashboardCard, series: RunSeries, id: string | null) {
  let min = card.options?.min;
  let max = card.options?.max;
  if ((min === undefined || max === undefined) && id !== null && series.data !== null) {
    const limits = autoLimits(series.data, [id], series.range.t0, series.range.t1);
    min ??= limits.lo;
    max ??= limits.hi;
  }
  min ??= 0;
  max ??= 1;
  return max > min ? { min, max } : { min, max: min + 1 };
}

const GAUGE_START = 135;
const GAUGE_SWEEP = 270;

function polar(cx: number, cy: number, r: number, degrees: number): [number, number] {
  const radians = (degrees * Math.PI) / 180;
  return [cx + r * Math.cos(radians), cy + r * Math.sin(radians)];
}

/** An SVG arc path from fraction `a` to `b` of the gauge sweep. */
export function gaugeArc(cx: number, cy: number, r: number, a: number, b: number): string {
  const from = GAUGE_START + GAUGE_SWEEP * Math.max(0, Math.min(1, a));
  const to = GAUGE_START + GAUGE_SWEEP * Math.max(0, Math.min(1, b));
  const [x0, y0] = polar(cx, cy, r, from);
  const [x1, y1] = polar(cx, cy, r, to);
  const large = to - from > 180 ? 1 : 0;
  return `M ${x0.toFixed(2)} ${y0.toFixed(2)} A ${r} ${r} 0 ${large} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`;
}

export function GaugeCard({ card, series }: DisplayCardProps) {
  if (needsBinding(card, series)) {
    return <EmptyBinding card={card} series={series} />;
  }
  const sample = sampleOf(card, series);
  const { min, max } = displayRange(card, series, sample.id);
  const fraction = fractionOf(sample.value, min, max);
  const tone = zoneOf(sample.value, card.options?.zones);
  const [nx, ny] = polar(60, 60, 38, GAUGE_START + GAUGE_SWEEP * fraction);
  return (
    <div
      className="dash-gauge"
      role="meter"
      aria-valuemin={min}
      aria-valuemax={max}
      aria-valuenow={sample.value ?? undefined}
      aria-valuetext={`${sample.text} ${sample.unit}`.trim()}
      aria-label={`${sample.id} at ${at(series)}`}
      data-testid={`dash-gauge-${card.id}`}
    >
      <svg viewBox="0 0 120 104" className="dash-gauge__svg" aria-hidden="true">
        <path d={gaugeArc(60, 60, 46, 0, 1)} className="dash-gauge__track" />
        {(card.options?.zones ?? []).map((zone, index) => (
          <path
            key={index}
            d={gaugeArc(60, 60, 46, fractionOf(Math.min(zone.from, zone.to), min, max), fractionOf(Math.max(zone.from, zone.to), min, max))}
            className={`dash-gauge__zone dash-zone--${zone.tone}`}
          />
        ))}
        <path
          d={gaugeArc(60, 60, 46, 0, fraction)}
          className={`dash-gauge__value${tone === null ? "" : ` dash-zone--${tone}`}`}
        />
        <line x1={60} y1={60} x2={nx} y2={ny} className="dash-gauge__needle" />
        <circle cx={60} cy={60} r={3.5} className="dash-gauge__hub" />
        <text x={60} y={86} textAnchor="middle" className="dash-gauge__text">
          {sample.text}
        </text>
        <text x={60} y={98} textAnchor="middle" className="dash-gauge__unit">
          {sample.unit}
        </text>
        <text x={22} y={102} textAnchor="middle" className="dash-gauge__limit">
          {formatNumber(min)}
        </text>
        <text x={98} y={102} textAnchor="middle" className="dash-gauge__limit">
          {formatNumber(max)}
        </text>
      </svg>
      {tone !== null ? <ToneChip tone={tone} /> : null}
    </div>
  );
}

// --------------------------------------------------------------------- bar

export function BarCard({ card, series }: DisplayCardProps) {
  if (needsBinding(card, series)) {
    return <EmptyBinding card={card} series={series} />;
  }
  const sample = sampleOf(card, series);
  const { min, max } = displayRange(card, series, sample.id);
  const fraction = fractionOf(sample.value, min, max);
  const tone = zoneOf(sample.value, card.options?.zones);
  const horizontal = card.options?.orientation === "horizontal";
  const percent = `${(fraction * 100).toFixed(1)}%`;
  return (
    <div
      className={`dash-bar${horizontal ? " dash-bar--horizontal" : ""}`}
      role="meter"
      aria-valuemin={min}
      aria-valuemax={max}
      aria-valuenow={sample.value ?? undefined}
      aria-valuetext={`${sample.text} ${sample.unit}`.trim()}
      aria-label={`${sample.id} at ${at(series)}`}
      data-testid={`dash-bar-${card.id}`}
    >
      <div className="dash-bar__track">
        {(card.options?.zones ?? []).map((zone, index) => {
          const a = fractionOf(Math.min(zone.from, zone.to), min, max) * 100;
          const b = fractionOf(Math.max(zone.from, zone.to), min, max) * 100;
          const style = horizontal
            ? { left: `${a}%`, width: `${b - a}%` }
            : { bottom: `${a}%`, height: `${b - a}%` };
          return <div key={index} className={`dash-bar__zone dash-zone--${zone.tone}`} style={style} />;
        })}
        <div
          className={`dash-bar__fill${tone === null ? "" : ` dash-zone--${tone}`}`}
          style={horizontal ? { width: percent } : { height: percent }}
        />
      </div>
      <div className="dash-bar__labels">
        <span className="dash-bar__value">
          {sample.text}
          {sample.unit.length > 0 ? ` ${sample.unit}` : ""}
        </span>
        {tone !== null ? <ToneChip tone={tone} /> : null}
        <span className="dash-bar__limits">
          {formatNumber(min)} – {formatNumber(max)}
        </span>
      </div>
    </div>
  );
}

// --------------------------------------------------------------- indicator

/** On when the value is above (default) or below the threshold; Bool signals default to 0.5. */
export function indicatorOn(
  value: number | null,
  threshold: number | undefined,
  onWhen: "above" | "below" | undefined,
): boolean | null {
  if (value === null) {
    return null;
  }
  const limit = threshold ?? 0.5;
  return onWhen === "below" ? value < limit : value > limit;
}

export function IndicatorCard({ card, series }: DisplayCardProps) {
  if (needsBinding(card, series)) {
    return <EmptyBinding card={card} series={series} />;
  }
  const sample = sampleOf(card, series);
  const on = indicatorOn(sample.value, card.options?.threshold, card.options?.onWhen);
  const state = on === null ? "no value" : on ? "on" : "off";
  return (
    <div
      className="dash-indicator"
      role="status"
      aria-label={`${sample.id}: ${state} (${sample.text}${sample.unit.length > 0 ? ` ${sample.unit}` : ""}) at ${at(series)}`}
      data-testid={`dash-indicator-${card.id}`}
      data-state={state}
    >
      <span className={`dash-indicator__led${on === true ? " is-on" : ""}`} aria-hidden="true" />
      <span className="dash-indicator__state">{on === null ? "—" : on ? "On" : "Off"}</span>
      <span className="dash-indicator__value">
        {sample.text}
        {sample.unit.length > 0 ? ` ${sample.unit}` : ""}
      </span>
    </div>
  );
}

// -------------------------------------------------------------------- plot

export function PlotCard({ card, series }: DisplayCardProps) {
  const ids = card.signals ?? [];
  const view = useRunStore((state) => state.view);
  const configuration = useMemo(
    () => panelConfiguration(ids, series.signalsById, new Set<string>()),
    // `ids` is the card's array, stable until the card changes.
    [card.signals, series.signalsById],
  );
  const onZoom = useCallback((next: { t0: number; t1: number } | null, px: number) => {
    useRunStore.getState().setView(next, px);
  }, []);
  const onReset = useCallback(() => useRunStore.getState().setView(null), []);
  const onCursor = useCallback((time: number | null) => {
    useRunStore.getState().setCursorTime(time);
  }, []);
  if (ids.length === 0 || series.manifest === null || configuration.current.length === 0) {
    return <EmptyBinding card={card} series={series} />;
  }
  return (
    <div className="dash-plot" data-testid={`dash-plot-${card.id}`}>
      <UPlotChart
        signals={configuration.current}
        compareSignals={[]}
        data={series.data}
        compare={null}
        view={view}
        fullRange={series.range}
        syncKey={PLOT_SYNC_KEY}
        cursorTime={series.cursorTime}
        onZoom={onZoom}
        onReset={onReset}
        onCursorTime={onCursor}
      />
    </div>
  );
}

// -------------------------------------------------------------------- text

export function TextCard({ card }: DisplayCardProps) {
  const text = card.options?.text ?? "";
  if (text.trim().length === 0) {
    return <p className="dash-card__hint">Add text in the card settings.</p>;
  }
  if (card.options?.markdown === false) {
    return <p className="dash-text dash-text--plain">{text}</p>;
  }
  return (
    <div className="dash-text">
      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]}>
        {text}
      </ReactMarkdown>
    </div>
  );
}
