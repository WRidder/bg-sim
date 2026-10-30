/**
 * The Debug panels (W4.2): the dock tab sections rendered from the contract
 * fixtures, the watch expressions re-evaluated at every pause, the Break-when
 * dialog and the expression it writes, the 16 watch slots, the break-on
 * switches, the edits (replay, save) and the Explain popover.
 */

import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useCodeSessionStore } from "../src/code/codeSession";
import type { ExplainResult, PausedInfo } from "../src/contracts/debug";
import type { Model } from "../src/contracts/model";
import type { RunManifest } from "../src/contracts/run-manifest";
import { resetBreakpointStore, useBreakpointStore } from "../src/debug/breakpointStore";
import { resetDebugStore, useDebugStore } from "../src/debug/debugStore";
import { ExplainBody, ExplainPopover } from "../src/debug/explain/ExplainPopover";
import { useExplainStore } from "../src/debug/explain/explainStore";
import {
  applyCompletion,
  completionFor,
  COMPARISONS,
  parseWatchValue,
  signalIdsOfExpression,
  watchExpression,
  watchSlotsText,
} from "../src/debug/panels/breakWhen";
import { BreakWhenDialog } from "../src/debug/panels/BreakWhenDialog";
import { openBreakWhen, useBreakWhenStore } from "../src/debug/panels/breakWhenStore";
import { DebugPanel } from "../src/debug/panels/DebugPanel";
import { applyParameterChanges, parameterChangesOf } from "../src/debug/panels/editsModel";
import { formatFrameValue, formatNumber } from "../src/debug/panels/frameFormat";
import {
  resetWatchExpressionStore,
  useWatchExpressionStore,
} from "../src/debug/panels/watchExpressionStore";
import { SignalBrowser } from "../src/plot/SignalBrowser";
import { resetRunStore, useRunStore } from "../src/plot/runStore";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";
import { createEmptyModel } from "../src/state/modelFactory";

const fixtureDir = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../contracts/fixtures/debug/valid",
);

function fixture<T>(name: string): T {
  return JSON.parse(readFileSync(path.join(fixtureDir, name), "utf8")) as T;
}

const statementPause = fixture<PausedInfo>("paused.statement.json");
const watchPause = fixture<PausedInfo>("paused.watch.json");

interface Call {
  url: string;
  method: string;
  body: Record<string, unknown> | null;
}

let calls: Call[] = [];
let answer: (call: Call) => { status?: number; body: unknown } = () => ({ body: {} });

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

function startDebugRun(runId: string): void {
  useDebugStore.getState().begin(runId);
}

function pause(info: PausedInfo): void {
  act(() => {
    useDebugStore.getState().applyPaused(info);
  });
}

beforeEach(() => {
  window.localStorage.clear();
  resetDocumentStore();
  resetRunStore();
  resetBreakpointStore();
  resetDebugStore();
  resetWatchExpressionStore();
  useBreakWhenStore.getState().close();
  useExplainStore.getState().close();
  useCodeSessionStore.getState().close();
  calls = [];
  answer = () => ({ body: {} });
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const call: Call = {
        url,
        method: init?.method ?? "GET",
        body: typeof init?.body === "string" ? (JSON.parse(init.body) as Record<string, unknown>) : null,
      };
      calls.push(call);
      const result = answer(call);
      return Promise.resolve(json(result.body, result.status ?? 200));
    }),
  );
});

afterEach(() => {
  resetDocumentStore();
  resetRunStore();
  resetBreakpointStore();
  resetDebugStore();
  resetWatchExpressionStore();
});

