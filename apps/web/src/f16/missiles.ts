/**
 * The AIM-9X FMU on the browser side. Each wingtip is one `Fmu` instance and one `Missile`
 * (a `Sim` view of it); the host gives the missile a launch frame and the target's launch-relative
 * NED position/velocity every 5 ms. The FMU has no fuze stop: the first `fuze`/`hit` retires the
 * shot in the game, the same as in the desktop host.
 */

import * as THREE from "three";
import { Fmu } from "../engine/fmu";
import { Sim } from "../engine/sim";
import { attitude } from "../engine/frames";
import type { Drone } from "./targets";
import { model as missileModel } from "./missile.gen";

export const MISSILE_INPUTS = [
  "target_north_m", "target_east_m", "target_down_m", "target_vn_mps", "target_ve_mps",
  "target_vd_mps", "target_ir_w", "seeker_on",
] as const;

export const MISSILE_OUTPUTS = [
  "north_m", "west_m", "alt_m", "q_w", "q_x", "q_y", "q_z", "thrust_n",
  "fin1_deg", "fin2_deg", "fin3_deg", "fin4_deg", "fuze", "hit", "range_m",
  "min_range_m", "lock", "mass_kg", "vt_mps", "alpha_deg", "beta_deg",
] as const;
export type MissileOutput = (typeof MISSILE_OUTPUTS)[number];

export interface LaunchFrame {
  north: number;
  east: number;
  heading: number;   // degrees, north toward east
  alt: number;
}

const DEG = Math.PI / 180;
const IR_W = 1e6;
const UP = new THREE.Vector3(0, 1, 0);

/** The target in the FMU's launch-relative NED frame (down is absolute, -altitude). */
export function targetInput(frame: LaunchFrame, target: Drone): number[] {
  const c = Math.cos(frame.heading * DEG);
  const s = Math.sin(frame.heading * DEG);
  const dn = target.north - frame.north;
  const de = target.east - frame.east;
  const vn = target.speed * Math.cos(target.heading * DEG);
  const ve = target.speed * Math.sin(target.heading * DEG);
  return [
    c * dn + s * de,
    -s * dn + c * de,
    -target.alt,
    c * vn + s * ve,
    -s * vn + c * ve,
    0,
    IR_W,
    1,
  ];
}

/** Model local north/west and absolute altitude -> world north/east/altitude. */
export function localToWorld(frame: LaunchFrame, north: number, west: number, alt: number): [number, number, number] {
  const c = Math.cos(frame.heading * DEG);
  const s = Math.sin(frame.heading * DEG);
  return [frame.north + c * north + s * west, frame.east + s * north - c * west, alt];
}

export class Missile extends Sim<MissileOutput> {
  id = 0;
  frame!: LaunchFrame;
  target!: Drone;
  targetId = 0;
  side = 0;
  active = false;
  done = false;
  justHit = false;

  constructor(fmu: Fmu) {
    super(fmu, MISSILE_INPUTS, MISSILE_OUTPUTS);
  }

  fire(id: number, frame: LaunchFrame, target: Drone, speed: number, side: number): void {
    this.id = id;
    this.frame = frame;
    this.target = target;
    this.targetId = target.id;
    this.side = side;
    this.active = true;
    this.done = false;
    this.justHit = false;
    this.restart({
      vt0: Math.max(100, Math.min(700, speed)),
      h0: Math.max(0, Math.min(20000, frame.alt)),
      alpha0: 2,
      tvc_on: 1,
      nav_N: 4,
      a_max_g: 60,
    }, () => {
      this.u.set(targetInput(frame, target));
    });
  }

  protected override beforeStep(): void {
    // The target is a live object; while it is alive its state is read at the frame rate. A dead
    // target keeps its last state, so the missile still flies to where it was.
    this.u.set(targetInput(this.frame, this.target));
  }

  protected override afterStep(healthy: boolean): void {
    if (!healthy) {
      this.stopped = true;
      return;
    }
    if (!this.done && (this.get("fuze") > 0.5 || this.get("hit") > 0.5)) {
      this.done = true;
      this.justHit = true;
      this.stopped = true;
    }
  }

  worldPosition(): THREE.Vector3 {
      const [north, east, alt] = localToWorld(
      this.frame,
      this.between("north_m"),
      this.between("west_m"),
      this.between("alt_m"),
    );
    return new THREE.Vector3(east, alt, -north);
  }

  worldQuaternion(into: THREE.Quaternion): THREE.Quaternion {
    attitude(
      this.between("q_w"),
      this.between("q_x"),
      -this.between("q_y"),
      -this.between("q_z"),
      into,
    );
    into.premultiply(new THREE.Quaternion().setFromAxisAngle(UP, -this.frame.heading * DEG));
    return into;
  }

  get thrust(): number {
    return this.get("thrust_n");
  }

  fin(index: 0 | 1 | 2 | 3): number {
    return this.get((["fin1_deg", "fin2_deg", "fin3_deg", "fin4_deg"] as const)[index]);
  }
}

export const RELOAD_DELAY = 5;

export class MissileSystem {
  private constructor(
    private readonly fmu: readonly [Fmu, Fmu],
  ) {}

  /** The loaded rounds; a slot is null while it is being reloaded or was fired. */
  readonly shots: (Missile | null)[] = [null, null];
  /** Every round ever fired, still needed for its FMU, trail and explosion. */
  readonly live: Missile[] = [];
  private nextId = 1;
  private reloadIn: number | null = null;

  static async create(): Promise<MissileSystem> {
    return new MissileSystem([await Fmu.load(missileModel), await Fmu.load(missileModel)]);
  }

  reset(): void {
    this.shots[0] = null;
    this.shots[1] = null;
    this.live.length = 0;
    this.reloadIn = null;
    this.nextId = 1;
  }

  get free(): number {
    return this.shots.filter((shot) => shot === null).length;
  }

  get reloading(): boolean {
    return this.reloadIn !== null;
  }

  get reloadLeft(): number {
    return Math.max(0, this.reloadIn ?? 0);
  }

  freeSide(): 0 | 1 | null {
    if (this.shots[0] === null) {
      return 0;
    }
    if (this.shots[1] === null) {
      return 1;
    }
    return null;
  }

  slotFree(side: 0 | 1): boolean {
    return this.shots[side] === null;
  }

  fire(side: 0 | 1, frame: LaunchFrame, target: Drone, speed: number): Missile | null {
    if (this.shots[side] !== null) {
      return null;
    }
    const missile = new Missile(this.fmu[side]);
    missile.fire(this.nextId, frame, target, speed, side);
    this.nextId += 1;
    this.shots[side] = missile;
    this.live.push(missile);
    if (this.shots.every((shot) => shot !== null)) {
      this.reloadIn = RELOAD_DELAY;
    }
    return missile;
  }

  advance(dt: number): void {
    for (const missile of this.live) {
      missile.advance(dt);
    }
    if (this.reloadIn !== null) {
      this.reloadIn -= dt;
      if (this.reloadIn <= 0) {
        this.shots[0] = null;
        this.shots[1] = null;
        this.reloadIn = null;
      }
    }
  }

  active(): Missile[] {
    return this.live.filter((missile) => missile.active && !missile.done);
  }
}
