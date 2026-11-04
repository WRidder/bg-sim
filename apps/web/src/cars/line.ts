/**
 * The racing line and the speed along it. The line is the tightest string that fits between the
 * track's edges: each point is pulled towards the chord of its neighbours, at a coarse scale first
 * so the whole corner moves, then finer. The speed comes from the grip at that curvature, then a
 * pass backwards for braking and one forwards for what the motor can do.
 */

import { hills } from "./hills";
import type { Kind, Track } from "./track";

export interface Grip {
  /** Friction the line is planned with. */
  mu: number;
  /** Extra normal acceleration per (m/s)^2 from downforce. */
  aero: number;
  /** Mass, kg, power, W, and top speed, m/s. */
  mass: number;
  power: number;
  top: number;
  /** Deceleration the plan uses, as a share of the grip. */
  brakeShare: number;
  /** Traction limit, m/s^2. */
  launch: number;
  /** Drag area, m^2. */
  dragArea: number;
  /** How far over the speed that just lifts off a crest the plan will go. */
  flight: number;
}

export const GRIPS: Record<Kind, Grip> = {
  racecar: { mu: 1.38, aero: 0.00215, mass: 724, power: 255000, top: 90, brakeShare: 0.82, launch: 9, dragArea: 0.95, flight: 0 },
  buggy: { mu: 0.74, aero: 0, mass: 908, power: 118000, top: 34, brakeShare: 0.8, launch: 6.5, dragArea: 1.3, flight: 1.3 },
};

export class Line {
  /** Lateral offset of the line from the centre, per sample, left positive. */
  readonly offset: Float32Array;
  readonly x: Float32Array;
  readonly y: Float32Array;
  readonly curvature: Float32Array;
  /** Target speed, m/s. */
  readonly speed: Float32Array;
  /** 1 where the plan brakes hard, for the painted hint. */
  readonly braking: Float32Array;
  /** Planned time to each sample, s; the last entry is the whole lap. */
  readonly time: Float32Array;

  constructor(track: Track, grip: Grip = GRIPS[track.definition.car], margin = 1.7) {
    const { n, x: cx, y: cy, tx, ty, width } = track;
    const limit = width - margin;
    const offset = new Float32Array(n);
    const nx = (i: number): number => -ty[i];
    const ny = (i: number): number => tx[i];
    for (const span of [64, 32, 16, 8, 4]) {
      for (let sweep = 0; sweep < 80; sweep += 1) {
        for (let i = 0; i < n; i += 1) {
          const a = (i + n - span) % n;
          const b = (i + span) % n;
          const px = 0.5 * (cx[a] + nx(a) * offset[a] + cx[b] + nx(b) * offset[b]);
          const py = 0.5 * (cy[a] + ny(a) * offset[a] + cy[b] + ny(b) * offset[b]);
          const wanted = (px - cx[i]) * nx(i) + (py - cy[i]) * ny(i);
          offset[i] = Math.max(-limit, Math.min(limit, offset[i] + 0.7 * (wanted - offset[i])));
        }
      }
    }
    this.offset = offset;
    this.x = new Float32Array(n);
    this.y = new Float32Array(n);
    for (let i = 0; i < n; i += 1) {
      this.x[i] = cx[i] + nx(i) * offset[i];
      this.y[i] = cy[i] + ny(i) * offset[i];
    }
    const curvature = new Float32Array(n);
    const h = 5;
    for (let i = 0; i < n; i += 1) {
      const a = (i + n - h) % n;
      const b = (i + h) % n;
      const ux = this.x[i] - this.x[a];
      const uy = this.y[i] - this.y[a];
      const vx = this.x[b] - this.x[i];
      const vy = this.y[b] - this.y[i];
      const cross = ux * vy - uy * vx;
      curvature[i] = (2 * cross) / Math.max(Math.hypot(ux, uy) * Math.hypot(vx, vy) * Math.hypot(ux + vx, uy + vy), 1e-3);
    }
    this.curvature = curvature;

    const speed = new Float32Array(n);
    for (let i = 0; i < n; i += 1) {
      const k = Math.abs(curvature[i]);
      const room = k - grip.mu * grip.aero;
      speed[i] = room > 1e-5 ? Math.min(grip.top, Math.sqrt((grip.mu * 9.81) / room)) : grip.top;
    }
    const step = track.length / n;
    if (track.definition.car === "buggy") {
      // A crest flies, and a buggy steers nothing in the air: the plan lifts before the sharp ones.
      const span = 7;
      for (let i = 0; i < n; i += 1) {
        const a = hills(this.x[(i + n - span) % n], this.y[(i + n - span) % n]);
        const b = hills(this.x[i], this.y[i]);
        const c = hills(this.x[(i + span) % n], this.y[(i + span) % n]);
        const crest = (2 * b - a - c) / (span * span);
        if (crest > 0.002) {
          speed[i] = Math.min(speed[i], Math.sqrt((9.81 * grip.flight) / crest));
        }
      }
    }
    const lateral = (v: number, i: number): number => v * v * Math.abs(curvature[i]);
    const total = (v: number): number => grip.mu * (9.81 + grip.aero * v * v);
    for (let round = 0; round < 2; round += 1) {
      for (let k = 2 * n - 1; k >= 0; k -= 1) {
        const i = k % n;
        const v = speed[(i + 1) % n];
        const left = Math.max(total(v) ** 2 - lateral(v, i) ** 2, 0.01);
        const decel = Math.sqrt(left) * grip.brakeShare + (0.6 * grip.dragArea * v * v) / grip.mass;
        speed[i] = Math.min(speed[i], Math.sqrt(v * v + 2 * decel * step));
      }
      for (let k = 0; k < 2 * n; k += 1) {
        const i = k % n;
        const v = speed[i];
        const left = Math.sqrt(Math.max(total(v) ** 2 - lateral(v, i) ** 2, 0.01));
        const push = Math.min(grip.launch, left * 0.7, grip.power / Math.max(grip.mass * v, 1)) - (0.6 * grip.dragArea * v * v) / grip.mass;
        const j = (i + 1) % n;
        speed[j] = Math.min(speed[j], Math.sqrt(Math.max(v * v + 2 * push * step, 0.1)));
      }
    }
    this.speed = speed;
    this.braking = new Float32Array(n);
    this.time = new Float32Array(n + 1);
    for (let i = 0; i < n; i += 1) {
      const j = (i + 1) % n;
      const v = 0.5 * (speed[i] + speed[j]);
      this.time[i + 1] = this.time[i] + step / Math.max(v, 1);
      this.braking[i] = Math.max(0, Math.min(1, ((speed[i] - speed[j]) / step) * v * 0.16));
    }
  }

  /** The planned lap, seconds. */
  get lap(): number {
    return this.time[this.time.length - 1];
  }
}