describe("break-when expressions", () => {
  it("writes the expression for each comparison", () => {
    const written = COMPARISONS.map((option) => watchExpression("Motor1/i", option.value, " 5 "));
    expect(written).toEqual([
      's"Motor1/i" > 5',
      's"Motor1/i" < 5',
      's"Motor1/i" >= 5',
      's"Motor1/i" <= 5',
    ]);
  });

  it("accepts numbers only", () => {
    expect(parseWatchValue("0.5")).toBe(0.5);
    expect(parseWatchValue("-1e-3")).toBe(-0.001);
    expect(parseWatchValue(" .25 ")).toBe(0.25);
    expect(parseWatchValue("")).toBeNull();
    expect(parseWatchValue("abc")).toBeNull();
    expect(parseWatchValue("1,5")).toBeNull();
  });

  it("finds the signal ids of an expression and completes s\" prefixes", () => {
    expect(signalIdsOfExpression('s"a/b" > 1 && s"c" < s"a/b"')).toEqual(["a/b", "c"]);
    const ids = ["Motor1/i", "Motor1/w", "Load/w"];
    const text = 's"Mo';
    const completion = completionFor(text, text.length, ids);
    expect(completion?.options).toEqual(["Motor1/i", "Motor1/w"]);
    expect(completionFor("t > 1", 5, ids)).toBeNull();
    expect(completionFor('ts"Mo', 5, ids)).toBeNull();
    expect(completionFor('s"Motor1/i" > 1', 14, ids)).toBeNull();
    if (completion !== null) {
      expect(applyCompletion(text, text.length, completion, "Motor1/w")).toEqual({
        text: 's"Motor1/w"',
        caret: 11,
      });
    }
  });

  it("counts the watch slots of the breakpoint list", () => {
    const watch = (id: string) =>
      ({ id, enabled: false, kind: "watch", watch: { expr: "t > 1", context: null } }) as const;
    expect(watchSlotsText([])).toBe("0 / 16 watch slots");
    expect(watchSlotsText([watch("bp1"), watch("bp2")])).toBe("2 / 16 watch slots");
  });

  it("formats values for the panels", () => {
    expect(formatNumber(0.12)).toBe("0.12");
    expect(formatNumber(1 / 3)).toBe("0.333333");
    expect(formatNumber(5)).toBe("5");
    expect(formatFrameValue([[1, 0], [0, 1]], [2, 2])).toBe("[[1, 0], [0, 1]]");
    expect(formatFrameValue(true)).toBe("true");
  });
});

