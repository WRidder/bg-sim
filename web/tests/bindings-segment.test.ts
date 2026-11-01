import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import { NullEngine } from "@babylonjs/core/Engines/nullEngine";
import type { Binding, SegmentBinding, SegmentBrokenStyle, ShapeAxis } from "../src/contracts/model";
import { buildScene, type BuiltScene } from "../src/scene/build";
import type { Mat4, Vec3 } from "../src/scene/pose";
import { resolveScene } from "../src/scene/resolve";
import { parseSdf, type SdfGeometry } from "../src/scene/sdf";
import { SNAP_FRACTION, planarPoint, segmentAxis, segmentPlacement, snappedPlacements, type SegmentAxis } from "../src/scene/segment";
import { BindingApplier, boundSignalIds, segmentEnds, type ApplyTarget } from "../src/viewer/bindingsApply";
import { validateBindings, type SceneLookup, type SignalUnits } from "../src/viewer/bindingsValidate";
import { SignalBuffer } from "../src/viewer/timeline";
import { ViewerScene } from "../src/viewer/viewerScene";

const here = path.dirname(fileURLToPath(import.meta.url));

/** Apply a column-convention Mat4 (row-major array, translation in the last column) to a point. */
function transform(m: Mat4, p: Vec3): Vec3 {
  const r = (i: number): number => (m[4 * i] ?? 0) * p[0] + (m[4 * i + 1] ?? 0) * p[1] + (m[4 * i + 2] ?? 0) * p[2] + (m[4 * i + 3] ?? 0);
  return [r(0), r(1), r(2)];
}

function expectPoint(actual: Vec3, expected: Vec3, digits = 9): void {
  actual.forEach((c, i) => {
    expect(c, `component ${String(i)}`).toBeCloseTo(expected[i] ?? NaN, digits);
  });
}

/** The two ends of the visual's axis after a placement (frame plus stretch along the axis). */
function ends(world: Mat4, scale: number, axis: SegmentAxis): [Vec3, Vec3] {
  const h = (axis.extent * scale) / 2;
  const d = axis.dir;
  return [transform(world, [-h * d[0], -h * d[1], -h * d[2]]), transform(world, [h * d[0], h * d[1], h * d[2]])];
}

const BOX: SdfGeometry = { kind: "box", size: [1, 0.1, 0.2] };
const ROD: SdfGeometry = { kind: "cylinder", radius: 0.02, length: 0.5 };

describe("segment placement maths", () => {
  it("maps planar points into the world plane", () => {
    expect(planarPoint(1, 2)).toEqual([1, 0, 2]);
    expect(planarPoint(1, 2, "xz", 0.7)).toEqual([1, 0.7, 2]);
    expect(planarPoint(1, 2, "xy", 0.7)).toEqual([1, 2, 0.7]);
    expect(planarPoint(1, 2, "yz", 0.7)).toEqual([0.7, 1, 2]);
  });

  it("puts the axis of a box or a cylinder on the line A-B, in any direction", () => {
    const cases: [SdfGeometry, ShapeAxis | undefined][] = [[BOX, undefined], [BOX, "-y"], [ROD, undefined], [ROD, "-z"]];
    const lines: [Vec3, Vec3][] = [
      [[0, 0, 0], [3, 0, 0]],
      [[1, 2, 3], [1, 2, -4]],
      [[0.5, -1, 2], [-2, 3, 0.25]],
      [[0, 0, 0], [-1, 0, 0]],
    ];
    for (const [g, ax] of cases) {
      const axis = segmentAxis(g, ax);
      if (typeof axis === "string") throw new Error(axis);
      for (const [a, b] of lines) {
        const p = segmentPlacement(a, b, axis);
        const [ea, eb] = ends(p.world, p.scale, axis);
        expectPoint(ea, a);
        expectPoint(eb, b);
      }
    }
  });

  it("rejects spheres, meshes and a cylinder across its axis", () => {
    expect(segmentAxis({ kind: "sphere", radius: 1 })).toMatch(/sphere/);
    expect(segmentAxis({ kind: "mesh", uri: "m.glb", scale: [1, 1, 1] })).toMatch(/mesh/);
    expect(segmentAxis(ROD, "+x")).toMatch(/own axis/);
    expect(segmentAxis(BOX, "+y")).toEqual({ dir: [0, 1, 0], extent: 0.1, index: 1 });
  });

  it("snaps a bar into two drooping stubs that start at A and at B", () => {
    const axis = segmentAxis(BOX);
    if (typeof axis === "string") throw new Error(axis);
    const a: Vec3 = [0, 0, 4];
    const b: Vec3 = [5, 0, 4];
    const [first, second] = snappedPlacements(a, b, axis);
    const [a0, a1] = ends(first.world, first.scale, axis);
    const [b0, b1] = ends(second.world, second.scale, axis);
    expectPoint(a0, a);
    expectPoint(b0, b);
    // each stub keeps SNAP_FRACTION of the length and hangs below the line
    expect(Math.hypot(a1[0] - a0[0], a1[1] - a0[1], a1[2] - a0[2])).toBeCloseTo(SNAP_FRACTION * 5, 9);
    expect(a1[2]).toBeLessThan(4);
    expect(b1[2]).toBeLessThan(4);
    // with a gap between the free ends
    expect(b1[0] - a1[0]).toBeGreaterThan(0.5);
  });
});

