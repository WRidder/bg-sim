/**
 * Auto-plot layout grouping: one panel, one per signal, or unit/type groups.
 */

import { describe, expect, it } from "vitest";

import { groupSignalsForAuto } from "../src/plot/autoPlotGroups";
import { runSignal } from "./plotFixtures";

const SIGNALS = [
  runSignal("A/v", { unit: "V", kind: "state", path: "A" }),
  runSignal("A/i", { unit: "A", kind: "state", path: "A" }),
  runSignal("A/v2", { unit: "V", kind: "algebraic", path: "A" }),
  runSignal("A/n", { unit: null, kind: "state", type: "Real", path: "A" }),
  runSignal("A/flag", { unit: null, kind: "state", type: "Bool", path: "A" }),
];

describe("groupSignalsForAuto", () => {
  it("keeps every signal in one panel", () => {
    const groups = groupSignalsForAuto(SIGNALS, "single");
    expect(groups).toHaveLength(1);
    expect(groups[0]?.signals.map((signal) => signal.id)).toEqual(
      SIGNALS.map((signal) => signal.id),
    );
  });

  it("gives every signal its own panel", () => {
    const groups = groupSignalsForAuto(SIGNALS, "separate");
    expect(groups.map((group) => group.signals[0]?.id)).toEqual(
      SIGNALS.map((signal) => signal.id),
    );
    expect(groups.every((group) => group.signals.length === 1)).toBe(true);
  });

  it("groups by unit and falls back to type for dimensionless signals", () => {
    const groups = groupSignalsForAuto(SIGNALS, "unit");
    expect(groups.map((group) => group.label)).toEqual([
      "V",
      "A",
      "Real (dimensionless)",
      "Bool (dimensionless)",
    ]);
    expect(groups.map((group) => group.signals.length)).toEqual([2, 1, 1, 1]);
  });

  it("returns no panels for an empty selection", () => {
    expect(groupSignalsForAuto([], "single")).toEqual([]);
  });
});
