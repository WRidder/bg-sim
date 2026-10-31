/**
 * The Dashboard tab (plan/DASHBOARD_PLAN.md): pure logic (value at the cursor, bindings,
 * schedule validation, the run inputs), the run request, the inspector badge, and the cards
 * rendered against a document and a run (labels, values at the cursor, keyboard inputs).
 */

import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import dashboardModel from "../../contracts/fixtures/model/valid/model.dashboard.json";
import globalModel from "../../contracts/fixtures/model/valid/model.dashboard-global.json";
import type { Catalog } from "../src/contracts/catalog";
import type { Model, ModelDashboardCard } from "../src/contracts/model";
import { DashboardTab } from "../src/dashboard/DashboardTab";
import { resetDashboardUi, useDashboardUi } from "../src/dashboard/dashboardUi";
import { gaugeArc, indicatorOn } from "../src/dashboard/DisplayCards";
import { knobKeyValue } from "../src/dashboard/InputCards";
import {
  bindingConflicts,
  dashboardRunInputs,
  findParameter,
  inputRange,
  listParameters,
  moveCard,
  scheduleIssues,
  snapToStep,
  valueAt,
} from "../src/dashboard/model";
import { overrideBadgeText } from "../src/dashboard/OverrideBadge";
import { runInputsSignature } from "../src/dashboard/useAutoRerun";
import { buildCatalogIndex } from "../src/library/catalogIndex";
import { useCatalogStore } from "../src/library/catalogStore";
import { runRequestBody } from "../src/plot/runApi";
import { resetRunStore, useRunStore } from "../src/plot/runStore";
import { useDocumentStore } from "../src/state/documentStore";
import { runManifest, runSignal } from "./plotFixtures";

// uPlot needs a canvas, which jsdom does not have; the plot card is covered by e2e.
vi.mock("../src/plot/UPlotChart", () => ({
  CHART_HEIGHT: 160,
  UPlotChart: () => <div data-testid="uplot-stub" />,
}));

const catalog = catalogJson as unknown as Catalog;
const index = buildCatalogIndex(catalog);

function model(cards?: ModelDashboardCard[]): Model {
  const doc = structuredClone(dashboardModel) as unknown as Model;
  if (cards !== undefined) {
    doc.dashboard = { cards };
  }
  return doc;
}

function openModel(doc: Model): void {
  useDocumentStore.getState().openDocument("demo", doc.name, doc);
}

// ---------------------------------------------------------------- pure logic

describe("valueAt", () => {
  const time = [0, 1, 2, 2, 3];
  const values = [0, 10, 20, 50, 60];

  it("interpolates between samples and holds for Bool/Int", () => {
    expect(valueAt(time, values, 0.5)).toBeCloseTo(5);
    expect(valueAt(time, values, 0.5, true)).toBe(0);
  });

  it("takes the right limit at an event instant (two rows with the same t)", () => {
    expect(valueAt(time, values, 2)).toBe(50);
    expect(valueAt(time, values, 2.5)).toBeCloseTo(55);
  });

  it("is the latest value without a cursor, null before the first sample", () => {
    expect(valueAt(time, values, null)).toBe(60);
    expect(valueAt(time, values, 99)).toBe(60);
    expect(valueAt(time, values, -1)).toBeNull();
    expect(valueAt([], [], null)).toBeNull();
  });
});