const GEOMETRY: Record<string, SdfGeometry> = { "visual:bar": BOX, "visual:rod": ROD, "visual:ball": { kind: "sphere", radius: 0.1 } };
const lookup: SceneLookup = { has: (ref) => ref in GEOMETRY, joint: () => null, visualGeometry: (ref) => GEOMETRY[ref] ?? null };
const units: SignalUnits = new Map<string, string | null>([
  ["T/x[1]", "m"],
  ["T/y[1]", "m"],
  ["T/x[2]", "m"],
  ["T/y[2]", "m"],
  ["T/z", null],
  ["T/failed[1]", null],
  ["T/N[1]", "N"],
]);

function seg(over: Partial<SegmentBinding> = {}): SegmentBinding {
  return { target: "visual:bar", property: "segment", signal: ["T/x[1]", "T/y[1]", "T/x[2]", "T/y[2]"], ...over };
}

const codes = (b: Binding[]): string[] => validateBindings(b, lookup, units).map((d) => d.code);

describe("segment binding validation", () => {
  it("accepts planar and spatial end points with a failure flag", () => {
    expect(codes([seg({ broken: "T/failed[1]", brokenStyle: "hidden", plane: "xy", depth: 1 })])).toEqual([]);
    expect(codes([seg({ target: "visual:rod", signal: ["T/x[1]", "T/y[1]", "T/z", "T/x[2]", "T/y[2]", "T/z"] })])).toEqual([]);
  });

  it("E301: a visual that cannot stretch", () => {
    expect(codes([seg({ target: "visual:ball" })])).toEqual(["E301"]);
    expect(codes([seg({ target: "visual:rod", axis: "+x" })])).toEqual(["E301"]);
    expect(codes([seg({ target: "visual:none" })])).toEqual(["E301"]);
  });

  it("E304: 4 or 6 coordinates as a list", () => {
    const five = ["T/x[1]", "T/y[1]", "T/z", "T/x[2]", "T/y[2]"] as SegmentBinding["signal"];
    expect(codes([seg({ signal: five })])).toEqual(["E304"]);
    expect(codes([seg({ signal: ["T/x[1]", "T/y[1]"] as unknown as SegmentBinding["signal"] })])).toEqual(["E304"]);
    expect(validateBindings([seg({ signal: five })], lookup, units)[0]?.message).toMatch(/4 or 6/);
  });

  it("E302 for an unknown failure flag, E303 for a coordinate that is no length", () => {
    expect(codes([seg({ broken: "T/nope" })])).toEqual(["E302"]);
    expect(codes([seg({ signal: ["T/x[1]", "T/N[1]", "T/x[2]", "T/y[2]"] })])).toEqual(["E303"]);
  });
});

interface SegmentCall {
  ref: string;
  a: Vec3;
  b: Vec3;
  axis: ShapeAxis | undefined;
  broken: SegmentBrokenStyle | null;
}

function recorder(): { target: ApplyTarget; calls: SegmentCall[] } {
  const calls: SegmentCall[] = [];
  const target: ApplyTarget = {
    setJointPosition: () => true,
    setPose: () => true,
    setVisualScale: () => true,
    setVisualColor: () => true,
    setVisible: () => true,
    setSegment: (ref, a, b, axis, broken) => {
      calls.push({ ref, a, b, axis, broken });
      return true;
    },
    reset: () => undefined,
  };
  return { target, calls };
}

