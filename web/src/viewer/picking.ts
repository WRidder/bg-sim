export interface ScreenTarget {
  readonly ref: string;
  /** Projected centre in CSS pixels, and its distance from the camera. */
  readonly x: number;
  readonly y: number;
  readonly depth: number;
}

/**
 * Finger-sized picking: when the ray under the finger hits nothing, the entity whose
 * projected centre lies nearest, within `radiusPx`, is taken; among equally near ones
 * the closer to the camera wins.  Entities behind the camera never qualify.
 */
export function nearestTarget(targets: readonly ScreenTarget[], x: number, y: number, radiusPx: number): string | null {
  let best: ScreenTarget | null = null;
  let bestD = Infinity;
  for (const t of targets) {
    if (!(t.depth > 0)) continue;
    const d = Math.hypot(t.x - x, t.y - y);
    if (d > radiusPx) continue;
    if (d < bestD - 0.5 || (Math.abs(d - bestD) <= 0.5 && best && t.depth < best.depth)) {
      best = t;
      bestD = d;
    }
  }
  return best?.ref ?? null;
}

/** A tap is a pick; a pointer that travelled farther than this is a camera gesture. */
export const TAP_SLOP_PX = 10;
/** Half the 48 px touch target. */
export const PICK_RADIUS_PX = 24;
