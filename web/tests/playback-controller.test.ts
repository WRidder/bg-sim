import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Binding } from "../src/contracts/model";
import type { ApplyTarget } from "../src/viewer/bindingsApply";
import { ViewerPlayback, type CursorPort } from "../src/viewer/playbackController";
import { openStream, streamUrl, subscribeMessage, timedOut } from "../src/viewer/playbackStream";
import { SignalBuffer } from "../src/viewer/timeline";

/** A manual wall clock and frame queue. */
function harness() {
  let now = 0;
  const queue = new Map<number, () => void>();
  let next = 1;
  const frames = {
    request: (cb: (t: number) => void) => {
      const id = next++;
      queue.set(id, () => { cb(now); });
      return id;
    },
    cancel: (id: number) => {
      queue.delete(id);
    },
  };
  const step = (ms = 0): number => {
    now += ms;
    const due = [...queue.values()];
    queue.clear();
    for (const f of due) f();
    return due.length;
  };
  let cursor: number | null = null;
  const listeners = new Set<(t: number | null) => void>();
  const port: CursorPort = {
    get: () => cursor,
    set: (t) => {
      cursor = t;
      for (const l of listeners) l(t);
    },
    subscribe: (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
  };
  const joint: number[] = [];
  const target: ApplyTarget = {
    setJointPosition: (_ref, q) => {
      joint.push(q);
      return true;
    },
    setPose: () => true,
    setVisualScale: () => true,
    setVisualColor: () => true,
    setVisible: () => true,
    reset: () => undefined,
  };
  const playback = new ViewerPlayback(port, { now: () => now, frames });
  return { playback, step, port, joint, target, queue, now: () => now, advance: (ms: number) => { now += ms; } };
}

const bindings: Binding[] = [{ target: "joint:j", property: "position", signal: "s" }];

function ramp(): SignalBuffer {
  const b = new SignalBuffer(["s"]);
  const rows: number[] = [];
  for (let i = 0; i <= 10; i++) rows.push(i / 10, i); // t = 0..1, s = 0..10
  b.append(new Float64Array(rows));
  return b;
}

describe("ViewerPlayback", () => {
  it("applies the sample at the plot cursor when it moves, with no frame loop running", () => {
    const h = harness();
    h.playback.setTarget(h.target);
    h.playback.setBindings(bindings);
    h.playback.setData(ramp(), false);
    h.step();
    h.joint.length = 0;
    h.port.set(0.35);
    expect(h.step()).toBe(1);
    expect(h.joint.at(-1)).toBeCloseTo(3.5);
    // paused: nothing further is scheduled
    expect(h.step(100)).toBe(0);
    expect(h.queue.size).toBe(0);
  });

  it("plays at the clock speed, writes the head to the plot cursor and stops at the end", () => {
    const h = harness();
    h.playback.setTarget(h.target);
    h.playback.setBindings(bindings);
    h.playback.setData(ramp(), false);
    h.step();
    h.playback.setSpeed(0.5);
    h.playback.setLoop(false); // loop is on by default
    h.playback.play();
    h.step();
    h.step(1000); // 1 s wall = 0.5 s sim
    expect(h.joint.at(-1)).toBeCloseTo(5);
    expect(h.port.get()).toBeCloseTo(0.5);
    expect(h.playback.snapshot().playing).toBe(true);
    h.step(1500); // past the end
    expect(h.joint.at(-1)).toBeCloseTo(10);
    expect(h.port.get()).toBe(1);
    expect(h.playback.snapshot().playing).toBe(false);
    expect(h.step(100)).toBe(0);
  });

  it("a seek from the slider moves the plot cursor, and the cursor seeks without echoing back", () => {
    const h = harness();
    h.playback.setTarget(h.target);
    h.playback.setBindings(bindings);
    h.playback.setData(ramp(), false);
    h.playback.seek(0.8);
    expect(h.port.get()).toBeCloseTo(0.8);
    h.step();
    h.port.set(0.2);
    h.step();
    expect(h.playback.clock.time(0)).toBeCloseTo(0.2);
    expect(h.port.get()).toBe(0.2); // not rewritten
  });

  it("starts at an existing cursor when data arrives", () => {
    const h = harness();
    h.port.set(0.6);
    h.playback.setTarget(h.target);
    h.playback.setBindings(bindings);
    h.playback.setData(ramp(), false);
    h.step();
    expect(h.joint.at(-1)).toBeCloseTo(6);
  });

  it("applies the cursor that was set before the stream delivered its blocks", () => {
    const h = harness();
    h.port.set(0.6);
    h.playback.setTarget(h.target);
    h.playback.setBindings(bindings);
    const buffer = new SignalBuffer(["s"]);
    h.playback.setData(buffer, false); // handshake: no frames yet
    buffer.append(new Float64Array([0, 0, 0.5, 5]));
    h.playback.dataChanged();
    buffer.append(new Float64Array([1, 10]));
    h.playback.dataChanged();
    h.step();
    expect(h.joint.at(-1)).toBeCloseTo(6);
    expect(h.port.get()).toBe(0.6);
  });

  it("live: follows the newest sample 1.5 intervals behind, never extrapolates, ignores the cursor", () => {
    const h = harness();
    h.playback.setTarget(h.target);
    h.playback.setBindings(bindings);
    const buffer = new SignalBuffer(["s"]);
    h.playback.setData(buffer, true);
    buffer.append(new Float64Array([0, 0, 0.1, 1, 0.2, 2, 0.3, 3]));
    h.playback.dataChanged();
    h.step();
    expect(h.playback.mode).toBe("live");
    expect(h.joint.at(-1)).toBeCloseTo(1.5); // head = 0.3 - 0.15
    h.port.set(0.9);
    h.step(16);
    expect(h.joint.at(-1)).toBeCloseTo(1.5);
    expect(h.queue.size).toBe(1); // the loop keeps running while live
  });

  it("live ends in clock playback standing where the head was", () => {
    const h = harness();
    h.playback.setTarget(h.target);
    h.playback.setBindings(bindings);
    const buffer = new SignalBuffer(["s"]);
    h.playback.setData(buffer, true);
    buffer.append(new Float64Array([0, 0, 0.1, 1, 0.2, 2, 0.3, 3]));
    h.playback.dataChanged();
    h.step();
    h.playback.finishLive();
    h.step();
    expect(h.playback.mode).toBe("playback");
    expect(h.playback.clock.time(0)).toBeCloseTo(0.15);
    expect(h.playback.clock.end).toBe(0.3);
  });

  it("loops by default", () => {
    const h = harness();
    expect(h.playback.snapshot().loop).toBe(true);
    expect(h.playback.clock.loop).toBe(true);
  });

  it("a run started from Play plays from its start once complete; without it the head stays", () => {
    for (const armed of [true, false]) {
      const h = harness();
      h.playback.setTarget(h.target);
      h.playback.setBindings(bindings);
      if (armed) h.playback.playWhenDone();
      const buffer = new SignalBuffer(["s"]);
      h.playback.setData(buffer, true);
      buffer.append(new Float64Array([0, 0, 0.1, 1, 0.2, 2, 0.3, 3]));
      h.playback.dataChanged();
      h.step();
      h.playback.complete();
      h.step();
      expect(h.playback.mode).toBe("playback");
      expect(h.playback.clock.playing(h.now())).toBe(armed);
      expect(h.playback.clock.time(h.now())).toBeCloseTo(armed ? 0 : 0.15);
      // consumed: the next run does not start on its own
      h.playback.pause();
      h.playback.setData(buffer, false);
      h.playback.complete();
      expect(h.playback.clock.playing(h.now())).toBe(false);
    }
  });

  it("a finished run loaded at once (no live phase) also plays when armed", () => {
    const h = harness();
    h.playback.setTarget(h.target);
    h.playback.setBindings(bindings);
    h.playback.playWhenDone();
    h.playback.setData(ramp(), false);
    h.playback.complete();
    expect(h.playback.clock.playing(h.now())).toBe(true);
  });

  it("changing the bindings resets the scene and applies the new ones", () => {
    const h = harness();
    let resets = 0;
    h.target.reset = () => {
      resets++;
    };
    h.playback.setTarget(h.target);
    h.playback.setBindings(bindings);
    h.playback.setData(ramp(), false);
    h.step();
    h.playback.setBindings([{ target: "joint:j", property: "position", signal: "s", gain: 2 }]);
    h.step();
    expect(resets).toBe(2);
    expect(h.joint.at(-1)).toBeCloseTo(0); // t = 0
    h.playback.seek(0.5);
    h.step();
    expect(h.joint.at(-1)).toBeCloseTo(10);
  });

  it("applies nothing while the view is inactive and catches up when it is shown", () => {
    const h = harness();
    h.playback.setActive(false);
    h.playback.setTarget(h.target);
    h.playback.setBindings(bindings);
    h.playback.setData(ramp(), false);
    h.port.set(0.5);
    expect(h.step()).toBe(0);
    h.playback.setActive(true);
    h.step();
    expect(h.joint.at(-1)).toBeCloseTo(5);
  });

  it("looping playback keeps going past the end", () => {
    const h = harness();
    h.playback.setTarget(h.target);
    h.playback.setBindings(bindings);
    h.playback.setData(ramp(), false);
    h.playback.setLoop(true);
    h.playback.play();
    h.step();
    h.step(1250);
    expect(h.playback.snapshot().playing).toBe(true);
    expect(h.joint.at(-1)).toBeCloseTo(2.5);
  });
});

describe("stream client", () => {
  it("builds a short stream URL: the mode and subscribe, never the ids", () => {
    const url = new URL(streamUrl("run-1", "playback", "http://h:1"));
    expect(url.protocol).toBe("ws:");
    expect(url.pathname).toBe("/ws/stream/run-1");
    expect(url.searchParams.get("ids")).toBeNull();
    expect(url.searchParams.get("subscribe")).toBe("1");
    expect(url.searchParams.get("mode")).toBe("playback");
  });

  class FakeSocket {
    binaryType = "";
    onopen: (() => void) | null = null;
    onmessage: ((e: MessageEvent) => void) | null = null;
    onclose: ((e: CloseEvent) => void) | null = null;
    onerror: (() => void) | null = null;
    closed = false;
    sent: string[] = [];
    url = "";
    send(text: string): void {
      this.sent.push(text);
    }
    close(): void {
      this.closed = true;
    }
  }

  it("sends the ids as the first message once open, however many there are", () => {
    const socket = new FakeSocket();
    // the 3D view of a formation flight: 2000 pose components, far over any request line
    const ids = Array.from({ length: 2000 }, (_, k) => `Craft${String(k % 6)}Trail/d${String(k % 12)}[${String((k % 7) + 1)}]`);
    openStream("r", ids, "playback", { onHandshake: () => undefined, onFrames: () => undefined, onEnd: () => undefined }, (url) => {
      socket.url = url;
      return socket as unknown as WebSocket;
    });
    expect(socket.url.length).toBeLessThan(200);
    expect(socket.sent).toEqual([]);
    socket.onopen?.();
    expect(socket.sent).toHaveLength(1);
    expect(JSON.parse(socket.sent[0] ?? "")).toEqual({ ids });
    expect(subscribeMessage(["A/y[1,2]"])).toBe('{"ids":["A/y[1,2]"]}');
  });

  describe("timeouts", () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });
    afterEach(() => {
      vi.useRealTimers();
    });

    function open(mode: "live" | "playback"): { socket: FakeSocket; ends: { ok: boolean; reason: string; code?: number }[]; handshakes: number } {
      const socket = new FakeSocket();
      const got = { socket, ends: [] as { ok: boolean; reason: string; code?: number }[], handshakes: 0 };
      openStream(
        "r",
        ["a"],
        mode,
        { onHandshake: () => { got.handshakes += 1; }, onFrames: () => undefined, onEnd: (e) => { got.ends.push(e); } },
        () => socket as unknown as WebSocket,
        { openMs: 1000, handshakeMs: 2000 },
      );
      return got;
    }

    it("reports a connection that never opens instead of waiting forever", () => {
      const got = open("live");
      vi.advanceTimersByTime(999);
      expect(got.ends).toEqual([]);
      vi.advanceTimersByTime(1);
      expect(got.ends).toEqual([{ ok: false, reason: timedOut("open", 1000), code: 1006 }]);
      expect(got.ends[0]?.reason).toMatch(/did not connect within 1 s/);
      expect(got.socket.closed).toBe(true);
      // a late close of the abandoned socket reaches nobody
      got.socket.onclose?.({ code: 1006, reason: "" } as CloseEvent);
      expect(got.ends).toHaveLength(1);
    });

    it("reports a playback stream that opens but sends no handshake", () => {
      const got = open("playback");
      vi.advanceTimersByTime(500);
      got.socket.onopen?.();
      vi.advanceTimersByTime(1999);
      expect(got.ends).toEqual([]);
      vi.advanceTimersByTime(1);
      expect(got.ends[0]?.reason).toMatch(/connected but sent no data within 2 s/);
    });

    it("lets a live stream wait for its handshake (the run may still be compiling)", () => {
      const got = open("live");
      got.socket.onopen?.();
      vi.advanceTimersByTime(60_000);
      expect(got.ends).toEqual([]);
      got.socket.onmessage?.({ data: JSON.stringify({ signals: [{ id: "a" }], rate: 60, mode: "live" }) } as MessageEvent);
      expect(got.handshakes).toBe(1);
    });

    it("stops the clock once the handshake is in", () => {
      const got = open("playback");
      got.socket.onopen?.();
      got.socket.onmessage?.({ data: JSON.stringify({ signals: [{ id: "a" }], rate: 60, mode: "playback" }) } as MessageEvent);
      vi.advanceTimersByTime(60_000);
      expect(got.ends).toEqual([]);
    });
  });

  it("decodes several frames per message after the handshake and reports the close", () => {
    const socket = new FakeSocket();
    const frames: number[][] = [];
    const ends: { ok: boolean; reason: string }[] = [];
    let signals = 0;
    openStream("r", ["a", "b"], "playback", {
      onHandshake: (h) => { signals = h.signals.length; },
      onFrames: (f) => { frames.push(Array.from(f)); },
      onEnd: (e) => { ends.push(e); },
    }, () => socket as unknown as WebSocket);
    expect(socket.binaryType).toBe("arraybuffer");
    socket.onmessage?.({ data: JSON.stringify({ signals: [{ id: "a", unit: "1" }, { id: "b" }], rate: 60, mode: "playback" }) } as MessageEvent);
    socket.onmessage?.({ data: new Float64Array([0, 1, 2, 0.1, 3, 4, 0.2, 5, 6]).buffer } as MessageEvent);
    socket.onmessage?.({ data: new Float64Array([0.3, 7, 8]).buffer } as MessageEvent);
    socket.onclose?.({ code: 1000, reason: "done" } as CloseEvent);
    expect(signals).toBe(2);
    expect(frames).toEqual([[0, 1, 2, 0.1, 3, 4, 0.2, 5, 6], [0.3, 7, 8]]);
    expect(ends).toEqual([{ ok: true, reason: "done" }]);
  });

  it("explains a refusal and rejects a torn message", () => {
    const refused = new FakeSocket();
    const ends: { ok: boolean; reason: string }[] = [];
    const handlers = { onHandshake: () => undefined, onFrames: () => undefined, onEnd: (e: { ok: boolean; reason: string }) => { ends.push(e); } };
    openStream("r", ["a"], "live", handlers, () => refused as unknown as WebSocket);
    refused.onclose?.({ code: 4404, reason: "unknown run" } as CloseEvent);
    expect(ends[0]?.ok).toBe(false);
    expect(ends[0]?.reason).toMatch(/run is gone.*run the model again/);

    const torn = new FakeSocket();
    openStream("r", ["a"], "live", handlers, () => torn as unknown as WebSocket);
    torn.onmessage?.({ data: JSON.stringify({ signals: [{ id: "a" }], rate: 60 }) } as MessageEvent);
    torn.onmessage?.({ data: new Float64Array(3).buffer } as MessageEvent);
    expect(torn.closed).toBe(true);
    expect(ends[1]?.ok).toBe(false);
    expect(ends[1]?.reason).toMatch(/whole number of frames/);
  });

  it("calls nothing after it is closed by the caller", () => {
    const socket = new FakeSocket();
    const ends: unknown[] = [];
    const close = openStream("r", ["a"], "live", { onHandshake: () => undefined, onFrames: () => undefined, onEnd: (e) => { ends.push(e); } }, () => socket as unknown as WebSocket);
    close();
    expect(socket.closed).toBe(true);
    socket.onclose?.({ code: 1000, reason: "done" } as CloseEvent);
    expect(ends).toEqual([]);
  });
});
