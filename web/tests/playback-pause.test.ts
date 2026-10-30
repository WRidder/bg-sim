/**
 * W4.3 / DEC-M4-1 (plan 7.9): the 3D playback at a debug pause ends at the pause time. A live head shows the
 * pause time, a recorded head and the clock range are held at it, and a resume releases them.
 */

import { describe, expect, it } from "vitest";

import type { Binding } from "../src/contracts/model";
import type { ApplyTarget } from "../src/viewer/bindingsApply";
import { clampToPause, markerFraction, pausedHead } from "../src/viewer/pauseClamp";
import { ViewerPlayback, type CursorPort } from "../src/viewer/playbackController";
import { SignalBuffer } from "../src/viewer/timeline";

describe("pause clamp helpers", () => {
  it("holds a time at the pause time", () => {
    expect(clampToPause(0.2, 0.1)).toBe(0.1);
    expect(clampToPause(0.05, 0.1)).toBe(0.05);
    expect(clampToPause(0.2, null)).toBe(0.2);
  });

  it("puts the paused head at the pause time, never past the newest sample", () => {
    expect(pausedHead({ t0: 0, t1: 0.1 }, 0.084)).toBe(0.084);
    expect(pausedHead({ t0: 0, t1: 0.05 }, 0.084)).toBe(0.05);
    expect(pausedHead(null, 0.084)).toBeNull();
  });

  it("places the marker as a fraction of the slider", () => {
    expect(markerFraction(0.5, 0, 1)).toBe(0.5);
    expect(markerFraction(2, 0, 1)).toBe(1);
    expect(markerFraction(null, 0, 1)).toBeNull();
    expect(markerFraction(0.5, 1, 1)).toBeNull();
  });
});

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
  const step = (ms = 0): void => {
    now += ms;
    const due = [...queue.values()];
    queue.clear();
    for (const f of due) f();
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
  const target: ApplyTarget = {
    setJointPosition: () => true,
    setPose: () => true,
    setVisualScale: () => true,
    setVisualColor: () => true,
    setVisible: () => true,
    reset: () => undefined,
  };
  const playback = new ViewerPlayback(port, { now: () => now, frames });
  return { playback, step, target };
}

const bindings: Binding[] = [{ target: "joint:j", property: "position", signal: "s" }];

function buffer(times: number[]): SignalBuffer {
  const b = new SignalBuffer(["s"]);
  b.append(Float64Array.from(times.flatMap((t) => [t, t])));
  return b;
}

describe("playback at a pause", () => {
  it("shows the pause time as the live head and ends the range there", () => {
    const { playback, step, target } = harness();
    playback.setTarget(target);
    playback.setBindings(bindings);
    playback.setData(buffer([0, 0.02, 0.04, 0.06, 0.08, 0.084]), true);
    step();
    // live: the head trails the newest sample
    expect(playback.snapshot().pauseTime).toBeNull();
    expect(playback.snapshot().time ?? 1).toBeLessThan(0.084);

    playback.setPauseTime(0.084);
    step();
    const paused = playback.snapshot();
    expect(paused.pauseTime).toBe(0.084);
    expect(paused.time).toBeCloseTo(0.084, 9);
    expect(paused.end).toBe(0.084);

    playback.setPauseTime(null);
    step();
    expect(playback.snapshot().pauseTime).toBeNull();
    expect(playback.snapshot().time ?? 1).toBeLessThan(0.084);
  });

  it("cannot play or seek a recorded run beyond the pause time", () => {
    const { playback, step, target } = harness();
    playback.setTarget(target);
    playback.setBindings(bindings);
    playback.setData(buffer([0, 0.02, 0.04, 0.06, 0.08, 0.1, 0.12]), false);
    step();
    expect(playback.snapshot().end).toBe(0.12);

    playback.setPauseTime(0.05);
    step();
    expect(playback.snapshot().end).toBe(0.05);
    playback.seek(0.1);
    step();
    expect(playback.snapshot().time).toBeCloseTo(0.05, 9);
    playback.play();
    step(1000);
    step(1000);
    expect(playback.snapshot().time).toBeCloseTo(0.05, 9);
  });
});
