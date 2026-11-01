/**
 * XY plots (one signal against another): the pure path, range and cursor logic of `xy.ts`, the
 * panel state of the run store (`x`, `equalAspect`, saved model plots, whole-row data while an
 * XY plot is open), the dashboard plot card's `x`, and the contract round trip (an edited model
 * still validates against model.schema.json).
 */

import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import Ajv2020 from "ajv/dist/2020";
import addFormats from "ajv-formats";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Model, ModelPlot } from "../src/contracts/model";
import { setCardEqualAspect, setCardX, dropSignalOnCard } from "../src/dashboard/actions";
import { dashboardHasXY, dashboardSignalIds, isXYCard } from "../src/dashboard/model";
import {
  needsExactRows,
  panelFromModelPlot,
  plottedSignalIds,
  resetRunStore,
  useRunStore,
  withPanelX,
  type PlotPanelState,
} from "../src/plot/runStore";
import {
  axisMap,
  equalAspectRanges,
  extendExtent,
  nearestDrawnPoint,
  paddedRange,
  pointAtTime,
  thinXYPath,
  windowIndices,
  xyAxisLabel,
} from "../src/plot/xy";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";
import { runManifest, runSignal } from "./plotFixtures";

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "..", "..");

function readJson<T>(...parts: string[]): T {
  return JSON.parse(readFileSync(path.join(repoRoot, ...parts), "utf8")) as T;
}

// ------------------------------------------------------------------------------ xy.ts

describe("windowIndices", () => {
  const time = [0, 0.1, 0.2, 0.2, 0.3, 0.4];
  it("returns the whole series without a window", () => {
    expect(windowIndices(time, null)).toEqual([0, 5]);
    expect(windowIndices([], null)).toBeNull();
  });
  it("keeps both limits of an event instant and is inclusive on both sides", () => {
    expect(windowIndices(time, { t0: 0.2, t1: 0.2 })).toEqual([2, 3]);
    expect(windowIndices(time, { t0: 0.05, t1: 0.3 })).toEqual([1, 4]);
  });
  it("is null for a window between samples or outside the run", () => {
    expect(windowIndices(time, { t0: 0.31, t1: 0.39 })).toBeNull();
    expect(windowIndices(time, { t0: 2, t1: 3 })).toBeNull();
  });
});

describe("ranges", () => {
  it("pads an extent and widens a flat one", () => {
    expect(paddedRange({ min: 0, max: 10 })).toEqual({ min: -0.5, max: 10.5 });
    expect(paddedRange({ min: 2, max: 2 })).toEqual({ min: 1.8, max: 2.2 });
    expect(paddedRange(null)).toEqual({ min: -1, max: 1 });
  });
  it("extends an extent over a window and skips NaN", () => {
    expect(extendExtent(null, [5, Number.NaN, -3, 9], 0, 2)).toEqual({ min: -3, max: 5 });
    expect(extendExtent({ min: 0, max: 1 }, [5, -3, 9], 2, 2)).toEqual({ min: 0, max: 9 });
    expect(extendExtent(null, [Number.NaN], 0, 0)).toBeNull();
  });
  it("makes one unit as long on both axes, only ever widening", () => {
    // 400 x 100 px, x spans 2 and y spans 2: y is the limiting axis (0.02 per px), x widens to 8.
    const { x, y } = equalAspectRanges({ min: -1, max: 1 }, { min: -1, max: 1 }, 400, 100);
    expect(y).toEqual({ min: -1, max: 1 });
    expect(x.max - x.min).toBeCloseTo(8);
    expect((x.max - x.min) / 400).toBeCloseTo((y.max - y.min) / 100);
    expect((x.min + x.max) / 2).toBeCloseTo(0);
    // A degenerate plot area leaves the ranges alone.
    expect(equalAspectRanges({ min: 0, max: 1 }, { min: 0, max: 1 }, 0, 100).x).toEqual({ min: 0, max: 1 });
  });
  it("labels an axis with the signal and unit, or the shared unit", () => {
    expect(xyAxisLabel([{ id: "Mass/x", unit: "m" }], "x")).toBe("Mass/x [m]");
    expect(xyAxisLabel([{ id: "Mass/x", unit: null }], "x")).toBe("Mass/x");
    expect(xyAxisLabel([{ id: "A/v", unit: "V" }, { id: "B/v", unit: "V" }], "value")).toBe("[V]");
    expect(xyAxisLabel([], "value")).toBe("value");
  });
});