describe("the Break-when dialog", () => {
  function manifestWith(signals: { id: string; unit: string | null }[]): void {
    useRunStore.setState({
      manifest: {
        id: "r0",
        signals: signals.map((signal) => ({ ...signal, kind: "observed", path: "Motor1", type: "Real" })),
      } as unknown as RunManifest,
    });
  }

  it("preselects the signal, shows its unit and adds a watch breakpoint for each comparison", () => {
    manifestWith([{ id: "Motor1/i", unit: "A" }]);
    render(<BreakWhenDialog />);
    act(() => openBreakWhen("Motor1/i", ["Motor1/i", "Motor1/w"]));
    expect(screen.getByTestId("break-when-signal")).toHaveProperty("value", "Motor1/i");
    expect(screen.getByText("Value (A)")).toBeTruthy();

    const expected: string[] = [];
    for (const option of COMPARISONS) {
      fireEvent.change(screen.getByTestId("break-when-comparison"), { target: { value: option.value } });
      fireEvent.change(screen.getByTestId("break-when-value"), { target: { value: "5" } });
      expect(screen.getByTestId("break-when-preview").textContent).toContain(
        `s"Motor1/i" ${option.value} 5`,
      );
      fireEvent.click(screen.getByTestId("break-when-add"));
      expected.push(`s"Motor1/i" ${option.value} 5`);
      expect(screen.queryByTestId("break-when-dialog")).toBeNull();
      act(() => openBreakWhen("Motor1/i"));
    }
    const exprs = useBreakpointStore
      .getState()
      .breakpoints.map((entry) => (entry.kind === "watch" ? entry.watch.expr : ""));
    expect(exprs).toEqual(expected);
  });

  it("refuses a non-numeric value without adding anything", () => {
    render(<BreakWhenDialog />);
    act(() => openBreakWhen("Motor1/i"));
    fireEvent.change(screen.getByTestId("break-when-value"), { target: { value: "five" } });
    fireEvent.click(screen.getByTestId("break-when-add"));
    expect(screen.getByTestId("break-when-error").textContent).toContain("number");
    expect(useBreakpointStore.getState().breakpoints).toHaveLength(0);
  });

  it("takes an advanced expression with signal-id completion", () => {
    manifestWith([{ id: "Motor1/i", unit: "A" }, { id: "Motor1/w", unit: "rad/s" }]);
    render(<BreakWhenDialog />);
    act(() => openBreakWhen("Motor1/i"));
    const details = screen.getByText("Advanced").closest("details") as HTMLDetailsElement;
    details.open = true;
    fireEvent(details, new Event("toggle"));
    const input = screen.getByTestId("break-when-advanced") as HTMLInputElement;
    input.focus();
    fireEvent.change(input, { target: { value: 's"Motor1/w' } });
    input.setSelectionRange(10, 10);
    fireEvent.select(input);
    const list = screen.getByTestId("break-when-completion");
    expect(within(list).getAllByRole("option").map((option) => option.textContent)).toEqual(["Motor1/w"]);
    fireEvent.mouseDown(within(list).getByText("Motor1/w"));
    expect(input.value).toBe('s"Motor1/w"');
    fireEvent.change(input, { target: { value: 's"Motor1/w" > 2 && t > 0.1' } });
    fireEvent.click(screen.getByTestId("break-when-add"));
    const [added] = useBreakpointStore.getState().breakpoints;
    expect(added?.kind === "watch" && added.watch.expr).toBe('s"Motor1/w" > 2 && t > 0.1');
  });

  it("warns that the 17th watch will be refused, and shows the server's refusal during a debug run", async () => {
    for (let index = 0; index < 16; index += 1) {
      useBreakpointStore.getState().add({
        enabled: true,
        kind: "watch",
        watch: { expr: `t > ${index}`, context: null },
        hitCount: null,
      });
    }
    render(<BreakWhenDialog />);
    act(() => openBreakWhen("Motor1/i"));
    expect(screen.getByTestId("break-when-slots").textContent).toContain("16 / 16");
    fireEvent.change(screen.getByTestId("break-when-value"), { target: { value: "1" } });
    fireEvent.click(screen.getByTestId("break-when-add"));
    expect(screen.getByTestId("break-when-error").textContent).toContain("All 16 watch slots are used");
    expect(useBreakpointStore.getState().breakpoints).toHaveLength(17);

    // During a debug run the server answers the full set; the 17th is not verified.
    useBreakpointStore.getState().clear();
    for (let index = 0; index < 16; index += 1) {
      useBreakpointStore.getState().add({
        enabled: true,
        kind: "watch",
        watch: { expr: `t > ${index}`, context: null },
        hitCount: null,
      });
    }
    act(() => useBreakWhenStore.getState().close());
    startDebugRun("r1");
    answer = (call) => {
      const list = (call.body?.breakpoints ?? []) as { id: string }[];
      return {
        body: {
          breakpoints: list.map((entry, index) => ({
            id: entry.id,
            verified: index < 16,
            resolved: { hooks: 0, paths: [] },
            diagnostics:
              index < 16
                ? []
                : [{ code: "E001", severity: "error", message: "at most 16 watch breakpoints", hint: "remove or disable another watch breakpoint first" }],
          })),
        },
      };
    };
    act(() => openBreakWhen("Motor1/i"));
    fireEvent.change(screen.getByTestId("break-when-value"), { target: { value: "1" } });
    await act(async () => {
      fireEvent.click(screen.getByTestId("break-when-add"));
    });
    await waitFor(() => expect(screen.getByTestId("break-when-refused")).toBeTruthy());
    expect(screen.getByTestId("break-when-refused").textContent).toContain("at most 16 watch breakpoints");
  });
});

