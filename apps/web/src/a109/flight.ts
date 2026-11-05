/**
 * The helicopter's flight, without any drawing: the FMU, the wind, and what it means to meet the
 * island. The FMU is the whole aircraft, gear included, but its gear stands on one flat ground at
 * z = 0. The island is not flat, so that ground is carried along under the helicopter: `datum` is
 * where the FMU's zero is in the world, and it follows the surface below while the wheels are clear.
 * Moving it needs the FMU's height to move the other way in the same instant, or the helicopter would
 * jump. Its start parameters could do that only through a restart, which zeroes the SCAS integrators
 * and the wind-up of the governor, so `Flight` writes the one height state in the Wasm memory instead.
 * Everything else the FMU holds carries on untouched: the gear meets the deck for real, and ground
 * effect comes from the height over what is really below.
 */

import { Fmu } from "../engine/fmu";
import { Gusts } from "../engine/gusts";
import { Sim } from "../engine/sim";
import { model } from "./model.gen";
import type { Surface } from "./surface";

export const INPUTS = ["collective", "cyclic_lon", "cyclic_lat", "pedals", "wind_n", "wind_e", "wind_d", "scas"] as const;
export const OUTPUTS = [
  "north_m", "east_m", "alt_m", "phi_deg", "theta_deg", "psi_deg", "p_dps", "q_dps", "r_dps", "u_mps", "v_mps", "w_mps",
  "vs_mps", "tas_mps", "kts", "beta_deg", "rotor_pct", "power_hp", "thrust_n", "a1_deg", "b1_deg", "theta0_deg", "B1_deg",
  "A1_deg", "theta_tr_deg", "fn_nose", "fn_left", "fn_right", "wow",
] as const;
export type Output = (typeof OUTPUTS)[number];

const [COLLECTIVE, LON, LAT, PEDALS, WIND_N, WIND_E, WIND_D, SCAS] = [0, 1, 2, 3, 4, 5, 6, 7];
const ALT = OUTPUTS.indexOf("alt_m");

export const MASS = 2449.856;
export const WEIGHT = MASS * 9.80665;
/** The wheels' contact points below the CG, and the CG over the ground on the compressed gear. */
export const GEAR_Z = 1.32;
export const ON_GEAR = 1.28;
export const HUB = { x: 0.00762, z: 1.51638 };
export const SHAFT_TILT = 0.10995574;
export const ROTOR_RADIUS = 5.4864;
export const TAIL_HUB = { x: -6.56082, y: 0.25, z: 0.8001 };
export const TAIL_RADIUS = 0.94488;
/** The rotor at 100 %. */
export const OMEGA = 40.31710572106901;
export const TAIL_RATIO = 5.402597402597402;
/** The engines' limit: the governor can give no more. */
export const POWER_LIMIT = 740;

/** Body points (x forward, y left, z up, from the CG) that must stay clear of everything. */
const STRIKE: readonly (readonly [string, number, number, number])[] = [
  ["The tail rotor", TAIL_HUB.x, TAIL_HUB.y, TAIL_HUB.z - TAIL_RADIUS],
  ["The tail", -6.25, 0, -0.3],
  ["The nose", 2.2, 0, -0.75],
  ["The belly", 0.35, 0, -0.8],
];
const WHEELS: readonly (readonly [number, number, number])[] = [[1.9, 0, -GEAR_Z], [-0.8, 0.95, -GEAR_Z], [-0.8, -0.95, -GEAR_Z]];
const TIPS = Array.from({ length: 8 }, (_, k) => {
  const a = (k * Math.PI) / 4;
  return [
    HUB.x + ROTOR_RADIUS * Math.cos(a) * Math.cos(SHAFT_TILT),
    ROTOR_RADIUS * Math.sin(a),
    HUB.z - ROTOR_RADIUS * Math.cos(a) * Math.sin(SHAFT_TILT),
  ] as const;
});

/** A wheel at this load folds the gear. */
const WHEEL_LIMIT = 2.5 * WEIGHT;
const SINK_LIMIT = 3;
const ROTOR_STALL = 80;
const ROLLOVER = 25;
/** Steeper than this the wheels will not hold it. */
const STEEPEST = 15;
/** How far the flat ground may lag the real one under a wheel before it counts as a hit. */
const WHEEL_SLACK = 0.45;
/** How fast the flat ground may follow the real one with the wheels on it, in m/s. */
const CREEP = 0.4;

