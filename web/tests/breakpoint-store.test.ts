/**
 * The breakpoint store (D26): toggling, enable/disable, condition and hit
 * count, per-model persistence, and that everything works without storage.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  bindBreakpointsToDocument,
  breakpointStorageKey,
  readBreakpoints,
  resetBreakpointStore,
  useBreakpointStore,
  writeBreakpoints,
} from "../src/debug/breakpointStore";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";
import { createEmptyModel } from "../src/state/modelFactory";

const REF = "project:LQGController";

function store() {
  return useBreakpointStore.getState();
}

beforeEach(() => {
  window.localStorage.clear();
  resetBreakpointStore();
});

afterEach(() => {
  resetBreakpointStore();
});

describe("breakpoint store", () => {
  it("toggles a line breakpoint on and off with stable ids", () => {
    store().loadModel("demo/Model1");
    const first = store().toggleLine(REF, 41);
    expect(first).toBe("bp1");
    expect(store().breakpoints).toHaveLength(1);
    expect(store().breakpoints[0]).toMatchObject({
      id: "bp1",
      enabled: true,
      kind: "line",
      line: { ref: REF, line: 41, path: null },
      condition: null,
      hitCount: null,
    });

    expect(store().toggleLine(REF, 41)).toBeNull();
    expect(store().breakpoints).toHaveLength(0);

    // Ids are never reused inside a model.
    expect(store().toggleLine(REF, 41)).toBe("bp2");
    expect(store().toggleLine(REF, 42)).toBe("bp3");
  });

  it("keeps breakpoints of different blocks apart", () => {
    store().loadModel("demo/Model1");
    store().toggleLine(REF, 5);
    store().toggleLine("inline:n3", 5);
    expect(store().breakpoints).toHaveLength(2);
    store().toggleLine(REF, 5);
    expect(store().breakpoints.map((entry) => entry.kind === "line" && entry.line.ref)).toEqual([
      "inline:n3",
    ]);
  });

  it("enables, disables, sets a condition and a hit count", () => {
    store().loadModel("demo/Model1");
    const id = store().toggleLine(REF, 41) as string;
    store().setEnabled(id, false);
    store().setCondition(id, "  k == 5 ");
    store().setHitCount(id, 3.9);
    expect(store().breakpoints[0]).toMatchObject({
      enabled: false,
      condition: "k == 5",
      hitCount: 3,
    });

    store().setCondition(id, "   ");
    store().setHitCount(id, 0);
    expect(store().breakpoints[0]).toMatchObject({ condition: null, hitCount: null });
  });

  it("moves a line breakpoint and ignores an unknown id", () => {
    store().loadModel("demo/Model1");
    const id = store().toggleLine(REF, 41) as string;
    store().moveLine(id, 44);
    store().moveLine("bp99", 7);
    store().setEnabled("bp99", false);
    expect(store().breakpoints).toHaveLength(1);
    expect(store().breakpoints[0]).toMatchObject({ line: { line: 44 } });
  });

  it("is generic: it stores watch, time, event and exception kinds", () => {
    store().loadModel("demo/Model1");
    store().add({ enabled: true, kind: "watch", watch: { expr: 's"Motor1/i" > 5', context: null }, hitCount: null });
    store().add({ enabled: true, kind: "time", time: { t: 0.5 } });
    store().add({ enabled: false, kind: "event", event: { path: null } });
    store().add({ enabled: true, kind: "exception", exception: { on: ["E901"] } });
    expect(store().breakpoints.map((entry) => entry.kind)).toEqual(["watch", "time", "event", "exception"]);
    // A condition only exists on line breakpoints.
    store().setCondition("bp1", "x");
    expect(store().breakpoints[0]).not.toHaveProperty("condition");
    store().setHitCount("bp1", 2);
    expect(store().breakpoints[0]).toMatchObject({ hitCount: 2 });
    store().setHitCount("bp2", 2);
    expect(store().breakpoints[1]).not.toHaveProperty("hitCount");
  });
});

describe("breakpoint persistence", () => {
  it("saves per model and restores after a reload", () => {
    store().loadModel("demo/Model1");
    const id = store().toggleLine(REF, 41) as string;
    store().setCondition(id, "k == 5");
    store().toggleLine("inline:n3", 2);

    expect(window.localStorage.getItem(breakpointStorageKey("demo/Model1"))).not.toBeNull();

    // A reload: the store starts empty and loads the model again.
    resetBreakpointStore();
    expect(store().breakpoints).toHaveLength(0);
    store().loadModel("demo/Model1");
    expect(store().breakpoints).toHaveLength(2);
    expect(store().breakpoints[0]).toMatchObject({ id: "bp1", condition: "k == 5" });
    // The id counter continues where it stopped.
    expect(store().toggleLine(REF, 50)).toBe("bp3");
  });

  it("keeps models separate", () => {
    store().loadModel("demo/A");
    store().toggleLine(REF, 41);
    store().loadModel("demo/B");
    expect(store().breakpoints).toHaveLength(0);
    store().toggleLine(REF, 42);
    store().loadModel("demo/A");
    expect(store().breakpoints).toHaveLength(1);
    expect(store().breakpoints[0]).toMatchObject({ line: { line: 41 } });
  });

  it("never touches the model document", () => {
    useDocumentStore.getState().openDocument("demo", "Model1", createEmptyModel("Model1"));
    const before = JSON.stringify(useDocumentStore.getState().doc);
    store().loadModel("demo/Model1");
    store().toggleLine(REF, 41);
    expect(JSON.stringify(useDocumentStore.getState().doc)).toBe(before);
    resetDocumentStore();
  });

  it("ignores corrupt storage and drops invalid entries", () => {
    window.localStorage.setItem(breakpointStorageKey("demo/Model1"), "{not json");
    store().loadModel("demo/Model1");
    expect(store().breakpoints).toEqual([]);

    window.localStorage.setItem(
      breakpointStorageKey("demo/Model2"),
      JSON.stringify({
        version: 1,
        next: 2,
        breakpoints: [
          { id: "bp7", enabled: true, kind: "line", line: { ref: REF, line: 3, path: null } },
          { id: "bp8", enabled: true, kind: "line", line: { ref: REF, line: 0, path: null } },
          { id: "bp7", enabled: true, kind: "time", time: { t: 1 } },
          "garbage",
        ],
      }),
    );
    const read = readBreakpoints("demo/Model2");
    expect(read?.breakpoints).toHaveLength(1);
    // The counter is at least above the highest stored id.
    expect(read?.next).toBe(8);
  });

  it("works when localStorage throws", () => {
    const failing = {
      getItem: () => {
        throw new Error("denied");
      },
      setItem: () => {
        throw new Error("quota");
      },
    };
    vi.stubGlobal("localStorage", failing);
    expect(readBreakpoints("demo/Model1")).toBeNull();
    expect(() => writeBreakpoints("demo/Model1", { breakpoints: [], next: 1 })).not.toThrow();

    store().loadModel("demo/Model1");
    expect(store().toggleLine(REF, 41)).toBe("bp1");
    store().setCondition("bp1", "k == 2");
    store().setEnabled("bp1", false);
    expect(store().breakpoints[0]).toMatchObject({ enabled: false, condition: "k == 2" });
  });

  it("works when localStorage is absent", () => {
    vi.stubGlobal("localStorage", undefined);
    expect(readBreakpoints("demo/Model1")).toBeNull();
    store().loadModel("demo/Model1");
    expect(store().toggleLine(REF, 41)).toBe("bp1");
    expect(store().toggleLine(REF, 41)).toBeNull();
    expect(store().toggleLine(REF, 42)).toBe("bp2");
    expect(store().breakpoints).toHaveLength(1);
  });

  it("follows the open model of the document store", () => {
    bindBreakpointsToDocument();
    useDocumentStore.getState().openDocument("demo", "A", createEmptyModel("A"));
    expect(store().modelKey).toBe("demo/A");
    store().toggleLine(REF, 9);
    useDocumentStore.getState().openDocument("demo", "B", createEmptyModel("B"));
    expect(store().modelKey).toBe("demo/B");
    expect(store().breakpoints).toHaveLength(0);
    useDocumentStore.getState().openDocument("demo", "A", createEmptyModel("A"));
    expect(store().breakpoints).toHaveLength(1);
    resetDocumentStore();
  });
});
