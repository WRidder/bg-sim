/**
 * The flight, without any drawing: the FMU, the pacing, the wind, the gates and the crash check.
 * The FMU flies in its own frame, starting at north = east = 0; `ORIGIN` puts that start out at sea,
 * so a flight begins with the island ahead.
 */

import { Fmu } from "../engine/fmu";
import { Pacer } from "../engine/pacer";
import { model } from "./model.gen";

export const INPUTS = ["stick_pitch", "stick_roll", "pedals", "throttle", "wind_n", "wind_e", "wind_d"] as const;
export const OUTPUTS = [
  "north_m", "east_m", "alt_m", "q_w", "q_x", "q_y", "q_z", "phi_deg", "theta_deg", "psi_deg", "gamma_deg",
  "p_dps", "q_dps", "r_dps", "u_mps", "v_mps", "w_mps", "vs_mps", "tas_mps", "cas_mps", "mach", "qbar_pa",
  "alpha_deg", "beta_deg", "nz_g", "ny_g", "stab_deg", "ail_deg", "rdr_deg", "power_pct", "thrust_n",
  "p_lim_dps", "nz_cmd_g", "limiter_active", "departed", "ground_contact",
] as const;
export type Output = (typeof OUTPUTS)[number];
const INDEX = Object.fromEntries(OUTPUTS.map((name, i) => [name, i])) as Record<Output, number>;

export const ORIGIN = { north: -27000, east: -5000 };
/** Seconds added to a gate run for each gate missed. */
export const MISS_PENALTY = 5;

export interface Start {
  label: string;
  vt0: number;
  h0: number;
  alpha0: number;
  el0: number;
  thtl0: number;
  xcg: number;
}

export interface Gate {
  north: number;
  east: number;
  alt: number;
  heading: number;
  radius: number;
  passed: boolean;
  hit: boolean;
  /** How far from the centre the aircraft went through, in metres. */
  miss: number;
}

/**
 * The gate run: north, east and height above the ground. In from the sea, down the runway, round
 * past the town, then through the pass and up the valley behind it.
 */
const COURSE: [number, number, number][] = [
  [-22000, -2500, 900], [-17500, 1500, 420], [-14000, 5000, 200],
  [-10864, 7373, 70], [-9936, 10227, 70],
  [-8300, 12600, 170], [-5800, 10800, 170], [-5800, 7200, 170], [-6300, 4600, 170], [-4200, 3000, 170],
  [-2000, 2000, 170], [3000, 1800, 170], [8500, 1800, 170], [13000, 1200, 170], [14300, -3500, 170],
];

/** Each gate faces along the course and clears the ground on the way in and out of it. */
export function gateCourse(ground: (north: number, east: number) => number): Gate[] {
  return COURSE.map(([north, east, height], i) => {
    const before = COURSE[Math.max(i - 1, 0)];
    const after = COURSE[Math.min(i + 1, COURSE.length - 1)];
    const heading = (Math.atan2(after[1] - before[1], after[0] - before[0]) * 180) / Math.PI;
    let highest = ground(north, east);
    if (height > 70) {
      for (const [n, e] of [before, after]) {
        for (let t = 0.1; t <= 0.3; t += 0.1) {
          highest = Math.max(highest, ground(north + (n - north) * t, east + (e - east) * t));
        }
      }
    }
    return { north, east, alt: Math.max(highest, 0) + height, heading, radius: 75, passed: false, hit: false, miss: 0 };
  });
}

/** Steady wind and first-order filtered gusts: a stand-in for a Dryden filter, enough to feel. */
class Gusts {
  intensity = 0;
  private readonly state = [0, 0, 0];

  sample(dt: number, speed: number, into: Float64Array): void {
    if (this.intensity > 0) {
      const a = Math.exp(-dt * Math.max(speed, 30) / 300);
      const b = Math.sqrt(1 - a * a) * this.intensity;
      for (let i = 0; i < 3; i += 1) {
        const normal = Math.sqrt(-2 * Math.log(1 - Math.random())) * Math.cos(2 * Math.PI * Math.random());
        this.state[i] = a * this.state[i] + b * normal;
      }
    }
    into[4] = this.state[0];
    into[5] = this.state[1];
    into[6] = this.state[2];
  }
}

export class Flight {
  readonly pacer: Pacer;
  readonly gusts = new Gusts();
  /** Stick pitch, stick roll, pedals, throttle, then the wind: the FMU's inputs. */
  readonly u = new Float64Array(INPUTS.length);
  y = new Float64Array(OUTPUTS.length);
  previous = new Float64Array(OUTPUTS.length);
  paused = false;
  crashed = false;
  crashReason = "";
  gates: Gate[] = [];
  gateTime = 0;
  gateDone: number | null = null;
  start: Start;
  /** Where the FMU's zero is in the world. */
  origin = { ...ORIGIN };
  private readonly inRefs: Uint32Array;
  private readonly outRefs: Uint32Array;
  private previousPoint = [0, 0, 0];
  /** Called once per gate, as the aircraft goes through it or past it. */
  onGate: (gate: Gate) => void = () => {};

