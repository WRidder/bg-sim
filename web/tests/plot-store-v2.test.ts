/**
 * Plot v2 store behaviour (plan 7.5): bulk plotting, splitting a panel's
 * third unit group, the global inspect time, live-follow state, compare pins
 * across a zoom, and the CSV export selection.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { runExportUrl } from "../src/plot/runApi";
import {
  getInspectTime,
  isLiveFollowing,
  resetRunStore,
  subscribeInspectTime,
  useRunStore,
} from "../src/plot/runStore";
import { runManifest, runSignal } from "./plotFixtures";

const SIGNALS = [
  runSignal("A/v1", { unit: "V", kind: "output" }),
  runSignal("A/v2", { unit: "V", kind: "output" }),
  runSignal("A/speed", { unit: "rad/s", kind: "state" }),
  runSignal("A/current", { unit: "A", kind: "state" }),
  runSignal("A/power", { unit: "W", kind: "power" }),
];

function loadRun(): void {
  useRunStore.setState({
    runId: "run-test",
    manifest: runManifest(SIGNALS),
    status: "done",
    activePanelId: useRunStore.getState().panels[0]?.id ?? "",
  });
}

beforeEach(() => {
  resetRunStore();
  loadRun();
  vi.stubGlobal("fetch", () => new Promise(() => {}));
});

afterEach(() => {
  resetRunStore();
  vi.unstubAllGlobals();
});

describe("addSignals", () => {
  it("plots all ids with one placement pass and one notice", () => {
    const added = useRunStore.getState().addSignals(SIGNALS.map((signal) => signal.id));
    expect(added).toBe(5);

    const state = useRunStore.getState();
    // V and rad/s fit the first panel; A (third group) starts the second;
    // W (the fourth group) continues in that second panel.
    expect(state.panels).toHaveLength(2);
    expect(state.panels[0]?.signals).toEqual(["A/v1", "A/v2", "A/speed"]);
    expect(state.panels[1]?.signals).toEqual(["A/current", "A/power"]);
    expect(state.notice).toMatch(/Plotted 5 signals/);
  });

  it("skips unknown and already-plotted ids", () => {
    const store = useRunStore.getState();
    store.addSignal("A/v1");
    const added = store.addSignals(["A/v1", "A/v2", "does/not/exist"]);

    expect(added).toBe(1);
    expect(useRunStore.getState().panels[0]?.signals).toEqual(["A/v1", "A/v2"]);
    expect(useRunStore.getState().notice).toMatch(/already plotted/);
    expect(useRunStore.getState().notice).toMatch(/not in this run/);
  });

  it("reports when there is no run at all", () => {
    resetRunStore();
    expect(useRunStore.getState().addSignals(["A/v1"])).toBe(0);
    expect(useRunStore.getState().notice).toMatch(/Run the model/);
  });
});

describe("splitPanel", () => {
  it("moves the third and later unit groups to a new panel", () => {
    const store = useRunStore.getState();
    store.addSignal("A/v1"); // V
    store.addSignal("A/speed"); // rad/s -> two groups, one panel
    const first = useRunStore.getState().panels[0]?.id ?? "";
    store.addSignal("A/current", first, { force: true }); // A forced in

    expect(useRunStore.getState().panels).toHaveLength(1);
    expect(useRunStore.getState().notice).toMatch(/3 unit groups/);

    const split = useRunStore.getState().splitPanel(first);
    expect(split).toBe(true);
    const state = useRunStore.getState();
    expect(state.panels).toHaveLength(2);
    expect(state.panels[0]?.signals).toEqual(["A/v1", "A/speed"]);
    expect(state.panels[1]?.signals).toEqual(["A/current"]);
    expect(state.activePanelId).toBe(state.panels[1]?.id);
    expect(state.notice).toMatch(/Moved 1 signal from Panel 1 to Panel 2/);
  });

  it("does nothing for a panel with two unit groups", () => {
    const store = useRunStore.getState();
    store.addSignal("A/v1");
    store.addSignal("A/speed");
    const first = useRunStore.getState().panels[0]?.id ?? "";

    expect(useRunStore.getState().splitPanel(first)).toBe(false);
    expect(useRunStore.getState().panels).toHaveLength(1);
    expect(useRunStore.getState().notice).toMatch(/nothing to split/);
  });
});

describe("global inspect time", () => {
  it("is stored in seconds and published to subscribers", () => {
    const seen: (number | null)[] = [];
    const unsubscribe = subscribeInspectTime((time) => seen.push(time));

    useRunStore.getState().setCursorTime(1.25);
    expect(getInspectTime()).toBe(1.25);
    useRunStore.getState().setCursorTime(null);
    expect(getInspectTime()).toBeNull();

    expect(seen).toEqual([1.25, null]);
    unsubscribe();
    useRunStore.getState().setCursorTime(2);
    expect(seen).toEqual([1.25, null]);
  });

  it("resets with the run", () => {
    useRunStore.getState().setCursorTime(0.5);
    resetRunStore();
    expect(getInspectTime()).toBeNull();
  });
});

describe("live following", () => {
  it("follows only while running and not zoomed", () => {
    useRunStore.setState({ status: "running", view: null });
    expect(isLiveFollowing()).toBe(true);

    useRunStore.setState({ view: { t0: 0, t1: 0.5 } });
    expect(isLiveFollowing()).toBe(false);

    useRunStore.setState({ status: "done" });
    expect(isLiveFollowing()).toBe(false);
  });

  it("followLive returns to show-all while running", () => {
    useRunStore.setState({ status: "running", view: { t0: 0, t1: 0.5 } });
    useRunStore.getState().followLive();
    expect(useRunStore.getState().view).toBeNull();

    useRunStore.setState({ status: "done", view: { t0: 0, t1: 0.5 } });
    useRunStore.getState().followLive();
    expect(useRunStore.getState().view).not.toBeNull();
  });
});

describe("compare pin", () => {
  it("keeps the pinned run across a zoom", () => {
    const store = useRunStore.getState();
    store.pinRun();
    expect(useRunStore.getState().pinned?.manifest.id).toBe("run-test");

    useRunStore.getState().setView({ t0: 0.2, t1: 0.8 }, 1200);
    expect(useRunStore.getState().pinned?.manifest.id).toBe("run-test");

    useRunStore.getState().unpinRun();
    expect(useRunStore.getState().pinned).toBeNull();
    expect(useRunStore.getState().compareData).toBeNull();
  });

  it("refuses to pin while the run is still going", () => {
    useRunStore.setState({ status: "running" });
    useRunStore.getState().pinRun();
    expect(useRunStore.getState().pinned).toBeNull();
    expect(useRunStore.getState().notice).toMatch(/finished/);
  });
});

describe("CSV export selection", () => {
  it("lists the plotted ids in request order", () => {
    const url = new URL(
      runExportUrl("run-7", ["A/v1", "A/speed"]),
      "http://bgsim.test",
    );
    expect(url.pathname).toBe("/api/runs/run-7/export.csv");
    expect(url.searchParams.get("ids")).toBe("A/v1,A/speed");
  });

  it("sends no ids when nothing is plotted (the backend exports all)", () => {
    const url = new URL(runExportUrl("run-7", []), "http://bgsim.test");
    expect(url.search).toBe("");
  });
});