describe("thinXYPath (screen-space thinning)", () => {
  const identity = axisMap(0, 100, 0, 100, false);

  it("keeps every sample that moves at least the tolerance, and the first and last", () => {
    const xs = [0, 0.1, 0.2, 5, 5.1, 10];
    const ys = [0, 0, 0, 0, 0, 0];
    const path = thinXYPath(xs, ys, 0, 5, identity, identity, 0.5);
    expect(Array.from(path.rows.subarray(0, path.count))).toEqual([0, 3, 5]);
  });

  it("flushes the last dwelling sample so a run ends on its real end", () => {
    const xs = [0, 10, 10.1, 10.2];
    const ys = [0, 0, 0, 0];
    const path = thinXYPath(xs, ys, 0, 3, identity, identity, 0.5);
    expect(Array.from(path.rows.subarray(0, path.count))).toEqual([0, 1, 3]);
  });

  it("breaks the line at a gap and maps y downwards", () => {
    const xs = [0, 10, Number.NaN, 20, 30];
    const ys = [0, 10, 0, 20, 30];
    const flipped = axisMap(0, 100, 0, 100, true);
    const path = thinXYPath(xs, ys, 0, 4, identity, flipped, 0.5);
    expect(Array.from(path.rows.subarray(0, path.count))).toEqual([0, 1, 3, 4]);
    expect(Array.from(path.breaks.subarray(0, path.count))).toEqual([1, 0, 1, 0]);
    expect(path.py[0]).toBe(100);
    expect(path.py[3]).toBe(70);
  });

  it("stays within the tolerance of the full-resolution curve", () => {
    const n = 20_000;
    const xs = new Float64Array(n);
    const ys = new Float64Array(n);
    for (let i = 0; i < n; i += 1) {
      const t = (i / n) * 2 * Math.PI * 5;
      xs[i] = Math.sin(t);
      ys[i] = Math.sin(2 * t + 0.3);
    }
    const mapX = axisMap(-1, 1, 0, 600, false);
    const mapY = axisMap(-1, 1, 0, 300, true);
    const path = thinXYPath(xs, ys, 0, n - 1, mapX, mapY, 0.5);
    // Every skipped sample lies within 0.5 px (per axis) of the drawn point before it.
    let k = 0;
    for (let i = 0; i < n; i += 1) {
      while (k + 1 < path.count && (path.rows[k + 1] as number) <= i) k += 1;
      const px = mapX.offset + (xs[i]! - mapX.min) * mapX.scale;
      const py = mapY.offset + (ys[i]! - mapY.min) * mapY.scale;
      expect(Math.abs(px - path.px[k]!)).toBeLessThan(0.5 + 1e-3);
      expect(Math.abs(py - path.py[k]!)).toBeLessThan(0.5 + 1e-3);
    }
    expect(path.count).toBeLessThan(n);
  });

  it("thins large runs fast (18 000 and 1 000 000 rows)", () => {
    for (const [n, loops, budgetMs] of [
      [18_000, 10, 25],
      [1_000_000, 50, 400],
    ] as const) {
      const xs = new Float64Array(n);
      const ys = new Float64Array(n);
      for (let i = 0; i < n; i += 1) {
        // A Van der Pol-like limit cycle, travelled `loops` times.
        const t = (i / n) * 2 * Math.PI * loops;
        xs[i] = 2 * Math.cos(t);
        ys[i] = 2 * Math.sin(t) * (1 + 0.3 * Math.cos(3 * t));
      }
      const mapX = axisMap(-2.5, 2.5, 0, 1200, false);
      const mapY = axisMap(-3, 3, 0, 480, true);
      thinXYPath(xs, ys, 0, n - 1, mapX, mapY, 0.5);
      const started = performance.now();
      const path = thinXYPath(xs, ys, 0, n - 1, mapX, mapY, 0.5);
      const elapsed = performance.now() - started;
      // eslint-disable-next-line no-console -- the measured numbers are part of the test report
      console.info(`thinXYPath: ${n} rows -> ${path.count} drawn points in ${elapsed.toFixed(2)} ms`);
      expect(path.count).toBeLessThanOrEqual(n);
      expect(elapsed).toBeLessThan(budgetMs);
      if (n === 1_000_000) {
        // 50 loops of a ~3000 px cycle: far fewer drawn points than rows.
        expect(path.count).toBeLessThan(n / 2);
      }
    }
  });
});

