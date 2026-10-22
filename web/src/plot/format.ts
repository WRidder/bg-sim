/**
 * Number formatting for plots and the run bar (plan 7.5).
 *
 * Plot values are read at a glance, so the rules are deliberately narrow:
 * three decimals in the normal engineering range, scientific notation outside
 * it, explicit Bool/Int rendering (the files store them as Float64), and "—"
 * for a missing point. The functions are pure and covered by unit tests.
 */

import type { ValueType } from "../contracts/run-manifest";

/** Remove trailing fraction zeros, but never a bare integer's digits. */
export function trimZeros(text: string): string {
  if (!text.includes(".")) {
    return text;
  }
  const trimmed = text.replace(/0+$/, "").replace(/\.$/, "");
  return trimmed === "-0" || trimmed === "" ? "0" : trimmed;
}

/** A compact engineering number: `0.42`, `1234`, `1.23e-5`. */
export function formatNumber(value: number): string {
  if (!Number.isFinite(value)) {
    return "—";
  }
  const magnitude = Math.abs(value);
  if (magnitude === 0) {
    return "0";
  }
  if (magnitude < 1e-3 || magnitude >= 1e5) {
    return value
      .toExponential(3)
      .replace(/\.?0+e/, "e")
      .replace("e+", "e");
  }
  return trimZeros(value.toFixed(3));
}

/**
 * Format one value for the cursor legend. A unit is appended with a space;
 * Bool and Int signals use their semantic spelling, not `1`/`0`.
 */
export function formatLegendValue(
  value: number | null | undefined,
  unit: string | null | undefined,
  type: ValueType,
): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "—";
  }
  let text: string;
  if (type === "Bool") {
    text = value !== 0 ? "true" : "false";
  } else if (type === "Int") {
    text = String(Math.round(value));
  } else {
    text = formatNumber(value);
  }
  const trimmedUnit = unit?.trim() ?? "";
  return trimmedUnit.length > 0 ? `${text} ${trimmedUnit}` : text;
}

/** The cursor time in seconds, e.g. `1.234 s`; adaptive precision. */
export function formatCursorTime(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "—";
  }
  const magnitude = Math.abs(value);
  const digits = magnitude < 10 ? 3 : magnitude < 100 ? 2 : 1;
  return `${trimZeros(value.toFixed(digits))} s`;
}

/** A time value on the x axis, without the unit (the axis label carries it). */
export function formatAxisTime(value: number): string {
  if (!Number.isFinite(value)) {
    return "";
  }
  const magnitude = Math.abs(value);
  const digits =
    magnitude < 10 ? 3 : magnitude < 100 ? 2 : magnitude < 1000 ? 1 : 0;
  return trimZeros(value.toFixed(digits));
}

/** A duration such as a run's `sim_s`: `0.94 s`, `12.3 s`. */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) {
    return "—";
  }
  return seconds < 10
    ? `${trimZeros(seconds.toFixed(2))} s`
    : `${trimZeros(seconds.toFixed(1))} s`;
}

/** The run bar's readout: `t / t_end`, e.g. `0.42 / 1 s`. */
export function formatProgress(t: number, tEnd: number): string {
  return `${formatNumber(t)} / ${formatNumber(tEnd)} s`;
}
