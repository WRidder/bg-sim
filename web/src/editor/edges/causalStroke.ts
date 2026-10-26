/**
 * Causal-stroke geometry (plan 5.7 and 7.3).
 *
 * SCAP returns `strokeAt: "from" | "to"` per bond: the end where effort is the
 * input. The editor draws a short bar perpendicular to the bond there. The bar
 * sits a little inside the endpoint so it never covers the port glyph, and the
 * `to` variant clears the bond's half arrow, which is 10 px long.
 *
 * Pure functions: the edge component and the unit tests share them.
 */

import type { Point } from "../geometry";

export type CausalStrokeAt = "from" | "to";

/** Half the length of the drawn bar. */
export const CAUSAL_STROKE_HALF = 7;
/** How far inside the `from` endpoint the bar sits. */
export const CAUSAL_STROKE_FROM_OFFSET = 7;
/** How far inside the `to` endpoint the bar sits (past the half arrow). */
export const CAUSAL_STROKE_TO_OFFSET = 15;

export interface CausalBar {
  strokeAt: CausalStrokeAt;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

function clampOffset(offset: number, length: number): number {
  // A very short bond still has room for a visible bar at both ends.
  return Math.min(offset, Math.max(1, length * 0.45));
}

/**
 * The perpendicular bar of one bond end, in flow coordinates.
 *
 * Returns `null` for a null stroke and for a degenerate (zero-length) bond.
 */
export function causalStrokeBar(
  from: Point,
  to: Point,
  strokeAt: CausalStrokeAt | null,
  half = CAUSAL_STROKE_HALF,
): CausalBar | null {
  if (strokeAt === null) {
    return null;
  }
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const length = Math.hypot(dx, dy);
  if (length < 1e-6) {
    return null;
  }
  const ux = dx / length;
  const uy = dy / length;
  const offset = clampOffset(
    strokeAt === "to" ? CAUSAL_STROKE_TO_OFFSET : CAUSAL_STROKE_FROM_OFFSET,
    length,
  );
  const centre =
    strokeAt === "to"
      ? { x: to.x - ux * offset, y: to.y - uy * offset }
      : { x: from.x + ux * offset, y: from.y + uy * offset };
  const nx = -uy * half;
  const ny = ux * half;
  return {
    strokeAt,
    x1: centre.x + nx,
    y1: centre.y + ny,
    x2: centre.x - nx,
    y2: centre.y - ny,
  };
}

/** The midpoint of a bar, for assertions and hit testing. */
export function causalBarMidpoint(bar: CausalBar): Point {
  return { x: (bar.x1 + bar.x2) / 2, y: (bar.y1 + bar.y2) / 2 };
}
