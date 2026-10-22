/**
 * Panel assignment in the run store (plan 7.5): the first two unit groups go
 * on one panel, a third starts a new one, and removing panels/signals keeps the
 * active panel valid.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resetRunStore, useRunStore } from "../src/plot/runStore";
import { runManifest, runSignal } from "./plotFixtures";

const SIGNALS = [
  runSignal("A/v1", { unit: "V", kind: "output" }),
  runSignal("A/v2", { unit: "V", kind: "output" }),
  runSignal("A/count", { unit: null, kind: "state", type: "Int" }),
  runSignal("A/speed", { unit: "rad/s", kind: "state" }),
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
  // The store may start a /data request; it is irrelevant to panel assignment.
  vi.stubGlobal("fetch", () => new Promise(() => {}));
});

afterEach(() => {
  resetRunStore();
  vi.unstubAllGlobals();
});

describe("addSignal", () => {
  it("keeps two unit groups on one panel", () => {
    const store = useRunStore.getState();
    store.addSignal("A/v1");
    store.addSignal("A/v2");
    store.addSignal("A/count");

    const state = useRunStore.getState();
    expect(state.panels).toHaveLength(1);
    expect(state.panels[0]?.signals).toEqual(["A/v1", "A/v2", "A/count"]);
    expect(state.activePanelId).toBe(state.panels[0]?.id);
  });

  it("starts a new panel when a third unit group arrives", () => {
    const store = useRunStore.getState();
    store.addSignal("A/v1");
    store.addSignal("A/count");
    store.addSignal("A/speed");

    const state = useRunStore.getState();
    expect(state.panels).toHaveLength(2);
    expect(state.panels[0]?.signals).toEqual(["A/v1", "A/count"]);
    expect(state.panels[1]?.signals).toEqual(["A/speed"]);
    expect(state.activePanelId).toBe(state.panels[1]?.id);
    expect(state.notice).toMatch(/third|two unit groups|started Panel 2/);
  });

  it("does not add the same signal to the same panel twice", () => {
    const store = useRunStore.getState();
    store.addSignal("A/v1");
    store.addSignal("A/v1");
    expect(useRunStore.getState().panels[0]?.signals).toEqual(["A/v1"]);
  });

  it("reports an unknown signal without changing the panels", () => {
    const store = useRunStore.getState();
    store.addSignal("does/not/exist");
    expect(useRunStore.getState().panels[0]?.signals).toEqual([]);
    expect(useRunStore.getState().notice).toMatch(/no signal/);
  });
});

describe("removeSignal and removePanel", () => {
  it("removes a signal from its panel and leaves the panel in place", () => {
    const store = useRunStore.getState();
    store.addSignal("A/v1");
    store.addSignal("A/v2");
    store.removeSignal(useRunStore.getState().panels[0]!.id, "A/v1");

    const state = useRunStore.getState();
    expect(state.panels).toHaveLength(1);
    expect(state.panels[0]?.signals).toEqual(["A/v2"]);
  });

  it("keeps one panel and clears it instead of deleting the last one", () => {
    const store = useRunStore.getState();
    store.addSignal("A/v1");
    store.removePanel(useRunStore.getState().panels[0]!.id);

    const state = useRunStore.getState();
    expect(state.panels).toHaveLength(1);
    expect(state.panels[0]?.signals).toEqual([]);
  });

  it("moves the active panel to a neighbour when the active one is removed", () => {
    const store = useRunStore.getState();
    store.addSignal("A/v1");
    store.addSignal("A/count");
    store.addSignal("A/speed");
    const second = useRunStore.getState().panels[1]!.id;
    expect(useRunStore.getState().activePanelId).toBe(second);

    store.removePanel(second);
    const state = useRunStore.getState();
    expect(state.panels).toHaveLength(1);
    expect(state.activePanelId).toBe(state.panels[0]?.id);
  });
});

describe("reset", () => {
  it("returns to one empty panel, no run and no pin", () => {
    const store = useRunStore.getState();
    store.addSignal("A/v1");
    store.pinRun();
    expect(useRunStore.getState().pinned).not.toBeNull();

    resetRunStore();
    const state = useRunStore.getState();
    expect(state.runId).toBeNull();
    expect(state.manifest).toBeNull();
    expect(state.status).toBe("idle");
    expect(state.panels).toHaveLength(1);
    expect(state.panels[0]?.signals).toEqual([]);
    expect(state.pinned).toBeNull();
    expect(state.view).toBeNull();
  });
});
