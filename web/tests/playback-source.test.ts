import { describe, expect, it } from "vitest";

import type { RunDataFrame } from "../src/plot/runData";
import { RunApiError } from "../src/plot/runApi";
import { fallbackNote, framesOf, loadOverHttp, openSamples, thinRows, UNREACHABLE, type SourceHandlers } from "../src/viewer/playbackSource";
import { SignalBuffer } from "../src/viewer/timeline";

/** Raw rows of a 1 kHz run with an event at t = 0.5 (two rows with the same time). */
function rawRun(): RunDataFrame {
  const t: number[] = [];
  const a: number[] = [];
  const b: number[] = [];
  for (let i = 0; i <= 1000; i++) {
    t.push(i / 1000);
    a.push(i);
    b.push(-i);
    if (i === 500) {
      t.push(0.5);
      a.push(9999);
      b.push(-9999);
    }
  }
  return { nSignals: 2, nPoints: t.length, time: Float64Array.from(t), values: [Float64Array.from(a), Float64Array.from(b)] };
}

class FakeSocket {
  binaryType = "";
  onmessage: ((e: MessageEvent) => void) | null = null;
  onclose: ((e: CloseEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  close(): void {
    this.closed = true;
  }
}

function collect(): { handlers: SourceHandlers; buffer: () => SignalBuffer | null; ends: { ok: boolean; reason: string }[]; notes: string[] } {
  let buffer: SignalBuffer | null = null;
  const ends: { ok: boolean; reason: string }[] = [];
  const notes: string[] = [];
  const handlers: SourceHandlers = {
    onHandshake: (h) => {
      buffer = new SignalBuffer(h.signals.map((s) => s.id));
    },
    onFrames: (f) => {
      buffer?.append(f);
    },
    onEnd: (e) => {
      ends.push({ ok: e.ok, reason: e.reason });
    },
    onNote: (n) => {
      notes.push(n);
    },
  };
  return { handlers, buffer: () => buffer, ends, notes };
}

const tick = (): Promise<void> => new Promise((resolve) => setTimeout(resolve, 0));

describe("thinRows", () => {
  it("keeps the first row, rows at least 1/60 s apart, collapses equal-time rows and keeps the last row", () => {
    const time = Float64Array.from([0, 0, 0.01, 0.02, 0.04, 0.05, 0.0501]);
    const frames = thinRows(time, [Float64Array.from([1, 2, 3, 4, 5, 6, 7])]);
    // 0 kept; the event twin (0), 0.01 are less than 1/60 s later; 0.02 is kept; 0.04 kept; 0.05 dropped; the last row is kept
    expect(Array.from(frames)).toEqual([0, 1, 0.02, 4, 0.04, 5, 0.0501, 7]);
  });

  it("is empty for no rows and keeps a single row", () => {
    expect(thinRows(new Float64Array(0), [new Float64Array(0)]).length).toBe(0);
    expect(Array.from(thinRows(Float64Array.from([2]), [Float64Array.from([7])]))).toEqual([2, 7]);
  });

  it("thins a 1 kHz run to about 60 Hz and keeps both ends", () => {
    const frames = framesOf(rawRun());
    const rows = frames.length / 3;
    expect(rows).toBeGreaterThanOrEqual(60);
    expect(rows).toBeLessThanOrEqual(62);
    expect(frames[0]).toBe(0);
    expect(frames[frames.length - 3]).toBe(1);
  });
});

describe("openSamples", () => {
  const ids = ["A/a", "A/b"];
  const data = rawRun();
  // what the stream endpoint sends for this run: the same thinning, computed independently of thinRows
  const streamFrames = ((): Float64Array => {
    const kept: number[] = [];
    let last = Number.NEGATIVE_INFINITY;
    const gap = (1 / 60) * (1 - 1e-9);
    data.time.forEach((t, i) => {
      if (i === 0 || t >= last + gap) {
        kept.push(i);
        last = t;
      }
    });
    if ((data.time[data.nPoints - 1] ?? 0) > last) kept.push(data.nPoints - 1);
    return Float64Array.from(kept.flatMap((i) => [data.time[i] ?? 0, data.values[0]?.[i] ?? 0, data.values[1]?.[i] ?? 0]));
  })();

  function viaStream(): SignalBuffer {
    const socket = new FakeSocket();
    const got = collect();
    openSamples("r", ids, "playback", got.handlers, { makeSocket: () => socket as unknown as WebSocket });
    socket.onmessage?.({ data: JSON.stringify({ signals: ids.map((id) => ({ id })), rate: 60, mode: "playback" }) } as MessageEvent);
    socket.onmessage?.({ data: streamFrames.buffer.slice(0) } as MessageEvent);
    socket.onclose?.({ code: 1000, reason: "done" } as CloseEvent);
    expect(got.ends).toEqual([{ ok: true, reason: "done" }]);
    const buffer = got.buffer();
    if (buffer === null) throw new Error("no stream data");
    return buffer;
  }

  it("falls back to HTTP when the socket closes with 1006 and the timeline equals the stream path", async () => {
    const expected = viaStream();
    const socket = new FakeSocket();
    const got = collect();
    const calls: unknown[][] = [];
    openSamples("r", ids, "playback", got.handlers, {
      makeSocket: () => socket as unknown as WebSocket,
      fetchData: (...args) => {
        calls.push(args.slice(0, 4));
        return Promise.resolve(data);
      },
    });
    socket.onclose?.({ code: 1006, reason: "" } as CloseEvent);
    await tick();
    expect(calls).toEqual([["r", ids, null, 0]]); // raw rows: px=0, no window
    const buffer = got.buffer();
    expect(buffer?.length).toBe(expected.length);
    expect(Array.from(buffer?.time.subarray(0, buffer.length) ?? [])).toEqual(Array.from(expected.time.subarray(0, expected.length)));
    for (let c = 0; c < 2; c++) {
      expect(Array.from(buffer?.column(c)?.subarray(0, buffer.length) ?? [])).toEqual(Array.from(expected.column(c)?.subarray(0, expected.length) ?? []));
    }
    expect(got.ends).toEqual([{ ok: true, reason: "done" }]);
    expect(got.notes).toEqual([fallbackNote(1006)]);
    expect(got.notes[0]).toMatch(/dropped \(1006\).*over HTTP/);
  });

  it("falls back on an error before the handshake, with no close event", async () => {
    const socket = new FakeSocket();
    const got = collect();
    openSamples("r", ids, "playback", got.handlers, { makeSocket: () => socket as unknown as WebSocket, fetchData: () => Promise.resolve(data) });
    socket.onerror?.();
    await tick();
    expect(socket.closed).toBe(true);
    expect(got.buffer()?.length).toBeGreaterThan(50);
    expect(got.notes).toHaveLength(1);
  });

  it("falls back when the socket cannot even be constructed", async () => {
    const got = collect();
    openSamples("r", ids, "playback", got.handlers, {
      makeSocket: () => {
        throw new Error("SecurityError");
      },
      fetchData: () => Promise.resolve(data),
    });
    await tick();
    await tick();
    expect(got.buffer()?.length).toBeGreaterThan(50);
  });

  it("restarts from a fresh buffer when the stream broke half-way", async () => {
    const socket = new FakeSocket();
    const got = collect();
    openSamples("r", ids, "playback", got.handlers, { makeSocket: () => socket as unknown as WebSocket, fetchData: () => Promise.resolve(data) });
    socket.onmessage?.({ data: JSON.stringify({ signals: ids.map((id) => ({ id })), rate: 60 }) } as MessageEvent);
    socket.onmessage?.({ data: streamFrames.slice(0, 30).buffer } as MessageEvent);
    socket.onclose?.({ code: 1006, reason: "" } as CloseEvent);
    await tick();
    expect(got.buffer()?.length).toBe(streamFrames.length / 3);
  });

  it("reports an actionable text when the stream and HTTP both fail", async () => {
    const socket = new FakeSocket();
    const got = collect();
    openSamples("r", ids, "playback", got.handlers, {
      makeSocket: () => socket as unknown as WebSocket,
      fetchData: () => Promise.reject(new RunApiError("Cannot reach the bg-sim backend at http://x. Is it running?", 0)),
    });
    socket.onclose?.({ code: 1006, reason: "" } as CloseEvent);
    await tick();
    expect(got.ends).toEqual([{ ok: false, reason: UNREACHABLE }]);
    expect(UNREACHABLE).toMatch(/check that the backend is running.*WebSockets.*reload/);
    expect(got.notes).toEqual([]);
  });

  it("names the HTTP problem when the backend answered but has no data", async () => {
    const socket = new FakeSocket();
    const got = collect();
    openSamples("r", ids, "playback", got.handlers, {
      makeSocket: () => socket as unknown as WebSocket,
      fetchData: () => Promise.reject(new RunApiError("run r is gone", 404)),
    });
    socket.onclose?.({ code: 1006, reason: "" } as CloseEvent);
    await tick();
    expect(got.ends[0]?.ok).toBe(false);
    expect(got.ends[0]?.reason).toMatch(/run r is gone/);
  });

  it("does not use HTTP for a refusal of the request, nor for a live stream", async () => {
    let fetched = 0;
    const fetchData = (): Promise<RunDataFrame> => {
      fetched += 1;
      return Promise.resolve(data);
    };
    const refused = new FakeSocket();
    const a = collect();
    openSamples("r", ids, "playback", a.handlers, { makeSocket: () => refused as unknown as WebSocket, fetchData });
    refused.onclose?.({ code: 4404, reason: "unknown run" } as CloseEvent);
    expect(a.ends[0]?.reason).toMatch(/run is gone/);

    const live = new FakeSocket();
    const b = collect();
    openSamples("r", ids, "live", b.handlers, { makeSocket: () => live as unknown as WebSocket, fetchData });
    live.onclose?.({ code: 1006, reason: "" } as CloseEvent);
    expect(b.ends[0]?.ok).toBe(false);
    expect(b.ends[0]?.reason).toMatch(/dropped \(1006\)/);
    await tick();
    expect(fetched).toBe(0);
  });

  it("loadOverHttp delivers nothing after it is cancelled", async () => {
    const got = collect();
    const cancel = loadOverHttp("r", ids, got.handlers, () => Promise.resolve(data));
    cancel();
    await tick();
    expect(got.buffer()).toBeNull();
    expect(got.ends).toEqual([]);
  });
});
