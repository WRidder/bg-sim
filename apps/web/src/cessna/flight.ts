/**
 * The aeroplane's flight, without any drawing: the FMU, the wind, the crash check, and the watch on
 * the wheels that turns a touchdown into a landing.
 *
 * The FMU's world is flat: its ground is a plane at z = 0 everywhere, with the gear standing on it.
 * So that plane is laid on the runway of the island, and it is the runway's only honest place. Its
 * x axis runs along runway 25, as the desktop app's runway 36 did, which keeps every trim of
 * starts.json valid as it is: `FRAME` turns and moves that world onto the island. Everywhere but
 * the airfield the FMU's plane means nothing, so the rest of the land and the sea are judged here,
 * from the same height function the terrain is drawn from.
 */

import { Fmu } from "../engine/fmu";
import { type Gate, GateRun } from "../engine/gates";
import { Gusts } from "../engine/gusts";
import { Sim } from "../engine/sim";
import {
  AIM_POINT, CALM, DATUM, LANDING_HEADING, type LandingState, runwayCoordinates, type Surface, surfaceAt, THRESHOLD, type Touchdown, type Wind,
} from "../island/airfield";
import { model } from "./model.gen";

export {
  AIM_POINT, CALM, DATUM, LANDING_HEADING, type LandingState, runwayCoordinates, type Surface, surfaceAt, THRESHOLD, type Touchdown, type Wind,
} from "../island/airfield";

export const INPUTS = [
  "yoke_pitch", "yoke_roll", "pedals", "throttle", "mixture", "flaps", "trim", "brake_l", "brake_r",
  "ap_roll_mode", "ap_alt_mode", "ap_hdg_deg", "ap_alt_m", "wind_n", "wind_e", "wind_d",
] as const;
type Input = (typeof INPUTS)[number];
export const OUTPUTS = [
  "north_m", "east_m", "alt_m", "q_w", "q_x", "q_y", "q_z", "phi_deg", "theta_deg", "psi_deg", "kias", "ktas",
  "vs_fpm", "alt_ft", "agl_ft", "turn_dps", "slip", "on_ground", "alpha_deg", "beta_deg", "gs_mps", "rpm", "hp",
  "map_inhg", "ff_gph", "thrust_n", "flap_deg", "elevator_deg", "aileron_deg", "rudder_deg", "steer_rad",
  "prop_angle", "stall_flag", "fn_nose", "fn_left", "fn_right",
] as const;
export type Output = (typeof OUTPUTS)[number];

const at = (name: Input): number => INPUTS.indexOf(name);
const YOKE_PITCH = at("yoke_pitch");
const YOKE_ROLL = at("yoke_roll");
const PEDALS = at("pedals");
const THROTTLE = at("throttle");
const MIXTURE = at("mixture");
const FLAPS = at("flaps");
const TRIM = at("trim");
const BRAKE_L = at("brake_l");
const BRAKE_R = at("brake_r");
const WIND = at("wind_n");

const DEG = Math.PI / 180;
const G0 = 9.80665;
const MASS = 1088.62;
/** On one wheel, this much and the gear folds. */
const GEAR_LIMIT = 3.5 * MASS * G0;

/** Where the desktop's trims put their aiming point, in the FMU's x. */
const TRIM_AIM = 120;

const heading = LANDING_HEADING * DEG;
const HN = Math.cos(heading);
const HE = Math.sin(heading);

/** The FMU's origin on the island, and the compass heading of its x axis. */
export const FRAME = {
  north: THRESHOLD.north + (AIM_POINT - TRIM_AIM) * HN,
  east: THRESHOLD.east + (AIM_POINT - TRIM_AIM) * HE,
  heading: LANDING_HEADING,
};
/** Runway 25's threshold in the FMU's x. */
export const THRESHOLD_X = TRIM_AIM - AIM_POINT;

export interface Start {
  label: string;
  values: Record<string, number>;
  controls: Record<string, number>;
  airborne: boolean;
}

