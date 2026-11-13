/**
 * What the policy drives. One interface, two implementations: the bg-sim model as an FMU
 * (fmuPlant.ts, once the model exports one), and the stand-in below, which exists only so the loop
 * pad → command → observation → policy → targets → plant → picture runs today.
 *
 * Frames are MuJoCo's, as the policy's: world x forward at the start, y left, z up; the trunk frame
 * x forward, y left, z up, with its origin at the MJCF's `trunk_base`.
 */

import * as THREE from "three";
import { Kinematics, SITES } from "./kinematics";
import { DEFAULT_POSITION, JOINT_RANGE, NUM_JOINTS } from "./robot";

export interface PlantState {
  /** Joint positions, all 15, rad. */
  q: Float64Array;
  /** Joint velocities, all 15, rad/s. */
  qd: Float64Array;
  /** Trunk angular velocity in the trunk frame, rad/s. */
  gyro: Float64Array;
  /** Gravity's direction in the trunk frame, unit vector; upright is (0, 0, −1). */
  gravity: Float64Array;
  /** Trunk origin in the world, m. */
  position: Float64Array;
  /** Trunk → world, w x y z. */
  quaternion: Float64Array;
  /** Foot contact, left and right, 0..1, or null when the plant does not say. */
  contact: Float64Array | null;
  time: number;
}

/** A plant that stopped: the step that failed (plant time, s) and what the plant reported. */
export interface PlantStop {
  /** Plant time at the start of the step that did not complete (the last good state), s. */
  from: number;
  /** Plant time the step was to reach, s. */
  to: number;
  reason: string;
}

/** One line for the HUD and the logs: "stopped in the step from 0.700 s to 0.720 s: …". */
export const describeStop = (stop: PlantStop): string =>
  `stopped in the step from ${stop.from.toFixed(3)} s to ${stop.to.toFixed(3)} s: ${stop.reason}`;

export interface Plant {
  readonly kind: "fmu" | "stand-in";
  /** What the HUD calls it. */
  readonly label: string;
  readonly state: PlantState;
  /** False once the plant cannot go on (an FMU that stopped). */
  readonly healthy: boolean;
  /** Why and when it stopped, while `healthy` is false (null otherwise, or when the plant cannot say). */
  readonly stop?: PlantStop | null;
  reset(): void;
  /**
   * Holds `targets` (15 joints, rad) for `dt` seconds of plant time and advances. `gain` is the servos'
   * Position P Gain register for the tick (200 walking, 160 standing); a plant without a gain ignores it.
   */
  step(targets: ArrayLike<number>, dt: number, gain?: number): void;
}

export const emptyState = (): PlantState => ({
  q: Float64Array.from(DEFAULT_POSITION),
  qd: new Float64Array(NUM_JOINTS),
  gyro: new Float64Array(3),
  gravity: Float64Array.of(0, 0, -1),
  position: new Float64Array(3),
  quaternion: Float64Array.of(1, 0, 0, 0),
  contact: null,
  time: 0,
});

/** Gravity in the trunk frame from trunk → world `w x y z`: R⁻¹ (0, 0, −1). */
export function projectedGravity(q: ArrayLike<number>, out: Float64Array = new Float64Array(3)): Float64Array {
  const v = new THREE.Vector3(0, 0, -1).applyQuaternion(new THREE.Quaternion(q[1], q[2], q[3], q[0]).normalize().invert());
  out[0] = v.x;
  out[1] = v.y;
  out[2] = v.z;
  return out;
}

/** How the stand-in carries the trunk. */
export type Carry = "foot" | "command";

/**
 * NOT a simulation. Each joint follows its target through a first-order lag with a speed limit. The
 * trunk is carried kinematically and kept level: either it moves at the commanded twist ("command",
 * the default), or the stance foot (the lower one) stays where it is on the ground and the trunk
 * moves round it ("foot"). Its height is whatever puts the lower sole on the ground. There is no
 * mass, no contact force, no balance: the duck cannot fall over, the gyro reads only the yaw rate,
 * and gravity always reads (0, 0, −1).
 *
 * What velstand.onnx does on it (tests/microduck.test.ts and a sweep while writing this): with a lag
 * of 25 ms the policy flails even at zero command (joints up to 0.97 rad off home); from about 40 ms
 * it stands calmly (0.15 rad) and steps under any stick command, so 60 ms it is. In "foot" mode
 * those steps do not carry the trunk where the stick asks, at any lag tried (40 to 120 ms): without
 * a body that tilts and a gyro that reads it, the policy is far outside what it was trained on.
 * That is what the FMU is for.
 */
