/**
 * A run over the pads: the clock, what counts as down on a pad, and what a landing is worth. It knows
 * nothing of the picture: the game reads its state and the test flies it.
 */

import type { Flight } from "./flight";
import type { Pad } from "./pads";

/** Seconds on the wheels, stopped, before a landing counts. */
export const HOLD = 2.5;

export interface Landing {
  pad: Pad;
  /** 0..100. */
  score: number;
  grade: string;
  sink: number;
  drift: number;
  /** Metres from the middle of the H. */
  offset: number;
  /** Seconds added to the clock. */
  penalty: number;
  /** The clock at this landing. */
  time: number;
}

/** The share a measure earns between the value that gets all of it and the one that gets none. */
const share = (value: number, full: number, none: number): number => Math.max(0, Math.min(1, (none - value) / (none - full)));

export function rate(pad: Pad, sink: number, drift: number, offset: number, time: number): Landing {
  const score = Math.round(100 * (0.5 * share(sink, 0.3, 2) + 0.2 * share(drift, 0.2, 2) + 0.3 * share(offset, 1, pad.radius)));
  const grade = score >= 90 ? "Feather" : score >= 75 ? "Smooth" : score >= 55 ? "Firm" : "Hard";
  return { pad, score, grade, sink, drift, offset, penalty: Math.round((100 - score) * 0.2), time };
}

export class Run {
  time = 0;
  /** Index into `pads` of the pad being flown to. */
  leg = 1;
  landings: Landing[] = [];
  /** Seconds it has stood on the next pad. */
  holding = 0;
  /** Set when the last landing counts. */
  done = false;
  active = false;
  pads: readonly Pad[] = [];
  private touch: { sink: number; drift: number; offset: number } | null = null;
  /** Called as each landing counts. */
  onLanding: (landing: Landing) => void = () => {};
  /** Called at each touchdown, on a pad or not. */
  onTouch: (sink: number) => void = () => {};

  start(pads: readonly Pad[]): void {
    this.pads = pads;
    this.time = 0;
    this.leg = 1;
    this.landings = [];
    this.holding = 0;
    this.done = false;
    this.active = true;
    this.touch = null;
  }

  stop(): void {
    this.active = false;
    this.done = false;
    this.pads = [];
  }

  get next(): Pad | undefined {
    return this.active && !this.done ? this.pads[this.leg] : undefined;
  }

  /** The clock plus what the landings cost. */
  score(): number {
    return this.time + this.landings.reduce((sum, landing) => sum + landing.penalty, 0);
  }

  /** Mean landing score, 0..100. */
  mean(): number {
    return this.landings.length ? Math.round(this.landings.reduce((sum, landing) => sum + landing.score, 0) / this.landings.length) : 0;
  }

  /** Once per frame or step, with what has passed since the last call. */
  update(flight: Flight, dt: number): void {
    if (!this.active || this.done) {
      return;
    }
    this.time += dt;
    const pad = this.pads[this.leg];
    const down = flight.touchdown;
    if (down) {
      flight.touchdown = null;
      this.onTouch(down.sink);
      this.touch = { sink: down.sink, drift: down.drift, offset: Math.hypot(down.north - pad.north, down.east - pad.east) };
    }
    const offset = Math.hypot(flight.north() - pad.north, flight.east() - pad.east);
    if (flight.groundTime > 0.2 && offset <= pad.radius && flight.groundSpeed() < 1 && flight.get("wow") > 0.9) {
      this.holding += dt;
    } else {
      this.holding = 0;
    }
    if (this.holding >= HOLD) {
      const touch = this.touch ?? { sink: 1, drift: 0, offset };
      const landing = rate(pad, touch.sink, touch.drift, Math.max(touch.offset, offset), this.time);
      this.landings.push(landing);
      this.holding = 0;
      this.touch = null;
      this.leg += 1;
      this.done = this.leg >= this.pads.length;
      this.onLanding(landing);
    }
  }
}
