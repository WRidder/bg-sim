/**
 * Hover read-out helpers for bonds and ports (plan 7.3 and 7.5).
 *
 * A bond carries the same effort and flow at both ends, so the source port (or
 * the target port when the source is a junction) names the recorded signals:
 * `<path>/<port>.e`, `.f` and `.P`. The power row is computed as `P = e·f`, so
 * it stays correct even when the manifest does not record a `P` column.
 *
 * Everything here is pure: the component only fetches and formats the columns
 * through these functions, and the unit tests cover the sample lookup and the
 * label formatting.
 */

import type { Model, ModelConnection } from "../../contracts/model";
import { formatNumber } from "../../plot/format";
import { endpointPort } from "../../plot/plotTargets";

/** One row of the hover tooltip. */
export interface HoverRow {
  key: "e" | "f" | "P" | "value";
  label: string;
  value: string;
  unit: string;
}

/** The three power variables a bond or power port offers. */
export const HOVER_VARIABLES = ["e", "f", "P"] as const;
export type HoverVariable = (typeof HOVER_VARIABLES)[number];

/** The three signal ids of one power port under a subsystem path prefix. */
export function powerHoverSignalIds(
  pathPrefix: string,
  path: string,
  port: string,
): Record<HoverVariable, string> {
  const base = pathPrefix.length > 0 ? `${pathPrefix}/${path}/${port}` : `${path}/${port}`;
  return { e: `${base}.e`, f: `${base}.f`, P: `${base}.P` };
}

/** The one signal id of a signal port under a subsystem path prefix. */
export function signalHoverSignalId(
  pathPrefix: string,
  path: string,
  port: string,
): string {
  return pathPrefix.length > 0 ? `${pathPrefix}/${path}/${port}` : `${path}/${port}`;
}

/**
 * The port that names a connection's power variables. The source wins (the
 * bond/arrow direction); a junction endpoint has no port, so the target is
 * used instead.
 */
export function connectionPowerPort(
  model: Model,
  connection: ModelConnection,
): { path: string; port: string } | null {
  return endpointPort(model, connection.from) ?? endpointPort(model, connection.to);
}

/** The index of the sample nearest `time`; -1 for an empty axis. */
export function nearestSampleIndex(time: ArrayLike<number>, at: number): number {
  const length = time.length;
  if (length === 0) {
    return -1;
  }
  if (!Number.isFinite(at) || at <= (time[0] as number)) {
    return 0;
  }
  const last = time[length - 1] as number;
  if (at >= last) {
    return length - 1;
  }
  let low = 0;
  let high = length - 1;
  while (low < high) {
    const middle = (low + high) >> 1;
    if ((time[middle] as number) < at) {
      low = middle + 1;
    } else {
      high = middle;
    }
  }
  // `low` is the first sample >= at; compare it with its predecessor.
  const before = low - 1;
  if (before < 0) {
    return low;
  }
  return at - (time[before] as number) <= (time[low] as number) - at ? before : low;
}

/** The value at the nearest sample, or null for a missing column. */
export function valueAtNearestSample(
  time: ArrayLike<number>,
  values: ArrayLike<number> | undefined,
  at: number,
): number | null {
  if (values === undefined) {
    return null;
  }
  const index = nearestSampleIndex(time, at);
  if (index < 0 || index >= values.length) {
    return null;
  }
  const value = values[index] as number;
  return Number.isFinite(value) ? value : null;
}

function unitOf(units: Partial<Record<string, string>>, key: string): string {
  return units[key]?.trim() ?? "";
}

/** `e`, `f` and `P = e·f` in the manifest's units. */
export function powerHoverRows(
  effort: number | null,
  flow: number | null,
  units: Partial<Record<HoverVariable | "value", string>> = {},
): HoverRow[] {
  const power =
    effort !== null && flow !== null && Number.isFinite(effort) && Number.isFinite(flow)
      ? effort * flow
      : null;
  return [
    {
      key: "e",
      label: "e",
      value: effort === null ? "—" : formatNumber(effort),
      unit: unitOf(units, "e"),
    },
    {
      key: "f",
      label: "f",
      value: flow === null ? "—" : formatNumber(flow),
      unit: unitOf(units, "f"),
    },
    {
      key: "P",
      label: "P = e·f",
      value: power === null ? "—" : formatNumber(power),
      unit: unitOf(units, "P"),
    },
  ];
}

/** One row for a signal wire or a signal port. */
export function signalHoverRow(
  value: number | null,
  unit: string | null | undefined,
): HoverRow {
  return {
    key: "value",
    label: "value",
    value: value === null ? "—" : formatNumber(value),
    unit: unit?.trim() ?? "",
  };
}

/** The unit of one signal id from the run manifest or the model check. */
export function signalUnit(
  id: string,
  sources: readonly (readonly { id: string; unit?: string | null }[])[],
): string | null {
  for (const source of sources) {
    const entry = source.find((signal) => signal.id === id);
    if (entry !== undefined) {
      return entry.unit ?? null;
    }
  }
  return null;
}

/** `e / f / P` units for a power port. */
export function powerUnits(
  ids: Record<HoverVariable, string>,
  sources: readonly (readonly { id: string; unit?: string | null }[])[],
): Partial<Record<HoverVariable | "value", string>> {
  return {
    e: signalUnit(ids.e, sources) ?? "",
    f: signalUnit(ids.f, sources) ?? "",
    P: signalUnit(ids.P, sources) ?? "",
  };
}
