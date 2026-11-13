/**
 * The AIM-9X FMU on the browser side. Each round in flight is one `Fmu` instance and one `Missile`
 * (a `Sim` view of it); the host gives the missile a launch frame and the target's launch-relative
 * NED position/velocity every 5 ms. The FMU has no fuze stop: the first `fuze`/`hit` retires the
 * shot in the game, the same as in the desktop host. A round that will not get there destroys
 * itself: once its seeker has been without the target for `LOST_LIMIT` seconds on end, or at
 * `MAX_FLIGHT` seconds whatever it sees.
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
  "min_range_m", "lock", "mass_kg", "vt_mps", "alpha_deg", "beta_deg", "t_go_s",
] as const;
export type MissileOutput = (typeof MISSILE_OUTPUTS)[number];

export interface LaunchFrame {
  north: number;
  east: number;
  heading: number;   // degrees, north toward east
  alt: number;
}

/** Seconds without the target, on end, after which the round destroys itself. */
export const LOST_LIMIT = 7;
/** Seconds of flight after which it does so anyway: by then it has coasted down to a glide. */
export const MAX_FLIGHT = 30;
/** The seeker needs this long off the rail before a missing lock counts as lost. */
const ACQUIRE = 0.6;

const DEG = Math.PI / 180;
const IR_W = 1e6;
const UP = new THREE.Vector3(0, 1, 0);
const TURN = new THREE.Quaternion();

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
  /** Set for the game when the round has destroyed itself; the game clears it. */
  justDestroyed = false;
  /** Seconds the seeker has been without the target, on end. */
  lostFor = 0;

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
    this.justDestroyed = false;
    this.lostFor = 0;
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
      return;
    }
    this.lostFor = this.tracking || this.time < ACQUIRE ? 0 : this.lostFor + this.fmu.step;
    if (!this.done && (this.lostFor >= LOST_LIMIT || this.time >= MAX_FLIGHT)) {
      this.done = true;
      this.justDestroyed = true;
      this.stopped = true;
    }
  }

  worldPosition(into = new THREE.Vector3()): THREE.Vector3 {
    const [north, east, alt] = localToWorld(
      this.frame,
      this.between("north_m"),
      this.between("west_m"),
      this.between("alt_m"),
    );
    return into.set(east, alt, -north);
  }

  worldQuaternion(into: THREE.Quaternion): THREE.Quaternion {
    attitude(
      this.between("q_w"),
      this.between("q_x"),
      -this.between("q_y"),
      -this.between("q_z"),
      into,
    );
    into.premultiply(TURN.setFromAxisAngle(UP, -this.frame.heading * DEG));
    return into;
  }

  uses(fmu: Fmu): boolean {
    return this.fmu === fmu;
  }

  /** Seconds to the target at the present closing speed, as the round's own guidance has it. */
  get timeToGo(): number {
    return this.get("t_go_s");
  }

  /** True while the seeker holds the target. */
  get tracking(): boolean {
    return this.get("lock") > 0.5;
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
    private readonly fmus: readonly Fmu[],
  ) {}

  /** The loaded rounds; a slot is null while it is being reloaded or was fired. */
  readonly shots: (Missile | null)[] = [null, null];
  /** Every round ever fired, still needed for its FMU, trail and explosion. */
  readonly live: Missile[] = [];
  private nextId = 1;
  private reloadIn: number | null = null;

  static async create(): Promise<MissileSystem> {
    // More instances than wingtips: a round can still be flying when its wingtip is loaded again,
    // and each round in flight needs an instance of its own.
    return new MissileSystem(await Promise.all([0, 1, 2, 3].map(() => Fmu.load(missileModel))));
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
    const fmu = this.fmus.find((candidate) => !this.live.some((round) => round.uses(candidate) && !round.done));
    if (!fmu) {
      return null;
    }
    const missile = new Missile(fmu);
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

  /** The last round fired that is still flying. */
  newest(): Missile | null {
    for (let i = this.live.length - 1; i >= 0; i -= 1) {
      if (this.live[i].active && !this.live[i].done) {
        return this.live[i];
      }
    }
    return null;
  }

  /** Forgets a spent round once the game no longer draws it. */
  retire(missile: Missile): void {
    const at = this.live.indexOf(missile);
    if (at >= 0) {
      this.live.splice(at, 1);
    }
  }
}
