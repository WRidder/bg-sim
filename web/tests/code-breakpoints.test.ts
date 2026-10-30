/**
 * The gutter extension (W4.1): which entries a source shows, the marker state
 * (filled / hollow / dashed / arrow), the tooltips, the pause line, and the
 * store sync.
 */

import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  attachBreakpointSync,
  breakpointGutter,
  gutterEntriesFor,
  gutterEntriesOf,
  markerState,
  pausedLineIn,
  pausedLineOf,
  setGutterEntries,
  storeHandlers,
  type GutterEntry,
  type GutterHandlers,
} from "../src/code/breakpoints";
import type { BreakpointStatus, PausedInfo } from "../src/contracts/debug";
import { resetBreakpointStore, useBreakpointStore } from "../src/debug/breakpointStore";
import { resetDebugStore, useDebugStore } from "../src/debug/debugStore";

const REF = "project:LQGController";
const SOURCE = Array.from({ length: 12 }, (_, index) => `line ${index + 1}`).join("\n");

function paused(line: number, ref = REF): PausedInfo {
  return {
    runId: "r1",
    t: 0.1,
    tick: 10,
    reason: "breakpoint",
    breakpointId: null,
    location: {
      path: "LQG",
      ref,
      scope: "@discrete",
      range: { line, col: 1, endLine: line, endCol: 5 },
    },
    frame: null,
    diagnostics: [],
  };
}

function status(id: string, verified: boolean, code?: string): BreakpointStatus {
  return {
    id,
    verified,
    resolved: { hooks: verified ? 1 : 0, paths: verified ? ["LQG"] : [] },
    diagnostics:
      code === undefined
        ? []
        : [{ code, severity: "error", message: "equations do not execute in order", hint: "add a watch" }],
  };
}

let host: HTMLElement;
let views: EditorView[] = [];

function makeView(handlers: GutterHandlers): EditorView {
  const view = new EditorView({
    state: EditorState.create({ doc: SOURCE, extensions: [breakpointGutter(() => handlers)] }),
    parent: host,
  });
  views.push(view);
  return view;
}

const noHandlers: GutterHandlers = {
  onToggle: () => undefined,
  onEdit: () => undefined,
  onMoved: () => undefined,
};

beforeEach(() => {
  window.localStorage.clear();
  resetBreakpointStore();
  resetDebugStore();
  host = document.createElement("div");
  document.body.append(host);
});

afterEach(() => {
  for (const view of views) {
    view.destroy();
  }
  views = [];
  host.remove();
  resetBreakpointStore();
  resetDebugStore();
});

describe("gutterEntriesFor", () => {
  beforeEach(() => {
    useBreakpointStore.getState().loadModel("demo/M");
  });

  it("is hollow (unverified) before any debug run", () => {
    useBreakpointStore.getState().toggleLine(REF, 5);
    const entries = gutterEntriesFor(REF, useBreakpointStore.getState().breakpoints, {}, null);
    expect(entries).toHaveLength(1);
    expect(entries[0]).toMatchObject({ line: 5, id: "bp1", verified: null, enabled: true });
    expect(markerState(entries[0] as GutterEntry)).toBe("unverified");
    expect(entries[0]?.title).toContain("checked when a debug run starts");
  });

  it("uses the server status: verified is filled, E401 stays hollow with the message", () => {
    useBreakpointStore.getState().toggleLine(REF, 5);
    useBreakpointStore.getState().toggleLine(REF, 3);
    const entries = gutterEntriesFor(
      REF,
      useBreakpointStore.getState().breakpoints,
      { bp1: status("bp1", true), bp2: status("bp2", false, "E401") },
      null,
    );
    expect(entries.map((entry) => entry.line)).toEqual([3, 5]);
    expect(markerState(entries[0] as GutterEntry)).toBe("unverified");
    expect(entries[0]?.title).toContain("E401: equations do not execute in order add a watch");
    expect(markerState(entries[1] as GutterEntry)).toBe("verified");
  });

  it("marks disabled breakpoints and shows condition and hit count", () => {
    const id = useBreakpointStore.getState().toggleLine(REF, 5) as string;
    useBreakpointStore.getState().setCondition(id, "k == 5");
    let entries = gutterEntriesFor(REF, useBreakpointStore.getState().breakpoints, { [id]: status(id, true) }, null);
    expect(entries[0]).toMatchObject({ conditional: true, hitCount: false });
    expect(entries[0]?.title).toContain("when k == 5");

    useBreakpointStore.getState().setHitCount(id, 4);
    useBreakpointStore.getState().setEnabled(id, false);
    entries = gutterEntriesFor(REF, useBreakpointStore.getState().breakpoints, { [id]: status(id, true) }, null);
    expect(entries[0]).toMatchObject({ enabled: false, hitCount: true });
    expect(markerState(entries[0] as GutterEntry)).toBe("disabled");
  });

  it("only lists the breakpoints of its own source", () => {
    useBreakpointStore.getState().toggleLine(REF, 5);
    useBreakpointStore.getState().toggleLine("inline:n1", 6);
    useBreakpointStore.getState().toggleLine("stdlib:discrete/PI", 7);
    expect(gutterEntriesFor("inline:n1", useBreakpointStore.getState().breakpoints, {}, null)).toHaveLength(1);
    expect(gutterEntriesFor("stdlib:discrete/PI", useBreakpointStore.getState().breakpoints, {}, null)).toHaveLength(1);
  });

  it("adds the pause arrow, on a breakpoint line or alone", () => {
    useBreakpointStore.getState().toggleLine(REF, 5);
    const list = useBreakpointStore.getState().breakpoints;
    let entries = gutterEntriesFor(REF, list, {}, paused(5));
    expect(entries).toHaveLength(1);
    expect(entries[0]).toMatchObject({ id: "bp1", paused: true });

    entries = gutterEntriesFor(REF, list, {}, paused(8));
    expect(entries.map((entry) => [entry.line, entry.id, entry.paused])).toEqual([
      [5, "bp1", false],
      [8, null, true],
    ]);
    expect(markerState(entries[1] as GutterEntry)).toBe("pause");

    // A pause in another block, or a watch pause, shows nothing here.
    expect(gutterEntriesFor(REF, list, {}, paused(8, "project:Other")).some((entry) => entry.paused)).toBe(false);
    expect(pausedLineIn(REF, paused(8))).toBe(8);
    expect(pausedLineIn("project:Other", paused(8))).toBeNull();
    expect(pausedLineIn(REF, null)).toBeNull();
    const watch = paused(8);
    if (watch.location !== null) {
      watch.location.scope = "watch";
    }
    expect(pausedLineIn(REF, watch)).toBeNull();
  });
});

