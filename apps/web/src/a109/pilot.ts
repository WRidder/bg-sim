/**
 * The loops a pilot closes on top of the SCAS: the climb on the collective, the speeds on the cyclic.
 * `Assist` lets a keyboard fly with them. `Autopilot` adds the phases of a flight from pad to pad,
 * for the title screen and for the test that proves a mission can be flown.
 */

import { type Flight, ON_GEAR, POWER_LIMIT } from "./flight";
import type { Pad } from "./pads";
import type { Surface } from "./surface";

const DEG = Math.PI / 180;
const STEP = 0.005;
const clamp = (value: number, low: number, high: number): number => Math.max(low, Math.min(high, value));
const wrap = (degrees: number): number => ((degrees + 540) % 360) - 180;

/** Collective of level flight over the speed in knots: the FMU's own trims. */
const LEVEL: readonly (readonly [number, number])[] = [[0, 0.604], [20, 0.54], [40, 0.46], [60, 0.414], [80, 0.425], [100, 0.46], [140, 0.62]];

function levelCollective(knots: number): number {
  for (let i = 1; i < LEVEL.length; i += 1) {
    const [x0, y0] = LEVEL[i - 1];
    const [x1, y1] = LEVEL[i];
    if (knots <= x1) {
      return y0 + ((y1 - y0) * (Math.max(knots, x0) - x0)) / (x1 - x0);
    }
  }
  return LEVEL[LEVEL.length - 1][1];
}

/** The speeds of a flight over the ground, along and across its nose. */
export function bodySpeeds(f: Flight): [number, number] {
  const psi = f.get("psi_deg") * DEG;
  const c = Math.cos(psi);
  const s = Math.sin(psi);
  return [f.vn * c + f.ve * s, -f.vn * s + f.ve * c];
}

export class Loops {
  collective = 0;
  private integral = 0;

  reset(collective: number): void {
    this.collective = collective;
    this.integral = 0;
  }

  /** The lever for a climb rate. A hover has 60 hp to spare: past that the rotor pays, so the loop eases off. */
  climb(f: Flight, wanted: number, rate = 0.25): number {
    const error = wanted - f.get("vs_mps");
    if (f.get("wow") < 0.5) {
      this.integral = clamp(this.integral + 0.02 * error * STEP, -0.15, 0.3);
    }
    let lever = levelCollective(f.get("kts")) + 0.04 * error + this.integral;
    const droop = Math.max(0, 98.5 - f.get("rotor_pct")) * 0.05 + Math.max(0, f.get("power_hp") - (POWER_LIMIT - 6)) * 0.004;
    if (droop > 0) {
      lever = Math.min(lever, this.collective - droop * rate * STEP * 40);
      this.integral = Math.max(-0.15, this.integral - droop * STEP);
    }
    this.collective += clamp(lever - this.collective, -rate * STEP, rate * STEP);
    this.collective = clamp(this.collective, 0, 1);
    return this.collective;
  }

  /** Lets the lever down once the wheels carry the weight. */
  settle(rate = 0.3): number {
    this.collective = Math.max(0, this.collective - rate * STEP);
    this.integral = 0;
    return this.collective;
  }

  /** The lever up off the ground until the helicopter gets light. */
  raise(rate = 0.3): number {
    this.collective = Math.min(0.66, this.collective + rate * STEP);
    return this.collective;
  }
}

/** The cyclic for speeds over the ground: `forward` along the nose, `right` across it. */
function cyclicFor(f: Flight, forward: number, right: number, limit = 0.4): [number, number] {
  const [along, across] = bodySpeeds(f);
  return [clamp((2 * (forward - along)) / 15, -limit, limit), clamp((2.5 * (right - across)) / 30, -limit, limit)];
}

/** What a player asks for, each -1..1. */
export interface Sticks {
  fore: number;
  side: number;
  pedals: number;
  lift: number;
}

/** How far ahead of the speed a full stick asks, in m/s: enough to hold the cyclic at its limit. */
const LEAD = 14;
/** Airspeed the autohover stops at, in m/s: a good cruise, and well short of where the nose gets away. */
const TOP_SPEED = 62;

/**
 * Flying by asking for speeds. The cyclic asks for a speed over the ground and the helicopter holds
 * it: at a low speed it dies by itself, so letting go means a hover, and above that it stays, so a
 * transit needs no held key. The lever asks for a climb rate and holds the height when let go.
 */
export class Assist {
  readonly sticks: Sticks = { fore: 0, side: 0, pedals: 0, lift: 0 };
  /** Set while a key asks for a hover, from any speed. */
  brake = false;
  speed = 0;
  private hold: number | null = null;
  private readonly loops = new Loops();

  reset(f: Flight): void {
    this.speed = bodySpeeds(f)[0];
    this.hold = f.onGround ? null : f.altitude();
    this.loops.reset(f.u[0]);
    this.brake = false;
  }