describe("parameters", () => {
  it("lists and finds block parameters by instance path", () => {
    const doc = model();
    const all = listParameters(doc, index).map((p) => p.target);
    expect(all).toContain("R1/R");
    expect(all).toContain("Step1/final");
    const r = findParameter(doc, index, "R1/R");
    expect(r?.modelValue).toBe(10);
    expect(r?.decl.unit).toBeDefined();
    expect(findParameter(doc, index, "R1/nope")).toBeNull();
    expect(findParameter(doc, index, "Nope/R")).toBeNull();
  });

  it("derives a slider range and snaps to its step", () => {
    const card: ModelDashboardCard = { id: "c", kind: "slider", size: "2x1", options: { min: 0, max: 10, step: 0.5 } };
    const range = inputRange(card, null);
    expect(range).toEqual({ min: 0, max: 10, step: 0.5 });
    expect(snapToStep(3.3, range)).toBe(3.5);
    expect(snapToStep(42, range)).toBe(10);
    // Without options: around the model value, from the declaration's min (R >= 0).
    const auto = inputRange({ id: "c", kind: "knob", size: "1x1" }, findParameter(model(), index, "R1/R"));
    expect(auto.min).toBe(0);
    expect(auto.max).toBeGreaterThan(10);
  });

  it("moves the knob with the arrow, page and home/end keys", () => {
    const range = { min: 0, max: 10, step: 1 };
    expect(knobKeyValue("ArrowUp", 4, range)).toBe(5);
    expect(knobKeyValue("ArrowLeft", 4, range)).toBe(3);
    expect(knobKeyValue("PageUp", 4, range)).toBe(10);
    expect(knobKeyValue("Home", 4, range)).toBe(0);
    expect(knobKeyValue("End", 4, range)).toBe(10);
    expect(knobKeyValue("a", 4, range)).toBeNull();
  });

  it("draws gauge arcs and switches indicators", () => {
    expect(gaugeArc(60, 60, 46, 0, 1)).toMatch(/^M .* A 46 46 0 1 1 /);
    expect(indicatorOn(1.2, 1, "above")).toBe(true);
    expect(indicatorOn(1.2, 1, "below")).toBe(false);
    expect(indicatorOn(null, 1, "above")).toBeNull();
  });

  it("reorders cards", () => {
    const cards = ["a", "b", "c"].map((id) => ({ id, kind: "value", size: "1x1" }) as ModelDashboardCard);
    expect(moveCard(cards, "c", 0).map((c) => c.id)).toEqual(["c", "a", "b"]);
    expect(moveCard(cards, "a", 9).map((c) => c.id)).toEqual(["b", "c", "a"]);
  });
});

describe("validation", () => {
  it("allows one input card or schedule column per parameter", () => {
    const issues = bindingConflicts({
      cards: [
        { id: "s", kind: "slider", size: "2x1", parameter: "R1/R", value: 3 },
        { id: "t", kind: "schedule", size: "2x2", schedule: { parameters: ["R1/R"], rows: [] } },
        { id: "k", kind: "knob", size: "1x1", parameter: "L1/L" },
      ],
    });
    expect(issues.map((i) => i.cardId).sort()).toEqual(["s", "t"]);
    expect(issues[0]?.message).toMatch(/R1\/R is bound by/);
  });

  it("checks schedule cells: numbers, t inside the run, no duplicate t", () => {
    const issues = scheduleIssues(
      {
        parameters: ["R1/R"],
        rows: [
          { t: 0, values: [1] },
          { t: 0, values: [2] },
          { t: 5, values: [null] },
        ],
      },
      { t_start: 0, t_end: 1 },
    );
    const messages = issues.map((i) => i.message).join(" | ");
    expect(messages).toMatch(/already row 1/);
    expect(messages).toMatch(/outside the run/);
    expect(messages).toMatch(/Enter a value for R1\/R/);
  });
});

