/**
 * Assumed-mode shapes of an Euler-Bernoulli beam and the kinematics of its deformed sections
 * (deformation bindings, contract `deformationBinding`). The Julia FlexibleBeam blocks use the same
 * formulas; `contracts/fixtures/modes/mode_shapes.json` (written by the Julia side) cross-checks them.
 *
 * Beam frame: origin at end A (s = 0), x along the beam to end B (s = L). Bending "y" deflects along
 * y (the section turns about z by the slope), bending "z" along z (the section turns about y), torsion
 * turns the section about x.
 *
 *   w(s) = sum_n phi_n(s) eta_n   (eta in m),   theta(s) = sum_n psi_n(s) eta_n   (eta in rad)
 *
 * Every shape is normalised to (1/L) integral_0^L f^2 ds = 1. Bending, with x = lambda_n s / L:
 *
 *   clamped-free: phi = cosh x - cos x - sigma (sinh x - sin x),  sigma = (sinh l - sin l)/(cosh l + cos l)
 *   free-free:    phi = cosh x + cos x - sigma (sinh x + sin x),  sigma = (cosh l - cos l)/(sinh l - sin l)
 *
 * Torsion: clamped-free psi = sqrt 2 sin((2n-1) pi s / 2L), free-free psi = sqrt 2 cos(n pi s / L).
 *
 * cosh x - sigma sinh x cancels badly for large x (sigma -> 1). It is evaluated as
 * ((1 - sigma) e^x + (1 + sigma) e^-x) / 2 with (1 - sigma) e^lambda from a closed form free of the
 * cancellation, so the hyperbolic part stays accurate to the last digits (and in float32 too).
 */

export type DeformationFamily = "bending-y" | "bending-z" | "torsion";
export type DeformationBasis = "clamped-free" | "free-free";

/** Modes per family a binding may give. */
export const MAX_MODES = 3;

/** Roots lambda_n of the frequency equations (cos l cosh l = -1, resp. +1). */
export const LAMBDA: Readonly<Record<DeformationBasis, readonly number[]>> = {
  "clamped-free": [1.87510407, 4.69409113, 7.85475744],
  "free-free": [4.73004074, 7.85320462, 10.99560784],
};

interface BendingConstants {
  readonly lambda: number;
  readonly sigma: number;
  /** (1 - sigma) e^lambda, from a cancellation-free form. */
  readonly aScaled: number;
  /** +1 clamped-free (trig part -cos x + sigma sin x), -1 free-free (cos x - sigma sin x). */
  readonly trigSign: 1 | -1;
}

function bendingConstants(basis: DeformationBasis, lambda: number): BendingConstants {
  const em = Math.exp(-lambda);
  const c = Math.cos(lambda);
  const s = Math.sin(lambda);
  if (basis === "clamped-free") {
    const sigma = (Math.sinh(lambda) - s) / (Math.cosh(lambda) + c);
    // 1 - sigma = (e^-l + cos l + sin l) / (cosh l + cos l); multiplied by e^l:
    const aScaled = (2 * (em + c + s)) / (1 + em * em + 2 * c * em);
    return { lambda, sigma, aScaled, trigSign: 1 };
  }
  const sigma = (Math.cosh(lambda) - c) / (Math.sinh(lambda) - s);
  // 1 - sigma = (cos l - sin l - e^-l) / (sinh l - sin l); multiplied by e^l:
  const aScaled = (2 * (c - s - em)) / (1 - em * em - 2 * s * em);
  return { lambda, sigma, aScaled, trigSign: -1 };
}

const BENDING: Readonly<Record<DeformationBasis, readonly BendingConstants[]>> = {
  "clamped-free": LAMBDA["clamped-free"].map((l) => bendingConstants("clamped-free", l)),
  "free-free": LAMBDA["free-free"].map((l) => bendingConstants("free-free", l)),
};

/** sigma_n of a bending mode (1-based n). */
export function bendingSigma(basis: DeformationBasis, n: number): number {
  return modeConstants(basis, n).sigma;
}

