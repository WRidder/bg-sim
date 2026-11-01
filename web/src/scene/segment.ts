/**
 * Placement maths of a `segment` binding (a bar between two moving points, such as a truss member), free
 * of Babylon: which visual-local axis runs from A to B, the world transform and stretch that put the
 * visual's axis on the line A-B, and the two drooping stubs of a snapped bar.
 *
 * The visual frame is centred on its shape (SDF boxes and cylinders are centred on their origin), so the
 * frame goes to the midpoint of A and B, its `axis` direction turns onto B - A by the shortest rotation,
 * and the shape is scaled along that axis by |AB| / extent. The cross-section keeps its size.
 */

import type { SegmentPlane, ShapeAxis } from "../contracts/model";
import { compose, normalize3, rotationAxisAngle, translation, type Mat4, type Vec3 } from "./pose";
import type { SdfGeometry } from "./sdf";

/** The local axis of a visual a segment stretches along. */
export interface SegmentAxis {
  /** Unit direction in the visual frame. */
  readonly dir: Vec3;
  /** Extent of the shape along it, m. */
  readonly extent: number;
  /** The scaling component (0 x, 1 y, 2 z) of the visual node that stretches it. */
  readonly index: 0 | 1 | 2;
}

/** World transform of the visual frame and the stretch along its axis. */
export interface SegmentPlacement {
  readonly world: Mat4;
  readonly scale: number;
}

/** Fraction of the length each stub of a snapped bar keeps. */
export const SNAP_FRACTION = 0.4;
/** Angle (rad) by which a snapped stub droops from the line A-B towards world -z. */
export const SNAP_DROOP = 0.45;

const AXIS_INDEX: Record<string, 0 | 1 | 2> = { x: 0, y: 1, z: 2 };

/** The default axis: a cylinder's own axis (+z), a box's +x. */
export function defaultSegmentAxis(geometry: SdfGeometry): ShapeAxis {
  return geometry.kind === "cylinder" ? "+z" : "+x";
}

/** The axis of `geometry` along `axis` (default per shape), or the reason the visual cannot be a segment. */
export function segmentAxis(geometry: SdfGeometry, axis?: ShapeAxis): SegmentAxis | string {
  const a = axis ?? defaultSegmentAxis(geometry);
  const sign = a.startsWith("-") ? -1 : 1;
  const index = AXIS_INDEX[a.slice(1)] ?? 0;
  const dir: Vec3 = [index === 0 ? sign : 0, index === 1 ? sign : 0, index === 2 ? sign : 0];
  switch (geometry.kind) {
    case "box": {
      const extent = geometry.size[index];
      return extent > 0 ? { dir, extent, index } : "the box has no extent along the segment axis";
    }
    case "cylinder":
      if (index !== 2) return "a cylinder stretches along its own axis only (+z or -z)";
      return geometry.length > 0 ? { dir, extent: geometry.length, index } : "the cylinder has no length";
    case "sphere":
      return "a sphere has no axis to stretch; use a box or a cylinder";
    case "mesh":
      return "a mesh cannot be stretched as a bar; use a box or a cylinder";
  }
}

/** A planar point (u, v) in the world: `xy` (u, v, depth), `xz` (u, depth, v), `yz` (depth, u, v). */
export function planarPoint(u: number, v: number, plane: SegmentPlane = "xz", depth = 0): Vec3 {
  switch (plane) {
    case "xy":
      return [u, v, depth];
    case "xz":
      return [u, depth, v];
    case "yz":
      return [depth, u, v];
  }
}

function sub(a: Vec3, b: Vec3): Vec3 {
  return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
}

function dot(a: Vec3, b: Vec3): number {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

function cross(a: Vec3, b: Vec3): Vec3 {
  return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
}

/** The shortest rotation that turns unit vector `from` onto unit vector `to`. */
export function rotationBetween(from: Vec3, to: Vec3): Mat4 {
  const c = Math.min(1, Math.max(-1, dot(from, to)));
  const axis = cross(from, to);
  const s = Math.hypot(axis[0], axis[1], axis[2]);
  if (s < 1e-12) {
    if (c > 0) return compose();
    // opposite: half a turn about any axis perpendicular to `from`
    const helper: Vec3 = Math.abs(from[0]) < 0.9 ? [1, 0, 0] : [0, 1, 0];
    return rotationAxisAngle(cross(from, helper), Math.PI);
  }
  return rotationAxisAngle(axis, Math.atan2(s, c));
}

/** The visual frame centred between `a` and `b`, its axis along B - A, and the stretch |AB| / extent. */
export function segmentPlacement(a: Vec3, b: Vec3, axis: SegmentAxis): SegmentPlacement {
  const d = sub(b, a);
  const length = Math.hypot(d[0], d[1], d[2]);
  const dir = length > 0 ? normalize3(d) : axis.dir;
  const mid: Vec3 = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2];
  return {
    world: compose(translation(mid[0], mid[1], mid[2]), rotationBetween(axis.dir, dir)),
    scale: length / axis.extent,
  };
}

/** `dir` turned by `angle` towards world -z (sideways along +x when `dir` is vertical). */
function droop(dir: Vec3, angle: number): Vec3 {
  const down: Vec3 = [0, 0, -1];
  const along = dot(down, dir);
  let perp = sub(down, [dir[0] * along, dir[1] * along, dir[2] * along]);
  if (Math.hypot(perp[0], perp[1], perp[2]) < 1e-9) perp = cross(dir, [0, 1, 0]);
  if (Math.hypot(perp[0], perp[1], perp[2]) < 1e-9) perp = [1, 0, 0];
  const p = normalize3(perp);
  const c = Math.cos(angle);
  const s = Math.sin(angle);
  return [dir[0] * c + p[0] * s, dir[1] * c + p[1] * s, dir[2] * c + p[2] * s];
}

/**
 * A snapped bar: two stubs of `SNAP_FRACTION` of the length, hanging from A and from B towards each other
 * and drooping by `SNAP_DROOP`, with a gap between them. The first stub keeps the visual's orientation sense
 * (its axis points from A towards B), the second points from B towards A.
 */
export function snappedPlacements(a: Vec3, b: Vec3, axis: SegmentAxis): [SegmentPlacement, SegmentPlacement] {
  const d = sub(b, a);
  const length = Math.hypot(d[0], d[1], d[2]);
  const dir = length > 0 ? normalize3(d) : axis.dir;
  const stub = SNAP_FRACTION * length;
  const make = (anchor: Vec3, towards: Vec3): SegmentPlacement => {
    const t = droop(towards, SNAP_DROOP);
    const end: Vec3 = [anchor[0] + t[0] * stub, anchor[1] + t[1] * stub, anchor[2] + t[2] * stub];
    return segmentPlacement(anchor, end, axis);
  };
  return [make(a, dir), make(b, [-dir[0], -dir[1], -dir[2]])];
}