describe("run inputs", () => {
  it("turns input cards into overrides and schedule rows into steps", () => {
    const inputs = dashboardRunInputs(model(), index);
    expect(inputs.issues).toEqual([]);
    // The fixture: slider R1/R = 12.5, number V1/V = 2; the knob has no value.
    expect(inputs.parameterOverrides).toEqual([
      { target: "R1/R", value: 12.5 },
      { target: "V1/V", value: 2 },
    ]);
    expect(inputs.parameterSchedule).toEqual([
      { t: 0, target: "Step1/final", value: 1 },
      { t: 0.01, target: "Step1/final", value: 0.5 },
    ]);
  });

  it("sorts schedule rows by t and reports problems instead of dropping them", () => {
    const doc = model([
      {
        id: "s",
        kind: "schedule",
        size: "4x2",
        schedule: { parameters: ["R1/R"], rows: [{ t: 0.005, values: [3] }, { t: 0.001, values: [2] }] },
      },
      { id: "x", kind: "number", size: "1x1", parameter: "Gone/R", value: 1 },
    ]);
    const inputs = dashboardRunInputs(doc, index);
    expect(inputs.parameterSchedule.map((s) => s.t)).toEqual([0.001, 0.005]);
    expect(inputs.issues).toHaveLength(1);
    expect(inputs.issues[0]?.message).toMatch(/no block parameter Gone\/R/);
    expect(runInputsSignature(doc, index)).toBeNull();
  });

  it("puts the inputs in the run request body only when there are any", () => {
    const doc = model();
    expect(runRequestBody(doc)).toEqual({ model: doc });
    const body = runRequestBody(doc, undefined, {
      parameterOverrides: [{ target: "R1/R", value: 2 }],
      parameterSchedule: [],
    });
    expect(body).toEqual({ model: doc, parameterOverrides: [{ target: "R1/R", value: 2 }] });
  });

  it("shows the override in the inspector badge", () => {
    const doc = model();
    expect(overrideBadgeText(doc, "R1/R")).toBe("dashboard: 12.5");
    expect(overrideBadgeText(doc, "Step1/final")).toBe("dashboard: schedule");
    expect(overrideBadgeText(doc, "L1/L")).toBeNull();
  });

  it("overrides a global parameter (kind global) but never schedules one", () => {
    const doc = structuredClone(globalModel) as unknown as Model;
    const globals = listParameters(doc, index).filter((p) => p.kind === "global");
    expect(globals.map((p) => [p.target, p.modelValue])).toEqual([
      ["global:m", 2],
      ["global:rate", 8],
      ["global:x0", Math.sqrt(2) + 0.5],
    ]);
    expect(findParameter(doc, null, "global:m")?.decl.unit).toBe("kg");
    expect(findParameter(doc, null, "global:nope")).toBeNull();

    // Globals need no catalog: the knob's value is a global override even before it loads.
    for (const catalogIndex of [index, null]) {
      const inputs = dashboardRunInputs(doc, catalogIndex);
      expect(inputs.issues).toEqual([]);
      expect(inputs.parameterOverrides).toEqual([{ target: "global:m", kind: "global", value: 3 }]);
    }
    expect(overrideBadgeText(doc, "global:m")).toBe("dashboard: 3");

    doc.dashboard!.cards[0]!.parameter = "global:gone";
    expect(dashboardRunInputs(doc, index).issues[0]?.message).toMatch(/no global parameter gone/);

    const issues = scheduleIssues(
      { parameters: ["global:m"], rows: [{ t: 0, values: [1] }] },
      { t_start: 0, t_end: 1 },
    );
    expect(issues[0]?.message).toMatch(/cannot be scheduled/);
  });

  it("evaluates a block parameter driven by a global and names the global", () => {
    const doc = structuredClone(globalModel) as unknown as Model;
    // Source/Rate/value = "rate", and rate = 4*m = 8.
    const rate = findParameter(doc, index, "Source/Rate/value");
    expect(rate?.modelText).toBe("rate");
    expect(rate?.modelValue).toBe(8);
    expect(rate?.drivenBy).toEqual(["rate"]);
    const listed = listParameters(doc, index).find((p) => p.target === "Source/Rate/value");
    expect(listed?.modelValue).toBe(8);
    // Globals list the globals they read; the slider range centres on the evaluated value.
    expect(findParameter(doc, index, "global:rate")?.drivenBy).toEqual(["m"]);
    expect(findParameter(doc, index, "global:m")?.drivenBy).toEqual([]);
    const range = inputRange({ id: "c", kind: "slider", size: "2x1" }, rate);
    expect(range.max).toBeGreaterThan(8);
    // An expression that cannot be evaluated has no value but still names its globals.
    doc.diagram.nodes[0]!.block = structuredClone(doc.diagram.nodes[0]!.block);
    const inner = (doc.diagram.nodes[0]!.block as { subsystem: { diagram: Model["diagram"] } }).subsystem.diagram;
    inner.nodes[0]!.params = { value: "rate / 0 + nope" };
    const broken = findParameter(doc, index, "Source/Rate/value");
    expect(broken?.modelValue).toBeNull();
    expect(broken?.drivenBy).toEqual(["rate"]);
  });
});

// --------------------------------------------------------- run store wiring

