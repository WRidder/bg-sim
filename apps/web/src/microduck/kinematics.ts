/**
 * Forward kinematics of the microduck, from the body tree of `kinematics/assets/alpha/robot_walk.xml`
 * in pollen-robotics/microduck: each body sits at `pos`, turned by `quat` (MuJoCo's w, x, y, z), in
 * its parent, and its hinge turns about its own z. Frames are MuJoCo's: x forward, y left, z up.
 * The MJCF carries no geometry and no mouth joint, so the drawing is ours (duck.ts) and the mouth
 * hinge is placed by eye on the head.
 */

import * as THREE from "three";
import { NUM_JOINTS } from "./robot";

export interface BodyDef {
  name: string;
  /** Index into `BODIES`, or -1 for the trunk. */
  parent: number;
  pos: readonly [number, number, number];
  /** w, x, y, z. */
  quat: readonly [number, number, number, number];
  /** Joint index (JOINT_NAMES) of the hinge at this body's origin, about its z; -1 for none. */
  joint: number;
}

const S = Math.SQRT1_2;

/** The tree, parents before children. Joint indices follow JOINT_NAMES. */
export const BODIES: readonly BodyDef[] = [
  { name: "trunk_base", parent: -1, pos: [0, 0, 0], quat: [1, 0, 0, 0], joint: -1 },
  { name: "yaw2roll", parent: 0, pos: [0.006, 0.0175, -0.005], quat: [0, -S, -S, 0], joint: 0 },
  { name: "hip_l", parent: 1, pos: [0, 0.0165, 0.0125], quat: [S, -S, 0, 0], joint: 1 },
  { name: "left_upper_leg", parent: 2, pos: [0.025, 0, -0.0185], quat: [0.5, -0.5, 0.5, -0.5], joint: 2 },
  { name: "leg", parent: 3, pos: [0.022, 0.0357771, -0.004], quat: [0, S, S, 0], joint: 3 },
  { name: "ankle_left", parent: 4, pos: [0, 0.042, -0.026], quat: [0, 1, 0, 0], joint: 4 },
  { name: "neck", parent: 0, pos: [0.026, 0.0145011, 0.0324424], quat: [0, 0, -S, S], joint: 5 },
  { name: "neck_pitch", parent: 6, pos: [0, -0.05, 0], quat: [0, 1, 0, 0], joint: 6 },
  { name: "yaw_roll_motion", parent: 7, pos: [0, 0.0186931, -0.0145], quat: [0, 0, -S, -S], joint: 7 },
  { name: "bottom_head_shell", parent: 8, pos: [-0.0179, 0, 0.0145], quat: [S, 0, -S, 0], joint: 8 },
  { name: "bearing_roll", parent: 0, pos: [0.006, -0.0175, -0.005], quat: [0, -S, -S, 0], joint: 10 },
  { name: "hip_l_2", parent: 10, pos: [0, 0.0165, 0.0125], quat: [0, 0, S, S], joint: 11 },
  { name: "right_upper_leg", parent: 11, pos: [0.025, 0, -0.0185], quat: [0.5, -0.5, 0.5, -0.5], joint: 12 },
  { name: "leg_2", parent: 12, pos: [-0.022, 0.0357771, -0.004], quat: [0, 1, 0, 0], joint: 13 },
  { name: "ankle_right", parent: 13, pos: [-0.042, 0, -0.026], quat: [0, -S, S, 0], joint: 14 },
];

export const TRUNK = 0;
export const LEFT_ANKLE = 5;
export const RIGHT_ANKLE = 14;
export const HEAD = 9;

/** Sites of the MJCF, in their body: the soles' centres, the beak's tip, the IMU. */
export const SITES = {
  leftFoot: { body: LEFT_ANKLE, pos: [0, -0.0237879, -0.0140852] as const },
  rightFoot: { body: RIGHT_ANKLE, pos: [0, 0.0237879, -0.0140852] as const },
  mouthTip: { body: HEAD, pos: [-0.00829334, 0, -0.0777383] as const },
  headCamera: { body: HEAD, pos: [0.01175, 0, -0.0735] as const },
  imu: { body: TRUNK, pos: [-0.021, 6.53121e-5, -0.0148911] as const },
};

/** The trunk's height over flat ground in the MJCF's spawn (`trunk_base pos="0 0 0.12"`). */
export const SPAWN_HEIGHT = 0.12;

export const bodyQuaternion = (b: BodyDef): THREE.Quaternion => new THREE.Quaternion(b.quat[1], b.quat[2], b.quat[3], b.quat[0]);

const Z = new THREE.Vector3(0, 0, 1);

/** Every body's pose in the trunk frame for joint angles `q`, reusing its own buffers. */
export class Kinematics {
  readonly position = BODIES.map(() => new THREE.Vector3());
  readonly orientation = BODIES.map(() => new THREE.Quaternion());
  private readonly fixed = BODIES.map(bodyQuaternion);
  private readonly turn = new THREE.Quaternion();
  private readonly offset = new THREE.Vector3();

  update(q: ArrayLike<number>): this {
    if (q.length < NUM_JOINTS) {
      throw new Error("Kinematics.update wants all 15 joints");
    }
    BODIES.forEach((body, i) => {
      if (body.parent < 0) {
        this.position[i].set(0, 0, 0);
        this.orientation[i].identity();
        return;
      }
      const parentPos = this.position[body.parent];
      const parentRot = this.orientation[body.parent];
      this.offset.set(body.pos[0], body.pos[1], body.pos[2]).applyQuaternion(parentRot);
      this.position[i].copy(parentPos).add(this.offset);
      this.orientation[i].copy(parentRot).multiply(this.fixed[i]);
      if (body.joint >= 0) {
        this.orientation[i].multiply(this.turn.setFromAxisAngle(Z, q[body.joint]));
      }
    });
    return this;
  }

  /** A site's position in the trunk frame, into `out`. */
  site(site: { body: number; pos: readonly [number, number, number] }, out: THREE.Vector3): THREE.Vector3 {
    return out.set(site.pos[0], site.pos[1], site.pos[2]).applyQuaternion(this.orientation[site.body]).add(this.position[site.body]);
  }
}