describe("nearestDrawnPoint and pointAtTime (the inspect cursor)", () => {
  it("finds the drawn point nearest the pointer over several paths", () => {
    const map = axisMap(0, 10, 0, 10, false);
    const a = thinXYPath([0, 5, 10], [0, 0, 0], 0, 2, map, map, 0.5);
    const b = thinXYPath([0, 5, 10], [8, 8, 8], 0, 2, map, map, 0.5);
    expect(nearestDrawnPoint([a, b], 4.6, 7)).toMatchObject({ path: 1, point: 1 });
    expect(nearestDrawnPoint([a, null], 9, 1)).toMatchObject({ path: 0, point: 2 });
    expect(nearestDrawnPoint([null], 0, 0)).toBeNull();
  });

  it("interpolates both coordinates at the same time, so the marker lies on the segment", () => {
    const time = [0, 1, 2];
    const xs = [0, 10, 20];
    const ys = [0, 100, 0];
    expect(pointAtTime(time, xs, ys, 0.5)).toEqual({ x: 5, y: 50, t: 0.5 });
    expect(pointAtTime(time, xs, ys, 1.5)).toEqual({ x: 15, y: 50, t: 1.5 });
  });

  it("takes the right limit at an event, the newest sample without a time and null outside", () => {
    const time = [0, 1, 1, 2];
    const xs = [0, 1, 5, 6];
    const ys = [0, 1, 5, 6];
    expect(pointAtTime(time, xs, ys, 1)).toEqual({ x: 5, y: 5, t: 1 });
    expect(pointAtTime(time, xs, ys, null)).toEqual({ x: 6, y: 6, t: 2 });
    expect(pointAtTime(time, xs, ys, 3)).toBeNull();
    // Inside a time window only.
    expect(pointAtTime(time, xs, ys, 2, 0, 2)).toBeNull();
    expect(pointAtTime(time, xs, ys, null, 0, 1)).toEqual({ x: 1, y: 1, t: 1 });
  });
});

// ------------------------------------------------------------------- panel state

const SIGNALS = [
  runSignal("Osc/x", { unit: "m", kind: "state" }),
  runSignal("Osc/v", { unit: "m/s", kind: "state" }),
  runSignal("Osc/F", { unit: "N", kind: "output" }),
];

