/**
 * The F-16's flight, without any drawing: the FMU, the wind, the gates and the crash check. The FMU
 * flies in its own frame, starting at north = east = 0; `ORIGIN` puts that start out at sea, so a
 * flight begins with the island ahead.
 */

import { Fmu } from "../engine/fmu";
import { buildCourse, type Gate, GateRun } from "../engine/gates";
import { Gusts } from "../engine/gusts";
import { Sim } from "../engine/sim";
import { model } from "./model.gen";

export const INPUTS = ["stick_pitch", "stick_roll", "pedals", "throttle", "wind_n", "wind_e", "wind_d"] as const;
export const OUTPUTS = [
  "north_m", "east_m", "alt_m", "q_w", "q_x", "q_y", "q_z", "phi_deg", "theta_deg", "psi_deg", "gamma_deg",
  "p_dps", "q_dps", "r_dps", "u_mps", "v_mps", "w_mps", "vs_mps", "tas_mps", "cas_mps", "mach", "qbar_pa",
  "alpha_deg", "beta_deg", "nz_g", "ny_g", "stab_deg", "ail_deg", "rdr_deg", "power_pct", "thrust_n",
  "p_lim_dps", "nz_cmd_g", "limiter_active", "departed", "ground_contact",
] as const;
export type Output = (typeof OUTPUTS)[number];

export const ORIGIN = { north: -27000, east: -5000 };

export interface Start {
  label: string;
  vt0: number;
  h0: number;
  alpha0: number;
  el0: number;
  thtl0: number;
  xcg: number;
}

/**
 * The gate run: north, east and height above the ground. In from the sea, down the runway, round
 * past the town, then through the pass and up the valley behind it.
 */
const COURSE = [
  [-22000, -2500, 900], [-17500, 1500, 420], [-14000, 5000, 200],
  [-10864, 7373, 70], [-9936, 10227, 70],
  [-8300, 12600, 170], [-5800, 10800, 170], [-5800, 7200, 170], [-6300, 4600, 170], [-4200, 3000, 170],
  [-2000, 2000, 170], [3000, 1800, 170], [8500, 1800, 170], [13000, 1200, 170], [14300, -3500, 170],
] as const;

export function gateCourse(ground: (north: number, east: number) => number): Gate[] {
  return buildCourse(COURSE, ground, 75);
}

export class Flight extends Sim<Output> {
  readonly gusts = new Gusts(300);
  readonly run = new GateRun();
  crashed = false;
  crashReason = "";
  start: Start;
  /** Where the FMU's zero is in the world. */
  origin = { ...ORIGIN };
  private previousPoint = [0, 0, 0];

  private constructor(
    fmu: Fmu,
    private readonly ground: (north: number, east: number) => number,
    start: Start,
  ) {
    super(fmu, INPUTS, OUTPUTS);
    this.start = start;
  }

  static async create(ground: (north: number, east: number) => number, start: Start): Promise<Flight> {
    const flight = new Flight(await Fmu.load(model), ground, start);
    flight.reset(start);
    return flight;
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
    this.restart({ vt0, h0, alpha0, el0, thtl0, xcg: this.tuning.changed.xcg ?? xcg, ...switches }, () => {
      this.u[3] = thtl0;
    });
    this.crashed = false;
    this.crashReason = "";
    this.previousPoint = [this.north(), this.east(), this.get("alt_m")];
    if (this.run.active) {
      this.run.start(gateCourse(this.ground));
    }
  }

  setControls(pitch: number, roll: number, pedals: number, throttle: number): void {
    this.u[0] = Math.max(-1, Math.min(1, pitch));
    this.u[1] = Math.max(-1, Math.min(1, roll));
    this.u[2] = Math.max(-1, Math.min(1, pedals));
    this.u[3] = Math.max(0, Math.min(1, throttle));
  }

  protected override beforeStep(): void {
    this.gusts.sample(this.fmu.step, this.get("tas_mps"), this.u, 4);
  }

  protected override afterStep(healthy: boolean): void {
    const n = this.north();
    const e = this.east();
    const h = this.get("alt_m");
    if (!healthy) {
      this.crash("The flight model stopped");
    } else if (this.get("ground_contact") > 0.5 || h <= Math.max(this.ground(n, e), 0)) {
      this.crash(this.ground(n, e) > 0 ? "Terrain" : "Water");
    }
    this.run.step(this.fmu.step, this.previousPoint, [n, e, h]);
    this.previousPoint = [n, e, h];
  }

  private crash(reason: string): void {
    this.crashed = true;
    this.crashReason = reason;
    this.stopped = true;
  }
}
