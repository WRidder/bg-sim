/**
 * The best lap, kept in the browser: the car's pose ten times a second. It replays as a ghost, and
 * its clock against the distance gives the gap shown while driving. A private window may keep
 * nothing, and the lap still counts.
 */

import type { Vehicle } from "./vehicle";

const FIELDS = 9;
/** x, y, z, qw, qx, qy, qz, steer, s */
export type Frame = number[];

export interface Pose {
  x: number;
  y: number;
  z: number;
  w: number;
  qx: number;
  qy: number;
  qz: number;
  steer: number;
}

export class Recording {
  private data: number[] = [];
  private next = 0;

  clear(): void {
    this.data = [];
    this.next = 0;
  }

  sample(car: Vehicle, time: number): void {
    if (time < this.next) {
      return;
    }
    this.next = time + 0.1;
    this.data.push(
      +car.get("chassis_px").toFixed(2), +car.get("chassis_py").toFixed(2), +car.get("chassis_pz").toFixed(3),
      +car.get("chassis_qw").toFixed(4), +car.get("chassis_qx").toFixed(4), +car.get("chassis_qy").toFixed(4), +car.get("chassis_qz").toFixed(4),
      +car.u[0].toFixed(2), +car.s.toFixed(1),
    );
  }

  take(time: number): GhostLap {
    return new GhostLap(this.data, time);
  }
}

export class GhostLap {
  readonly frames: number;

  constructor(
    readonly data: number[],
    readonly time: number,
  ) {
    this.frames = Math.floor(data.length / FIELDS);
  }

  /** The pose `time` seconds into the lap, null past its end. */
  at(time: number, into: Pose): Pose | null {
    const f = time / 0.1;
    const i = Math.floor(f);
    if (i < 0 || i >= this.frames - 1) {
      return null;
    }
    const t = f - i;
    const d = this.data;
    const a = i * FIELDS;
    const b = a + FIELDS;
    const mix = (k: number): number => d[a + k] + (d[b + k] - d[a + k]) * t;
    into.x = mix(0);
    into.y = mix(1);
    into.z = mix(2);
    into.w = mix(3);
    into.qx = mix(4);
    into.qy = mix(5);
    into.qz = mix(6);
    into.steer = mix(7);
    return into;
  }

  /** When the recorded lap passed arc length `s`. */
  timeAt(s: number): number | null {
    const d = this.data;
    let low = 0;
    let high = this.frames - 1;
    // The first frames sit before the line on an opening lap, with s near the end of the route.
    while (low < high && d[low * FIELDS + 8] > d[(this.frames - 1) * FIELDS + 8] && low < 20) {
      low += 1;
    }
    if (s < d[low * FIELDS + 8] || s > d[high * FIELDS + 8]) {
      return null;
    }
    while (high - low > 1) {
      const mid = (low + high) >> 1;
      if (d[mid * FIELDS + 8] <= s) {
        low = mid;
      } else {
        high = mid;
      }
    }
    const from = d[low * FIELDS + 8];
    const to = d[high * FIELDS + 8];
    return (low + (to > from ? (s - from) / (to - from) : 0)) * 0.1;
  }
}

export function loadGhost(key: string): GhostLap | null {
  try {
    const text = localStorage.getItem(key);
    if (!text) {
      return null;
    }
    const { time, data } = JSON.parse(text) as { time: number; data: number[] };
    return new GhostLap(data, time);
  } catch {
    return null;
  }
}

export function saveGhost(key: string, ghost: GhostLap): void {
  try {
    localStorage.setItem(key, JSON.stringify({ time: ghost.time, data: ghost.data }));
  } catch {
    // Not kept; see above.
  }
}