describe("the Debug panel", () => {
  it("shows guidance when no debug run exists, and while it is running", () => {
    render(<DebugPanel />);
    expect(screen.getByTestId("variables-empty").textContent).toContain("Start a debug run (F5)");
    expect(screen.getByTestId("breakpoints-empty")).toBeTruthy();
    expect(screen.getByTestId("edits-empty")).toBeTruthy();
    expect(screen.getByTestId("watch-expressions-empty")).toBeTruthy();
    act(() => startDebugRun("r1"));
    expect(screen.getByTestId("variables-empty").textContent).toContain("running");
  });

  it("renders the frame of a statement pause: locals, held outputs, previous values, matrices expand", () => {
    answer = () => ({ body: { t: 0.4123, values: {} } });
    render(<DebugPanel />);
    startDebugRun(statementPause.runId);
    pause(statementPause);
    expect(screen.getByTestId("variables-pause").textContent).toContain("0.4123");
    expect(screen.getByTestId("var-locals-v-value").textContent).toBe("0.12");
    expect(screen.getByTestId("var-locals-k-value").textContent).toBe("5");
    expect(screen.getByTestId("var-locals-on-value").textContent).toBe("true");
    const matrix = screen.getByTestId("var-locals-x");
    expect(within(matrix).getByTestId("var-locals-x-value").textContent).toBe("[[1, 0], [0, 1]]");
    expect(within(matrix).getAllByText(/^\[\d\]$/).length).toBeGreaterThan(0);
    expect(screen.getByTestId("variables-held")).toBeTruthy();
    expect(screen.queryByTestId("variables-previous")).toBeNull();
    expect(screen.queryByTestId("variables-no-frame")).toBeNull();
  });

  it("at a watch pause explains the missing frame and reads the watched and selected signals", async () => {
    const model = createEmptyModel("M");
    model.diagram.nodes.push({
      id: "n1",
      name: "Motor1",
      block: { ref: "stdlib:converters/DCMotor" },
      position: { x: 0, y: 0 },
    });
    useDocumentStore.getState().openDocument("project", "M", model);
    useDocumentStore.getState().setSelection(["n1"], []);
    useRunStore.setState({
      manifest: {
        id: "r1",
        signals: [
          { id: "Motor1/i", unit: "A", kind: "observed", path: "Motor1", type: "Real" },
          { id: "Motor1/w", unit: "rad/s", kind: "state", path: "Motor1", type: "Real" },
          { id: "Other/x", unit: null, kind: "state", path: "Other", type: "Real" },
        ],
      } as unknown as RunManifest,
    });
    useBreakpointStore.getState().add({
      enabled: true,
      kind: "watch",
      watch: { expr: 's"Synthetic/sine" > 0.5', context: null },
      hitCount: null,
    });
    answer = () => ({ body: { t: 0.084, values: { "Motor1/i": 1.5, "Motor1/w": 20, "Synthetic/sine": 0.51 } } });
    render(<DebugPanel />);
    startDebugRun("r1");
    pause({ ...watchPause, runId: "r1" });
    expect(screen.getByTestId("variables-no-frame")).toBeTruthy();
    await waitFor(() => expect(screen.getAllByTestId("var-signal-value").map((el) => el.textContent)).toEqual(["1.5", "20", "0.51"]));
    const ids = screen.getAllByTestId("var-signal").map((el) => el.getAttribute("data-signal-id"));
    expect(ids).toEqual(["Motor1/i", "Motor1/w", "Synthetic/sine"]);
    const request = calls.find((call) => call.url.includes("/values"));
    expect(decodeURIComponent(request?.url ?? "")).toContain("ids=Motor1/i,Motor1/w,Synthetic/sine");
  });

  it("re-evaluates the watch expressions at every pause and shows errors with their message", async () => {
    let round = 0;
    answer = (call) => {
      if (!call.url.includes("/evaluate")) {
        return { body: { t: 0, values: {} } };
      }
      if (call.body?.expr === "bad(") {
        return {
          body: {
            value: 0,
            type: "Real",
            size: [],
            unit: null,
            diagnostics: [{ code: "E001", severity: "error", message: "unexpected end of expression", hint: "close the bracket" }],
          },
        };
      }
      round += 1;
      return { body: { value: round * 10, type: "Real", size: [], unit: "V", diagnostics: [] } };
    };
    render(<DebugPanel />);
    startDebugRun("r1");
    pause({ ...watchPause, runId: "r1" });
    fireEvent.change(screen.getByTestId("watch-expression-input"), { target: { value: 't * 2' } });
    fireEvent.click(screen.getByTestId("watch-expression-add"));
    await waitFor(() => expect(screen.getByTestId("watch-expression-value").textContent).toBe("10 V"));

    pause({ ...watchPause, runId: "r1", t: 0.2 });
    await waitFor(() => expect(screen.getByTestId("watch-expression-value").textContent).toBe("20 V"));
    expect(calls.filter((call) => call.url.includes("/evaluate"))).toHaveLength(2);

    fireEvent.change(screen.getByTestId("watch-expression-input"), { target: { value: "bad(" } });
    fireEvent.click(screen.getByTestId("watch-expression-add"));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("unexpected end of expression close the bracket"));

    // Resuming drops the results; the expressions stay (and persist per model).
    act(() => useDebugStore.getState().applyResumed("r1"));
    expect(screen.getAllByTestId("watch-expression-value").map((el) => el.textContent)).toEqual(["—", "—"]);
    expect(useWatchExpressionStore.getState().items.map((item) => item.expr)).toEqual(["t * 2", "bad("]);

    fireEvent.click(screen.getAllByTestId("watch-expression-remove")[0] as HTMLElement);
    expect(useWatchExpressionStore.getState().items.map((item) => item.expr)).toEqual(["bad("]);
  });

  it("lists every breakpoint kind with its verified state and the server's diagnostics", () => {
    const store = useBreakpointStore.getState();
    const line = store.add({
      enabled: true,
      kind: "line",
      line: { ref: "project:LQGController", line: 37, path: null },
      condition: null,
      hitCount: null,
    });
    const watch = store.add({ enabled: true, kind: "watch", watch: { expr: 's"a" > 1', context: null }, hitCount: null });
    store.add({ enabled: true, kind: "time", time: { t: 0.25 } });
    store.add({ enabled: false, kind: "event", event: { path: null } });
    store.add({ enabled: true, kind: "exception", exception: { on: ["E901"] } });
    startDebugRun("r1");
    useDebugStore.setState({
      statuses: {
        [line]: {
          id: line,
          verified: false,
          resolved: { hooks: 0, paths: [] },
          diagnostics: [{ code: "E401", severity: "error", message: "line 37 is not a statement", hint: "use a watch breakpoint" }],
        },
        [watch]: { id: watch, verified: true, resolved: { hooks: 1, paths: ["Motor1"] }, diagnostics: [] },
      },
    });
    render(<DebugPanel />);
    const rows = screen.getAllByTestId("breakpoint-row");
    expect(rows.map((row) => row.getAttribute("data-kind"))).toEqual(["line", "watch", "time", "event", "exception"]);
    expect(rows[0]?.getAttribute("data-verified")).toBe("false");
    expect(within(rows[0] as HTMLElement).getByTestId("breakpoint-diagnostics").textContent).toContain("E401");
    expect(rows[1]?.getAttribute("data-verified")).toBe("true");
    expect(screen.getByTestId("watch-slots").textContent).toBe("1 / 16 watch slots");
    for (const kind of ["Line", "Watch", "Time", "Event", "Exception"]) {
      expect(screen.getAllByRole("img", { name: `${kind} breakpoint` })).toHaveLength(1);
    }

    // Toggle and delete go through the breakpoint store.
    fireEvent.click(within(rows[3] as HTMLElement).getByTestId("breakpoint-enable"));
    expect(useBreakpointStore.getState().breakpoints.find((entry) => entry.kind === "event")?.enabled).toBe(true);
    fireEvent.click(within(rows[1] as HTMLElement).getByTestId("breakpoint-delete"));
    expect(screen.getByTestId("watch-slots").textContent).toBe("0 / 16 watch slots");
  });

  it("the break-on switches create and merge the event and exception breakpoints", () => {
    render(<DebugPanel />);
    fireEvent.click(screen.getByTestId("break-on-events"));
    fireEvent.click(screen.getByTestId("break-on-E901"));
    fireEvent.click(screen.getByTestId("break-on-W206"));
    let list = useBreakpointStore.getState().breakpoints;
    expect(list.map((entry) => entry.kind)).toEqual(["event", "exception"]);
    const exception = list.find((entry) => entry.kind === "exception");
    expect(exception?.kind === "exception" && exception.exception.on).toEqual(["E901", "W206"]);
    expect((screen.getByTestId("break-on-W206") as HTMLInputElement).checked).toBe(true);

    fireEvent.click(screen.getByTestId("break-on-E901"));
    list = useBreakpointStore.getState().breakpoints;
    const rest = list.find((entry) => entry.kind === "exception");
    expect(rest?.kind === "exception" && rest.exception.on).toEqual(["W206"]);
    fireEvent.click(screen.getByTestId("break-on-W206"));
    fireEvent.click(screen.getByTestId("break-on-events"));
    list = useBreakpointStore.getState().breakpoints;
    expect(list.filter((entry) => entry.kind === "exception")).toHaveLength(0);
    expect(list.find((entry) => entry.kind === "event")?.enabled).toBe(false);
  });
});

