import { describe, expect, it } from "vitest";
import type { Binding } from "../src/contracts/model";
import { BindingApplier, boundSignalIds, gainOffset, type ApplyTarget } from "../src/viewer/bindingsApply";
import { colormapColor } from "../src/viewer/bindingsColormaps";
import { SignalBuffer } from "../src/viewer/timeline";

class Recorder implements ApplyTarget {
  calls: [string, ...unknown[]][] = [];
  setJointPosition(ref: string, q: number): boolean {
    this.calls.push(["joint", ref, q]);
    return true;
  }
  setPose(ref: string, pose: readonly number[]): boolean {
    this.calls.push(["pose", ref, [...pose]]);
    return true;
  }
  setVisualScale(ref: string, x: number, y: number, z: number): boolean {
    this.calls.push(["scale", ref, x, y, z]);
    return true;
  }
  setVisualColor(ref: string, r: number, g: number, b: number): boolean {
    this.calls.push(["color", ref, r, g, b]);
    return true;
  }
  setVisible(ref: string, v: boolean): boolean {
    this.calls.push(["visible", ref, v]);
    return true;
  }
  reset(): void {
    this.calls.push(["reset"]);
  }
}

describe("gain and offset", () => {
  it("applies value * gain + offset with defaults 1 and 0", () => {
    expect(gainOffset(2, {})).toBe(2);
    expect(gainOffset(2, { gain: 3, offset: 1 })).toBe(7);
    expect(gainOffset(2, { offset: -1 })).toBe(1);
  });
});

describe("colormaps", () => {
  for (const map of ["heat", "viridis", "coolwarm"] as const) {
    it(`${map}: distinct ends, clamped outside the range, channels in 0..1`, () => {
      const lo = colormapColor(map, 0, [0, 1]);
      const hi = colormapColor(map, 1, [0, 1]);
      expect(lo).not.toEqual(hi);
      expect(colormapColor(map, -5, [0, 1])).toEqual(lo);
      expect(colormapColor(map, 9, [0, 1])).toEqual(hi);
      for (const c of colormapColor(map, 0.37, [0, 1])) {
        expect(c).toBeGreaterThanOrEqual(0);
        expect(c).toBeLessThanOrEqual(1);
      }
    });
  }
  it("maps the range, not 0..1", () => {
    expect(colormapColor("viridis", 70, [20, 120])).toEqual(colormapColor("viridis", 0.5, [0, 1]));
  });
  it("coolwarm is blue at the low end and red at the high end", () => {
    const lo = colormapColor("coolwarm", 0, [0, 1]);
    const hi = colormapColor("coolwarm", 1, [0, 1]);
    expect(lo[2]).toBeGreaterThan(lo[0]);
    expect(hi[0]).toBeGreaterThan(hi[2]);
  });
  it("gives the low end for a degenerate range", () => {
    expect(colormapColor("heat", 5, [1, 1])).toEqual(colormapColor("heat", 0, [0, 1]));
  });
});

