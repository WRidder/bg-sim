/**
 * Text for the values of the Debug panel (frames, evaluate results, signal
 * values). Numbers show six significant digits; vectors and matrices show a
 * compact one-line form here and expand to one row per element in the panel.
 */

import type { FrameValue } from "../../contracts/debug";

export type FrameScalar = number | boolean;
export type FrameData = FrameValue["value"];

/** A number with at most six significant digits and no trailing zeros. */
export function formatNumber(value: number): string {
  if (Number.isNaN(value)) {
    return "NaN";
  }
  if (!Number.isFinite(value)) {
    return value > 0 ? "Inf" : "-Inf";
  }
  if (Number.isInteger(value) && Math.abs(value) < 1e9) {
    return String(value);
  }
  const text = Number(value.toPrecision(6)).toString();
  return text.includes("e") ? Number(value.toPrecision(6)).toExponential() : text;
}

function scalarText(value: unknown): string {
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  return typeof value === "number" ? formatNumber(value) : String(value);
}

/** A value on one line: `3.14`, `true`, `[0.1, 0.2]`, `[[1, 0], [0, 1]]`. */
export function formatFrameValue(value: unknown, size: readonly number[] = [], limit = 6): string {
  if (!Array.isArray(value)) {
    return scalarText(value);
  }
  const shown = value.slice(0, limit).map((entry) => formatFrameValue(entry, size.slice(1), limit));
  const more = value.length > limit ? `, … (${value.length})` : "";
  return `[${shown.join(", ")}${more}]`;
}

/** `Real`, `Real[2]`, `Real[2×2]`. */
export function frameTypeText(type: string, size: readonly number[]): string {
  const dims = size.filter((entry) => entry !== 1 || size.length > 1);
  return dims.length === 0 ? type : `${type}[${dims.join("×")}]`;
}

/** One expandable row of a vector or matrix: its label and the value below it. */
export interface FrameElement {
  label: string;
  value: unknown;
}

/** The elements of an array value, one per first index. */
export function frameElements(value: unknown): FrameElement[] {
  return Array.isArray(value) ? value.map((entry, index) => ({ label: `[${index + 1}]`, value: entry })) : [];
}
