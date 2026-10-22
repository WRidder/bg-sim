/**
 * Unit grouping and axis assignment for plot panels (plan 7.5).
 *
 * A panel has at most two y axes: one for the first unit group and one for the
 * second. A third unit group would make the axis meaningless, so the store
 * starts a new panel instead (and the panel header explains why). Keeping this
 * logic pure makes the rule testable without a chart.
 */

import type { RunSignal } from "../contracts/run-manifest";

/** How many y axes (unit groups) one panel can show (plan 7.5). */
export const MAX_PANEL_UNIT_GROUPS = 2;

/** A group of signals that share a unit (and therefore an axis). */
export interface UnitGroup {
  /** The unit exactly as the manifest reports it, or null when dimensionless. */
  unit: string | null;
  /** The axis label. */
  label: string;
  signals: RunSignal[];
}

/** The unit key of a signal; dimensionless signals share the empty key. */
export function signalUnitKey(signal: RunSignal): string {
  return signal.unit ?? "";
}

/** A human axis label for a unit, or "dimensionless". */
export function unitLabel(unit: string | null): string {
  return unit === null || unit.trim().length === 0 ? "dimensionless" : unit;
}

/**
 * Group signals by unit, preserving the order in which units first appear in
 * the recording order. Signals with no unit form one group.
 */
export function groupSignalsByUnit(
  signals: readonly RunSignal[],
): UnitGroup[] {
  const groups = new Map<string, UnitGroup>();
  for (const signal of signals) {
    const key = signalUnitKey(signal);
    const existing = groups.get(key);
    if (existing === undefined) {
      groups.set(key, {
        unit: signal.unit ?? null,
        label: unitLabel(signal.unit ?? null),
        signals: [signal],
      });
    } else {
      existing.signals.push(signal);
    }
  }
  return [...groups.values()];
}

/** The y-axis assignment of one panel. */
export interface PanelAxes {
  /** The group on the left axis, or null for an empty panel. */
  left: UnitGroup | null;
  /** The group on the right axis, or null when only one group is shown. */
  right: UnitGroup | null;
  /** Groups that do not fit and need a new panel. */
  overflow: UnitGroup[];
}

/**
 * Assign groups to the two axes of a panel. The first group goes left, the
 * second right; any further group is returned in `overflow` so the caller can
 * suggest (or start) another panel.
 */
export function assignPanelAxes(signals: readonly RunSignal[]): PanelAxes {
  const groups = groupSignalsByUnit(signals);
  return {
    left: groups[0] ?? null,
    right: groups[1] ?? null,
    overflow: groups.slice(MAX_PANEL_UNIT_GROUPS),
  };
}

/** A short "V · rad/s" summary for a panel header. */
export function panelUnitSummary(signals: readonly RunSignal[]): string {
  if (signals.length === 0) {
    return "no signals";
  }
  const labels = groupSignalsByUnit(signals).map((group) => group.label);
  return labels.join(" · ");
}

/** True when adding `signal` keeps the panel at two unit groups or fewer. */
export function canAddSignalToPanel(
  existing: readonly RunSignal[],
  signal: RunSignal,
): boolean {
  if (existing.some((entry) => entry.id === signal.id)) {
    return true;
  }
  return (
    groupSignalsByUnit([...existing, signal]).length <= MAX_PANEL_UNIT_GROUPS
  );
}