function modeConstants(basis: DeformationBasis, n: number): BendingConstants {
  const k = BENDING[basis][n - 1];
  if (k === undefined) throw new RangeError(`mode ${String(n)} of ${basis}: only modes 1 to ${String(MAX_MODES)} exist`);
  return k;
}

/**
 * A shape and its first two derivatives with respect to xi = s / L, at xi (0..1).
 * Divide the derivatives by L and L^2 for d/ds and d^2/ds^2.
 */
export type ShapeValues = readonly [f: number, df: number, d2f: number];

/** Bending mode n (1-based) of `basis` at xi = s / L. */
export function bendingShape(basis: DeformationBasis, n: number, xi: number): ShapeValues {
  const { lambda, sigma, aScaled, trigSign } = modeConstants(basis, n);
  const x = lambda * xi;
  const ae = aScaled * Math.exp(x - lambda); // (1 - sigma) e^x
  const be = (1 + sigma) * Math.exp(-x); // (1 + sigma) e^-x
  const h0 = (ae + be) / 2; // cosh x - sigma sinh x
  const h1 = (ae - be) / 2; // its derivative
  const cx = Math.cos(x);
  const sx = Math.sin(x);
  // clamped-free trig part and derivatives; free-free is the negative
  const t0 = trigSign * (-cx + sigma * sx);
  const t1 = trigSign * (sx + sigma * cx);
  const t2 = trigSign * (cx - sigma * sx);
  return [h0 + t0, lambda * (h1 + t1), lambda * lambda * (h0 + t2)];
}

/** Torsion mode n (1-based) of `basis` at xi = s / L. */
export function torsionShape(basis: DeformationBasis, n: number, xi: number): ShapeValues {
  if (n < 1 || n > MAX_MODES) throw new RangeError(`mode ${String(n)} of ${basis}: only modes 1 to ${String(MAX_MODES)} exist`);
  const k = basis === "clamped-free" ? ((2 * n - 1) * Math.PI) / 2 : n * Math.PI;
  const r = Math.SQRT2;
  if (basis === "clamped-free") {
    const sv = Math.sin(k * xi);
    return [r * sv, r * k * Math.cos(k * xi), -r * k * k * sv];
  }
  const cv = Math.cos(k * xi);
  return [r * cv, -r * k * Math.sin(k * xi), -r * k * k * cv];
}

/** Mode n of a family at xi = s / L. */
export function modeShape(family: DeformationFamily, basis: DeformationBasis, n: number, xi: number): ShapeValues {
  return family === "torsion" ? torsionShape(basis, n, xi) : bendingShape(basis, n, xi);
}

/** One family's modal coordinates on a beam (gain applied, not exaggerated). */
export interface ModalSet {
  readonly family: DeformationFamily;
  readonly basis: DeformationBasis;
  readonly eta: readonly number[];
}

/** The deformation of the section at s. Slopes and curvatures are d/ds and d^2/ds^2. */
export interface SectionState {
  /** Deflection along y and z (m). */
  readonly wy: number;
  readonly wz: number;
  /** Slopes dw/ds. */
  readonly slopeY: number;
  readonly slopeZ: number;
  /** Curvatures d^2w/ds^2 (1/m). */
  readonly curvY: number;
  readonly curvZ: number;
  /** Twist about x (rad). */
  readonly theta: number;
}

export const REST_SECTION: SectionState = { wy: 0, wz: 0, slopeY: 0, slopeZ: 0, curvY: 0, curvZ: 0, theta: 0 };

/**
 * The section at s of a beam of length L, deformed by `sets` (each family at most once is meant; a
 * repeated family adds up) with every coordinate times `scale` (the exaggeration). Outside 0..L the
 * shape continues rigidly with the end section: w(s) = w(end) + w'(end) (s - end), no curvature.
 */