describe("panel state", () => {
  it("withPanelX moves the x signal out of the y list and back", () => {
    const panel: PlotPanelState = { id: "p", signals: ["Osc/x", "Osc/v"] };
    const xy = withPanelX(panel, "Osc/x");
    expect(xy).toEqual({ id: "p", signals: ["Osc/v"], x: "Osc/x" });
    const other = withPanelX({ ...xy, equalAspect: true }, "Osc/F");
    expect(other).toEqual({ id: "p", signals: ["Osc/x", "Osc/v"], x: "Osc/F", equalAspect: true });
    expect(withPanelX(other, null)).toEqual({ id: "p", signals: ["Osc/F", "Osc/x", "Osc/v"] });
    expect(withPanelX(panel, null)).toBe(panel);
  });

  it("a saved model plot becomes a panel with its title, x and aspect", () => {
    const plot: ModelPlot = { id: "p2", title: " Phase ", signals: ["Osc/v", "Osc/x"], x: "Osc/x", equalAspect: true };
    expect(panelFromModelPlot(plot, "panel-9")).toEqual({
      id: "panel-9",
      name: "Phase",
      signals: ["Osc/v"],
      x: "Osc/x",
      equalAspect: true,
    });
    expect(panelFromModelPlot({ id: "p1", title: "", signals: ["Osc/x"], equalAspect: true }, "q")).toEqual({
      id: "q",
      signals: ["Osc/x"],
    });
  });

  it("plottedSignalIds includes an XY panel's x first; needsExactRows follows the XY panels", () => {
    const panels: PlotPanelState[] = [
      { id: "a", signals: ["Osc/F"] },
      { id: "b", signals: ["Osc/v"], x: "Osc/x" },
    ];
    expect(plottedSignalIds(panels)).toEqual(["Osc/F", "Osc/x", "Osc/v"]);
    expect(needsExactRows({ panels, dashboardExact: false })).toBe(true);
    expect(needsExactRows({ panels: [panels[0]!], dashboardExact: false })).toBe(false);
    expect(needsExactRows({ panels: [panels[0]!], dashboardExact: true })).toBe(true);
  });
});

describe("run store with XY panels", () => {
  let dataUrls: string[] = [];

  beforeEach(() => {
    resetRunStore();
    dataUrls = [];
    vi.stubGlobal("fetch", (input: RequestInfo | URL) => {
      dataUrls.push(String(input));
      return new Promise(() => {});
    });
    useRunStore.setState({
      runId: "run-test",
      manifest: runManifest(SIGNALS),
      status: "done",
      panels: [{ id: "panel-a", signals: ["Osc/x", "Osc/v"] }],
      activePanelId: "panel-a",
    });
  });

  afterEach(() => {
    resetRunStore();
    resetDocumentStore();
    vi.unstubAllGlobals();
  });

  it("setPanelX switches the axis, refuses an unknown signal and setPanelEqualAspect needs an x", () => {
    const store = useRunStore.getState();
    store.setPanelEqualAspect("panel-a", true);
    expect(useRunStore.getState().panels[0]?.equalAspect).toBeUndefined();
    store.setPanelX("panel-a", "Osc/x");
    expect(useRunStore.getState().panels[0]).toEqual({ id: "panel-a", signals: ["Osc/v"], x: "Osc/x" });
    store.setPanelEqualAspect("panel-a", true);
    expect(useRunStore.getState().panels[0]?.equalAspect).toBe(true);
    store.setPanelX("panel-a", "No/such");
    expect(useRunStore.getState().notice).toMatch(/no signal No\/such/);
    store.setPanelX("panel-a", null);
    expect(useRunStore.getState().panels[0]).toEqual({ id: "panel-a", signals: ["Osc/x", "Osc/v"] });
  });

  it("does not add the x signal as a y signal of its own panel", () => {
    const store = useRunStore.getState();
    store.setPanelX("panel-a", "Osc/x");
    store.addSignal("Osc/x", "panel-a");
    expect(useRunStore.getState().panels[0]?.signals).toEqual(["Osc/v"]);
    expect(useRunStore.getState().notice).toMatch(/x axis/);
  });

  it("requests whole rows (px=0) for a zoom while an XY panel is open", async () => {
    const store = useRunStore.getState();
    store.setView({ t0: 0.2, t1: 0.4 }, 800);
    await Promise.resolve();
    expect(dataUrls.at(-1)).toMatch(/px=800/);
    store.setPanelX("panel-a", "Osc/x");
    await Promise.resolve();
    expect(dataUrls.at(-1)).toMatch(/px=0/);
    expect(dataUrls.at(-1)).toMatch(/t0=0\.2/);
    store.setPanelX("panel-a", null);
    await Promise.resolve();
    expect(dataUrls.at(-1)).toMatch(/px=800/);
  });

  it("opens a saved model plot as a new panel (replacing an untouched first panel)", () => {
    useRunStore.setState({ panels: [{ id: "panel-a", signals: [] }], activePanelId: "panel-a" });
    const id = useRunStore.getState().openModelPlot({ id: "p1", title: "Phase", signals: ["Osc/v"], x: "Osc/x" });
    let state = useRunStore.getState();
    expect(state.panels).toHaveLength(1);
    expect(state.panels[0]).toMatchObject({ id, name: "Phase", signals: ["Osc/v"], x: "Osc/x" });
    expect(state.activePanelId).toBe(id);
    useRunStore.getState().openModelPlot({ id: "p2", title: "Force", signals: ["Osc/F"] });
    state = useRunStore.getState();
    expect(state.panels).toHaveLength(2);
    expect(state.panels[1]?.x).toBeUndefined();
    expect(state.notice).toMatch(/Force/);
  });
});