describe("startRun", () => {
  let bodies: unknown[] = [];

  class SilentSocket {
    onopen: (() => void) | null = null;
    onmessage: (() => void) | null = null;
    onclose: (() => void) | null = null;
    onerror: (() => void) | null = null;
    readyState = 0;
    send(): void {}
    close(): void {}
  }

  beforeEach(() => {
    bodies = [];
    resetRunStore();
    useCatalogStore.getState().setCatalog(catalog);
    vi.stubGlobal("WebSocket", SilentSocket);
    vi.stubGlobal("fetch", async (_input: RequestInfo | URL, init?: RequestInit) => {
      if ((init?.method ?? "GET") === "POST") {
        bodies.push(JSON.parse(String(init?.body)));
        return new Response(JSON.stringify({ runId: "run-dash" }), {
          status: 201,
          headers: { "content-type": "application/json" },
        });
      }
      return new Response("{}", { status: 404 });
    });
  });

  afterEach(() => {
    resetRunStore();
    vi.unstubAllGlobals();
    useCatalogStore.getState().reset();
  });

  it("sends the dashboard's overrides and schedule with the run", async () => {
    openModel(model());
    await useRunStore.getState().startRun();
    expect(bodies).toHaveLength(1);
    const body = bodies[0] as Record<string, unknown>;
    expect(body.parameterOverrides).toEqual([
      { target: "R1/R", value: 12.5 },
      { target: "V1/V", value: 2 },
    ]);
    expect(body.parameterSchedule).toHaveLength(2);
    useRunStore.setState({ status: "idle" });
  });

  it("refuses a run while the dashboard has a problem", async () => {
    openModel(
      model([
        { id: "a", kind: "slider", size: "2x1", parameter: "R1/R", value: 1 },
        { id: "b", kind: "knob", size: "1x1", parameter: "R1/R", value: 2 },
      ]),
    );
    await useRunStore.getState().startRun();
    expect(bodies).toHaveLength(0);
    expect(useRunStore.getState().status).toBe("failed");
    expect(useRunStore.getState().error).toMatch(/^Dashboard: R1\/R is bound by/);
  });
});

// ------------------------------------------------------------------ the tab