describe("BindingApplier", () => {
  const ids = ["a", "b", "qw", "qx", "qy", "qz", "x", "y", "z"];
  function buffer(): SignalBuffer {
    const b = new SignalBuffer(ids);
    // t = 0 and 1; a: 0 -> 2; b: 0 -> 1; identity rotation to 90 deg about z; position (0,0,0) -> (1,2,3)
    b.append(new Float64Array([0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 1, 2, 1, Math.SQRT1_2, 0, 0, Math.SQRT1_2, 1, 2, 3]));
    return b;
  }

  it("lists each bound signal once, in first-use order", () => {
    const b: Binding[] = [
      { target: "joint:j", property: "position", signal: "a" },
      { target: "visual:v", property: "scale.z", signal: "a" },
      { target: "link:l", property: "pose", signal: ["qw", "qx", "qy", "qz", "x", "y", "z"] },
    ];
    expect(boundSignalIds(b)).toEqual(["a", "qw", "qx", "qy", "qz", "x", "y", "z"]);
  });

  it("sets a joint position from the interpolated signal with gain and offset", () => {
    const t = new Recorder();
    const applier = new BindingApplier(t, [{ target: "joint:j", property: "position", signal: "a", gain: 2, offset: 0.5 }], ids);
    applier.apply(buffer(), 0.25);
    expect(t.calls).toEqual([["joint", "joint:j", 1.5]]); // (2 * 0.25) * 2 + 0.5
    expect(applier.applied.get("joint:j")).toBe(1.5);
  });

  it("holds the ends", () => {
    const t = new Recorder();
    const applier = new BindingApplier(t, [{ target: "joint:j", property: "position", signal: "a" }], ids);
    applier.apply(buffer(), -4);
    applier.apply(buffer(), 40);
    expect(t.calls.map((c) => c[2])).toEqual([0, 2]);
  });

  it("slerps the pose quaternion and moves the position by gain and offset only", () => {
    const t = new Recorder();
    const applier = new BindingApplier(t, [{ target: "link:l", property: "pose", signal: ["qw", "qx", "qy", "qz", "x", "y", "z"], gain: 2, offset: 1 }], ids);
    applier.apply(buffer(), 0.5);
    const pose = t.calls[0]?.[2] as number[];
    expect(pose[0]).toBeCloseTo(Math.cos(Math.PI / 8), 12);
    expect(pose[3]).toBeCloseTo(Math.sin(Math.PI / 8), 12);
    expect(pose.slice(4)).toEqual([2, 3, 4]); // (0.5, 1, 1.5) * 2 + 1
  });

  it("interpolates the periodic position components of a pose the shorter way round their period", () => {
    // a scrolling floor: x wraps from -49 to -1 (period 50), y is periodic but does not wrap, z is not periodic
    const b = new SignalBuffer(ids);
    b.append(new Float64Array([0, 0, 0, 1, 0, 0, 0, -49, -10, -150, 1, 0, 0, 1, 0, 0, 0, -1, -14, -100]));
    const t = new Recorder();
    const sig: [string, ...string[]] = ["qw", "qx", "qy", "qz", "x", "y", "z"];
    new BindingApplier(t, [{ target: "link:l", property: "pose", signal: sig, period: [50, 50, 0] }], ids).apply(b, 0.25);
    new BindingApplier(t, [{ target: "link:l", property: "pose", signal: sig }], ids).apply(b, 0.25);
    const periodic = t.calls[0]?.[2] as number[];
    const plain = t.calls[1]?.[2] as number[];
    expect(periodic[4]).toBeCloseTo(-49.5, 12); // half a metre on (-2 m and one wrap per second), not 12 m back
    expect(periodic[5]).toBeCloseTo(-11, 12);
    expect(periodic[6]).toBeCloseTo(-137.5, 12);
    expect(plain.slice(4)).toEqual([-37, -11, -137.5]);
  });

  it("combines scale axes of one visual into a single call", () => {
    const t = new Recorder();
    const applier = new BindingApplier(
      t,
      [
        { target: "visual:v", property: "scale.z", signal: "a", gain: 0.5 },
        { target: "visual:v", property: "scale.x", signal: "b", offset: 1 },
      ],
      ids,
    );
    applier.apply(buffer(), 1);
    expect(t.calls).toEqual([["scale", "visual:v", 2, 1, 1]]);
  });

  it("colours through the map and range, and shows with a threshold of 0.5", () => {
    const t = new Recorder();
    const applier = new BindingApplier(
      t,
      [
        { target: "visual:v", property: "color", signal: "a", colormap: "viridis", range: [0, 2] },
        { target: "link:l", property: "visible", signal: "b" },
        { target: "visual:w", property: "visible", signal: "b", gain: -1, offset: 1 },
      ],
      ids,
    );
    applier.apply(buffer(), 0.4);
    expect(t.calls[0]?.slice(1)).toEqual(["visual:v", ...colormapColor("viridis", 0.8, [0, 2])]);
    expect(t.calls[1]).toEqual(["visible", "link:l", false]); // b = 0.4
    expect(t.calls[2]).toEqual(["visible", "visual:w", true]); // 1 - 0.4 = 0.6
    t.calls = [];
    applier.apply(buffer(), 0.6);
    expect(t.calls[1]).toEqual(["visible", "link:l", true]);
  });

  it("skips bindings with unknown signals or a wrong count, and still applies the others", () => {
    const t = new Recorder();
    const applier = new BindingApplier(
      t,
      [
        { target: "joint:x", property: "position", signal: "missing" },
        { target: "link:l", property: "pose", signal: ["qw", "qx"] },
        { target: "joint:j", property: "position", signal: "b" },
      ],
      ids,
    );
    expect(applier.count).toBe(1);
    applier.apply(buffer(), 1);
    expect(t.calls).toEqual([["joint", "joint:j", 1]]);
  });
});