describe("live tail subscription", () => {
  class FakeSocket {
    static last: FakeSocket | null = null;
    readyState = 0;
    sent: string[] = [];
    onopen: (() => void) | null = null;
    onclose: (() => void) | null = null;
    onerror: (() => void) | null = null;
    onmessage: (() => void) | null = null;
    constructor() {
      FakeSocket.last = this;
    }
    send(data: string): void {
      this.sent.push(data);
    }
    close(): void {}
  }

  beforeEach(() => {
    resetRunStore();
    vi.stubGlobal("WebSocket", FakeSocket);
    vi.stubGlobal("fetch", async (_input: RequestInfo | URL, init?: RequestInit) => {
      if ((init?.method ?? "GET") === "POST") {
        return new Response(JSON.stringify({ runId: "run-live" }), {
          status: 201,
          headers: { "content-type": "application/json" },
        });
      }
      return new Response(JSON.stringify(runManifest(SIGNALS, { id: "run-live", status: "running" })), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    });
    useDocumentStore.setState({
      project: "p",
      modelName: "M",
      doc: { format: "bgsim.model", language: "0.1.0", name: "M", diagram: { nodes: [], connections: [] }, settings: {} } as unknown as Model,
    });
  });

  afterEach(() => {
    resetRunStore();
    resetDocumentStore();
    vi.unstubAllGlobals();
  });

  it("subscribes exact (whole rows) while an XY panel is open", async () => {
    await useRunStore.getState().startRun();
    await vi.waitFor(() => expect(FakeSocket.last).not.toBeNull());
    const socket = FakeSocket.last!;
    socket.readyState = 1;
    socket.onopen?.();
    useRunStore.getState().addSignal("Osc/x");
    useRunStore.getState().addSignal("Osc/v");
    expect(JSON.parse(socket.sent.at(-1)!)).toEqual({ subscribe: ["Osc/x", "Osc/v"] });
    const panelId = useRunStore.getState().panels[0]!.id;
    useRunStore.getState().setPanelX(panelId, "Osc/x");
    expect(JSON.parse(socket.sent.at(-1)!)).toEqual({ subscribe: ["Osc/x", "Osc/v"], exact: true });
    useRunStore.getState().setPanelX(panelId, null);
    expect(JSON.parse(socket.sent.at(-1)!)).toEqual({ subscribe: ["Osc/x", "Osc/v"] });
    useRunStore.getState().setDashboardSignals(["Osc/F"], true);
    expect(JSON.parse(socket.sent.at(-1)!)).toEqual({ subscribe: ["Osc/x", "Osc/v", "Osc/F"], exact: true });
  });

  it("drops an x signal the new run does not record (the panel falls back to time)", async () => {
    vi.stubGlobal("fetch", async (_input: RequestInfo | URL, init?: RequestInit) => {
      if ((init?.method ?? "GET") === "POST") {
        return new Response(JSON.stringify({ runId: "run-live" }), {
          status: 201,
          headers: { "content-type": "application/json" },
        });
      }
      const without = runManifest([SIGNALS[1]!, SIGNALS[2]!], { id: "run-live", status: "running" });
      return new Response(JSON.stringify(without), { status: 200, headers: { "content-type": "application/json" } });
    });
    useRunStore.setState({
      panels: [{ id: "panel-a", signals: ["Osc/v"], x: "Osc/x", equalAspect: true }],
      activePanelId: "panel-a",
    });
    await useRunStore.getState().startRun();
    await vi.waitFor(() => expect(useRunStore.getState().manifest?.id).toBe("run-live"));
    expect(useRunStore.getState().panels[0]).toEqual({ id: "panel-a", signals: ["Osc/v"] });
  });
});

// --------------------------------------------------------------- dashboard + contract

describe("dashboard plot card x and the contract round trip", () => {
  const ajv = new Ajv2020({ allErrors: true, strict: true });
  addFormats(ajv);
  for (const name of [
    "catalog", "model", "project", "diagnostic", "run-manifest", "worker-rpc", "stream-handshake",
    "bindings", "debug", "docs", "export-request", "export-report", "export-job", "clipboard",
  ]) {
    const schema = readJson<{ $id: string }>("contracts", "schemas", `${name}.schema.json`);
    ajv.addSchema(schema, schema.$id);
  }
  const validateModel = ajv.getSchema("https://bgsim.local/schemas/model.schema.json")!;

  afterEach(() => resetDocumentStore());

  it("the XY fixture validates and its plots and cards read as XY", () => {
    const doc = readJson<Model>("contracts", "fixtures", "model", "valid", "model.xy-plots.json");
    expect(validateModel(doc)).toBe(true);
    expect(doc.plots?.filter((plot) => plot.x !== undefined).map((plot) => plot.id)).toEqual(["p2", "p3"]);
    expect(dashboardHasXY(doc.dashboard)).toBe(true);
    expect(doc.dashboard?.cards.filter(isXYCard).map((card) => card.id)).toEqual(["c1"]);
    expect(dashboardSignalIds(doc.dashboard)).toEqual(["C1/v", "L1/i"]);
    // Plot -> panel keeps the contract fields.
    const panel = panelFromModelPlot(doc.plots![2]!, "x");
    expect(panel).toMatchObject({ x: "C1/v", equalAspect: true, signals: ["L1/i", "C1/i"] });
  });

  it("setCardX / setCardEqualAspect edit the card and the model still validates", () => {
    const doc = readJson<Model>("contracts", "fixtures", "model", "valid", "model.dashboard.json");
    useDocumentStore.getState().openDocument("demo", doc.name, doc);
    setCardEqualAspect("c1", true);
    let card = useDocumentStore.getState().doc!.dashboard!.cards.find((entry) => entry.id === "c1")!;
    expect(card.equalAspect).toBeUndefined();

    setCardX("c1", "C1/v");
    setCardEqualAspect("c1", true);
    card = useDocumentStore.getState().doc!.dashboard!.cards.find((entry) => entry.id === "c1")!;
    expect(card).toMatchObject({ x: "C1/v", signals: ["L1/i"], equalAspect: true });
    expect(validateModel(useDocumentStore.getState().doc)).toBe(true);
    const saved = JSON.parse(JSON.stringify(useDocumentStore.getState().doc)) as Model;
    expect(validateModel(saved)).toBe(true);

    // Dropping the x signal does not add it again as a y signal.
    dropSignalOnCard("c1", "C1/v");
    card = useDocumentStore.getState().doc!.dashboard!.cards.find((entry) => entry.id === "c1")!;
    expect(card.signals).toEqual(["L1/i"]);

    setCardX("c1", null);
    card = useDocumentStore.getState().doc!.dashboard!.cards.find((entry) => entry.id === "c1")!;
    expect(card).not.toHaveProperty("x");
    expect(card).not.toHaveProperty("equalAspect");
    expect(card.signals).toEqual(["C1/v", "L1/i"]);
    // Only plot cards take an x.
    setCardX("c2", "L1/i");
    expect(useDocumentStore.getState().doc!.dashboard!.cards.find((entry) => entry.id === "c2")).not.toHaveProperty("x");
  });
});