describe("the Edits section", () => {
  function edits() {
    return [
      { t: 0.1, kind: "parameter", target: "Motor1/R", value: 2 },
      { t: 0.2, kind: "parameter", target: "Motor1/R", value: 2.5 },
      { t: 0.2, kind: "state", target: "Motor1/w", value: 3 },
      { t: 0.3, kind: "parameter", target: "Ghost/k", value: 1 },
    ] as const;
  }

  function withManifest(status: string): void {
    useRunStore.setState({
      runId: "r1",
      status: status as "done",
      manifest: { id: "r1", status, signals: [], debug: { breakpoints: [], pauses: [], edits: edits() } } as unknown as RunManifest,
    });
  }

  function openMotorModel(): void {
    const model = createEmptyModel("M");
    model.diagram.nodes.push({
      id: "n1",
      name: "Motor1",
      block: { ref: "stdlib:converters/DCMotor" },
      position: { x: 0, y: 0 },
      params: { R: "1" },
    });
    useDocumentStore.getState().openDocument("project", "M", model);
  }

  it("lists the edits of the session", () => {
    withManifest("done");
    render(<DebugPanel />);
    const rows = screen.getAllByTestId("edit-row");
    expect(rows).toHaveLength(4);
    expect(rows[1]?.textContent).toContain("Motor1/R = 2.5 at t = 0.2000 s");
    expect(rows[2]?.getAttribute("data-kind")).toBe("state");
  });

  it("replays the run and follows the new one", async () => {
    withManifest("done");
    const startRun = vi.fn(() => Promise.resolve());
    const original = useRunStore.getState().startRun;
    useRunStore.setState({ startRun });
    answer = () => ({ body: { runId: "r2" } });
    try {
      render(<DebugPanel />);
      fireEvent.click(screen.getByTestId("edits-replay"));
      await waitFor(() => expect(startRun).toHaveBeenCalledWith({ followRunId: "r2" }));
      const post = calls.find((call) => call.url.endsWith("/api/runs/r1/replay"));
      expect(post?.method).toBe("POST");
    } finally {
      useRunStore.setState({ startRun: original });
    }
  });

  it("disables Replay while the run is not finished and without edits", () => {
    withManifest("paused");
    useRunStore.setState({ status: "paused" });
    render(<DebugPanel />);
    expect((screen.getByTestId("edits-replay") as HTMLButtonElement).disabled).toBe(true);
    act(() => useRunStore.setState({ status: "done", manifest: { id: "r1", status: "done", signals: [] } as unknown as RunManifest }));
    expect((screen.getByTestId("edits-replay") as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByTestId("edits-save") as HTMLButtonElement).disabled).toBe(true);
  });

  it("saves the last value of each edited parameter as one undoable change, skipping state edits", () => {
    openMotorModel();
    withManifest("done");
    render(<DebugPanel />);
    const before = useDocumentStore.getState().past.length;
    fireEvent.click(screen.getByTestId("edits-save"));
    const state = useDocumentStore.getState();
    expect(state.doc?.diagram.nodes[0]?.params).toEqual({ R: "2.5" });
    expect(state.past.length).toBe(before + 1);
    expect(screen.getByTestId("edits-message").textContent).toContain("Ghost/k");
    act(() => useDocumentStore.getState().undo());
    expect(useDocumentStore.getState().doc?.diagram.nodes[0]?.params).toEqual({ R: "1" });
  });

  it("resolves a parameter target through subsystems and reports unknown ones", () => {
    const model = createEmptyModel("M") as Model;
    model.diagram.nodes.push({
      id: "s1",
      name: "Axis",
      block: { subsystem: { ports: [], diagram: { nodes: [{ id: "m", name: "Motor1", block: { ref: "x" }, position: { x: 0, y: 0 } }], connections: [] } } },
      position: { x: 0, y: 0 },
    });
    const { changes, skipped } = parameterChangesOf([
      { t: 0, kind: "parameter", target: "Axis/Motor1/J", value: 0.5 },
      { t: 0, kind: "parameter", target: "J", value: 1 },
    ]);
    expect(skipped).toEqual(["J"]);
    expect(applyParameterChanges(model, changes)).toEqual([]);
    const subsystem = model.diagram.nodes[0]?.block;
    expect(subsystem !== undefined && "subsystem" in subsystem && subsystem.subsystem.diagram.nodes[0]?.params).toEqual({ J: "0.5" });
    expect(applyParameterChanges(model, [{ path: ["Axis", "Nope"], name: "J", value: 1 }])).toEqual(["Axis/Nope/J"]);
  });
});

