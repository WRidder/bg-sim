/**
 * The F-16's flight, without any drawing: the FMU, the wind, the gates, the wheels and the crash
 * check. The FMU flies in its own frame and always starts heading north; `frame` lays that on the
 * world. In the air any frame will do, and `ORIGIN` puts the start out at sea with the island ahead.
 * On the wheels the frame's only job is to turn the FMU's north down the runway.
 *
 * The FMU's ground is a plane at z = 0 everywhere. `lift` lays it on the runway at the airfield and
 * on the sea everywhere else; away from the airfield it means nothing to a wheel, so a wheel that
 * touches it there has hit what is really below.
 */

import { Fmu } from "../engine/fmu";
import { buildCourse, type Gate, GateRun } from "../engine/gates";
import { Gusts } from "../engine/gusts";
import { Sim } from "../engine/sim";
import {
  AIM_POINT, DATUM, LANDING_HEADING, type LandingState, lift, runwayCoordinates, type Surface, surfaceAt, THRESHOLD, type Touchdown,
} from "../island/airfield";
import { model } from "./model.gen";

export const INPUTS = ["stick_pitch", "stick_roll", "pedals", "throttle", "wind_n", "wind_e", "wind_d", "gear_cmd", "brake_l", "brake_r"] as const;
export const OUTPUTS = [
  "north_m", "east_m", "alt_m", "q_w", "q_x", "q_y", "q_z", "phi_deg", "theta_deg", "psi_deg", "gamma_deg",
  "p_dps", "q_dps", "r_dps", "u_mps", "v_mps", "w_mps", "vs_mps", "tas_mps", "cas_mps", "mach", "qbar_pa",
  "alpha_deg", "beta_deg", "nz_g", "ny_g", "stab_deg", "ail_deg", "rdr_deg", "power_pct", "thrust_n",
  "p_lim_dps", "nz_cmd_g", "limiter_active", "departed", "ground_contact",
  "fn_nose", "fn_left", "fn_right", "on_ground", "steer_rad", "gear_pos",
] as const;
export type Output = (typeof OUTPUTS)[number];

const GEAR = INPUTS.indexOf("gear_cmd");
const BRAKE_L = INPUTS.indexOf("brake_l");
const BRAKE_R = INPUTS.indexOf("brake_r");
const MPS_TO_KT = 1.94384;
const M_TO_FT = 3.28084;
const DEG = Math.PI / 180;

export const ORIGIN = { north: -27000, east: -5000 };

/** Where the FMU's zero is in the world, and the compass heading of its north. */
export interface Frame {
  north: number;
  east: number;
  heading: number;
}

export interface Start {
  label: string;
  vt0: number;
  h0: number;
  alpha0: number;
  el0: number;
  thtl0: number;
  xcg: number;
  /** Climb angle, degrees; a trim on the glide path has one. */
  gamma0?: number;
  /** 1 with the gear down. */
  gear0?: number;
  /** Along the frame's north, m. */
  north0?: number;
  /** In the runway's frame rather than out at sea. */
  runway?: boolean;
}

/** The FMU's north along runway 25, its zero on the threshold. */
export const RUNWAY_FRAME: Frame = { ...THRESHOLD, heading: LANDING_HEADING };

/** The rest on the wheels: gear.json's static height and pitch, at idle, just past the threshold. */
export const RUNWAY_START: Start = {
  label: "Runway 25, ready to go", vt0: 0, h0: 1.6231583378728471, alpha0: -0.07072523603713064, el0: 0, thtl0: 0, xcg: 0.35,
  gear0: 1, north0: 60, runway: true,
};

/** The desktop app's final approach, placed so that its 3 degrees end on the aiming point. */
const FINAL_HEIGHT = 158.84649618699646;
export const FINAL_START: Start = {
  label: "Final to runway 25, gear down", vt0: 76, h0: FINAL_HEIGHT, alpha0: 12.897638361920855, el0: -0.5659692648291801,
  thtl0: 0.13227639339474015, xcg: 0.35, gamma0: -3, gear0: 1, north0: AIM_POINT - (FINAL_HEIGHT - 1.7) / Math.tan(3 * DEG), runway: true,
};

/** Airframe points that must stay off the ground, from the CG: x forward, y left, z up. */
const STRIKE: Record<string, readonly [number, number, number]> = {
  "left wing": [-2.3, 4.9, 0.05],
  "right wing": [-2.3, -4.9, 0.05],
  tail: [-6.5, 0, -0.29],
  belly: [0.5, 0, -0.85],
  nose: [2.8, 0, -0.95],
};

