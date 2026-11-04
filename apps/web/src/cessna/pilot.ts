/**
 * A pilot for the title screen and for the tests: the phases of a circuit, flown closed loop with
 * the same levers as the player has. The inner loops are those of the desktop app's pilot.py:
 * attitude with rate damping on the yoke, bank on the ailerons, a heading loop on the bank.
 * Everything here is in the FMU's frame, where the runway lies along x and the circuit is to the left.
 */

import type { Gate } from "../engine/gates";
import { toFrame } from "./course";
import { THRESHOLD_X, type Flight } from "./flight";

const clamp = (value: number, low: number, high: number): number => Math.max(low, Math.min(high, value));
const wrap = (angle: number): number => ((angle + 540) % 360) - 180;

const FT = 0.3048;
const KT = 0.51444;
const AIM = 120;
const GLIDE = (3 * Math.PI) / 180;
const CIRCUIT = 700 * FT;
const DOWNWIND_OFFSET = 900;
/** How far past the threshold the circuit turns base. */
const BASE_AT = THRESHOLD_X - 1200;
const UPWIND_END = 2150;

export type Phase = "roll" | "rotate" | "climb" | "crosswind" | "downwind" | "base" | "final" | "flare" | "landed" | "route" | "glide";

export class Pilot {
  phase: Phase;
  private time = 0;
  private held = 0;
  private integral = 0;
  private leg = 0;
  private velocity = [0, 0];
  private point: [number, number] | null = null;
  private last: [number, number, number] | null = null;
  private rates: [number, number, number] = [0, 0, 0];

  constructor(phase: Phase = "roll") {
    this.phase = phase;
  }

  private go(phase: Phase): void {
    this.phase = phase;
    this.time = 0;
  }

  private ramp(target: number, dt: number, rate = 1.5): number {
    this.held += clamp(target - this.held, -rate * dt, rate * dt);
    return this.held;
  }

  private pitch(want: number, theta: number, q: number): number {
    return 0.175 * (want - theta) - 0.035 * q;
  }

  private roll(want: number, phi: number, p: number): number {
    return clamp(0.035 * (want - phi) - 0.005 * p, -0.6, 0.6);
  }

  private bankTo(heading: number, psi: number, limit = 20): number {
    return clamp(1.2 * wrap(heading - psi), -limit, limit);
  }

  private climbAttitude(kias: number, agl: number): number {
    const theta = clamp(6.5 + 0.8 * (kias - 75), 4.5, 10);
    return agl < 60 ? Math.max(theta, 6) : theta;
  }

  /** Low and fast to the next ring, on the near side of its line, for the coast run. */
  route(f: Flight, gate: Gate, ground: (north: number, east: number) => number): void {
    const [x, east] = toFrame(gate.north, gate.east);
    const dx = x - f.get("north_m");
    const de = east - f.get("east_m");
    const range = Math.hypot(dx, de);
    const lead = Math.min(range * 0.35, 500);
    const through = ((gate.heading - 252) * Math.PI) / 180;
    const bearing = (Math.atan2(de - lead * Math.sin(through), dx - lead * Math.cos(through)) * 180) / Math.PI;
    const psi = f.get("psi_deg");
    const phi = f.get("phi_deg");
    const theta = f.get("theta_deg");
    const [p, q] = this.rates;
    // Terrain ahead overrides the ring's height.
    const speed = f.get("ktas") * KT;
    const h = ((psi + 252) * Math.PI) / 180;
    let floor = 0;
    for (const seconds of [2, 4, 6, 9, 12]) {
      const reach = Math.min(speed * seconds, Math.max(range, 120));
      floor = Math.max(floor, ground(f.north() + reach * Math.cos(h), f.east() + reach * Math.sin(h)));
    }
    const want = Math.max(gate.alt, floor + (gate.alt < 60 ? 12 : 35));
    const error = want - f.altitude();
    const climb = clamp(error * 0.3, -8, 7);
    const attitude = clamp(((climb / Math.max(speed, 30)) * 180) / Math.PI + f.get("alpha_deg"), -9, 12);
    f.setControls(this.pitch(attitude, theta, q), this.roll(this.bankTo(bearing, psi, 32), phi, p), -0.01 * this.rates[2], 1);
  }

