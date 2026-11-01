/**
 * The 3D camera's wheel zoom, orbit pivot and clip planes, as pure vector maths (`ViewerScene` applies it to
 * the orbit camera). After the HMI viewer (plan 7.6, `framework/hmi/src/viewer/orbitPivot.ts`), with one change:
 * a wheel notch moves the camera a fixed *fraction* of its distance to the point under the cursor, not a fixed
 * number of metres, so the zoom feels the same on a 10 cm part and on a 2 km race track.
 *
 * Zoom: the camera moves along the ray through the cursor toward (or away from) the scene point under it. The
 * view direction is unchanged, so that point stays under the cursor; it becomes the orbit pivot.
 *
 * Pivot: the orbit target becomes a scene point while the camera keeps its place and orientation. The point
 * lies off the view axis, which the orbit camera would turn the view to, so the lateral part of the offset is
 * kept as the camera's screen offset (`targetScreenOffset`, view-space metres) and the view does not move.
 */
import { Vector3, type Matrix } from "@babylonjs/core/Maths/math.vector";

/** One wheel notch in brings the camera to this fraction of its distance to the point under the cursor. */
export const ZOOM_RATIO_PER_NOTCH = 0.8;
/** Most notches one wheel event may count (a trackpad burst or a fast spin). */
export const MAX_NOTCHES_PER_EVENT = 3;
/** The camera stops this close to the point it zooms to, m. */
export const MIN_ZOOM_DISTANCE_M = 1e-3;
/** The ground plane is a zoom point only up to this many times the orbit radius away (not at the horizon). */
export const GROUND_MAX_RADII = 10;

/**
 * Notches a wheel event stands for, positive = zoom in. A mouse notch is 100 px (or 3 lines); a trackpad scroll
 * sends fractions. A trackpad pinch arrives as a wheel event with `ctrlKey`, whose `deltaY` is −100·ln(scale):
 * it maps to the notches that scale the distance by exactly the pinch, so the scene follows the fingers.
 */
export function wheelNotches(deltaY: number, deltaMode: number, ctrlKey = false): number {
  let n: number;
  if (ctrlKey && deltaMode === 0) n = -deltaY / (100 * Math.log(1 / ZOOM_RATIO_PER_NOTCH));
  else if (deltaMode === 1) n = -deltaY / 3;
  else if (deltaMode === 2) n = -deltaY;
  else n = -deltaY / 100;
  return Math.max(-MAX_NOTCHES_PER_EVENT, Math.min(MAX_NOTCHES_PER_EVENT, n));
}

/** The factor the distance to the zoom point is multiplied by for `notches` (exponential: each notch alike). */
export function zoomFactor(notches: number): number {
  return Math.pow(ZOOM_RATIO_PER_NOTCH, notches);
}

/**
 * The eye after zooming by `factor` toward `point`: on the line from `point` through `eye`, at `factor` times
 * the distance. Zooming in stops at `minDistance` from the point; zooming out at `maxDistance` (never closer
 * than before). Null when the eye does not move (at a limit, or on the point).
 */
export function zoomEye(eye: Vector3, point: Vector3, factor: number, minDistance: number, maxDistance: number): Vector3 | null {
  const rel = eye.subtract(point);
  const d = rel.length();
  const nd = zoomScale(d, factor, minDistance, maxDistance);
  return nd === null ? null : point.add(rel.scale(nd / d));
}

/**
 * `value` (a distance, or a view size) times `factor`, kept within `min`..`max`: a zoom in never grows it, a zoom
 * out never shrinks it. Null when it does not change.
 */
export function zoomScale(value: number, factor: number, min: number, max: number): number | null {
  if (!(value > 0) || !Number.isFinite(factor) || factor <= 0) return null;
  const next = factor < 1 ? Math.min(value, Math.max(value * factor, min)) : Math.max(value, Math.min(value * factor, max));
  return next === value ? null : next;
}

/**
 * The orthographic zoom: the view shrinks by `factor` about `point`, so the eye slides sideways toward the point by
 * (1 − factor) of its offset from the view axis; its depth does not matter in a parallel projection.
 */
export function orthoZoomEye(eye: Vector3, forward: Vector3, point: Vector3, factor: number): Vector3 {
  const rel = point.subtract(eye);
  const lateral = rel.subtract(forward.scale(Vector3.Dot(rel, forward)));
  return eye.add(lateral.scale(1 - factor));
}

/** The orbit camera's placement: position, target and the screen offset's world vector (`offsetWorld`, camera position less effective eye). */
export interface Rig {
  readonly position: Vector3;
  readonly target: Vector3;
  /** The effective eye is `position - offsetWorld`; zero without a screen offset. */
  readonly offsetWorld: Vector3;
}

/** Where the camera really looks from: the orbit position less the screen offset. */
export function rigEye(rig: Rig): Vector3 {
  return rig.position.subtract(rig.offsetWorld);
}

export interface Pivoted {
  readonly position: Vector3;
  readonly target: Vector3;
  /** The screen offset (view x, y, m) that keeps the view where it was. */
  readonly offset: readonly [number, number];
  /** Distance of the pivot along the view axis: the new orbit radius. */
  readonly radius: number;
}

/**
 * The orbit rig with its target at `point`, seen from `eye` in the view direction `forward` (unit). `view` is the
 * camera's view matrix (only its rotation is used: it takes world directions to the view axes).
 */
export function pivotRig(eye: Vector3, forward: Vector3, point: Vector3, view: Matrix): Pivoted {
  const rel = point.subtract(eye);
  const depth = Vector3.Dot(rel, forward);
  const lateral = rel.subtract(forward.scale(depth));
  const v = Vector3.TransformNormal(lateral, view);
  return { position: point.subtract(forward.scale(depth)), target: point.clone(), offset: [v.x, v.y], radius: depth };
}

/** The point where the ray meets the plane through `origin` with unit `normal`, or null (parallel, or behind the ray's start). */
export function rayPlane(rayOrigin: Vector3, rayDir: Vector3, origin: Vector3, normal: Vector3): Vector3 | null {
  const denom = Vector3.Dot(rayDir, normal);
  if (Math.abs(denom) < 1e-9) return null;
  const t = Vector3.Dot(origin.subtract(rayOrigin), normal) / denom;
  return t > 0 ? rayOrigin.add(rayDir.scale(t)) : null;
}

/** The near plane is at most this fraction of the orbit radius (the distance to what the view is about). */
export const NEAR_RADIUS_FRACTION = 0.005;
/** ... and at most this fraction of the distance to the nearest object in front of the camera. */
export const NEAR_GAP_FRACTION = 0.5;
/** The near plane never comes closer than this, m. */
export const NEAR_MIN_M = 1e-4;
/** Room behind the farthest object, as a fraction. */
export const FAR_MARGIN = 1.1;

/**
 * Near and far clip planes for the orbit radius, the distance to the nearest object the camera is outside of
 * (null: unknown) and to the far side of the farthest object. The near plane follows the radius, so a close-up
 * does not clip and a km-scale view keeps its depth precision; the far plane takes in everything.
 */
export function clipPlanes(radius: number, nearestGap: number | null, farthest: number): { readonly near: number; readonly far: number } {
  const far = Math.max(farthest * FAR_MARGIN, radius * 2, 1);
  let near = radius * NEAR_RADIUS_FRACTION;
  if (nearestGap !== null && nearestGap > 0) near = Math.min(near, nearestGap * NEAR_GAP_FRACTION);
  return { near: Math.max(near, NEAR_MIN_M), far };
}
