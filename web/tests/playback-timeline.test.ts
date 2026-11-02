import { describe, expect, it } from "vitest";
import { bracket, decodeFrames, lerp, lerpPeriodic, normalizeQuat, SignalBuffer, slerp, type Quat } from "../src/viewer/timeline";

const times = [0, 1, 2, 4];

describe("bracket", () => {
  it("finds the samples around a time", () => {
    expect(bracket(times, 4, 1.5)).toEqual({ lo: 1, hi: 2, frac: 0.5 });
    expect(bracket(times, 4, 3)).toEqual({ lo: 2, hi: 3, frac: 0.5 });
  });
  it("lands exactly on a sample", () => {
    expect(bracket(times, 4, 1)).toEqual({ lo: 1, hi: 2, frac: 0 });
  });
  it("holds the first sample before the start and the last after the end", () => {
    expect(bracket(times, 4, -3)).toEqual({ lo: 0, hi: 0, frac: 0 });
    expect(bracket(times, 4, 4)).toEqual({ lo: 3, hi: 3, frac: 0 });
    expect(bracket(times, 4, 99)).toEqual({ lo: 3, hi: 3, frac: 0 });
  });
  it("handles one sample, none, and a filled part shorter than the array", () => {
    expect(bracket([5], 1, 7)).toEqual({ lo: 0, hi: 0, frac: 0 });
    expect(bracket(times, 0, 1)).toBeNull();
    expect(bracket(times, 2, 3)).toEqual({ lo: 1, hi: 1, frac: 0 });
  });
});

describe("lerp and slerp", () => {
  it("lerps", () => {
    expect(lerp(2, 4, 0.25)).toBe(2.5);
  });
  it("lerps a periodic value the shorter way round its period", () => {
    // a floor offset wrapped into [-50, 0]: -49 then -1 is a step of -2 m and one wrap, not +48 m back
    expect(lerpPeriodic(-49, -1, 0.25, 50)).toBeCloseTo(-49.5, 12);
    expect(lerpPeriodic(-49, -1, 0.75, 50)).toBeCloseTo(-0.5, 12); // measured from the nearer sample
    // halfway both directions reach the wrap point (-50 and 0 are the same place mod 50)
    expect(lerpPeriodic(-49, -1, 0.5, 50)).toBeCloseTo(0, 12);
    expect(lerpPeriodic(-1, -49, 0.5, 50)).toBeCloseTo(-50, 12);
    expect(lerpPeriodic(-49, -1, 0, 50)).toBe(-49);
    expect(lerpPeriodic(-49, -1, 1, 50)).toBe(-1);
    // within a period it is a plain lerp; a period of 0 is not periodic
    expect(lerpPeriodic(-30, -20, 0.5, 50)).toBeCloseTo(-25, 12);
    expect(lerpPeriodic(-49, -1, 0.5, 0)).toBe(-25);
    expect(lerpPeriodic(-49, -1, 0.5, Number.NaN)).toBe(-25);
  });
  const id: Quat = [1, 0, 0, 0];
  const quarterZ: Quat = [Math.SQRT1_2, 0, 0, Math.SQRT1_2]; // 90 deg about z
  it("interpolates halfway along the arc and returns unit quaternions", () => {
    const q = slerp(id, quarterZ, 0.5);
    const half = Math.PI / 8; // 45 deg about z is a half angle of 22.5 deg
    expect(q[0]).toBeCloseTo(Math.cos(half), 12);
    expect(q[3]).toBeCloseTo(Math.sin(half), 12);
    expect(Math.hypot(...q)).toBeCloseTo(1, 12);
  });
  it("takes the shorter path when the dot product is negative", () => {
    const flipped: Quat = [-quarterZ[0], -quarterZ[1], -quarterZ[2], -quarterZ[3]];
    const a = slerp(id, quarterZ, 0.5);
    const b = slerp(id, flipped, 0.5);
    for (let i = 0; i < 4; i++) expect(b[i]).toBeCloseTo(a[i] ?? 0, 12);
  });
  it("returns the ends at f = 0 and 1", () => {
    expect(slerp(id, quarterZ, 0)).toEqual(id);
    const end = slerp(id, quarterZ, 1);
    for (let i = 0; i < 4; i++) expect(end[i]).toBeCloseTo(quarterZ[i] ?? 0, 12);
  });
  it("falls back to a normalised lerp for nearly equal quaternions", () => {
    const near: Quat = normalizeQuat([1, 1e-6, 0, 0]);
    const q = slerp(id, near, 0.5);
    expect(Math.hypot(...q)).toBeCloseTo(1, 12);
  });
  it("normalises, and gives the identity for a zero quaternion", () => {
    expect(normalizeQuat([2, 0, 0, 0])).toEqual([1, 0, 0, 0]);
    expect(normalizeQuat([0, 0, 0, 0])).toEqual([1, 0, 0, 0]);
  });
});

describe("decodeFrames", () => {
  it("splits a message with several frames", () => {
    const frames = new Float64Array([0, 1, 10, 0.5, 2, 20, 1, 3, 30]);
    const out = decodeFrames(frames.buffer, 2);
    expect(Array.from(out)).toEqual(Array.from(frames));
    expect(out.length / 3).toBe(3);
  });
  it("refuses a message that is not whole frames", () => {
    expect(() => decodeFrames(new Float64Array(5).buffer, 2)).toThrow(/whole number of frames/);
  });
});

describe("SignalBuffer", () => {
  function make(): SignalBuffer {
    const b = new SignalBuffer(["a", "b"], 2);
    b.append(new Float64Array([0, 0, 10, 1, 2, 20, 2, 4, 40])); // grows past its capacity of 2
    return b;
  }
  it("appends frames across messages and interpolates scalars", () => {
    const b = make();
    b.append(new Float64Array([3, 6, 60]));
    expect(b.length).toBe(4);
    expect(b.valueAt(0, 1.5)).toBeCloseTo(3);
    expect(b.valueAt(1, 2.5)).toBeCloseTo(50);
    expect(b.valueAt(0, -1)).toBe(0);
    expect(b.valueAt(0, 99)).toBe(6);
    expect(b.span).toEqual({ t0: 0, t1: 3 });
    expect(b.interval).toBe(1);
  });
  it("ignores frames that do not advance time", () => {
    const b = make();
    b.append(new Float64Array([2, 9, 9, 1, 9, 9]));
    expect(b.length).toBe(3);
  });
  it("interpolates a quaternion over four columns with slerp", () => {
    const b = new SignalBuffer(["w", "x", "y", "z"]);
    b.append(new Float64Array([0, 1, 0, 0, 0, 1, Math.SQRT1_2, 0, 0, Math.SQRT1_2]));
    const q = b.quatAt([0, 1, 2, 3], 0.5);
    expect(q?.[0]).toBeCloseTo(Math.cos(Math.PI / 8), 12);
    expect(q?.[3]).toBeCloseTo(Math.sin(Math.PI / 8), 12);
  });
  it("is empty after clear", () => {
    const b = make();
    b.clear();
    expect(b.valueAt(0, 1)).toBeNull();
    expect(b.span).toBeNull();
  });
});