  fly = (f: Flight): void => {
    const { fore, side, pedals, lift } = this.sticks;
    const [along] = bodySpeeds(f);
    // The stick leads the speed there is, so that letting go keeps it and braking starts at once.
    // The top is in the air, not over the ground: into a wind the same stick would pass the rotor's limit.
    const top = TOP_SPEED + along - f.get("tas_mps");
    if (this.brake) {
      this.speed = along - Math.sign(along) * Math.min(Math.abs(along), LEAD);
    } else if (fore !== 0) {
      this.speed = clamp(along + fore * LEAD, -8, top);
    } else if (Math.abs(this.speed) < 12) {
      this.speed -= Math.sign(this.speed) * Math.min(Math.abs(this.speed), 5 * STEP);
    }
    this.speed = Math.min(this.speed, top);
    if (f.get("wow") > 0.5) {
      const collective = lift > 0.05 ? this.loops.raise() : this.loops.settle();
      this.hold = lift > 0.05 ? f.altitude() + 1.5 : null;
      f.setControls(collective, 0, 0, pedals * 0.5);
      return;
    }
    // Fast, the stick banks. Below the speed where a bank turns it, the same stick slides it sideways.
    const fast = clamp((Math.abs(along) - 12) / 12, 0, 1);
    // Close to the ground the nose stays down, or a hard stop would put the tail on it.
    const radar = Math.max(f.radar(), 0);
    const [lon, slide] = cyclicFor(f, this.speed, 8 * side, (this.brake ? 0.9 : 0.75) * clamp(radar / 10, 0.2, 1));
    const lat = slide * (1 - fast) + ((side * 26) / 30) * fast;
    const coordinate = f.get("kts") > 25 && pedals === 0 ? clamp(0.03 * f.get("beta_deg"), -0.3, 0.3) : 0;
    if (lift !== 0) {
      this.hold = null;
    }
    // Let go, and it holds the height it will have stopped at, not the one it passed.
    this.hold ??= f.altitude() + f.get("vs_mps");
    const wanted = lift !== 0
      ? (lift > 0 ? lift * 7 : lift * Math.min(6, 0.45 + radar * 0.24))
      : clamp(0.6 * (this.hold - f.altitude()), -2, 2);
    f.setControls(this.loops.climb(f, wanted, 0.32), lon, lat, pedals + coordinate);
  };
}

/** Height of the CG over a deck in the hover before the descent. */
const HOVER = 5;
const GLIDE = 7 * DEG;

/** A pilot that flies a list of pads as a helicopter pilot would, and stops on the last. */
export class Autopilot {
  phase = "parked";
  index = 0;
  done = false;
  log: string[] = [];
  private inPhase = 0;
  private readonly loops = new Loops();
  private heading = 0;
  private hold: [number, number] = [0, 0];
  private speed = 0;

  constructor(
    private readonly route: readonly Pad[],
    private readonly surface: Surface,
    private readonly cruise = 60,
    private readonly clearance = 90,
  ) {}

  private set(f: Flight, phase: string): void {
    this.log.push(`${f.time.toFixed(1)} ${phase}`);
    this.phase = phase;
    this.inPhase = 0;
  }

  /** On the gear now, or in the air: fly on from here. */
  begin(f: Flight): void {
    this.heading = f.get("psi_deg");
    this.hold = [f.north(), f.east()];
    this.speed = bodySpeeds(f)[0];
    this.loops.reset(f.u[0]);
    this.phase = f.onGround ? "parked" : "route";
    this.inPhase = 0;
  }

  /** The mission has counted the landing: on to the next pad. */
  next(f: Flight): void {
    this.index += 1;
    if (this.index + 1 < this.route.length) {
      this.begin(f);
    } else {
      this.done = true;
    }
  }

  /** The highest thing on the way from here towards `pad`. */
  private highestAhead(f: Flight, pad: Pad, distance: number): number {
    const n = f.north();
    const e = f.east();
    const full = Math.max(Math.hypot(pad.north - n, pad.east - e), 1);
    const reach = Math.min(distance, 1800);
    let highest = 0;
    for (let i = 1; i <= 8; i += 1) {
      const t = (i * reach) / (8 * full);
      highest = Math.max(highest, this.surface.at(n + (pad.north - n) * t, e + (pad.east - e) * t));
    }
    return highest;
  }

  private holdOver(f: Flight, north: number, east: number): [number, number, number] {
    const psi = f.get("psi_deg") * DEG;
    const c = Math.cos(psi);
    const s = Math.sin(psi);
    const dn = north - f.north();
    const de = east - f.east();
    const [lon, lat] = cyclicFor(f, clamp(0.25 * (dn * c + de * s), -3, 3), clamp(0.25 * (-dn * s + de * c), -3, 3), 0.35);
    return [lon, lat, clamp(0.03 * wrap(this.heading - f.get("psi_deg")), -0.4, 0.4)];
  }

