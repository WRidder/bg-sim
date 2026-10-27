/**
 * The Plots tab shell (plan 7.5): the split-panel offer for a third unit
 * group, the CSV link's plotted selection, the global inspect-time readout,
 * the live/autoscroll badge, and the dashed compare legend.
 *
 * uPlot draws to a canvas, which jsdom does not implement; a small fake keeps
 * the React contract (data updates and chart lifecycle) and lets the test
 * assert the chrome around the chart.
 */

import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("uplot", () => {
  class FakeUPlot {
    static join(tables: unknown[][][]): unknown[] {
      const joined = [...(tables[0] ?? [])];
      for (let index = 1; index < tables.length; index += 1) {
        joined.push(...(tables[index] ?? []).slice(1));
      }
      return joined;
    }

    data: unknown;
    scales = { x: { min: 0, max: 1 }, y: {}, y2: {} };
    cursor = { idx: null, left: null, top: null };
    over = document.createElement("div");
    constructor(_options: unknown, data: unknown) {
      this.data = data;
    }
    setData(data: unknown): void {
      this.data = data;
    }
    setSize(): void {}
    setScale(): void {}
    setSelect(): void {}
    setCursor(): void {}
    valToPos(): number {
      return 10;
    }
    batch(action: (self: FakeUPlot) => void): void {
      action(this);
    }
    syncRect(): void {}
    destroy(): void {}
  }
  return { default: FakeUPlot };
});

import { PlotPanel } from "../src/plot/PlotPanel";
import { resetRunStore, useRunStore } from "../src/plot/runStore";
import { runManifest, runSignal } from "./plotFixtures";

const SIGNALS = [
  runSignal("Motor/w", { unit: "rad/s", kind: "state", path: "Motor" }),
  runSignal("Motor/i", { unit: "A", kind: "state", path: "Motor" }),
  runSignal("Motor/v", { unit: "V", kind: "output", path: "Motor" }),
];

function loadThreeGroups(): void {
  useRunStore.setState({
    runId: "run-panel",
    manifest: runManifest(SIGNALS, { id: "run-panel" }),
    status: "done",
    panels: [{ id: "panel-a", signals: SIGNALS.map((signal) => signal.id) }],
    activePanelId: "panel-a",
  });
}

beforeEach(() => {
  resetRunStore();
  loadThreeGroups();
  vi.stubGlobal("fetch", () => new Promise(() => {}));
});

afterEach(() => {
  resetRunStore();
  vi.unstubAllGlobals();
});

describe("PlotPanel chrome", () => {
  it("offers Split panel for a third unit group and performs the split", () => {
    render(<PlotPanel />);
    expect(screen.getAllByTestId("plot-chart-panel")).toHaveLength(1);
    const split = screen.getByTestId("split-panel");

    fireEvent.click(split);

    expect(useRunStore.getState().panels).toHaveLength(2);
    expect(screen.getAllByTestId("plot-chart-panel")).toHaveLength(2);
    expect(screen.queryByTestId("split-panel")).toBeNull();
  });

  it("renames a panel in its header and restores the default on an empty name", () => {
    render(<PlotPanel />);
    const title = screen.getByTestId("plot-panel-title-1") as HTMLInputElement;
    expect(title.value).toBe("Panel 1");

    fireEvent.focus(title);
    fireEvent.change(title, { target: { value: "Speed" } });
    fireEvent.blur(title);
    expect(useRunStore.getState().panels[0]?.name).toBe("Speed");
    expect(title.value).toBe("Speed");

    fireEvent.focus(title);
    fireEvent.change(title, { target: { value: "   " } });
    fireEvent.blur(title);
    expect(useRunStore.getState().panels[0]?.name).toBeUndefined();
    expect(title.value).toBe("Panel 1");
  });

  it("exports exactly the plotted signals as CSV", () => {
    render(<PlotPanel />);
    const link = screen.getByTestId("export-csv");
    const url = new URL(link.getAttribute("href") ?? "", "http://bgsim.test");
    expect(url.pathname).toBe("/api/runs/run-panel/export.csv");
    expect(url.searchParams.get("ids")).toBe("Motor/w,Motor/i,Motor/v");
    expect(link.getAttribute("aria-disabled")).toBe("false");
  });

  it("shows the global inspect time in seconds", async () => {
    render(<PlotPanel />);
    expect(screen.getByTestId("plot-inspect-time").textContent).toMatch(/—/);

    await act(async () => {
      useRunStore.getState().setCursorTime(0.42);
    });
    expect(screen.getByTestId("plot-inspect-time").textContent).toMatch(
      /0\.42 s/,
    );
  });

  it("labels live autoscroll and offers Follow live after a zoom", async () => {
    useRunStore.setState({ status: "running", view: null });
    render(<PlotPanel />);

    const badge = screen.getByTestId("live-badge");
    expect(badge.getAttribute("data-following")).toBe("true");
    expect(screen.queryByTestId("follow-live")).toBeNull();

    await act(async () => {
      useRunStore.setState({ view: { t0: 0.1, t1: 0.5 } });
    });
    expect(screen.getByTestId("live-badge").getAttribute("data-following")).toBe(
      "false",
    );
    fireEvent.click(screen.getByTestId("follow-live"));
    expect(useRunStore.getState().view).toBeNull();
  });

  it("renders pinned signals as dashed compare legend items", () => {
    useRunStore.setState({
      pinned: { manifest: runManifest(SIGNALS, { id: "run-pinned" }) },
      compareData: {
        key: "pinned",
        time: new Float64Array([0, 1]),
        values: {
          "Motor/w": new Float64Array([1, 2]),
          "Motor/i": new Float64Array([3, 4]),
          "Motor/v": new Float64Array([5, 6]),
        },
      },
    });
    render(<PlotPanel />);

    const compare = screen
      .getAllByTestId("legend-item")
      .filter((item) => item.getAttribute("data-compare") === "true");
    expect(compare).toHaveLength(3);
    for (const item of compare) {
      const swatch = item.querySelector(".plot-legend__swatch");
      expect(swatch?.className).toMatch(/plot-legend__swatch--dashed/);
    }
    expect(screen.getByTestId("pinned-run").textContent).toMatch(/run-pinned/);
  });
});
