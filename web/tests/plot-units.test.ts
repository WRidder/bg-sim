import { describe, expect, it } from "vitest";

import type { RunSignal } from "../src/contracts/run-manifest";
import {
  MAX_PANEL_UNIT_GROUPS,
  assignPanelAxes,
  canAddSignalToPanel,
  groupSignalsByUnit,
  panelUnitSummary,
  signalUnitKey,
  unitLabel,
} from "../src/plot/units";

function signal(id: string, unit: string | null): RunSignal {
  return {
    id,
    unit,
    kind: "state",
    path: id.split("/")[0] ?? null,
    type: "Real",
  } as RunSignal;
}

describe("unit grouping", () => {
  it("groups by unit in first-appearance order", () => {
    const groups = groupSignalsByUnit([
      signal("A/w", "rad/s"),
      signal("A/v", "V"),
      signal("B/w", "rad/s"),
    ]);
    expect(groups.map((group) => group.label)).toEqual(["rad/s", "V"]);
    expect(groups[0]?.signals.map((entry) => entry.id)).toEqual([
      "A/w",
      "B/w",
    ]);
  });

  it("puts every dimensionless signal in one group", () => {
    const groups = groupSignalsByUnit([
      signal("A/x", null),
      signal("A/y", ""),
    ]);
    expect(groups).toHaveLength(1);
    expect(groups[0]?.label).toBe("dimensionless");
    expect(signalUnitKey(signal("A/x", null))).toBe("");
    expect(unitLabel(null)).toBe("dimensionless");
    expect(unitLabel("N*m")).toBe("N*m");
  });

  it("assigns the first two groups to the two axes and reports the overflow", () => {
    const axes = assignPanelAxes([
      signal("A/w", "rad/s"),
      signal("A/v", "V"),
      signal("A/F", "N"),
    ]);
    expect(MAX_PANEL_UNIT_GROUPS).toBe(2);
    expect(axes.left?.label).toBe("rad/s");
    expect(axes.right?.label).toBe("V");
    expect(axes.overflow.map((group) => group.label)).toEqual(["N"]);
  });

  it("leaves the right axis empty for one group and both for none", () => {
    expect(assignPanelAxes([signal("A/w", "rad/s")]).right).toBeNull();
    const empty = assignPanelAxes([]);
    expect(empty.left).toBeNull();
    expect(empty.right).toBeNull();
    expect(empty.overflow).toEqual([]);
  });

  it("refuses a third unit group but accepts a duplicate signal", () => {
    const existing = [signal("A/w", "rad/s"), signal("A/v", "V")];
    expect(canAddSignalToPanel(existing, signal("A/w", "rad/s"))).toBe(true);
    expect(canAddSignalToPanel(existing, signal("A/F", "N"))).toBe(false);
    expect(
      canAddSignalToPanel([signal("A/w", "rad/s")], signal("A/v", "V")),
    ).toBe(true);
  });

  it("summarises the units of a panel", () => {
    expect(panelUnitSummary([])).toBe("no signals");
    expect(
      panelUnitSummary([signal("A/w", "rad/s"), signal("A/v", "V")]),
    ).toBe("rad/s · V");
  });
});