describe("segment binding applier", () => {
  it("computes planar and spatial end points with gain, offset and depth", () => {
    expect(segmentEnds(seg({ depth: -1, gain: 2, offset: 1 }), [1, 2, 3, 4])).toEqual({ a: [3, -1, 5], b: [7, -1, 9], broken: null });
    expect(segmentEnds(seg({ signal: ["a", "b", "c", "d", "e", "f"] }), [1, 2, 3, 4, 5, 6])).toEqual({ a: [1, 2, 3], b: [4, 5, 6], broken: null });
    expect(segmentEnds(seg(), [1, null, 3, 4])).toBeNull();
    expect(segmentEnds(seg({ broken: "f" }), [0, 0, 1, 0, 1])?.broken).toBe("snapped");
    expect(segmentEnds(seg({ broken: "f", brokenStyle: "hidden" }), [0, 0, 1, 0, 1])?.broken).toBe("hidden");
    expect(segmentEnds(seg({ broken: "f" }), [0, 0, 1, 0, 0.2])?.broken).toBeNull();
  });

  it("requests the failure flag and draws the bar broken once it is set", () => {
    const binding = seg({ broken: "T/failed[1]", axis: "+x" });
    const ids = boundSignalIds([binding]);
    expect(ids).toEqual(["T/x[1]", "T/y[1]", "T/x[2]", "T/y[2]", "T/failed[1]"]);
    const buffer = new SignalBuffer(ids, 8);
    buffer.append(new Float64Array([0, 0, 0, 5, 0, 0, 1, 0, -0.1, 5, -0.1, 1]));
    const { target, calls } = recorder();
    const applier = new BindingApplier(target, [binding], ids);
    expect(applier.count).toBe(1);
    expect(applier.apply(buffer, 0)).toBe(1);
    expect(calls[0]).toEqual({ ref: "visual:bar", a: [0, 0, 0], b: [5, 0, 0], axis: "+x", broken: null });
    applier.apply(buffer, 1);
    expect(calls[1]?.broken).toBe("snapped");
    expect(calls[1]?.a).toEqual([0, 0, -0.1]);
  });

  it("skips a segment whose failure flag is not streamed", () => {
    const { target } = recorder();
    expect(new BindingApplier(target, [seg({ broken: "T/missing" })], ["T/x[1]", "T/y[1]", "T/x[2]", "T/y[2]"]).count).toBe(0);
  });
});

const engines: NullEngine[] = [];
afterEach(() => {
  for (const e of engines.splice(0)) e.dispose();
});

async function framesScene(): Promise<{ v: ViewerScene; scene: BuiltScene }> {
  const engine = new NullEngine({ renderWidth: 64, renderHeight: 64, textureSize: 64, deterministicLockstep: false, lockstepMaxSteps: 1, useHighPrecisionMatrix: true });
  engines.push(engine);
  const v = new ViewerScene(engine);
  const parsed = parseSdf(readFileSync(path.join(here, "fixtures", "scenes", "frames.sdf"), "utf8"), "scenes/t.sdf");
  const resolved = parsed.scene === null ? null : resolveScene(parsed.scene).scene;
  if (resolved === null) throw new Error("frames.sdf does not resolve");
  const { scene } = await buildScene(v, resolved);
  return { v, scene };
}

/** World matrix of a node relative to sdf_root, column convention. */
function nodeWorld(v: ViewerScene, node: { computeWorldMatrix(force: boolean): { multiply(o: unknown): { m: ArrayLike<number> } } }): Mat4 {
  const w = node.computeWorldMatrix(true);
  v.root.computeWorldMatrix(true);
  const m = w.multiply(v.root.getWorldMatrix().clone().invert()).m;
  const e = (i: number): number => m[i] ?? NaN;
  return [e(0), e(4), e(8), e(12), e(1), e(5), e(9), e(13), e(2), e(6), e(10), e(14), 0, 0, 0, 1];
}

describe("BuiltScene.setSegment", () => {
  it("stretches a box of a moved link between two world points, snaps and hides it", async () => {
    const { v, scene } = await framesScene();
    const a: Vec3 = [-1, 0.5, 2];
    const b: Vec3 = [3, 0.5, 4];
    expect(scene.setSegment("visual:a_box", a, b, undefined, null)).toBe(true);
    const node = scene.nodeOf("visual:a_box");
    if (node === null) throw new Error("no visual node");
    // the box is 1 m along x: its ends (-0.5, 0, 0) and (0.5, 0, 0) land on A and B
    const w = nodeWorld(v, node);
    expectPoint(transform(w, [-0.5, 0, 0]), a, 6);
    expectPoint(transform(w, [0.5, 0, 0]), b, 6);
    expect(node.isEnabled()).toBe(true);
    expect(scene.segmentTwinOf("visual:a_box")).toBeNull();

    expect(scene.setSegment("visual:a_box", a, b, undefined, "snapped")).toBe(true);
    const twin = scene.segmentTwinOf("visual:a_box");
    expect(twin?.isEnabled()).toBe(true);
    expect(twin?.getChildMeshes().length).toBe(1);
    expectPoint(transform(nodeWorld(v, node), [-0.5, 0, 0]), a, 6);
    if (twin === null) throw new Error("no twin");
    expectPoint(transform(nodeWorld(v, twin), [-0.5, 0, 0]), b, 6);

    expect(scene.setSegment("visual:a_box", a, b, undefined, "hidden")).toBe(true);
    expect(node.isEnabled()).toBe(false);
    expect(twin.isEnabled()).toBe(false);

    expect(scene.setSegment("visual:a_box", a, b, undefined, null)).toBe(true);
    expect(node.isEnabled()).toBe(true);
    expect(twin.isEnabled()).toBe(false);

    expect(scene.setSegment("visual:inner_visual", a, b, undefined, null)).toBe(false);
    expect(scene.setSegment("visual:a_box", [NaN, 0, 0], b, undefined, null)).toBe(false);
    scene.setSegment("visual:a_box", a, b, undefined, "snapped");
    scene.reset();
    expect(node.isEnabled()).toBe(true);
    expect(twin.isEnabled()).toBe(false);
  });
});
