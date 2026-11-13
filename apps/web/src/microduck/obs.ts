/**
 * The observation the policies see, re-implemented from `duck-control/src/obs.rs` in
 * pollen-robotics/microduck (Apache-2.0). 61 float32:
 *
 *   0..3    gyro, trunk frame, rad/s
 *   3..6    projected gravity, trunk frame, unit vector (upright is 0, 0, −1)
 *   6..20   joint position minus home pose, mouth excluded
 *   20..34  joint velocity, mouth excluded
 *   34..48  previous action: the raw policy output, before scaling
 *   48..61  command: vx, vy, vyaw, neck_pitch, head_pitch, head_yaw, head_roll,
 *           body x (0), body y (0), body z, body roll, body pitch, body yaw (0)
 *
 * The body block is z, roll, pitch; x, y and yaw are unbound in training and always zero. Head
 * targets ride in the command and are never added to the policy's output.
 */

import { ACTION_LEN, COMMAND_LEN, MOUTH_INDEX, NUM_JOINTS, OBS_LEN } from "./robot";

export interface BodyPose {
  z: number;
  roll: number;
  pitch: number;
}

/** What is asked of the robot, in physical units in the trunk frame. */
export interface Command {
  /** Forward m/s, left m/s, yaw rate rad/s (counter-clockwise from above). */
  twist: [number, number, number];
  /** neck_pitch, head_pitch, head_yaw, head_roll. */
  head: [number, number, number, number];
  body: BodyPose;
}

export const zeroCommand = (): Command => ({ twist: [0, 0, 0], head: [0, 0, 0, 0], body: { z: 0, roll: 0, pitch: 0 } });

/** What selects walking against standing: the twist alone, never the head or the body. */
export const twistMagnitude = (c: Command): number => Math.hypot(c.twist[0], c.twist[1], c.twist[2]);

export interface Sensors {
  gyro: ArrayLike<number>;
  gravity: ArrayLike<number>;
  /** All 15 joints, absolute, rad. */
  positions: ArrayLike<number>;
  /** All 15 joints, rad/s. */
  velocities: ArrayLike<number>;
}

/** The joint a policy slot refers to: below the mouth straight through, at and above shifted by one. */
export const jointOf = (slot: number): number => (slot < MOUTH_INDEX ? slot : slot + 1);

/** The 14 policy slots of a 15-joint vector. */
export function policyJoints(values: ArrayLike<number>): Float64Array {
  const out = new Float64Array(ACTION_LEN);
  for (let slot = 0; slot < ACTION_LEN; slot += 1) {
    out[slot] = values[jointOf(slot)];
  }
  return out;
}

/** 14 actions onto 15 joints, the mouth left at zero. */
export function scatterAction(action: ArrayLike<number>): Float64Array {
  const out = new Float64Array(NUM_JOINTS);
  for (let slot = 0; slot < ACTION_LEN; slot += 1) {
    out[jointOf(slot)] = action[slot];
  }
  return out;
}

/** The inverse of `scatterAction`. */
export function gatherAction(values: ArrayLike<number>): Float32Array {
  return Float32Array.from(policyJoints(values));
}

export function buildObservation(
  sensors: Sensors,
  home: ArrayLike<number>,
  lastAction: ArrayLike<number>,
  command: Command,
  out: Float32Array = new Float32Array(OBS_LEN),
): Float32Array {
  if (out.length !== OBS_LEN || lastAction.length !== ACTION_LEN) {
    throw new Error("observation or action of the wrong width");
  }
  out[0] = sensors.gyro[0];
  out[1] = sensors.gyro[1];
  out[2] = sensors.gyro[2];
  out[3] = sensors.gravity[0];
  out[4] = sensors.gravity[1];
  out[5] = sensors.gravity[2];
  for (let slot = 0; slot < ACTION_LEN; slot += 1) {
    const joint = jointOf(slot);
    out[6 + slot] = sensors.positions[joint] - home[joint];
    out[20 + slot] = sensors.velocities[joint];
    out[34 + slot] = lastAction[slot];
  }
  const c = 48;
  const block = [
    command.twist[0],
    command.twist[1],
    command.twist[2],
    command.head[0],
    command.head[1],
    command.head[2],
    command.head[3],
    0, // body x: unbound in training
    0, // body y: unbound
    command.body.z,
    command.body.roll,
    command.body.pitch,
    0, // body yaw: unbound
  ];
  for (let i = 0; i < COMMAND_LEN; i += 1) {
    out[c + i] = block[i];
  }
  return out;
}