export interface Start {
  label: string;
  values: Record<string, number>;
  controls: { collective: number; cyclic_lon: number; cyclic_lat: number; pedals: number; scas: number };
  airborne: boolean;
  settle: number;
}

/** Where a flight begins: a start of the list, turned and placed. */
export interface Placing {
  north: number;
  east: number;
  /** The height of what it stands on, or of the ground below for a hover. */
  floor: number;
  heading: number;
}

export interface Touchdown {
  /** Metres per second: how fast it sank, and how fast it was still sliding. */
  sink: number;
  drift: number;
  bank: number;
  north: number;
  east: number;
}

/** The quaternion of a turn about the world's vertical, times `q`. */
function turned(values: Record<string, number>, degrees: number): Record<string, number> {
  // Up in the model's world (north, west, up): a right turn is a negative turn about it.
  const half = (-degrees * Math.PI) / 360;
  const w = Math.cos(half);
  const z = Math.sin(half);
  const { qw0: a, qx0: b, qy0: c, qz0: d } = values;
  return { ...values, qw0: w * a - z * d, qx0: w * b - z * c, qy0: w * c + z * b, qz0: w * d + z * a };
}

export class Flight extends Sim<Output> {
  readonly gusts = new Gusts(90);
  /** The steady wind, towards north and east, in m/s at 100 m and above. */
  wind = { north: 0, east: 0 };
  crashed = false;
  crashReason = "";
  start: Start;
  placing: Placing;
  /** Where the FMU's zero is in the world. */
  origin = { north: 0, east: 0 };
  /** The height of the FMU's flat ground in the world. */
  datum = 0;
  /** Called before each step: whoever flies sets the controls here. */
  pilot: ((flight: Flight) => void) | null = null;
  /** The last touchdown after a flight; read and cleared by whoever scores it. */
  touchdown: Touchdown | null = null;
  /** Seconds in the air, on the gear. */
  airTime = 0;
  groundTime = 0;
  vn = 0;
  ve = 0;
  /** The address of the FMU's height state in its memory. */
  private heightAt = -1;
  /** The FMU's clock must run on from its start, so a flight's time counts from the settling's end. */
  private settled = 0;
  private readonly memory: Float64Array;
  private readonly sink = new Float64Array(20);
  private sinkAt = 0;
  private readonly gust = new Float64Array(3);
  private readonly rows = new Float64Array(9);

  private constructor(
    fmu: Fmu,
    readonly surface: Surface,
    start: Start,
    placing: Placing,
  ) {
    super(fmu, INPUTS, OUTPUTS);
    this.memory = fmu.memory();
    this.start = start;
    this.placing = placing;
  }

  static async create(surface: Surface, start: Start, placing: Placing): Promise<Flight> {
    const flight = new Flight(await Fmu.load(model), surface, start, placing);
    flight.findHeight();
    flight.reset();
    return flight;
  }

  /**
   * The height state has no address the FMU would tell, so it is found by what it does: of the
   * doubles that hold the height, the one that moves the helicopter when it is changed. Once per
   * load, on a throwaway start.
   */
  private findHeight(): void {
    this.restart(this.start.values, () => this.startControls());
    const { memory } = this;
    const probe = (): number => {
      this.fmu.write(this.fmu.select(INPUTS), this.u);
      this.fmu.advance();
      this.fmu.read(this.fmu.select(["alt_m"]), this.rows);
      return this.rows[0];
    };
    const height = probe();
    const candidates: number[] = [];
    for (let i = 0; i < memory.length; i += 1) {
      if (memory[i] === height) {
        candidates.push(i);
      }
    }
    for (const at of candidates) {
      const before = probe();
      memory[at] += 50;
      const after = probe();
      if (Math.abs(after - before - 50) < 1) {
        memory[at] -= 50;
        this.heightAt = at;
        return;
      }
      memory[at] -= 50;
    }
    throw new Error("The helicopter's height is not in the FMU's memory");
  }