export function sectionState(sets: readonly ModalSet[], s: number, length: number, scale = 1): SectionState {
  const L = length > 0 ? length : 1;
  const xi = Math.min(1, Math.max(0, s / L));
  const beyond = s - xi * L;
  let wy = 0;
  let wz = 0;
  let slopeY = 0;
  let slopeZ = 0;
  let curvY = 0;
  let curvZ = 0;
  let theta = 0;
  for (const set of sets) {
    set.eta.forEach((eta, i) => {
      if (i >= MAX_MODES || !Number.isFinite(eta) || eta === 0) return;
      const [f, df, d2f] = modeShape(set.family, set.basis, i + 1, xi);
      const e = eta * scale;
      if (set.family === "torsion") {
        theta += f * e;
      } else if (set.family === "bending-y") {
        wy += f * e;
        slopeY += (df / L) * e;
        curvY += (d2f / (L * L)) * e;
      } else {
        wz += f * e;
        slopeZ += (df / L) * e;
        curvZ += (d2f / (L * L)) * e;
      }
    });
  }
  if (beyond !== 0) {
    wy += slopeY * beyond;
    wz += slopeZ * beyond;
    curvY = 0;
    curvZ = 0;
  }
  return { wy, wz, slopeY, slopeZ, curvY, curvZ, theta };
}

/** Row-major 3x3 rotation. */
export type Mat3 = readonly [number, number, number, number, number, number, number, number, number];

/**
 * The rotation of a section (beam frame): first the twist theta about x, then the smallest rotation
 * that turns x onto the tangent (1, w_y', w_z') of the deflected axis, so the section stays
 * perpendicular to the axis (Euler-Bernoulli). For small slopes this turns about z by w_y' and about
 * y by -w_z'.
 */
export function sectionRotation(state: SectionState): Mat3 {
  const a = state.slopeY;
  const b = state.slopeZ;
  const inv = 1 / Math.hypot(1, a, b);
  const tx = inv;
  const ty = a * inv;
  const tz = b * inv;
  // Rodrigues for e_x -> t: axis k = e_x x t = (0, -tz, ty), sin = |k|, cos = tx
  const c = tx;
  // (1 - c) / s^2 = 1 / (1 + c), stable at s -> 0
  const f = 1 / (1 + c);
  const kx = 0;
  const ky = -tz;
  const kz = ty;
  // R_bend = c I + [k]x + f k k^T  (k unnormalised: |k| = sin)
  const r00 = c + f * kx * kx;
  const r01 = -kz + f * kx * ky;
  const r02 = ky + f * kx * kz;
  const r10 = kz + f * ky * kx;
  const r11 = c + f * ky * ky;
  const r12 = -kx + f * ky * kz;
  const r20 = -ky + f * kz * kx;
  const r21 = kx + f * kz * ky;
  const r22 = c + f * kz * kz;
  // times R_x(theta)
  const ct = Math.cos(state.theta);
  const st = Math.sin(state.theta);
  return [
    r00, r01 * ct + r02 * st, -r01 * st + r02 * ct,
    r10, r11 * ct + r12 * st, -r11 * st + r12 * ct,
    r20, r21 * ct + r22 * st, -r21 * st + r22 * ct,
  ];
}

/** Where the material point (s, y, z) of the rest beam goes (beam frame). */
export function deformPoint(state: SectionState, rotation: Mat3, s: number, y: number, z: number): [number, number, number] {
  const R = rotation;
  return [s + R[1] * y + R[2] * z, state.wy + R[4] * y + R[5] * z, state.wz + R[7] * y + R[8] * z];
}

/** A rest direction (beam frame) turned with the section. */
export function rotateVector(R: Mat3, x: number, y: number, z: number): [number, number, number] {
  return [R[0] * x + R[1] * y + R[2] * z, R[3] * x + R[4] * y + R[5] * z, R[6] * x + R[7] * y + R[8] * z];
}

/**
 * Bending strain magnitude of the outer fibre at a section: |curvature| times the distance of the
 * outer fibre from the neutral axis. A rectangle (half sizes cy, cz) peaks at a corner, cy |w_y''| +
 * cz |w_z''|; a circle (radius r) at r |(w_y'', w_z'')|.
 */
export function outerStrain(state: SectionState, section: { readonly round: boolean; readonly cy: number; readonly cz: number }): number {
  return section.round ? section.cy * Math.hypot(state.curvY, state.curvZ) : section.cy * Math.abs(state.curvY) + section.cz * Math.abs(state.curvZ);
}