export class StandInPlant implements Plant {
  readonly kind = "stand-in";
  readonly label = "Stand-in plant, not the bg-sim model";
  readonly state = emptyState();
  readonly healthy = true;
  carry: Carry = "command";
  /** The twist the trunk follows when `carry` is "command": forward, left, yaw rate. */
  readonly twist = new Float64Array(3);
  tau = 0.06;
  maxSpeed = 8;
  private readonly kin = new Kinematics();
  private readonly feet = [new THREE.Vector3(), new THREE.Vector3()];
  private readonly footYaw = [0, 0];
  private stance = 0;
  private anchor = new THREE.Vector3();
  private anchorYaw = 0;
  private yaw = 0;
  private readonly previousQ = new Float64Array(NUM_JOINTS);

  constructor() {
    this.reset();
  }

  reset(): void {
    const s = this.state;
    s.q.set(DEFAULT_POSITION);
    s.qd.fill(0);
    s.gyro.fill(0);
    s.gravity.set([0, 0, -1]);
    s.position.fill(0);
    s.time = 0;
    this.yaw = 0;
    this.twist.fill(0);
    this.measureFeet();
    s.position[2] = -Math.min(this.feet[0].z, this.feet[1].z);
    this.stance = this.feet[0].z <= this.feet[1].z ? 0 : 1;
    this.pin();
    this.write();
  }

  private measureFeet(): void {
    this.kin.update(this.state.q);
    this.kin.site(SITES.leftFoot, this.feet[0]);
    this.kin.site(SITES.rightFoot, this.feet[1]);
    // A foot's heading in the trunk frame is its hip yaw: both hip-yaw axes point down (−z) in
    // the trunk at home, so a positive angle turns the foot clockwise seen from above.
    this.footYaw[0] = -this.state.q[0];
    this.footYaw[1] = -this.state.q[10];
  }

  /** The stance foot's world position and heading, from the trunk's pose now. */
  private pin(): void {
    const s = this.state;
    const f = this.feet[this.stance];
    const c = Math.cos(this.yaw);
    const n = Math.sin(this.yaw);
    this.anchor.set(s.position[0] + c * f.x - n * f.y, s.position[1] + n * f.x + c * f.y, 0);
    this.anchorYaw = this.yaw + this.footYaw[this.stance];
  }

  step(targets: ArrayLike<number>, dt: number): void {
    const s = this.state;
    this.previousQ.set(s.q);
    const sub = 4;
    const h = dt / sub;
    for (let k = 0; k < sub; k += 1) {
      for (let j = 0; j < NUM_JOINTS; j += 1) {
        const [lo, hi] = JOINT_RANGE[j];
        const want = Math.min(hi, Math.max(lo, targets[j]));
        const speed = Math.max(-this.maxSpeed, Math.min(this.maxSpeed, (want - s.q[j]) / this.tau));
        s.q[j] += speed * h;
      }
    }
    for (let j = 0; j < NUM_JOINTS; j += 1) {
      s.qd[j] = (s.q[j] - this.previousQ[j]) / dt;
    }
    const yawBefore = this.yaw;
    this.measureFeet();
    if (this.carry === "command") {
      const c = Math.cos(this.yaw);
      const n = Math.sin(this.yaw);
      s.position[0] += (c * this.twist[0] - n * this.twist[1]) * dt;
      s.position[1] += (n * this.twist[0] + c * this.twist[1]) * dt;
      this.yaw += this.twist[2] * dt;
      this.stance = this.feet[0].z <= this.feet[1].z ? 0 : 1;
    } else {
      // The stance foot neither slides nor turns: the trunk goes round it.
      this.yaw = this.anchorYaw - this.footYaw[this.stance];
      const f = this.feet[this.stance];
      const c = Math.cos(this.yaw);
      const n = Math.sin(this.yaw);
      s.position[0] = this.anchor.x - (c * f.x - n * f.y);
      s.position[1] = this.anchor.y - (n * f.x + c * f.y);
      // The other foot takes over once it is a millimetre lower: a step.
      const other = 1 - this.stance;
      if (this.feet[other].z < this.feet[this.stance].z - 0.001) {
        this.stance = other;
      }
    }
    this.pin();
    s.position[2] = -Math.min(this.feet[0].z, this.feet[1].z);
    s.gyro[0] = 0;
    s.gyro[1] = 0;
    s.gyro[2] = (this.yaw - yawBefore) / dt;
    s.time += dt;
    this.write();
  }

  private write(): void {
    const s = this.state;
    s.quaternion.set([Math.cos(this.yaw / 2), 0, 0, Math.sin(this.yaw / 2)]);
    s.gravity.set([0, 0, -1]);
    const ground = -s.position[2];
    s.contact = Float64Array.of(this.feet[0].z - ground < 0.002 ? 1 : 0, this.feet[1].z - ground < 0.002 ? 1 : 0);
  }

  /** Changes how the trunk is carried, from where it is now. */
  setCarry(carry: Carry): void {
    this.carry = carry;
    this.measureFeet();
    this.stance = this.feet[0].z <= this.feet[1].z ? 0 : 1;
    this.pin();
  }

  /** Which foot holds the ground, for the drawing: 0 left, 1 right. */
  get stanceFoot(): number {
    return this.stance;
  }
}
