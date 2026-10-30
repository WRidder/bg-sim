/**
 * The debug session store: reducers for paused / resumed / done, the routing
 * of run events, the API calls, the breakpoint sync, and the status text.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Breakpoint, PausedInfo } from "../src/contracts/debug";
import { resetBreakpointStore, useBreakpointStore } from "../src/debug/breakpointStore";
import {
  handleRunEvent,
  isDebugging,
  resetDebugStore,
  subscribePaused,
  useDebugStore,
} from "../src/debug/debugStore";
import { blockLabel, formatPauseTime, pausedStatusText } from "../src/debug/format";
import { resetRunStore } from "../src/plot/runStore";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";
import { createEmptyModel } from "../src/state/modelFactory";

function info(overrides: Partial<PausedInfo> = {}): PausedInfo {
  return {
    runId: "r1",
    t: 0.4123,
    tick: 412,
    reason: "breakpoint",
    breakpointId: "bp1",
    location: {
      path: "Ctrl",
      ref: "project:LQGController",
      scope: "@discrete",
      range: { line: 14, col: 9, endLine: 14, endCol: 30 },
    },
    frame: null,
    diagnostics: [],
    ...overrides,
  };
}

function debug() {
  return useDebugStore.getState();
}

interface Call {
  url: string;
  method: string;
  body: unknown;
}

function mockFetch(answer: (call: Call) => { status?: number; body: unknown }): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const call: Call = {
        url,
        method: init?.method ?? "GET",
        body: typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : null,
      };
      calls.push(call);
      const result = answer(call);
      return Promise.resolve(
        new Response(JSON.stringify(result.body), {
          status: result.status ?? 200,
          headers: { "content-type": "application/json" },
        }),
      );
    }),
  );
  return calls;
}

beforeEach(() => {
  window.localStorage.clear();
  resetBreakpointStore();
  resetDebugStore();
});

afterEach(() => {
  resetBreakpointStore();
  resetDebugStore();
});

describe("debug store reducers", () => {
  it("goes running -> paused -> running -> done", () => {
    expect(debug().status).toBe("idle");
    debug().begin("r1");
    expect(debug()).toMatchObject({ runId: "r1", status: "running", pausedInfo: null });
    expect(isDebugging(debug())).toBe(true);

    debug().applyPaused(info());
    expect(debug().status).toBe("paused");
    expect(debug().pausedInfo?.t).toBe(0.4123);
    expect(debug().pauseCount).toBe(1);

    debug().applyResumed("r1");
    expect(debug().status).toBe("running");
    expect(debug().pausedInfo).toBeNull();

    debug().applyPaused(info({ t: 0.5 }));
    expect(debug().pauseCount).toBe(2);
    debug().applyDone("r1");
    expect(debug().status).toBe("done");
    expect(debug().pausedInfo).toBeNull();
    expect(isDebugging(debug())).toBe(false);
  });

  it("ignores messages of other runs and late pauses after done", () => {
    debug().begin("r1");
    debug().applyPaused(info({ runId: "other" }));
    debug().applyResumed("other");
    debug().applyDone("other");
    expect(debug().status).toBe("running");
    expect(debug().pauseCount).toBe(0);

    debug().applyDone("r1");
    debug().applyPaused(info());
    expect(debug().status).toBe("done");
  });

  it("calls the paused listeners and stops after unsubscribe", () => {
    debug().begin("r1");
    const seen: number[] = [];
    const off = subscribePaused((paused) => seen.push(paused.t));
    debug().applyPaused(info({ t: 1 }));
    off();
    debug().applyPaused(info({ t: 2 }));
    expect(seen).toEqual([1]);
  });

  it("routes run events: reset, started (debug), messages", () => {
    mockFetch(() => ({ body: { breakpoints: [] } }));
    handleRunEvent({ type: "started", runId: "r1", debug: true });
    expect(debug()).toMatchObject({ runId: "r1", status: "running" });

    handleRunEvent({ type: "message", method: "debug.paused", params: { ...info() } });
    expect(debug().status).toBe("paused");
    handleRunEvent({ type: "message", method: "debug.resumed", params: { runId: "r1" } });
    expect(debug().status).toBe("running");
    handleRunEvent({ type: "message", method: "run.done", params: { runId: "r1", status: "done" } });
    expect(debug().status).toBe("done");

    handleRunEvent({ type: "reset" });
    expect(debug()).toMatchObject({ runId: null, status: "idle" });

    // A plain run is not a debug run.
    handleRunEvent({ type: "started", runId: "r2", debug: false });
    expect(debug().status).toBe("idle");
  });

  it("rejects a malformed paused message", () => {
    debug().begin("r1");
    handleRunEvent({ type: "message", method: "debug.paused", params: { runId: "r1" } });
    expect(debug().status).toBe("running");
  });
});

describe("debug store API calls", () => {
  it("sends commands to the active run", async () => {
    const calls = mockFetch(() => ({ body: { ok: true } }));
    debug().begin("r1");
    await debug().continueRun();
    await debug().pause();
    await debug().step("statement");
    await debug().runTo(0.75);
    expect(calls.map((call) => [call.method, call.url, call.body])).toEqual([
      ["POST", "/api/runs/r1/debug/continue", {}],
      ["POST", "/api/runs/r1/debug/pause", {}],
      ["POST", "/api/runs/r1/debug/step", { granularity: "statement" }],
      ["POST", "/api/runs/r1/debug/runTo", { t: 0.75 }],
    ]);
    expect(debug().error).toBeNull();
  });

  it("does nothing without a debug run and shows a refusal as an error", async () => {
    const calls = mockFetch(() => ({ status: 409, body: { detail: "run is not paused" } }));
    await debug().continueRun();
    expect(calls).toHaveLength(0);

    debug().begin("r1");
    await debug().step("tick");
    expect(debug().error).toBe("run is not paused");
    debug().clearError();
    expect(debug().error).toBeNull();
  });

  it("evaluates and reads values at the pause", async () => {
    const calls = mockFetch((call) =>
      call.url.includes("/values")
        ? { body: { t: 0.1, values: { "Synthetic/sine": 0.5 } } }
        : { body: { value: 3, type: "Real", size: [], unit: null, diagnostics: [] } },
    );
    await expect(debug().evaluate("1 + 2")).rejects.toThrow(/Start debugging/);
    await expect(debug().values(["a"])).rejects.toThrow(/Start debugging/);

    debug().begin("r1");
    const result = await debug().evaluate("1 + 2", "Ctrl");
    expect(result.value).toBe(3);
    expect(calls[0]).toMatchObject({
      method: "POST",
      url: "/api/runs/r1/evaluate",
      body: { expr: "1 + 2", context: "Ctrl" },
    });
    const values = await debug().values(["Synthetic/sine", "Synthetic/step"]);
    expect(values.values["Synthetic/sine"]).toBe(0.5);
    expect(calls[1]?.url).toBe("/api/runs/r1/values?ids=Synthetic%2Fsine%2CSynthetic%2Fstep");
  });

  it("stores the breakpoint statuses of the server", async () => {
    const calls = mockFetch(() => ({
      body: {
        breakpoints: [
          { id: "bp1", verified: true, resolved: { hooks: 1, paths: ["Ctrl"] }, diagnostics: [] },
          {
            id: "bp2",
            verified: false,
            resolved: { hooks: 0, paths: [] },
            diagnostics: [{ code: "E401", severity: "error", message: "no statement here" }],
          },
        ],
      },
    }));
    useBreakpointStore.getState().loadModel("demo/M");
    useBreakpointStore.getState().toggleLine("project:LQGController", 41);
    useBreakpointStore.getState().toggleLine("project:LQGController", 37);
    debug().begin("r1");
    await debug().syncBreakpoints();
    expect(calls[0]).toMatchObject({ method: "PUT", url: "/api/runs/r1/breakpoints" });
    expect((calls[0]?.body as { breakpoints: Breakpoint[] }).breakpoints).toHaveLength(2);
    expect(debug().statuses.bp1?.verified).toBe(true);
    expect(debug().statuses.bp2?.diagnostics[0]?.code).toBe("E401");
  });

  it("sends the full set whenever the breakpoints change during a debug run", async () => {
    const calls = mockFetch(() => ({ body: { breakpoints: [] } }));
    useBreakpointStore.getState().loadModel("demo/M");
    // Not debugging: no request.
    useBreakpointStore.getState().toggleLine("project:A", 3);
    expect(calls).toHaveLength(0);

    debug().begin("r1");
    useBreakpointStore.getState().toggleLine("project:A", 4);
    await vi.waitFor(() => expect(calls).toHaveLength(1));
    const sent = (calls[0]?.body as { breakpoints: Breakpoint[] }).breakpoints;
    expect(sent.map((entry) => entry.id)).toEqual(["bp1", "bp2"]);

    useBreakpointStore.getState().setEnabled("bp1", false);
    await vi.waitFor(() => expect(calls).toHaveLength(2));
    expect((calls[1]?.body as { breakpoints: Breakpoint[] }).breakpoints[0]?.enabled).toBe(false);
  });
});

describe("pause status text", () => {
  it("reads like the plan example for a statement pause", () => {
    expect(pausedStatusText(info())).toBe("Paused at t = 0.4123 s: LQGController line 14 (Ctrl)");
  });

  it("describes the other reasons", () => {
    const none = { location: null };
    expect(pausedStatusText(info({ ...none, reason: "entry", t: 0 }))).toBe("Paused at t = 0.0000 s (entry)");
    expect(pausedStatusText(info({ ...none, reason: "time" }))).toBe("Paused at t = 0.4123 s (time breakpoint)");
    expect(pausedStatusText(info({ ...none, reason: "event" }))).toBe("Paused at t = 0.4123 s (event)");
    expect(pausedStatusText(info({ ...none, reason: "pause" }))).toBe("Paused at t = 0.4123 s (paused)");
    expect(pausedStatusText(info({ ...none, reason: "step" }))).toBe("Paused at t = 0.4123 s (step)");
    expect(
      pausedStatusText(
        info({
          ...none,
          reason: "exception",
          diagnostics: [{ code: "E901", severity: "error", message: "solver failed" }],
        }),
      ),
    ).toBe("Paused at t = 0.4123 s (exception E901)");
  });

  it("names the watch expression of a watch pause", () => {
    const watch: Breakpoint = {
      id: "bp4",
      enabled: true,
      kind: "watch",
      watch: { expr: 's"Motor1/i" > 5', context: null },
      hitCount: null,
    };
    const paused = info({
      breakpointId: "bp4",
      location: {
        path: "Motor1",
        ref: "inline:Synthetic",
        scope: "watch",
        range: { line: 1, col: 1, endLine: 1, endCol: 2 },
      },
    });
    expect(pausedStatusText(paused, [watch])).toBe('Paused at t = 0.4123 s: watch s"Motor1/i" > 5');
    expect(pausedStatusText(paused, [])).toBe("Paused at t = 0.4123 s: watch");
  });

  it("labels block refs", () => {
    expect(blockLabel("project:LQGController")).toBe("LQGController");
    expect(blockLabel("stdlib:discrete/PIController")).toBe("PIController");
    expect(blockLabel("inline:n7")).toBe("n7");
    expect(formatPauseTime(2)).toBe("2.0000 s");
  });
});

describe("starting a debug run", () => {
  it("posts the breakpoints with the run and follows the run events", async () => {
    useDocumentStore.getState().openDocument("demo", "M", createEmptyModel("M"));
    useBreakpointStore.getState().loadModel("demo/M");
    useBreakpointStore.getState().toggleLine("project:LQGController", 41);
    vi.stubGlobal("WebSocket", undefined);
    const calls = mockFetch((call) => {
      if (call.url.endsWith("/runs") && call.method === "POST") {
        return { body: { runId: "r9" } };
      }
      if (call.url.endsWith("/breakpoints")) {
        return { body: { breakpoints: [] } };
      }
      return { status: 404, body: { detail: "not needed" } };
    });

    await debug().startDebug({ pauseOnEntry: true });
    const post = calls.find((call) => call.url === "/api/projects/demo/runs");
    expect(post?.body).toMatchObject({
      debug: { pauseOnEntry: true, breakpoints: [{ id: "bp1", kind: "line" }] },
    });
    expect(debug()).toMatchObject({ runId: "r9", status: "running" });
    await vi.waitFor(() => expect(calls.some((call) => call.method === "PUT")).toBe(true));

    // A second start while the run is active does nothing.
    const before = calls.length;
    await debug().startDebug();
    expect(calls.length).toBe(before);

    resetRunStore();
    expect(debug().status).toBe("idle");
    resetDocumentStore();
  });
});