describe("breakpoint gutter extension", () => {
  it("draws filled, hollow, dashed and arrow markers with tooltips", () => {
    const view = makeView(noHandlers);
    const base = { conditional: false, hitCount: false, paused: false };
    view.dispatch({
      effects: setGutterEntries.of([
        { ...base, line: 2, id: "bp1", enabled: true, verified: true, title: "verified one" },
        { ...base, line: 3, id: "bp2", enabled: true, verified: false, title: "E401: not a statement" },
        { ...base, line: 4, id: "bp3", enabled: false, verified: true, title: "off" },
        { ...base, line: 6, id: null, enabled: true, verified: null, title: "Paused here", paused: true },
        { ...base, line: 99, id: "bp9", enabled: true, verified: true, title: "beyond the text" },
      ]),
    });
    const markers = [...host.querySelectorAll<HTMLElement>('[data-testid="bp-marker"]')];
    expect(markers.map((marker) => [marker.dataset.line, marker.dataset.state])).toEqual([
      ["2", "verified"],
      ["3", "unverified"],
      ["4", "disabled"],
      ["6", "pause"],
    ]);
    expect(markers[1]?.title).toContain("E401");
    expect(markers[3]?.textContent).toBe("▶");
    expect(gutterEntriesOf(view)).toHaveLength(4);
    // The line past the end of the text is not drawn.
    expect(host.querySelector('[data-line="99"]')).toBeNull();
  });

  it("highlights the paused line and clears it on resume", () => {
    const view = makeView(noHandlers);
    const base = { conditional: false, hitCount: false };
    view.dispatch({
      effects: setGutterEntries.of([
        { ...base, line: 7, id: null, enabled: true, verified: null, title: "p", paused: true },
      ]),
    });
    const highlighted = [...host.querySelectorAll(".cm-line.cm-paused-line")];
    expect(highlighted).toHaveLength(1);
    expect(highlighted[0]?.textContent).toBe("line 7");
    expect(pausedLineOf(view)).toBe(7);

    view.dispatch({ effects: setGutterEntries.of([]) });
    expect(host.querySelector(".cm-paused-line")).toBeNull();
    expect(pausedLineOf(view)).toBeNull();
  });

  it("toggles on F9 for the line of the caret", () => {
    const toggled: number[] = [];
    const view = makeView({ ...noHandlers, onToggle: (line) => toggled.push(line) });
    view.dispatch({ selection: { anchor: view.state.doc.line(4).from + 2 } });
    view.contentDOM.dispatchEvent(new KeyboardEvent("keydown", { key: "F9", bubbles: true }));
    expect(toggled).toEqual([4]);
  });

  it("reports a breakpoint that moved with the text", async () => {
    const moved: [string, number][] = [];
    const view = makeView({ ...noHandlers, onMoved: (id, line) => moved.push([id, line]) });
    const base = { conditional: false, hitCount: false, paused: false };
    view.dispatch({
      effects: setGutterEntries.of([
        { ...base, line: 5, id: "bp1", enabled: true, verified: true, title: "t" },
      ]),
    });
    view.dispatch({ changes: { from: 0, insert: "new first line\n" } });
    await Promise.resolve();
    expect(moved).toEqual([["bp1", 6]]);
  });
});

describe("attachBreakpointSync", () => {
  it("follows the breakpoint store and the debug store", () => {
    useBreakpointStore.getState().loadModel("demo/M");
    const handlers = storeHandlers({ ref: REF, onEdit: () => undefined });
    const view = makeView(handlers);
    const detach = attachBreakpointSync(view, REF);
    expect(gutterEntriesOf(view)).toHaveLength(0);

    handlers.onToggle(5);
    expect(gutterEntriesOf(view).map((entry) => [entry.line, entry.id])).toEqual([[5, "bp1"]]);
    expect(host.querySelector('[data-testid="bp-marker"]')?.getAttribute("data-state")).toBe("unverified");

    useDebugStore.getState().begin("r1");
    useDebugStore.setState({ statuses: { bp1: status("bp1", true) } });
    expect(host.querySelector('[data-testid="bp-marker"]')?.getAttribute("data-state")).toBe("verified");

    useDebugStore.getState().applyPaused(paused(8));
    expect(pausedLineOf(view)).toBe(8);
    expect(host.querySelector(".cm-paused-line")?.textContent).toBe("line 8");

    useDebugStore.getState().applyResumed("r1");
    expect(pausedLineOf(view)).toBeNull();

    handlers.onToggle(5);
    expect(gutterEntriesOf(view)).toHaveLength(0);

    detach();
    handlers.onToggle(6);
    expect(gutterEntriesOf(view)).toHaveLength(0);
  });
});