  fly = (f: Flight): void => {
    this.inPhase += STEP;
    const more = this.index + 1 < this.route.length;
    const pad = this.route[more ? this.index + 1 : this.index];
    const from = this.route[this.index];
    const here = f.altitude();
    const dn = pad.north - f.north();
    const de = pad.east - f.east();
    const distance = Math.max(Math.hypot(dn, de), 1);
    const bearing = Math.atan2(de, dn) / DEG;
    switch (this.phase) {
      case "parked": {
        f.setControls(this.loops.settle(), 0, 0, 0);
        if (this.inPhase > 1 && more) {
          this.hold = [f.north(), f.east()];
          this.heading = f.get("psi_deg");
          this.set(f, "liftoff");
        }
        return;
      }
      case "liftoff": {
        const collective = f.get("wow") > 0.5 ? this.loops.raise(0.25) : this.loops.climb(f, 1.5, 0.2);
        const [lon, lat, pedals] = f.get("wow") < 0.5 ? this.holdOver(f, this.hold[0], this.hold[1]) : [0, 0, 0];
        f.setControls(collective, lon, lat, pedals);
        if (here - from.top > HOVER + 3) {
          this.heading = bearing;
          this.speed = 0;
          this.set(f, "turn");
        }
        return;
      }
      case "turn": {
        const [lon, lat, pedals] = this.holdOver(f, this.hold[0], this.hold[1]);
        f.setControls(this.loops.climb(f, 0.6), lon, lat, pedals);
        if (Math.abs(wrap(this.heading - f.get("psi_deg"))) < 5) {
          this.set(f, "route");
        }
        return;
      }
      case "route": {
        // Climbing takes power the engines cannot give at speed too: go as fast as the height allows.
        const ahead = this.highestAhead(f, pad, distance);
        const wanted = Math.max(ahead + this.clearance, pad.top + 45);
        const climbTime = Math.max(Math.max(wanted, pad.top + HOVER + 20) - here, 0) / 6;
        const stopping = Math.sqrt(2 * 0.7 * Math.max(distance - 8, 0));
        const allowed = climbTime > 1 ? Math.max(distance / climbTime, 18) : this.cruise;
        // Rock close ahead and not above it yet: stop and climb, it will not get any further away.
        const wall = this.highestAhead(f, pad, Math.min(distance, 220)) + 14 > here ? 4 : this.cruise;
        this.speed += clamp(Math.min(this.cruise, allowed, stopping, wall) - this.speed, -1.2 * STEP, 1.1 * STEP);
        const glide = pad.top + HOVER + Math.max(distance - 30, 0) * Math.tan(GLIDE);
        const target = distance < 900 ? Math.max(Math.min(wanted, glide), ahead + (distance > 60 ? 18 : 0)) : wanted;
        const [along] = bodySpeeds(f);
        const [lon] = cyclicFor(f, this.speed, 0, 0.75);
        const track = Math.hypot(f.vn, f.ve) > 5 ? Math.atan2(f.ve, f.vn) / DEG : f.get("psi_deg");
        let lat = clamp((1.6 * wrap(bearing - track)) / 30, -0.7, 0.7);
        let pedals = f.get("kts") > 25 ? clamp(0.03 * f.get("beta_deg"), -0.3, 0.3) : 0;
        if (along < 9) {
          // Slow, a bank no longer turns it: the pedals point the nose and the cyclic stops the slide.
          pedals = distance > 15 ? clamp(0.03 * wrap(bearing - f.get("psi_deg")), -0.3, 0.3) : 0;
          lat = cyclicFor(f, this.speed, 0, 0.3)[1];
        }
        f.setControls(this.loops.climb(f, clamp(0.4 * (target - here), -3.5, 7.5)), lon, lat, pedals);
        if (distance < 14 && along < 3) {
          this.heading = f.get("psi_deg");
          this.set(f, "over pad");
        }
        return;
      }
      case "over pad": {
        const [lon, lat, pedals] = this.holdOver(f, pad.north, pad.east);
        f.setControls(this.loops.climb(f, clamp(0.4 * (pad.top + HOVER - here), -2.5, 1)), lon, lat, pedals);
        if (this.inPhase > 2 && distance < 2 && f.groundSpeed() < 0.7 && Math.abs(here - pad.top - HOVER) < 1.5) {
          this.set(f, "descend");
        }
        return;
      }
      case "descend": {
        const [lon, lat, pedals] = this.holdOver(f, pad.north, pad.east);
        f.setControls(this.loops.climb(f, here - pad.top - ON_GEAR > 0.8 ? -0.8 : -0.35), lon, lat, pedals);
        if (f.get("wow") > 0.5) {
          this.set(f, "landed");
        }
        return;
      }
      default:
        f.setControls(this.loops.settle(0.15), 0, 0, 0);
    }
  };
}