describe("DashboardTab", () => {
  beforeEach(() => {
    resetRunStore();
    resetDashboardUi();
    useCatalogStore.getState().setCatalog(catalog);
    vi.stubGlobal("fetch", () => new Promise(() => {}));
  });

  afterEach(() => {
    resetRunStore();
    vi.unstubAllGlobals();
    useCatalogStore.getState().reset();
  });

  function loadRun(): void {
    const signals = [runSignal("C1/v", { unit: "V" }), runSignal("L1/i", { unit: "A" })];
    useRunStore.setState({
      runId: "run-test",
      manifest: runManifest(signals, { time: { n: 3, t0: 0, t1: 0.01 } }),
      status: "done",
      data: {
        key: "k",
        time: new Float64Array([0, 0.005, 0.01]),
        values: {
          "C1/v": new Float64Array([0, 1, 1.2]),
          "L1/i": new Float64Array([0, 0.02, 0.06]),
        },
      },
    });
  }

  it("renders labelled cards and shows values at the cursor or the latest", () => {
    openModel(model());
    loadRun();
    render(<DashboardTab />);
    const value = screen.getByTestId("dash-card-c2");
    expect(within(value).getByRole("heading", { name: "v_C" })).toBeTruthy();
    expect(screen.getByTestId("dash-value-c2").textContent).toContain("1.200");

    act(() => useRunStore.getState().setCursorTime(0.0025));
    expect(screen.getByTestId("dash-value-c2").textContent).toContain("0.500");
    const gauge = screen.getByRole("meter", { name: /L1\/i at t = 0.003 s|L1\/i at t = 0.0025 s/ });
    expect(Number(gauge.getAttribute("aria-valuenow"))).toBeCloseTo(0.01);
    expect(screen.getByTestId("dash-indicator-c5").getAttribute("data-state")).toBe("off");

    act(() => useRunStore.getState().setCursorTime(null));
    expect(screen.getByTestId("dash-indicator-c5").getAttribute("data-state")).toBe("on");
    expect(screen.getByTestId("dash-summary").textContent).toMatch(/2 parameter overrides, 2 scheduled changes/);
  });

  it("changes input values with the keyboard and the slider", () => {
    openModel(model());
    render(<DashboardTab />);
    const knob = screen.getByRole("slider", { name: "L1/L" });
    const before = Number(knob.getAttribute("aria-valuenow"));
    fireEvent.keyDown(knob, { key: "ArrowUp" });
    const card = () => useDocumentStore.getState().doc?.dashboard?.cards.find((c) => c.id === "c8");
    expect(card()?.value).toBeGreaterThan(before);

    fireEvent.change(screen.getByTestId("dash-slider-c7"), { target: { value: "20" } });
    expect(useDocumentStore.getState().doc?.dashboard?.cards.find((c) => c.id === "c7")?.value).toBe(20);

    const number = screen.getByTestId("dash-number-c9");
    fireEvent.change(number, { target: { value: "abc" } });
    fireEvent.keyDown(number, { key: "Enter" });
    expect(screen.getByRole("alert").textContent).toMatch(/not a number/);
    fireEvent.change(number, { target: { value: "3.5" } });
    fireEvent.keyDown(number, { key: "Enter" });
    expect(useDocumentStore.getState().doc?.dashboard?.cards.find((c) => c.id === "c9")?.value).toBe(3.5);
  });

  it("shows the global that drives a block parameter and binds the card to it", () => {
    const doc = structuredClone(globalModel) as unknown as Model;
    doc.dashboard = {
      cards: [{ id: "s", kind: "slider", size: "2x1", parameter: "Source/Rate/value", options: { min: 0, max: 20, step: 1 } }],
    };
    openModel(doc);
    render(<DashboardTab />);
    // The slider shows the value the global gives (8), not the slider minimum.
    expect((screen.getByTestId("dash-slider-s") as HTMLInputElement).value).toBe("8");
    expect(screen.getByTestId("dash-driven-s").textContent).toMatch(/driven by global rate = 8/);
    fireEvent.click(screen.getByTestId("dash-bind-global-s"));
    const card = useDocumentStore.getState().doc?.dashboard?.cards[0];
    expect(card?.parameter).toBe("global:rate");
    expect(card?.value).toBeUndefined();
    expect(screen.queryByTestId("dash-driven-s")).toBeNull();
  });

  it("adds, edits and removes cards in edit mode; a schedule row is added sorted", () => {
    openModel(model([]));
    render(<DashboardTab />);
    expect(screen.getByText("No cards yet")).toBeTruthy();
    fireEvent.click(screen.getByTestId("dash-edit-toggle"));
    fireEvent.click(screen.getByTestId("dash-add-card"));
    fireEvent.click(screen.getByTestId("dash-add-schedule"));
    // The settings of the new card open; close them.
    expect(useDashboardUi.getState().settingsCardId).toBe("card-1");
    act(() => useDashboardUi.getState().openSettings(null));
    fireEvent.change(screen.getByTestId("dash-schedule-card-1-add-column"), { target: { value: "R1/R" } });
    fireEvent.click(screen.getByTestId("dash-schedule-card-1-add-row"));
    fireEvent.click(screen.getByTestId("dash-schedule-card-1-add-row"));
    const schedule = () => useDocumentStore.getState().doc?.dashboard?.cards[0]?.schedule;
    expect(schedule()?.parameters).toEqual(["R1/R"]);
    expect(schedule()?.rows.map((r) => r.values[0])).toEqual([10, 10]);
    expect(schedule()?.rows[0]?.t).toBe(0);
    // Editing t re-sorts the rows.
    const t1 = screen.getByTestId("dash-schedule-card-1-t-1");
    fireEvent.change(t1, { target: { value: "0" } });
    fireEvent.blur(t1);
    expect(screen.getAllByRole("alert")[0]?.textContent).toMatch(/already row 1/);

    fireEvent.click(screen.getByTestId("dash-card-remove-card-1"));
    expect(useDocumentStore.getState().doc?.dashboard).toBeUndefined();
  });

  it("binds a dropped signal to a display card", () => {
    openModel(model([{ id: "v", kind: "value", size: "1x1" }]));
    loadRun();
    render(<DashboardTab />);
    const card = screen.getByTestId("dash-card-v");
    const data = new Map<string, string>([["application/x-bgsim-signal", "L1/i"]]);
    const dataTransfer = {
      types: [...data.keys()],
      getData: (type: string) => data.get(type) ?? "",
      dropEffect: "none",
    };
    fireEvent.dragOver(card, { dataTransfer });
    fireEvent.drop(card, { dataTransfer });
    expect(useDocumentStore.getState().doc?.dashboard?.cards[0]?.signals).toEqual(["L1/i"]);
    // The real store fetches the newly subscribed signal; here the data is set again.
    act(() => loadRun());
    expect(screen.getByTestId("dash-value-v").textContent).toContain("0.06");
  });
});