  private startControls(): void {
    const c = this.start.controls;
    this.u[COLLECTIVE] = c.collective;
    this.u[LON] = c.cyclic_lon;
    this.u[LAT] = c.cyclic_lat;
    this.u[PEDALS] = c.pedals;
    this.u[SCAS] = c.scas;
  }

  override get time(): number {
    return this.fmu.time - this.settled;
  }

  north(): number {
    return this.get("north_m") + this.origin.north;
  }

  east(): number {
    return this.get("east_m") + this.origin.east;
  }

  /** Height of the CG above the sea. */
  altitude(): number {
    return this.get("alt_m") + this.datum;
  }

  /** Height of the wheels over what is below them. */
  radar(): number {
    return this.altitude() - GEAR_Z - this.surface.at(this.north(), this.east());
  }

  get scas(): boolean {
    return this.u[SCAS] > 0.5;
  }

  set scas(on: boolean) {
    this.u[SCAS] = on ? 1 : 0;
  }

  /** Total load on the gear in newtons. */
  gearLoad(): number {
    return this.get("fn_nose") + this.get("fn_left") + this.get("fn_right");
  }

  get onGround(): boolean {
    return this.gearLoad() > 0.02 * WEIGHT;
  }

  reset(start: Start = this.start, placing: Placing = this.placing): void {
    this.start = start;
    this.placing = placing;
    const params = turned(start.values, placing.heading);
    // A start's position is its place in the desktop app's circuit: here the FMU flies from zero.
    params.x0 = 0;
    params.y0 = -0;
    this.origin = { north: placing.north, east: placing.east };
    this.datum = placing.floor;
    this.restart(params, () => this.startControls());
    this.crashed = false;
    this.crashReason = "";
    this.touchdown = null;
    this.airTime = start.airborne ? 10 : 0;
    this.groundTime = start.airborne ? 0 : 10;
    this.sink.fill(0);
    if (start.settle > 0) {
      const pilot = this.pilot;
      this.pilot = null;
      for (let i = Math.round(start.settle / this.fmu.step); i > 0; i -= 1) {
        this.advance(this.fmu.step);
      }
      this.pilot = pilot;
    }
    this.settled = this.fmu.time;
    this.previous.set(this.y);
    this.velocities();
    this.pacer.reset();
  }

  setControls(collective: number, lon: number, lat: number, pedals: number): void {
    this.u[COLLECTIVE] = Math.max(0, Math.min(1, collective));
    this.u[LON] = Math.max(-1, Math.min(1, lon));
    this.u[LAT] = Math.max(-1, Math.min(1, lat));
    this.u[PEDALS] = Math.max(-1, Math.min(1, pedals));
  }

  /** Body to world, one row per north, east and up, for a body vector x forward, y left, z up. */
  private rotation(): Float64Array {
    const degrees = Math.PI / 180;
    const phi = this.get("phi_deg") * degrees;
    const theta = this.get("theta_deg") * degrees;
    const psi = this.get("psi_deg") * degrees;
    const [sf, cf, st, ct, sp, cp] = [Math.sin(phi), Math.cos(phi), Math.sin(theta), Math.cos(theta), Math.sin(psi), Math.cos(psi)];
    const r = this.rows;
    r[0] = ct * cp;
    r[1] = -(sf * st * cp - cf * sp);
    r[2] = -(cf * st * cp + sf * sp);
    r[3] = ct * sp;
    r[4] = -(sf * st * sp + cf * cp);
    r[5] = -(cf * st * sp - sf * cp);
    r[6] = st;
    r[7] = sf * ct;
    r[8] = cf * ct;
    return r;
  }

  private velocities(): void {
    const r = this.rotation();
    const u = this.get("u_mps");
    const v = -this.get("v_mps");
    const w = -this.get("w_mps");
    this.vn = r[0] * u + r[1] * v + r[2] * w;
    this.ve = r[3] * u + r[4] * v + r[5] * w;
  }

  groundSpeed(): number {
    return Math.hypot(this.vn, this.ve);
  }