/** Airframe points that must stay off the ground, from the CG: x forward, y left, z up. */
const STRIKE: Record<string, readonly [number, number, number]> = {
  "left wing": [0.061, 5.456, 0.607],
  "right wing": [0.061, -5.456, 0.607],
  tail: [-3.617, 0, -0.699],
  propeller: [2.116, 0, -1.178],
};

export class Flight extends Sim<Output> {
  readonly gusts = new Gusts(150);
  readonly run = new GateRun();
  wind: Wind = CALM;
  crashed = false;
  crashReason = "";
  start: Start;
  /** The engine has stopped: mixture to nothing, whatever the throttle says. */
  engineOut = false;
  /** Every touch of the wheels after flying, first one first. */
  touchdowns: Touchdown[] = [];
  landing: LandingState = "rolling";
  /** The tail skid has touched since the start. */
  scraped = false;
  /** Runs before every step: a scripted pilot's hands. */
  private brakeLeft = 0;
  private brakeRight = 0;
  autopilot: (() => void) | null = null;
  /** Off the end of a roll: how far it took, and whether it ended on the runway. */
  stoppedAt: { along: number; across: number; surface: Surface } | null = null;
  private airTime = 0;
  private groundTime = 0;
  private readonly sinkHistory = new Float64Array(20);
  private sinkAt = 0;
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
    return FRAME.north + this.get("north_m") * HN - this.get("east_m") * HE;
  }

  east(): number {
    return FRAME.east + this.get("north_m") * HE + this.get("east_m") * HN;
  }

  /** The compass heading on the island, not in the FMU's own frame. */
  heading(): number {
    return (((this.get("psi_deg") + FRAME.heading) % 360) + 360) % 360;
  }

  /** Where to draw the aeroplane between the last two steps, in the scene's axes. */
  drawnPoint(into: { x: number; y: number; z: number }): void {
    const x = this.between("north_m");
    const e = this.between("east_m");
    into.x = FRAME.east + x * HE + e * HN;
    into.y = this.between("alt_m") + DATUM;
    into.z = -(FRAME.north + x * HN - e * HE);
  }

  /** The CG's height above the sea. */
  altitude(): number {
    return this.get("alt_m") + DATUM;
  }

  altitudeAboveGround(): number {
    return this.altitude() - Math.max(this.ground(this.north(), this.east()), 0);
  }

  /** The way the air is going over the ground, in the climb. */
  flightPath(): number {
    const sink = this.get("vs_fpm") * 0.00508;
    return Math.atan2(sink, Math.max(this.get("gs_mps"), 1)) / DEG;
  }

  reset(start: Start = this.start, values: Record<string, number> = {}, gates?: Gate[]): void {
    this.start = start;
    this.restart({ ...start.values, ...values }, () => {
      this.u[MIXTURE] = 1;
      for (const [name, value] of Object.entries(start.controls)) {
        this.u[at(name as Input)] = value;
      }
    });
    this.crashed = false;
    this.crashReason = "";
    this.engineOut = false;
    this.scraped = false;
    this.touchdowns = [];
    this.stoppedAt = null;
    this.landing = start.airborne ? "air" : "rolling";
    this.airTime = start.airborne ? 10 : 0;
    this.groundTime = 0;
    this.sinkHistory.fill(0);
    this.previousPoint = [this.north(), this.east(), this.altitude()];
    if (gates) {
      this.run.start(gates);
    }
  }

  setControls(pitch: number, roll: number, pedals: number, throttle: number): void {
    this.u[YOKE_PITCH] = Math.max(-1, Math.min(1, pitch));
    this.u[YOKE_ROLL] = Math.max(-1, Math.min(1, roll));
    this.u[PEDALS] = Math.max(-1, Math.min(1, pedals));
    this.u[THROTTLE] = Math.max(0, Math.min(1, throttle));
  }

  setBrakes(left: number, right = left): void {
    this.brakeLeft = Math.max(0, Math.min(1, left));
    this.brakeRight = Math.max(0, Math.min(1, right));
  }

  /** One detent at a time, 0..3. */
  setFlaps(detent: number): void {
    this.u[FLAPS] = Math.max(0, Math.min(3, Math.round(detent)));
  }

  get flaps(): number {
    return this.u[FLAPS];
  }

  get trim(): number {
    return this.u[TRIM];
  }

  set trim(value: number) {
    this.u[TRIM] = Math.max(-1, Math.min(1, value));
  }

  get throttle(): number {
    return this.u[THROTTLE];
  }

  get brakes(): number {
    return Math.max(this.brakeLeft, this.brakeRight);
  }

  cutEngine(): void {
    this.engineOut = true;
    this.u[MIXTURE] = 0;
  }

  protected override beforeStep(): void {
    this.autopilot?.();
    // The FMU's nose leg is a soft spring, and full brakes at speed would put the propeller in the
    // tarmac. Toe pressure eases as the strut nears the end of its travel, as a pilot's feet would.
    const ease = Math.max(0.2, Math.min(1, (this.get("theta_deg") - 0.5) / 1.5));
    this.u[BRAKE_L] = this.brakeLeft * ease;
    this.u[BRAKE_R] = this.brakeRight * ease;
    const { head, cross } = this.wind;
    // A 1/7 power law below 100 m: the wind dies on the runway, and a crosswind eases in the flare.
    const agl = Math.max(this.get("alt_m") - 1.25, 0);
    const shear = agl > 0 ? Math.min(agl / 100, 1) ** (1 / 7) : 0;
    this.gusts.intensity = this.wind.gusts;
    this.gusts.sample(this.fmu.step, this.get("ktas") * 0.5144, this.u, WIND);
    if (agl < 30) {
      this.u[WIND + 2] *= agl / 30; // no gusts up out of the runway
    }
    this.u[WIND] += -head * shear;
    this.u[WIND + 1] += -cross * shear;
  }

  /** Height of the lowest point of the airframe over the FMU's plane. */
  private clearance(): { name: string; z: number } {
    const w = this.get("q_w");
    const x = this.get("q_x");
    const y = this.get("q_y");
    const z = this.get("q_z");
    const zx = 2 * (x * z - w * y);
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
    const onGround = this.get("on_ground") > 0.5;
    const land = this.ground(north, east);
    const surface = surfaceAt(north, east);
    const lowest = this.clearance();
    if (surface === "none") {
      // The FMU's plane means nothing here, and it is above the sea and the beaches. Whatever
      // touches it, or the island's own ground, has hit what is really below.
      if (onGround || lowest.z < 0 || lowest.z + DATUM <= Math.max(land, 0)) {
        this.crash(land > 0 ? "Terrain" : "Water");
      }
    } else if (lowest.z < 0) {
      // A rotation a shade too eager drags the tail skid: embarrassing, not fatal.
      if (lowest.name === "tail" && lowest.z > -0.45 && this.get("vs_fpm") > -350) {
        this.scraped = true;
      } else {
        this.crash(`${lowest.name} strike`);
      }
    } else if (Math.max(this.get("fn_nose"), this.get("fn_left"), this.get("fn_right")) > GEAR_LIMIT) {
      this.crash("The gear folded");
    }
    this.sinkHistory[this.sinkAt] = this.get("vs_fpm");
    this.sinkAt = (this.sinkAt + 1) % this.sinkHistory.length;
    if (!this.crashed) {
      this.watchWheels(onGround, north, east, surface);
    }
    this.run.step(this.fmu.step, this.previousPoint, [north, east, alt]);
    this.previousPoint = [north, east, alt];
  }

  /** From the former desktop app's `core.py`: the sink over the last 0.1 s, since the contact has already stopped it. */
  private watchWheels(onGround: boolean, north: number, east: number, surface: Surface): void {
    const dt = this.fmu.step;
    if (onGround) {
      if (this.airTime > 2) {
        const { along, across } = runwayCoordinates(north, east);
        this.touchdowns.push({
          sink: -Math.min(...this.sinkHistory),
          kias: this.get("kias"),
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
      if (this.landing === "rolling" && this.touchdowns.length > 0 && this.get("gs_mps") < 1.5 && this.groundTime > 1) {
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
        if (this.altitudeAboveGround() > 25) {
          this.touchdowns = [];
        }
      }
    }
  }

  private crash(reason: string): void {
    this.crashed = true;
    this.crashReason = reason;
    this.stopped = true;
  }
}
