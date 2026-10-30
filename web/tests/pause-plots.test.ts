/**
 * W4.3 (plan 7.9, "At a pause"): the pause marker plugin, the clipping and choice of the plotted series,
 * the pause time the plots follow, what a pause does to the inspect time, and the rewind enablement rules.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PausedInfo } from "../src/contracts/debug";
import type { RunManifest } from "../src/contracts/run-manifest";
import { resetDebugStore, useDebugStore } from "../src/debug/debugStore";
import {
  chooseSeries,
  clipSeriesAtPause,
  countUpTo,
  pauseMarkerPlugin,
} from "../src/plot/pauseMarker";
import {
  rewindAvailability,
  rewindToHere,
  type RewindContext,
} from "../src/plot/pauseRewind";
import { applyPauseToPlots, pauseTimeOf } from "../src/plot/pauseState";
import { resetRunStore, useRunStore } from "../src/plot/runStore";

function series(times: number[]) {
  return { time: times, values: { a: times.map((t) => t * 2) } };
}

function paused(overrides: Partial<PausedInfo> = {}): PausedInfo {
  return {
    runId: "r1",
    t: 0.084,
    tick: null,
    reason: "breakpoint",
    breakpointId: null,
    location: null,
    frame: null,
    diagnostics: [],
    ...overrides,
  };
}

describe("clipping and choosing the series at a pause", () => {
  it("counts the samples up to the pause time", () => {
    expect(countUpTo([0, 0.1, 0.2, 0.3], 0.2)).toBe(3);
    expect(countUpTo([0, 0.1, 0.2, 0.3], 0.15)).toBe(2);
    expect(countUpTo([], 1)).toBe(0);
  });

  it("cuts a series that runs past the pause and keeps the columns aligned", () => {
    const clipped = clipSeriesAtPause(series([0, 0.1, 0.2, 0.3]), 0.2);
    expect(Array.from(clipped?.time ?? [])).toEqual([0, 0.1, 0.2]);
    expect(Array.from(clipped?.values.a ?? [])).toEqual([0, 0.2, 0.4]);
  });

  it("returns the same object when nothing is cut or the run is not paused", () => {
    const data = series([0, 0.1]);
    expect(clipSeriesAtPause(data, 0.1)).toBe(data);
    expect(clipSeriesAtPause(data, null)).toBe(data);
    expect(clipSeriesAtPause(null, 0.1)).toBeNull();
  });

  it("plots live when running and prefers data that reaches the pause when paused", () => {
    const live = series([0, 0.05, 0.1]);
    const stale = series([0, 0.05]);
    const fresh = series([0, 0.05, 0.084]);
    expect(chooseSeries(live, stale, null)).toBe(live);
    expect(chooseSeries(null, stale, null)).toBe(stale);
    // the stale fetch does not reach the pause, the live tail does (and is cut at the pause)
    expect(Array.from(chooseSeries(live, stale, 0.084)?.time ?? [])).toEqual([0, 0.05]);
    expect(Array.from(chooseSeries(live, fresh, 0.084)?.time ?? [])).toEqual([0, 0.05, 0.084]);
  });

  it("falls back to the live tail, clipped at the pause, while the fetch is in flight", () => {
    const live = series([0, 0.05, 0.084, 0.09]);
    const stale = series([0, 0.05]);
    expect(Array.from(chooseSeries(live, stale, 0.084)?.time ?? [])).toEqual([0, 0.05, 0.084]);
  });
});

describe("the pause marker plugin", () => {
  function fakeChart(pauseSpan: { min: number; max: number }) {
    const host = document.createElement("div");
    const root = document.createElement("div");
    host.appendChild(root);
    const calls: string[] = [];
    const ctx = {
      save: () => calls.push("save"),
      restore: () => calls.push("restore"),
      beginPath: () => undefined,
      rect: () => undefined,
      clip: () => undefined,
      moveTo: (x: number) => calls.push(`moveTo:${x}`),
      lineTo: () => undefined,
      stroke: () => calls.push("stroke"),
      setLineDash: (dash: number[]) => calls.push(`dash:${dash.length}`),
      measureText: () => ({ width: 30 }),
      fillText: (text: string) => calls.push(`text:${text}`),
      strokeStyle: "",
      fillStyle: "",
      lineWidth: 1,
      font: "",
      textAlign: "",
      textBaseline: "",
    };
    const chart = {
      root,
      ctx,
      bbox: { left: 10, top: 5, width: 200, height: 100 },
      valToPos: (value: number, _scale: string, canvas?: boolean) =>
        (canvas === true ? 10 : 0) +
        ((value - pauseSpan.min) / (pauseSpan.max - pauseSpan.min)) * 200,
    };
    return { host, chart, calls };
  }

  function draw(plugin: ReturnType<typeof pauseMarkerPlugin>, chart: unknown): void {
    const hook = plugin.hooks.draw;
    const fn = Array.isArray(hook) ? hook[0] : hook;
    (fn as (u: unknown) => void)(chart);
  }

  it("draws a dashed line and the label at the pause time and publishes the test hooks", () => {
    const { host, chart, calls } = fakeChart({ min: 0, max: 0.1 });
    draw(pauseMarkerPlugin({ getTime: () => 0.05 }), chart);
    expect(calls).toContain("stroke");
    expect(calls).toContain("text:paused");
    expect(calls.some((entry) => entry.startsWith("dash:2"))).toBe(true);
    // x = 10 + 0.5 * 200 on the canvas
    expect(calls).toContain("moveTo:110");
    expect(host.dataset.pauseTime).toBe("0.05");
    expect(Number(host.dataset.pauseX)).toBeCloseTo(100, 1);
  });

  it("is removed on resume: nothing is drawn and the hooks are cleared", () => {
    const { host, chart, calls } = fakeChart({ min: 0, max: 0.1 });
    let time: number | null = 0.05;
    const plugin = pauseMarkerPlugin({ getTime: () => time });
    draw(plugin, chart);
    expect(host.dataset.pauseTime).toBe("0.05");
    calls.length = 0;
    time = null;
    draw(plugin, chart);
    expect(calls).toEqual([]);
    expect(host.dataset.pauseTime).toBeUndefined();
    expect(host.dataset.pauseX).toBeUndefined();
  });

  it("draws nothing outside the visible window but still reports the pause time", () => {
    const { host, chart, calls } = fakeChart({ min: 0, max: 0.1 });
    draw(pauseMarkerPlugin({ getTime: () => 0.5 }), chart);
    expect(calls).toEqual([]);
    expect(host.dataset.pauseTime).toBe("0.5");
    expect(host.dataset.pauseX).toBeUndefined();
  });
});

describe("the pause time the plots follow", () => {
  it("is the pause time only for the paused run that is shown", () => {
    const info = paused();
    expect(pauseTimeOf({ status: "paused", runId: "r1", pausedInfo: info }, "r1")).toBe(0.084);
    expect(pauseTimeOf({ status: "paused", runId: "r1", pausedInfo: info }, "r2")).toBeNull();
    expect(pauseTimeOf({ status: "running", runId: "r1", pausedInfo: null }, "r1")).toBeNull();
    expect(pauseTimeOf({ status: "done", runId: "r1", pausedInfo: null }, "r1")).toBeNull();
  });
});

describe("a pause moves the inspect time", () => {
  beforeEach(() => {
    resetRunStore();
    resetDebugStore();
  });

  it("sets the cursor to the pause time of the shown run and ignores another run", () => {
    useRunStore.setState({ runId: "r1", cursorTime: 0.5 });
    applyPauseToPlots(paused({ runId: "r2", t: 0.3 }));
    expect(useRunStore.getState().cursorTime).toBe(0.5);
    applyPauseToPlots(paused({ runId: "r1", t: 0.084 }));
    expect(useRunStore.getState().cursorTime).toBe(0.084);
  });
});

function manifestOf(overrides: Partial<RunManifest> & { t1?: number } = {}): RunManifest {
  const { t1 = 1, ...rest } = overrides;
  return {
    id: "r1",
    time: { t0: 0, t1, n: 11 },
    ...rest,
  } as unknown as RunManifest;
}

function context(overrides: Partial<RewindContext> = {}): RewindContext {
  return {
    runId: "r1",
    runStatus: "done",
    manifest: manifestOf(),
    debugStatus: "idle",
    debugRunId: null,
    pauseTime: null,
    ...overrides,
  };
}

describe("rewind enablement", () => {
  it("is enabled for a finished run at an earlier time", () => {
    expect(rewindAvailability(context(), 0.4)).toEqual({ enabled: true, reason: null });
  });

  it("is enabled for a paused debug run before the pause time", () => {
    const paused = context({
      runStatus: "running",
      debugStatus: "paused",
      debugRunId: "r1",
      pauseTime: 0.084,
      manifest: manifestOf({ t1: 0.084 }),
    });
    expect(rewindAvailability(paused, 0.05).enabled).toBe(true);
    expect(rewindAvailability(paused, 0.084).enabled).toBe(false);
    expect(rewindAvailability(paused, 0.2).enabled).toBe(false);
  });

  it("needs a cursor time earlier than the run's current time", () => {
    expect(rewindAvailability(context(), null).enabled).toBe(false);
    const late = rewindAvailability(context(), 1);
    expect(late.enabled).toBe(false);
    expect(late.reason).toContain("before");
    expect(rewindAvailability(context(), 1.5).enabled).toBe(false);
  });

  it("is disabled without a run or while the run is running unpaused", () => {
    expect(rewindAvailability(context({ runId: null, manifest: null }), 0.4).enabled).toBe(false);
    const running = context({ runStatus: "running", debugStatus: "running", debugRunId: "r1" });
    expect(rewindAvailability(running, 0.4).enabled).toBe(false);
    expect(rewindAvailability(running, 0.4).reason).toContain("Pause");
  });
});

describe("rewind follows the branch run", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    resetRunStore();
    resetDebugStore();
  });

  it("posts the branch time and follows the new run as a debug run", async () => {
    const calls: { url: string; body: unknown }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => {
        calls.push({ url, body: typeof init?.body === "string" ? JSON.parse(init.body) : null });
        return Promise.resolve(
          new Response(JSON.stringify({ runId: "branch1" }), {
            status: 201,
            headers: { "content-type": "application/json" },
          }),
        );
      }),
    );
    const startRun = vi.fn(() => Promise.resolve());
    useRunStore.setState({ runId: "r1", status: "done", startRun });
    const id = await rewindToHere(0.25);
    expect(id).toBe("branch1");
    expect(calls[0]?.url).toContain("/api/runs/r1/branch");
    expect(calls[0]?.body).toEqual({ t: 0.25 });
    expect(startRun).toHaveBeenCalledTimes(1);
    const options = (startRun.mock.calls as unknown as [{ followRunId: string; debug: { pauseOnEntry: boolean } }][])[0]?.[0];
    expect(options?.followRunId).toBe("branch1");
    expect(options?.debug.pauseOnEntry).toBe(false);
    // the debug store adopts the branch run like any debug run
    useDebugStore.getState().begin("branch1");
    expect(useDebugStore.getState().runId).toBe("branch1");
  });

  it("reports the backend's refusal", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify({ detail: "no manifest for run r1" }), { status: 404 }),
        ),
      ),
    );
    useRunStore.setState({ runId: "r1", status: "done" });
    await expect(rewindToHere(0.25)).rejects.toThrow("no manifest for run r1");
  });
});
