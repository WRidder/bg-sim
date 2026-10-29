/**
 * Rigid-transform maths for the SDF scene (plan 7.6), free of Babylon.
 *
 * A `Mat4` is a row-major 4x4 homogeneous matrix in the column-vector convention
 * (`p' = M * p`, translation in the last column), stored as 16 numbers. All matrices here are
 * rigid (rotation plus translation); `inverse` relies on that.
 */

export type Vec3 = readonly [number, number, number];
export type Mat4 = readonly number[];
/** Unit quaternion, scalar part first (the model's `Vec{7}` pose chart orders it the same way). */
export type Quat = readonly [number, number, number, number];
/** `(qw, qx, qy, qz, x, y, z)`: the pose chart of the bindings. */
export type Pose7 = readonly [number, number, number, number, number, number, number];

export const IDENTITY: Mat4 = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];

export function multiply(a: Mat4, b: Mat4): Mat4 {
  const out = new Array<number>(16).fill(0);
  for (let r = 0; r < 4; r += 1) {
    for (let c = 0; c < 4; c += 1) {
      let s = 0;
      for (let k = 0; k < 4; k += 1) s += (a[r * 4 + k] ?? 0) * (b[k * 4 + c] ?? 0);
      out[r * 4 + c] = s;
    }
  }
  return out;
}

/** Product of several matrices, left to right. */
export function compose(...ms: readonly Mat4[]): Mat4 {
  return ms.reduce((acc, m) => multiply(acc, m), IDENTITY);
}

/** Inverse of a rigid transform: `[R t; 0 1]^-1 = [R^T -R^T t; 0 1]`. */
export function inverse(m: Mat4): Mat4 {
  const g = (r: number, c: number) => m[r * 4 + c] ?? 0;
  const out = new Array<number>(16).fill(0);
  for (let r = 0; r < 3; r += 1) for (let c = 0; c < 3; c += 1) out[r * 4 + c] = g(c, r);
  for (let r = 0; r < 3; r += 1) out[r * 4 + 3] = -(out[r * 4] ?? 0) * g(0, 3) - (out[r * 4 + 1] ?? 0) * g(1, 3) - (out[r * 4 + 2] ?? 0) * g(2, 3);
  out[15] = 1;
  return out;
}

export function translation(x: number, y: number, z: number): Mat4 {
  return [1, 0, 0, x, 0, 1, 0, y, 0, 0, 1, z, 0, 0, 0, 1];
}

export function rotationX(a: number): Mat4 {
  const c = Math.cos(a);
  const s = Math.sin(a);
  return [1, 0, 0, 0, 0, c, -s, 0, 0, s, c, 0, 0, 0, 0, 1];
}

export function rotationY(a: number): Mat4 {
  const c = Math.cos(a);
  const s = Math.sin(a);
  return [c, 0, s, 0, 0, 1, 0, 0, -s, 0, c, 0, 0, 0, 0, 1];
}

