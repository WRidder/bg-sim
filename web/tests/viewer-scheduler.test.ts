import { describe, expect, it, vi } from "vitest";
import { hardwareScaling, RenderScheduler, type FrameClock } from "../src/viewer/renderScheduler";

function fakeClock() {
  const queue = new Map<number, (now: number) => void>();
  let id = 0;
  const clock: FrameClock = {
    request: (cb) => {
      id += 1;
      queue.set(id, cb);
      return id;
    },
    cancel: (i) => {
      queue.delete(i);
    },
  };
  const tick = (now: number) => {
    const cbs = [...queue.values()];
    queue.clear();
    for (const cb of cbs) cb(now);
  };
  return { clock, tick, pending: () => queue.size };
}

describe("RenderScheduler", () => {
  it("draws only on demand, continues while motion is reported, pauses while hidden", () => {
    const c = fakeClock();
    let moving = 2;
    const draw = vi.fn(() => moving-- > 0);
    const s = new RenderScheduler(draw, c.clock);
    c.tick(0);
    expect(draw).not.toHaveBeenCalled();
    s.invalidate();
    s.invalidate();
    expect(c.pending()).toBe(1);
    c.tick(16);
    c.tick(32);
    c.tick(48);
    c.tick(64);
    expect(draw).toHaveBeenCalledTimes(3);
    expect(s.frames).toBe(3);
    expect(s.idle).toBe(true);
    s.setVisible(false);
    s.invalidate();
    expect(c.pending()).toBe(0);
    s.setVisible(true);
    c.tick(80);
    expect(draw).toHaveBeenCalledTimes(4);
    s.dispose();
    s.invalidate();
    expect(c.pending()).toBe(0);
  });

  it("cancels a queued frame when it becomes hidden", () => {
    const c = fakeClock();
    const draw = vi.fn(() => false);
    const s = new RenderScheduler(draw, c.clock);
    s.invalidate();
    s.setVisible(false);
    expect(c.pending()).toBe(0);
    c.tick(16);
    expect(draw).not.toHaveBeenCalled();
  });

  it("caps the render resolution", () => {
    expect(hardwareScaling(3, 1.5)).toBeCloseTo(1 / 1.5, 12);
    expect(hardwareScaling(1, 1.5)).toBe(1);
    expect(hardwareScaling(Number.NaN, 2)).toBe(1);
  });
});
