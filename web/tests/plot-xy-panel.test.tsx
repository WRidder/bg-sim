/**
 * The XY controls of the Plots tab: a panel header's x select switches the chart between time and
 * a signal (keyboard: a native select), the 1:1 toggle, dropping a signal on the x control, and
 * the toolbar's "Saved plots" menu that opens a model plot with its `x`.
 *
 * uPlot draws to a canvas, which jsdom does not implement; a small fake keeps the chart lifecycle.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("uplot", () => {
  class FakeUPlot {
    static join(tables: unknown[][][]): unknown[] {
      return [...(tables[0] ?? [])];
    }
    static pxRatio = 1;
    data: unknown;
    width = 400;
    height = 240;
    bbox = { left: 0, top: 0, width: 400, height: 200 };
    scales: Record<string, { min?: number; max?: number }> = { x: { min: 0, max: 1 }, y: { min: 0, max: 1 } };
    cursor = { idx: null, left: null, top: null };
    over = document.createElement("div");
    root = document.createElement("div");
    series: unknown[] = [];
    status = 1;
    constructor(_options: unknown, data: unknown) {
      this.data = data;
    }
    setData(data: unknown): void {
      this.data = data;
    }
    setSize(): void {}
    setScale(key: string, range: { min: number; max: number }): void {
      this.scales[key] = range;
    }
    setSelect(): void {}
    setCursor(): void {}
    valToPos(): number {
      return 10;
    }
    posToVal(): number {
      return 0.5;
    }
    redraw(): void {}
    batch(action: (self: FakeUPlot) => void): void {
      action(this);
    }
    syncRect(): void {}
    destroy(): void {}
  }
  return { default: FakeUPlot };
});

import type { Model } from "../src/contracts/model";
import { PlotPanel } from "../src/plot/PlotPanel";
import { resetRunStore, useRunStore } from "../src/plot/runStore";
import { SIGNAL_DRAG_MIME } from "../src/plot/signalDnd";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";
import { runManifest, runSignal } from "./plotFixtures";

const SIGNALS = [
  runSignal("Osc/x", { unit: "m", kind: "state", path: "Osc" }),
  runSignal("Osc/v", { unit: "m/s", kind: "state", path: "Osc" }),
  runSignal("Osc/F", { unit: "N", kind: "output", path: "Osc" }),
];

beforeEach(() => {
  resetRunStore();
  useRunStore.setState({
    runId: "run-xy",
    manifest: runManifest(SIGNALS, { id: "run-xy" }),
    status: "done",
    panels: [{ id: "panel-a", signals: ["Osc/x", "Osc/v"] }],
    activePanelId: "panel-a",
  });
  vi.stubGlobal("fetch", () => new Promise(() => {}));
});

afterEach(() => {
  resetRunStore();
  resetDocumentStore();
  vi.unstubAllGlobals();
});

describe("the x axis control", () => {
  it("switches a panel to XY and back with the native select", () => {
    render(<PlotPanel />);
    const select = screen.getByRole("combobox", { name: "X axis of Panel 1" });
    expect(screen.getByTestId("plot-chart").getAttribute("data-mode")).toBeNull();
    // The panel's own signals come first, then the rest of the run.
    const groups = select.querySelectorAll("optgroup");
    expect(Array.from(groups).map((group) => group.label)).toEqual(["Signals of this plot", "Other signals"]);
    expect(Array.from(groups[1]!.querySelectorAll("option")).map((option) => option.value)).toEqual(["Osc/F"]);

    fireEvent.change(select, { target: { value: "Osc/x" } });
    const chart = screen.getByTestId("plot-chart");
    expect(chart.getAttribute("data-mode")).toBe("xy");
    expect(chart.getAttribute("data-x-signal")).toBe("Osc/x");
    expect(chart.getAttribute("data-series-count")).toBe("1");
    expect(chart.getAttribute("aria-label")).toBe("XY plot of Osc/v against Osc/x");
    expect(screen.getByTestId("legend-x").textContent).toContain("Osc/x");
    expect(screen.getByText("m/s against m")).toBeTruthy();

    const aspect = screen.getByRole("button", { name: "1:1 equal aspect for Panel 1" });
    expect(aspect.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(aspect);
    expect(useRunStore.getState().panels[0]?.equalAspect).toBe(true);
    expect(screen.getByTestId("plot-chart").getAttribute("data-equal-aspect")).toBe("true");

    fireEvent.change(select, { target: { value: "" } });
    expect(screen.getByTestId("plot-chart").getAttribute("data-mode")).toBeNull();
    expect(useRunStore.getState().panels[0]).toEqual({ id: "panel-a", signals: ["Osc/x", "Osc/v"] });
    expect(screen.queryByRole("button", { name: /equal aspect/ })).toBeNull();
  });

  it("takes a signal dropped on the x control without adding it to the y list", () => {
    render(<PlotPanel />);
    const zone = screen.getByTestId("plot-panel-x-1-zone");
    const dataTransfer = {
      types: [SIGNAL_DRAG_MIME, "text/plain"],
      getData: (type: string) => (type === SIGNAL_DRAG_MIME ? "Osc/F" : ""),
      dropEffect: "none",
    };
    fireEvent.dragOver(zone, { dataTransfer });
    fireEvent.drop(zone, { dataTransfer });
    expect(useRunStore.getState().panels[0]).toEqual({ id: "panel-a", signals: ["Osc/x", "Osc/v"], x: "Osc/F" });
    expect(screen.getByTestId("plot-chart").getAttribute("data-series-count")).toBe("2");
  });
});

describe("saved plots", () => {
  it("lists the model's plots and opens one as an XY panel", () => {
    const doc = {
      format: "bgsim.model",
      language: "0.1.0",
      name: "Osc",
      diagram: { nodes: [], connections: [] },
      settings: {},
      plots: [
        { id: "p1", title: "Phase portrait", signals: ["Osc/v"], x: "Osc/x", equalAspect: true },
        { id: "p2", title: "Force", signals: ["Osc/F"] },
      ],
    } as unknown as Model;
    useDocumentStore.setState({ project: "demo", modelName: "Osc", doc });
    render(<PlotPanel />);
    const saved = screen.getByRole("combobox", { name: "Open a saved plot of the model as a new panel" });
    expect(Array.from(saved.querySelectorAll("option")).map((option) => option.textContent)).toEqual([
      "Saved plots…",
      "Phase portrait (against Osc/x)",
      "Force",
    ]);
    fireEvent.change(saved, { target: { value: "p1" } });
    const panels = useRunStore.getState().panels;
    expect(panels).toHaveLength(2);
    expect(panels[1]).toMatchObject({ name: "Phase portrait", x: "Osc/x", equalAspect: true, signals: ["Osc/v"] });
    const charts = screen.getAllByTestId("plot-chart");
    expect(charts[1]!.getAttribute("data-mode")).toBe("xy");
    expect((screen.getByTestId("plot-panel-title-2") as HTMLInputElement).value).toBe("Phase portrait");
  });
});