  protected override beforeStep(): void {
    this.pilot?.(this);
    this.gusts.sample(this.fmu.step, this.get("tas_mps"), this.gust, 0);
    const height = Math.max(this.get("alt_m") - GEAR_Z, 0);
    // The wind dies towards the ground on a 1/7 power law, the gusts' vertical part below 20 m.
    const shear = Math.min(1, height / 100) ** (1 / 7);
    this.u[WIND_N] = this.wind.north * shear + this.gust[0];
    this.u[WIND_E] = this.wind.east * shear + this.gust[1];
    this.u[WIND_D] = this.gust[2] * Math.min(1, height / 20);
  }

  protected override afterStep(healthy: boolean): void {
    if (!healthy) {
      this.crash("The flight model stopped");
      return;
    }
    this.velocities();
    const n = this.north();
    const e = this.east();
    const below = this.surface.at(n, e);
    const dt = this.fmu.step;
    this.carryGround(below, dt);
    this.watch(n, e, below, dt);
  }

  /** Moves the FMU's ground towards `height` without moving the helicopter. */
  private carryGround(height: number, dt: number): void {
    const clear = this.get("alt_m") - GEAR_Z;
    let shift = height - this.datum;
    if (clear > 0.6) {
      // Ground that rises faster than the wheels is a crash for `watch` to find, not a lift.
      shift = Math.min(shift, clear - 0.3);
    } else {
      // On the wheels it can only creep, or the tyres would feel it as a kick.
      shift = Math.max(-CREEP * dt, Math.min(CREEP * dt, shift));
    }
    if (Math.abs(shift) < 1e-4) {
      return;
    }
    this.memory[this.heightAt] -= shift;
    this.datum += shift;
    this.y[ALT] -= shift;
    this.previous[ALT] -= shift;
  }

  private watch(n: number, e: number, below: number, dt: number): void {
    const strike = this.strike(n, e);
    if (strike) {
      this.crash(strike);
      return;
    }
    if (this.onGround && this.surface.water(n, e)) {
      this.crash("Water");
      return;
    }
    const wheel = Math.max(this.get("fn_nose"), this.get("fn_left"), this.get("fn_right"));
    if (wheel > WHEEL_LIMIT) {
      this.crash("The gear folded");
      return;
    }
    if (this.get("rotor_pct") < ROTOR_STALL) {
      this.crash("The rotor stalled");
      return;
    }
    this.sink[this.sinkAt] = this.get("vs_mps");
    this.sinkAt = (this.sinkAt + 1) % this.sink.length;
    if (!this.onGround) {
      this.airTime += dt;
      if (this.airTime > 0.5) {
        this.groundTime = 0;
      }
      return;
    }
    if (Math.abs(this.get("phi_deg")) > ROLLOVER) {
      this.crash("It rolled over");
      return;
    }
    if (this.airTime > 2) {
      const sink = -Math.min(...this.sink);
      this.touchdown = { sink, drift: this.groundSpeed(), bank: this.get("phi_deg"), north: n, east: e };
      if (sink > SINK_LIMIT) {
        this.crash("The gear folded");
        return;
      }
      if (this.surface.slope(n, e) > STEEPEST) {
        this.crash("Too steep to stand on");
        return;
      }
    }
    if (below - this.datum > WHEEL_SLACK) {
      this.crash("Terrain");
      return;
    }
    this.airTime = 0;
    this.groundTime += dt;
  }

  /** What part of the helicopter is inside something, if any. */
  private strike(n: number, e: number): string {
    const up = this.altitude();
    const r = this.rotation();
    const hit = (x: number, y: number, z: number): boolean => {
      const pn = n + r[0] * x + r[1] * y + r[2] * z;
      const pe = e + r[3] * x + r[4] * y + r[5] * z;
      const pu = up + r[6] * x + r[7] * y + r[8] * z;
      return pu < this.surface.at(pn, pe) || this.surface.inTree(pn, pe, pu);
    };
    for (const [name, x, y, z] of STRIKE) {
      if (hit(x, y, z)) {
        return `${name} hit`;
      }
    }
    for (const [x, y, z] of TIPS) {
      if (hit(x, y, z)) {
        return "The main rotor hit";
      }
    }
    for (const [x, y, z] of WHEELS) {
      if (hit(x, y, z + WHEEL_SLACK)) {
        return this.surface.water(n, e) ? "Water" : "Terrain";
      }
    }
    return "";
  }

  private crash(reason: string): void {
    this.crashed = true;
    this.crashReason = reason;
    this.stopped = true;
  }
}