  /** One step: call before `flight.advance`. */
  fly(f: Flight, dt = 0.005): void {
    this.time += dt;
    const phi = f.get("phi_deg");
    const theta = f.get("theta_deg");
    const psi = f.get("psi_deg");
    if (this.last) {
      const raw = [(phi - this.last[0]) / dt, (theta - this.last[1]) / dt, wrap(psi - this.last[2]) / dt];
      this.rates = this.rates.map((rate, i) => rate + 0.3 * (raw[i] - rate)) as [number, number, number];
    }
    this.last = [phi, theta, psi];
    const [p, q, r] = this.rates;
    const kias = f.get("kias");
    const agl = f.get("agl_ft");
    const north = f.get("north_m");
    const east = f.get("east_m");
    if (this.point) {
      this.velocity[0] += 0.03 * ((north - this.point[0]) / dt - this.velocity[0]);
      this.velocity[1] += 0.03 * ((east - this.point[1]) / dt - this.velocity[1]);
    }
    this.point = [north, east];
    const onGround = f.get("on_ground") > 0.5;
    let yoke = 0;
    let roll = 0;
    let pedals = -0.01 * r;
    let throttle = f.throttle;
    let brake = 0;
    const level = (): number => clamp(2 + 0.04 * (CIRCUIT - f.get("alt_m")) / FT, -3, 8);
    switch (this.phase) {
      case "roll":
        throttle = clamp(this.time / 2, 0, 1);
        pedals = clamp(-0.06 * wrap(psi) - 0.04 * r - 0.03 * east, -1, 1);
        roll = this.roll(0, phi, p);
        yoke = -0.05;
        if (kias > 50) {
          this.go("rotate");
          this.held = theta;
        }
        break;
      case "rotate":
        throttle = 1;
        yoke = this.pitch(this.ramp(8, dt, 3), theta, q);
        pedals = onGround ? clamp(-0.06 * wrap(psi) - 0.04 * r, -1, 1) : pedals;
        roll = this.roll(0, phi, p);
        if (agl > 15) {
          this.go("climb");
        }
        break;
      case "climb":
        throttle = 1;
        yoke = this.pitch(this.ramp(this.climbAttitude(kias, agl), dt), theta, q);
        if (agl > 300) {
          f.setFlaps(0);
        }
        roll = this.roll(this.bankTo(-0.03 * east, psi), phi, p);
        if (north > UPWIND_END) {
          this.go("crosswind");
        }
        break;
      case "crosswind": {
        const below = f.get("alt_m") < CIRCUIT - 10;
        throttle = below ? 1 : 0.78;
        yoke = this.pitch(this.ramp(below ? this.climbAttitude(kias, agl) : level(), dt), theta, q);
        roll = this.roll(this.bankTo(270, psi), phi, p);
        if (-east > DOWNWIND_OFFSET - 280) {
          this.go("downwind");
        }
        break;
      }
      case "downwind":
        throttle = f.get("alt_m") < CIRCUIT - 10 ? 1 : 0.76;
        yoke = this.pitch(this.ramp(level(), dt), theta, q);
        roll = this.roll(this.bankTo(180 - 0.04 * (-east - DOWNWIND_OFFSET), psi), phi, p);
        if (north < BASE_AT) {
          f.setFlaps(2);
          this.go("base");
        }
        break;
      case "glide": {
        // No engine: the nose holds the best glide, and the turn back is flown by geometry.
        yoke = this.pitch(this.ramp(clamp(-3 + 1.2 * (kias - 72), -9, 5), dt), theta, q);
        if (this.leg === 0) {
          roll = this.roll(this.bankTo(180, psi), phi, p);
          if (north < -60) {
            this.leg = 1;
          }
        } else if (this.leg === 1) {
          roll = this.roll(this.bankTo(90, psi, 28), phi, p);
          if (east > -300) {
            this.leg = 2;
          }
        } else {
          roll = this.roll(this.bankTo(clamp(-0.09 * east, -50, 50), psi, 28), phi, p);
          if (Math.abs(east) < 60 && Math.abs(wrap(psi)) < 12) {
            f.setFlaps(agl < 200 ? 3 : 2);
          }
        }
        if (agl < 22) {
          this.go("flare");
        }
        break;
      }
      case "base":
        throttle = 0.18;
        yoke = this.pitch(this.ramp(clamp(-2 + 1.5 * (kias - 70), -8, 6), dt), theta, q);
        roll = this.roll(this.bankTo(90, psi), phi, p);
        if (east > -420) {
          f.setFlaps(3);
          this.integral = 0;
          this.go("final");
        }
        break;
      case "final": {
        // Steer the track over the ground, not the nose: in a crosswind that is a crab.
        const drift = wrap(psi - (Math.atan2(this.velocity[1], this.velocity[0]) * 180) / Math.PI);
        roll = this.roll(this.bankTo(clamp(-0.06 * east, -25, 25) + drift, psi), phi, p);
        const path = Math.max(0, (AIM - north) * Math.tan(GLIDE));
        const wantSink = (-kias * KT * Math.sin(GLIDE)) / FT * 60;
        yoke = this.pitch(clamp(-1 + 0.6 * (path - agl * FT) + 0.006 * (wantSink - f.get("vs_fpm")), -7, 7), theta, q);
        this.integral = clamp(this.integral + dt * (65 - kias), -40, 40);
        throttle = clamp(0.68 + 0.06 * (65 - kias) + 0.01 * this.integral, 0, 1);
        if (agl < 22) {
          this.go("flare");
        }
        break;
      }
      case "flare": {
        throttle = 0;
        const want = -(60 + 5 * agl);
        yoke = this.pitch(clamp(theta + 0.02 * (want - f.get("vs_fpm")), -2, 9), theta, q);
        roll = this.roll(0, phi, p);
        pedals = clamp(-0.06 * wrap(psi) - 0.02 * r, -1, 1);
        if (onGround && this.time > 0.3) {
          this.go("landed");
        }
        break;
      }
      case "landed":
        throttle = 0;
        yoke = this.time < 2 ? this.pitch(0, theta, q) : 0.2;
        roll = this.roll(0, phi, p);
        pedals = clamp(-0.06 * wrap(psi) - 0.04 * r - 0.03 * east, -1, 1);
        brake = kias > 3 ? clamp((this.time - 2) / 3, 0, 0.7) : 0.4;
        if (this.time > 3) {
          f.setFlaps(0);
        }
        break;
    }
    f.setControls(yoke, roll, pedals, throttle);
    f.setBrakes(brake);
  }
}
