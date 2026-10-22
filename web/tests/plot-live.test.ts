/**
 * Live tails (plan 7.5): the run store opens `WS /ws/runs/{id}`, subscribes
 * the plotted ids, appends `run.tail` payloads to the in-memory series,
 * ignores tails for other runs or after completion, and stops cleanly on
 * `run.done` with a final `/data` refresh.
 *
 * The WebSocket is a small fake with the browser's four handler properties;
 * the fetch layer is stubbed at the same boundary the real API uses.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useDocumentStore } from "../src/state/documentStore";
import { createEmptyModel } from "../src/state/modelFactory";
import {
  liveSeriesFor,
  resetRunStore,
  useRunStore,
} from "../src/plot/runStore";
import { RUN_DATA_HEADER_BYTES } from "../src/plot/runData";
import { runManifest, runSignal } from "./plotFixtures";

const LIVE_SIGNALS = [
  runSignal("Synth/sine", { unit: "V", kind: "output", path: "Synth" }),
  runSignal("Synth/step", { unit: "V", kind: "output", path: "Synth" }),
];

type Handler = ((event: Event) => void) | null;

class FakeSocket {
  static instances: FakeSocket[] = [];

  readyState = 0;
  readonly sent: string[] = [];
  closed = false;
  onopen: Handler = null;
  onclose: Handler = null;
  onerror: Handler = null;
  onmessage: ((event: MessageEvent) => void) | null = null;

  constructor(readonly url: string) {
    FakeSocket.instances.push(this);
  }

  open(): void {
    this.readyState = 1;
    this.onopen?.({} as Event);
  }

  send(data: string): void {
    this.sent.push(data);
  }

  close(): void {
    if (this.closed) {
      return;
    }
    this.closed = true;
    this.readyState = 3;
    this.onclose?.({} as Event);
  }

  message(payload: unknown): void {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent);
  }

  subscriptions(): string[][] {
    return this.sent.map(
      (message) =>
        (JSON.parse(message) as { subscribe?: string[] }).subscribe ?? [],
    );
  }
}

function frame(time: number[], columns: number[][]): ArrayBuffer {
  const buffer = new ArrayBuffer(
    RUN_DATA_HEADER_BYTES + (columns.length + 1) * time.length * 8,
  );
  const view = new DataView(buffer);
  view.setUint32(0, columns.length, true);
  view.setUint32(4, time.length, true);
  const floats = new Float64Array(buffer, RUN_DATA_HEADER_BYTES);
  floats.set(time, 0);
  columns.forEach((column, index) => {
    floats.set(column, (index + 1) * time.length);
  });
  return buffer;
}

let dataRequests: string[] = [];

function stubFetch(): void {
  dataRequests = [];
  vi.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    if (method === "POST") {
      return new Response(JSON.stringify({ runId: "run-live" }), {
        status: 201,
        headers: { "content-type": "application/json" },
      });
    }
    if (method === "DELETE") {
      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }
    if (url.includes("/data?")) {
      dataRequests.push(url);
      const ids = new URL(url, "http://bgsim.test").searchParams.get("ids");
      const count = (ids ?? "").split(",").filter(Boolean).length;
      const body = frame(
        [0, 0.05, 0.1],
        Array.from({ length: count }, (_, index) => [0, index, index * 2]),
      );
      return new Response(body, {
        status: 200,
        headers: { "content-type": "application/octet-stream" },
      });
    }
    return new Response(
      JSON.stringify(
        runManifest(LIVE_SIGNALS, {
          id: "run-live",
          status: "running",
          time: { n: 0, t0: 0, t1: 1 },
        }),
      ),
      { status: 200, headers: { "content-type": "application/json" } },
    );
  });
}

beforeEach(() => {
  resetRunStore();
  FakeSocket.instances = [];
  vi.stubGlobal("WebSocket", FakeSocket);
  stubFetch();
  useDocumentStore.setState({
    project: "live-project",
    modelName: "LiveModel",
    doc: createEmptyModel("LiveModel"),
  });
});

afterEach(() => {
  resetRunStore();
  vi.unstubAllGlobals();
  useDocumentStore.setState({ project: null, modelName: null, doc: null });
});

async function startLiveRun(): Promise<FakeSocket> {
  await useRunStore.getState().startRun();
  await vi.waitFor(() => {
    expect(useRunStore.getState().runId).toBe("run-live");
    expect(FakeSocket.instances).toHaveLength(1);
  });
  const socket = FakeSocket.instances[0] as FakeSocket;
  socket.open();
  return socket;
}

describe("live streaming", () => {
  it("subscribes the plotted ids and appends run.tail payloads", async () => {
    const socket = await startLiveRun();
    expect(useRunStore.getState().status).toBe("running");

    useRunStore.getState().addSignal("Synth/sine");
    expect(socket.subscriptions().at(-1)).toEqual(["Synth/sine"]);

    const before = useRunStore.getState().liveVersion;
    socket.message({
      method: "run.tail",
      params: {
        runId: "run-live",
        ids: ["Synth/sine"],
        t0: 0,
        t1: 0.1,
        time: [0, 0.05, 0.1],
        values: [[0, 1, 0]],
      },
    });

    const live = liveSeriesFor("run-live");
    expect(live?.time).toEqual([0, 0.05, 0.1]);
    expect(live?.values["Synth/sine"]).toEqual([0, 1, 0]);
    expect(useRunStore.getState().liveVersion).toBeGreaterThan(before);
  });

  it("keeps the tail for a second signal in the same series", async () => {
    const socket = await startLiveRun();
    useRunStore.getState().addSignal("Synth/sine");
    useRunStore.getState().addSignal("Synth/step");
    expect(socket.subscriptions().at(-1)).toEqual(["Synth/sine", "Synth/step"]);

    socket.message({
      method: "run.tail",
      params: {
        runId: "run-live",
        ids: ["Synth/sine", "Synth/step"],
        time: [0, 0.1],
        values: [[0, 1], [0, 2]],
      },
    });
    expect(liveSeriesFor("run-live")?.values).toEqual({
      "Synth/sine": [0, 1],
      "Synth/step": [0, 2],
    });
  });

  it("ignores malformed tails and tails from another run", async () => {
    const socket = await startLiveRun();
    useRunStore.getState().addSignal("Synth/sine");
    socket.message({
      method: "run.tail",
      params: {
        runId: "other-run",
        ids: ["Synth/sine"],
        time: [0, 1],
        values: [[0, 1]],
      },
    });
    socket.message({
      method: "run.tail",
      params: {
        runId: "run-live",
        ids: ["Synth/sine"],
        time: [0, 1],
        values: [["bad", "values"]],
      },
    });
    expect(liveSeriesFor("run-live")).toBeNull();
  });

  it("stops on run.done, closes the socket and refreshes final data", async () => {
    const socket = await startLiveRun();
    useRunStore.getState().addSignal("Synth/sine");
    socket.message({
      method: "run.tail",
      params: {
        runId: "run-live",
        ids: ["Synth/sine"],
        time: [0, 0.1],
        values: [[0, 1]],
      },
    });
    socket.message({
      method: "run.done",
      params: {
        runId: "run-live",
        status: "done",
        stats: {
          compile_s: 0.1,
          sim_s: 0.2,
          steps: 2,
          events: 0,
          states: 1,
          equations: 1,
        },
        diagnostics: [],
      },
    });

    await vi.waitFor(() => {
      expect(useRunStore.getState().status).toBe("done");
      expect(socket.closed).toBe(true);
      expect(dataRequests.length).toBeGreaterThan(0);
    });
    // The final refresh is a raw show-all request (px=0).
    expect(dataRequests.at(-1)).toMatch(/[?&]px=0(&|$)/);
    expect(useRunStore.getState().socketState).toBe("off");

    // A tail already in flight after completion must not extend the series.
    const before = liveSeriesFor("run-live")?.time.length;
    socket.message({
      method: "run.tail",
      params: {
        runId: "run-live",
        ids: ["Synth/sine"],
        time: [0.2],
        values: [[9]],
      },
    });
    expect(liveSeriesFor("run-live")?.time.length).toBe(before);
  });

  it("keeps a pinned previous run when the next run starts", async () => {
    useRunStore.setState({
      runId: "run-old",
      manifest: runManifest(LIVE_SIGNALS, { id: "run-old", status: "done" }),
      status: "done",
    });
    useRunStore.getState().pinRun();
    expect(useRunStore.getState().pinned?.manifest.id).toBe("run-old");

    await startLiveRun();
    expect(useRunStore.getState().pinned?.manifest.id).toBe("run-old");
    expect(useRunStore.getState().runId).toBe("run-live");
  });
});