  private constructor(
    private readonly fmu: Fmu,
    private readonly ground: (north: number, east: number) => number,
    start: Start,
  ) {
    this.start = start;
    this.pacer = new Pacer(fmu.step);
    this.inRefs = fmu.select(INPUTS);
    this.outRefs = fmu.select(OUTPUTS);
  }

  static async create(ground: (north: number, east: number) => number, start: Start): Promise<Flight> {
    const flight = new Flight(await Fmu.load(model), ground, start);
    flight.reset(start);
    return flight;
  }

  get time(): number {
    return this.fmu.time;
  }

  get(name: Output): number {
    return this.y[INDEX[name]];
  }

  /** A value between the last two steps, for drawing. */
  between(name: Output): number {
    const i = INDEX[name];
    return this.previous[i] + (this.y[i] - this.previous[i]) * this.pacer.fraction;
  }

  north(): number {
    return this.get("north_m") + this.origin.north;
  }

  east(): number {
    return this.get("east_m") + this.origin.east;
  }

  altitudeAboveGround(): number {
    return this.get("alt_m") - Math.max(this.ground(this.north(), this.east()), 0);
  }

  reset(start: Start = this.start, switches: Record<string, number> = {}): void {
    this.start = start;
    const { vt0, h0, alpha0, el0, thtl0, xcg } = start;
    this.fmu.restart({ vt0, h0, alpha0, el0, thtl0, xcg, ...switches });
    this.u.fill(0);
    this.u[3] = thtl0;
    this.fmu.write(this.inRefs, this.u);
    this.fmu.read(this.outRefs, this.y);
    this.previous.set(this.y);
    this.pacer.reset();
    this.crashed = false;
    this.crashReason = "";
    this.previousPoint = [this.north(), this.east(), this.get("alt_m")];
    this.gateDone = null;
    this.gateTime = 0;
    if (this.gates.length > 0) {
      this.startGates();
    }
  }

  startGates(): void {
    this.gates = gateCourse(this.ground);
    this.gateTime = 0;
    this.gateDone = null;
  }

  stopGates(): void {
    this.gates = [];
    this.gateDone = null;
  }

  nextGate(): Gate | undefined {
    return this.gates.find((gate) => !gate.passed);
  }

  setControls(pitch: number, roll: number, pedals: number, throttle: number): void {
    this.u[0] = Math.max(-1, Math.min(1, pitch));
    this.u[1] = Math.max(-1, Math.min(1, roll));
    this.u[2] = Math.max(-1, Math.min(1, pedals));
    this.u[3] = Math.max(0, Math.min(1, throttle));
  }

  /** The gate run's result: time, plus a penalty per missed gate. */
  gateScore(): number {
    return this.gateTime + MISS_PENALTY * this.gates.filter((gate) => gate.passed && !gate.hit).length;
  }

  /** Runs as many fixed steps as a frame of `dt` seconds holds. */
  advance(dt: number): void {
    if (this.paused || this.crashed) {
      this.pacer.reset();
      return;
    }
    const steps = this.pacer.stepsFor(dt);
    for (let i = 0; i < steps && !this.crashed; i += 1) {
      this.stepOnce();
    }
  }

  private stepOnce(): void {
    this.gusts.sample(this.fmu.step, this.get("tas_mps"), this.u);
    [this.previous, this.y] = [this.y, this.previous];
    this.fmu.write(this.inRefs, this.u);
    const running = this.fmu.advance();
    this.fmu.read(this.outRefs, this.y);
    const n = this.north();
    const e = this.east();
    const h = this.get("alt_m");
    if (!running || this.y.some((value) => !Number.isFinite(value))) {
      this.crashed = true;
      this.crashReason = "The flight model stopped";
    } else if (this.get("ground_contact") > 0.5 || h <= Math.max(this.ground(n, e), 0)) {
      this.crashed = true;
      this.crashReason = this.ground(n, e) > 0 ? "Terrain" : "Water";
    }
    this.gatePass(this.previousPoint, n, e, h);
    this.previousPoint = [n, e, h];
  }

  private gatePass(from: number[], n: number, e: number, h: number): void {
    if (this.gates.length === 0 || this.gateDone !== null) {
      return;
    }
    this.gateTime += this.fmu.step;
    const gate = this.nextGate();
    if (!gate) {
      return;
    }
    const a = (gate.heading * Math.PI) / 180;
    const axis = [Math.cos(a), Math.sin(a)];
    const before = (from[0] - gate.north) * axis[0] + (from[1] - gate.east) * axis[1];
    const after = (n - gate.north) * axis[0] + (e - gate.east) * axis[1];
    if (before < 0 && after >= 0) {
      const t = -before / (after - before);
      const miss = Math.hypot(
        from[0] + (n - from[0]) * t - gate.north,
        from[1] + (e - from[1]) * t - gate.east,
        from[2] + (h - from[2]) * t - gate.alt,
      );
      if (miss <= 1200) {
        gate.passed = true;
        gate.hit = miss <= gate.radius;
        gate.miss = miss;
        this.onGate(gate);
        if (this.gates.every((g) => g.passed)) {
          this.gateDone = this.gateTime;
        }
      }
    }
  }
}
