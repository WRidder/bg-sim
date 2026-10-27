/**
 * Layout grouping for the automatic selection plot.
 *
 * `single` keeps every signal in one chart, `separate` gives every signal its
 * own chart, and `unit` groups by unit with the value type as the fallback for
 * dimensionless signals.
 */

import type { RunSignal } from "../contracts/run-manifest";
import type { AutoPlotLayout } from "./runStore";
import { unitLabel } from "./units";

export interface AutoPlotGroup {
  key: string;
  label: string;
  signals: RunSignal[];
}

function unitKey(signal: RunSignal): string {
  const unit = signal.unit ?? null;
  return unit !== null && unit.trim().length > 0 ? `unit:${unit}` : `type:${signal.type}`;
}

function unitGroupLabel(signal: RunSignal): string {
  const unit = signal.unit ?? null;
  if (unit !== null && unit.trim().length > 0) {
    return unitLabel(unit);
  }
  return `${signal.type} (dimensionless)`;
}

export function groupSignalsForAuto(
  signals: readonly RunSignal[],
  layout: AutoPlotLayout,
): AutoPlotGroup[] {
  if (signals.length === 0) {
    return [];
  }
  if (layout === "single") {
    return [{ key: "all", label: "All signals", signals: [...signals] }];
  }
  if (layout === "separate") {
    return signals.map((signal) => ({
      key: signal.id,
      label: signal.id,
      signals: [signal],
    }));
  }
  const groups = new Map<string, AutoPlotGroup>();
  for (const signal of signals) {
    const key = unitKey(signal);
    const existing = groups.get(key);
    if (existing === undefined) {
      groups.set(key, {
        key,
        label: unitGroupLabel(signal),
        signals: [signal],
      });
    } else {
      existing.signals.push(signal);
    }
  }
  return [...groups.values()];
}