/** Per wheel, N: past this the gear folds. About what 6 m/s of sink puts on it, twice the 3 it is built for. */
const MAIN_LIMIT = 320e3;
const NOSE_LIMIT = 150e3;

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
  frame: Frame = { ...ORIGIN, heading: 0 };
  /** Every touch of the wheels after flying, first one first. */
  touchdowns: Touchdown[] = [];
  landing: LandingState = "air";
  /** Off the end of a roll: how far it took, and whether it ended on the runway. */
  stoppedAt: { along: number; across: number; surface: Surface } | null = null;
  /** The tail has touched since the start. */
  scraped = false;
  private previousPoint = [0, 0, 0];
  private airTime = 0;
  private groundTime = 0;
  private readonly sinkHistory = new Float64Array(20);
  private sinkAt = 0;

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

  /** A point of the FMU's frame in the world: north, east. */
  at(fmuNorth: number, fmuEast: number): [number, number] {
    const a = this.frame.heading * DEG;
    const [c, s] = [Math.cos(a), Math.sin(a)];
    return [this.frame.north + fmuNorth * c - fmuEast * s, this.frame.east + fmuNorth * s + fmuEast * c];
  }

  north(): number {
    return this.at(this.get("north_m"), this.get("east_m"))[0];
  }

  east(): number {
    return this.at(this.get("north_m"), this.get("east_m"))[1];
  }

  /** Compass heading, degrees. */
  heading(): number {
    return (((this.get("psi_deg") + this.frame.heading) % 360) + 360) % 360;
  }

  /** The F-16's body x axis in NED (north, east, down). */
  noseNed(): [number, number, number] {
    const w = this.get("q_w");
    const x = this.get("q_x");
    const y = this.get("q_y");
    const z = this.get("q_z");
    return [
      1 - 2 * (y * y + z * z),
      2 * (x * y + w * z),
      2 * (x * z - w * y),
    ];
  }

  /** A wingtip station's world north/east/altitude; side 0 is left, 1 right. */
  stationWorld(side: 0 | 1): { north: number; east: number; alt: number } {
    const w = this.get("q_w");
    const x = this.get("q_x");
    const y = this.get("q_y");
    const z = this.get("q_z");
    const r00 = 1 - 2 * (y * y + z * z);
    const r01 = 2 * (x * y - w * z);
    const r02 = 2 * (x * z + w * y);
    const r10 = 2 * (x * y + w * z);
    const r11 = 1 - 2 * (x * x + z * z);
    const r12 = 2 * (y * z - w * x);
    const r20 = 2 * (x * z - w * y);
    const r21 = 2 * (y * z + w * x);
    const r22 = 1 - 2 * (x * x + y * y);
    // Body frame is forward-left-up; the quotient is forward-right-down.
    const bx = -2.6;
    const by = side === 0 ? -4.82 : 4.82;
    const bz = 0;
    return {
      north: this.north() + r00 * bx + r01 * by + r02 * bz,
      east: this.east() + r10 * bx + r11 * by + r12 * bz,
      alt: this.altitude() - (r20 * bx + r21 * by + r22 * bz),
    };
  }

  /** Height above the sea. */
  altitude(): number {
    return this.get("alt_m") + lift(this.north(), this.east());
  }

  /** What is really under a point: the pavement, or the island, or the sea. */
  floor(north: number, east: number): number {
    const surface = surfaceAt(north, east);
    return surface === "runway" || surface === "paved" ? DATUM : Math.max(this.ground(north, east), 0);
  }

  altitudeAboveGround(): number {
    return this.altitude() - this.floor(this.north(), this.east());
  }

  get onGround(): boolean {
    return this.get("on_ground") > 0.5;
  }

  reset(start: Start = this.start, switches: Record<string, number> = {}): void {
    this.start = start;
    if (start.runway) {
      this.frame = RUNWAY_FRAME;
    }
    const { vt0, h0, alpha0, el0, thtl0, xcg, gamma0 = 0, gear0 = 0, north0 = 0 } = start;
    this.restart({ vt0, h0, alpha0, el0, thtl0, gamma0, gear0, north0, xcg: this.tuning.changed.xcg ?? xcg, ...switches }, () => {
      this.u[3] = thtl0;
      this.u[GEAR] = gear0;
    });
    this.crashed = false;
    this.crashReason = "";
    this.touchdowns = [];
    const rolling = vt0 < 1;
    this.landing = rolling ? "rolling" : "air";
    this.stoppedAt = null;
    this.scraped = false;
    this.airTime = rolling ? 0 : 5;
    this.groundTime = 0;
    this.sinkHistory.fill(0);
    this.previousPoint = [this.north(), this.east(), this.altitude()];
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

  setBrakes(amount: number): void {
    this.u[BRAKE_L] = Math.max(0, Math.min(1, amount));
    this.u[BRAKE_R] = this.u[BRAKE_L];
  }

  /** The gear handle. On the wheels the FMU's interlock holds the gear down whatever it says. */
  toggleGear(): void {
    this.u[GEAR] = this.u[GEAR] > 0.5 ? 0 : 1;
  }

  /** The handle's position. */
  get gearDown(): boolean {
    return this.u[GEAR] > 0.5;
  }

  get braking(): boolean {
    return this.u[BRAKE_L] > 0;
  }

  protected override beforeStep(): void {
    this.gusts.sample(this.fmu.step, this.get("tas_mps"), this.u, 4);
    // The air goes still towards the ground, and the FMU's plane is near enough to it for that.
    const near = Math.max(this.get("alt_m"), 0) / 30;
    if (near < 1) {
      this.u[4] *= near;
      this.u[5] *= near;
      this.u[6] *= near;
    }
  }

  /** Height of the lowest point of the airframe over the FMU's plane. */
  private clearance(): { name: string; z: number } {
    const w = this.get("q_w");
    const x = this.get("q_x");
    const y = this.get("q_y");
    const z = this.get("q_z");
    // The FMU's body axes are x forward, y right, z down; STRIKE's are y left, z up.
    const zx = -2 * (x * z - w * y);
    const zy = 2 * (y * z + w * x);
    const zz = 1 - 2 * (x * x + y * y);
    let lowest = { name: "", z: Infinity };
    for (const [name, r] of Object.entries(STRIKE)) {
      const height = this.get("alt_m") + zx * r[0] + zy * r[1] + zz * r[2];
      if (height < lowest.z) {
        lowest = { name, z: height };
      }
    }
    return lowest;
  }

  protected override afterStep(healthy: boolean): void {
    const north = this.north();
    const east = this.east();
    const alt = this.altitude();
    if (!healthy) {
      this.crash("The flight model stopped");
      return;
    }
    const land = this.ground(north, east);
    const surface = surfaceAt(north, east);
    const lowest = this.clearance();
    if (surface === "none") {
      if (this.onGround || this.get("ground_contact") > 0.5 || lowest.z < 0 || alt <= Math.max(land, 0)) {
        this.crash(land > 0 ? "Terrain" : "Water");
      }
    } else if (this.get("gear_pos") < 0.9 && (this.get("ground_contact") > 0.5 || lowest.z < 0)) {
      this.crash("A belly landing");
    } else if (lowest.z < 0) {
      // A rotation a shade too eager drags the nozzle: embarrassing, not fatal.
      if (lowest.name === "tail" && lowest.z > -0.3 && this.get("vs_mps") > -1.5) {
        this.scraped = true;
      } else {
        this.crash(`A ${lowest.name} strike`);
      }
    } else if (this.get("ground_contact") > 0.5 || this.get("fn_nose") > NOSE_LIMIT || Math.max(this.get("fn_left"), this.get("fn_right")) > MAIN_LIMIT) {
      this.crash("The gear folded");
    }
    this.sinkHistory[this.sinkAt] = this.get("vs_mps");
    this.sinkAt = (this.sinkAt + 1) % this.sinkHistory.length;
    if (!this.crashed) {
      this.watchWheels(north, east, surface);
    }
    this.run.step(this.fmu.step, this.previousPoint, [north, east, alt]);
    this.previousPoint = [north, east, alt];
  }

  /** The sink is taken over the last 0.1 s, since the contact has already stopped it. */
  private watchWheels(north: number, east: number, surface: Surface): void {
    const dt = this.fmu.step;
    if (this.onGround) {
      if (this.airTime > 2) {
        const { along, across } = runwayCoordinates(north, east);
        this.touchdowns.push({
          sink: -Math.min(...this.sinkHistory) * M_TO_FT * 60,
          kias: this.get("cas_mps") * MPS_TO_KT,
          along,
          across,
          pitch: this.get("theta_deg"),
          bank: this.get("phi_deg"),
          surface,
          noseFirst: this.get("fn_nose") > Math.max(this.get("fn_left"), this.get("fn_right")),
          bounce: this.touchdowns.length > 0,
        });
        this.landing = "rolling";
      }
      this.airTime = 0;
      this.groundTime += dt;
      const speed = Math.hypot(north - this.previousPoint[0], east - this.previousPoint[1]) / dt;
      if (this.landing === "rolling" && this.touchdowns.length > 0 && speed < 1.5 && this.groundTime > 1) {
        this.landing = "stopped";
        this.stoppedAt = { ...runwayCoordinates(north, east), surface };
      }
    } else {
      this.airTime += dt;
      if (this.airTime > 0.5) {
        this.groundTime = 0;
      }
      if (this.airTime > 4) {
        // Back in the air and meaning it: a touch and go wipes the slate.
        this.landing = "air";
        this.touchdowns = [];
        this.scraped = false;
      }
    }
  }

  private crash(reason: string): void {
    this.crashed = true;
    this.crashReason = reason;
    this.stopped = true;
  }
}