describe("Explain", () => {
  it("renders an observed signal: kind, unit, expression and a source link", () => {
    const result = fixture<ExplainResult>("explain.observed.json");
    const onNavigate = vi.fn();
    render(<ExplainBody result={result} onNavigate={onNavigate} />);
    expect(screen.getByTestId("explain-kind").textContent).toBe("Observed variable");
    expect(screen.getByTestId("explain-unit").textContent).toBe("A");
    expect(screen.getByTestId("explain-expression").textContent).toContain("Motor1/V");
    const link = screen.getByTestId("explain-origin");
    expect(link.textContent).toBe("converters/DCMotor line 22 (Motor1)");
    fireEvent.click(link);
    expect(onNavigate).toHaveBeenCalled();
    const request = useCodeSessionStore.getState().request;
    expect(request?.detail).toMatchObject({ kind: "stdlib", ref: "stdlib:converters/DCMotor", line: 22, col: 5 });
  });

  it("renders an alias with no source and the findings", () => {
    const result: ExplainResult = {
      ...fixture<ExplainResult>("explain.alias.json"),
      diagnostics: [{ code: "W201", severity: "warning", message: "the signal is an alias", hint: "plot the target" }],
    };
    render(<ExplainBody result={result} />);
    expect(screen.getByTestId("explain-kind").textContent).toBe("Alias");
    expect(screen.getByTestId("explain-alias").textContent).toBe("Load/shaft.f");
    expect(screen.queryByTestId("explain-origin")).toBeNull();
    expect(screen.getByTestId("explain-findings").textContent).toContain("W201");
  });

  it.each([
    ["state", "State variable"],
    ["algebraic", "Algebraic variable"],
    ["parameter", "Parameter"],
    ["discrete", "Discrete signal"],
  ] as const)("renders the %s kind", (kind, text) => {
    render(
      <ExplainBody
        result={{ signal: "a/b", kind, unit: null, expression: null, aliasOf: null, equations: [], diagnostics: [] }}
      />,
    );
    expect(screen.getByTestId("explain-kind").textContent).toBe(text);
    expect(screen.getByTestId("explain-unit").textContent).toBe("dimensionless");
    expect(screen.getByText(/No source equation defines this signal directly/)).toBeTruthy();
  });

  it("loads the result from the backend without a run and shows a failure with what to do", async () => {
    useDocumentStore.getState().openDocument("proj", "M", createEmptyModel("M"));
    answer = () => ({ body: fixture<ExplainResult>("explain.observed.json") });
    render(<ExplainPopover />);
    await act(async () => {
      await useExplainStore.getState().open("Motor1/i");
    });
    expect(screen.getByTestId("explain-title").textContent).toBe("Motor1/i");
    expect(screen.getByTestId("explain-kind").textContent).toBe("Observed variable");
    const call = calls[0];
    expect(call?.url).toContain("/api/check/explain?project=proj");
    expect(call?.body).toMatchObject({ signal: "Motor1/i" });
    expect(useRunStore.getState().runId).toBeNull();

    answer = () => ({ status: 422, body: { detail: "the model has errors" } });
    await act(async () => {
      await useExplainStore.getState().open("Motor1/i");
    });
    expect(screen.getByTestId("explain-error").textContent).toContain("the model has errors");
    fireEvent.keyDown(screen.getByTestId("explain-popover"), { key: "Escape" });
    expect(screen.queryByTestId("explain-popover")).toBeNull();
  });
});

