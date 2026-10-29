import { describe, expect, it } from "vitest";
import type { Binding } from "../src/contracts/model";
import type { ApplyTarget } from "../src/viewer/bindingsApply";
import { ViewerPlayback, type CursorPort } from "../src/viewer/playbackController";
import { openStream, streamUrl } from "../src/viewer/playbackStream";
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
  return { playback, step, port, joint, target, queue, advance: (ms: number) => { now += ms; } };
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
  it("builds the stream URL with the ids in order and the mode", () => {
    const url = new URL(streamUrl("run-1", ["A/x", "A/y[1,2]"], "playback", "http://h:1"));
    expect(url.protocol).toBe("ws:");
    expect(url.pathname).toBe("/ws/stream/run-1");
    expect(url.searchParams.get("ids")).toBe("A/x,A/y[1,2]");
    expect(url.searchParams.get("mode")).toBe("playback");
  });

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