export function rotationZ(a: number): Mat4 {
  const c = Math.cos(a);
  const s = Math.sin(a);
  return [c, -s, 0, 0, s, c, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
}

/** SDF pose `x y z roll pitch yaw`: `R = Rz(yaw) * Ry(pitch) * Rx(roll)`, then the translation. */
export function fromPose(x: number, y: number, z: number, roll: number, pitch: number, yaw: number): Mat4 {
  const r = compose(rotationZ(yaw), rotationY(pitch), rotationX(roll));
  return multiply(translation(x, y, z), r);
}

/** Rotation by `angle` (rad) about `axis` (normalised here), Rodrigues' formula. */
export function rotationAxisAngle(axis: Vec3, angle: number): Mat4 {
  const n = Math.hypot(axis[0], axis[1], axis[2]) || 1;
  const x = axis[0] / n;
  const y = axis[1] / n;
  const z = axis[2] / n;
  const c = Math.cos(angle);
  const s = Math.sin(angle);
  const t = 1 - c;
  return [
    t * x * x + c, t * x * y - s * z, t * x * z + s * y, 0,
    t * x * y + s * z, t * y * y + c, t * y * z - s * x, 0,
    t * x * z - s * y, t * y * z + s * x, t * z * z + c, 0,
    0, 0, 0, 1,
  ];
}

/** The motion a joint adds: a rotation about the axis (revolute, continuous) or a slide along it (prismatic). */
export function jointMotion(type: "revolute" | "continuous" | "prismatic" | "fixed", axis: Vec3, q: number): Mat4 {
  switch (type) {
    case "revolute":
    case "continuous":
      return rotationAxisAngle(axis, q);
    case "prismatic": {
      const n = Math.hypot(axis[0], axis[1], axis[2]) || 1;
      return translation((axis[0] / n) * q, (axis[1] / n) * q, (axis[2] / n) * q);
    }
    case "fixed":
      return IDENTITY;
  }
}

export function transformPoint(m: Mat4, p: Vec3): Vec3 {
  const g = (i: number) => m[i] ?? 0;
  return [
    g(0) * p[0] + g(1) * p[1] + g(2) * p[2] + g(3),
    g(4) * p[0] + g(5) * p[1] + g(6) * p[2] + g(7),
    g(8) * p[0] + g(9) * p[1] + g(10) * p[2] + g(11),
  ];
}

export function transformDirection(m: Mat4, d: Vec3): Vec3 {
  const g = (i: number) => m[i] ?? 0;
  return [g(0) * d[0] + g(1) * d[1] + g(2) * d[2], g(4) * d[0] + g(5) * d[1] + g(6) * d[2], g(8) * d[0] + g(9) * d[1] + g(10) * d[2]];
}

export function positionOf(m: Mat4): Vec3 {
  return [m[3] ?? 0, m[7] ?? 0, m[11] ?? 0];
}

/** Unit quaternion `(w, x, y, z)` of the rotation part (Shepperd's method, w >= 0). */
export function quaternionOf(m: Mat4): Quat {
  const g = (r: number, c: number) => m[r * 4 + c] ?? 0;
  const tr = g(0, 0) + g(1, 1) + g(2, 2);
  let w: number;
  let x: number;
  let y: number;
  let z: number;
  if (tr > 0) {
    const s = Math.sqrt(tr + 1) * 2;
    w = s / 4;
    x = (g(2, 1) - g(1, 2)) / s;
    y = (g(0, 2) - g(2, 0)) / s;
    z = (g(1, 0) - g(0, 1)) / s;
  } else if (g(0, 0) > g(1, 1) && g(0, 0) > g(2, 2)) {
    const s = Math.sqrt(1 + g(0, 0) - g(1, 1) - g(2, 2)) * 2;
    w = (g(2, 1) - g(1, 2)) / s;
    x = s / 4;
    y = (g(0, 1) + g(1, 0)) / s;
    z = (g(0, 2) + g(2, 0)) / s;
  } else if (g(1, 1) > g(2, 2)) {
    const s = Math.sqrt(1 + g(1, 1) - g(0, 0) - g(2, 2)) * 2;
    w = (g(0, 2) - g(2, 0)) / s;
    x = (g(0, 1) + g(1, 0)) / s;
    y = s / 4;
    z = (g(1, 2) + g(2, 1)) / s;
  } else {
    const s = Math.sqrt(1 + g(2, 2) - g(0, 0) - g(1, 1)) * 2;
    w = (g(1, 0) - g(0, 1)) / s;
    x = (g(0, 2) + g(2, 0)) / s;
    y = (g(1, 2) + g(2, 1)) / s;
    z = s / 4;
  }
  const n = Math.hypot(w, x, y, z) || 1;
  const sign = w < 0 ? -1 : 1;
  return [(sign * w) / n, (sign * x) / n, (sign * y) / n, (sign * z) / n];
}

/** The transform of a pose `(qw, qx, qy, qz, x, y, z)`; the quaternion is normalised (a zero quaternion is the identity rotation). */
export function fromPose7(p: Pose7): Mat4 {
  const n = Math.hypot(p[0], p[1], p[2], p[3]);
  const [w, x, y, z] = n > 0 ? [p[0] / n, p[1] / n, p[2] / n, p[3] / n] : [1, 0, 0, 0];
  return [
    1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), p[4],
    2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), p[5],
    2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), p[6],
    0, 0, 0, 1,
  ];
}

export function toPose7(m: Mat4): Pose7 {
  const q = quaternionOf(m);
  const p = positionOf(m);
  return [q[0], q[1], q[2], q[3], p[0], p[1], p[2]];
}

export function normalize3(v: Vec3): Vec3 {
  const n = Math.hypot(v[0], v[1], v[2]) || 1;
  return [v[0] / n, v[1] / n, v[2] / n];
}