describe("the signal browser menu", () => {
  function renderBrowser(): void {
    useRunStore.setState({
      runId: "run-test",
      status: "done",
      manifest: {
        id: "run-test",
        status: "done",
        signals: [
          { id: "Synthetic/sine", unit: "V", kind: "output", path: "Synthetic", type: "Real" },
          { id: "Synthetic/step", unit: "V", kind: "output", path: "Synthetic", type: "Real" },
        ],
        time: { n: 0, t0: 0, t1: 0 },
        settings: {},
      } as unknown as RunManifest,
    });
    render(<SignalBrowser />);
  }

  function menuFor(signalId: string): void {
    const row = document.querySelector(`[data-signal-id="${signalId}"]`) as HTMLElement;
    fireEvent.contextMenu(row, { clientX: 40, clientY: 50 });
  }

  it("opens Break when... with the signal preselected", () => {
    renderBrowser();
    menuFor("Synthetic/sine");
    expect(screen.getByRole("menu", { name: "Actions for Synthetic/sine" })).toBeTruthy();
    fireEvent.click(screen.getByTestId("break-when"));
    expect(useBreakWhenStore.getState().request?.signalId).toBe("Synthetic/sine");
    expect(screen.queryByTestId("signal-menu")).toBeNull();
  });

  it("opens Explain signal, and Escape closes the menu", async () => {
    useDocumentStore.getState().openDocument("proj", "M", createEmptyModel("M"));
    answer = () => ({ body: fixture<ExplainResult>("explain.observed.json") });
    renderBrowser();
    menuFor("Synthetic/step");
    fireEvent.keyDown(screen.getByTestId("signal-menu"), { key: "Escape" });
    expect(screen.queryByTestId("signal-menu")).toBeNull();
    menuFor("Synthetic/step");
    await act(async () => {
      fireEvent.click(screen.getByTestId("explain-signal"));
    });
    await waitFor(() => expect(useExplainStore.getState().status).toBe("ready"));
    expect(useExplainStore.getState().signalId).toBe("Synthetic/step");
  });
});

describe("the frame groups", () => {
  it("shows the previous values of a statement pause", () => {
    answer = () => ({ body: { t: 0, values: {} } });
    render(<DebugPanel />);
    startDebugRun("r1");
    pause({
      ...statementPause,
      runId: "r1",
      frame: {
        locals: [],
        held: [],
        previous: [{ name: "u_prev", type: "Real", size: [2], value: [0.5, 0.25] }],
      },
    });
    expect(screen.getByTestId("var-previous-u_prev-value").textContent).toBe("[0.5, 0.25]");
  });
});
