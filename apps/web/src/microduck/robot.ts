/**
 * The microduck as data: its joints, its home pose, the limits a pad asks for and the tuning the
 * published policies were trained with. Every number here is lifted from pollen-robotics/microduck
 * (Apache-2.0), file named beside it; the policy silently stops working if any one of them drifts.
 */

/** `duck-ipc-proto/src/lib.rs` JOINT_NAMES: left leg (5), neck/head/mouth (5), right leg (5). */
export const JOINT_NAMES = [
  "left_hip_yaw",
  "left_hip_roll",
  "left_hip_pitch",
  "left_knee",
  "left_ankle",
  "neck_pitch",
  "head_pitch",
  "head_yaw",
  "head_roll",
  "mouth",
  "right_hip_yaw",
  "right_hip_roll",
  "right_hip_pitch",
  "right_knee",
  "right_ankle",
] as const;

export type JointName = (typeof JOINT_NAMES)[number];
export const NUM_JOINTS = 15;

/** `duck-control/src/model.rs` MOUTH_INDEX: absent from every policy, on both sides. */
export const MOUTH_INDEX = 9;

/** `duck-control/src/obs.rs`: 61 in, 14 out, the mouth skipped. */
export const OBS_LEN = 61;
export const ACTION_LEN = 14;
export const COMMAND_LEN = 13;

/** `duck-control/src/model.rs` DEFAULT_POSITION, rad: the pose the policies observe joints against. */
export const DEFAULT_POSITION: readonly number[] = [
  0.0, // left_hip_yaw
  -0.0873, // left_hip_roll
  -0.4579, // left_hip_pitch
  -0.0049, // left_knee
  0.453, // left_ankle
  0.3491, // neck_pitch
  0.3491, // head_pitch
  0.0, // head_yaw
  0.0, // head_roll
  0.0, // mouth
  0.0, // right_hip_yaw
  0.0873, // right_hip_roll
  0.4579, // right_hip_pitch
  0.0049, // right_knee
  -0.453, // right_ankle
];

/** `robotd/src/control.rs` HEAD_JOINTS: neck_pitch, head_pitch, head_yaw, head_roll. */
export const HEAD_JOINTS = [5, 6, 7, 8] as const;
/** The ten leg joints: every joint but the head four and the mouth. */
export const LEG_JOINTS = [0, 1, 2, 3, 4, 10, 11, 12, 13, 14] as const;

/** `duck-control/src/model.rs` MOUTH_CLOSED / MOUTH_OPEN and `mouth_target`. */
export const MOUTH_CLOSED = (-5 * Math.PI) / 180;
export const MOUTH_OPEN = (30 * Math.PI) / 180;
export function mouthTarget(open: number): number {
  const o = Number.isFinite(open) ? Math.min(1, Math.max(0, open)) : 0;
  return MOUTH_CLOSED + o * (MOUTH_OPEN - MOUTH_CLOSED);
}

/** `robotd/src/control.rs` Tuning::default: the prototype's alpha configuration. */
export const TUNING = {
  actionScale: 0.9,
  standingActionScale: 1.0,
  /** The servos' Position P Gain register while walking; standing runs at `standingGainRatio` of it (160). */
  gain: 200,
  standingGainRatio: 0.8,
  /** `SkillsConfig::ground_pick_gain_ratio`. */
  groundPickGainRatio: 1.0,
  /** Low-pass `target = a·target + (1−a)·previous`, a per group; "must match training". */
  headLowpass: 0.5,
  legsLowpass: 0.7,
} as const;

/** `duck-control/src/policy.rs` DEFAULT_STANDING_THRESHOLD, on the twist magnitude. */
export const STANDING_THRESHOLD = 0.05;

/** `robotd-params/src/lib.rs` Control::default: 50 Hz, and per-tick EMAs on the command. */
export const CONTROL_HZ = 50;
export const CONTROL_DT = 1 / CONTROL_HZ;
export const CMD_ALPHA = 0.2;
export const HEAD_ALPHA = 0.2;

/** `robotd-params/src/lib.rs` PadDriveParams::default: what full stick asks for while walking. */
export const DRIVE_LIMITS = {
  vxMin: -0.3,
  vxMax: 0.4,
  vyMin: -0.3,
  vyMax: 0.3,
  vyawMin: -1.0,
  vyawMax: 1.0,
} as const;

/** `robotd-params/src/lib.rs` PadHeadParams::default: full-deflection head command per joint. */
export const HEAD_LIMITS = { neckPitch: 2.5, headPitch: 2.5, headYaw: 2.5, headRoll: 2.5 } as const;

/** `robotd-params/src/lib.rs` PadBodyParams::default: body + head mode's height and tilt. */
export const BODY_LIMITS = { zMin: -0.025, zMax: 0.01, pitchMax: 0.2618, rollMax: 0.2618 } as const;

/** `robotd-params/src/pad_axes.rs` PadAxesParams::default. */
export const PAD_DEADZONE = 0.1;

/**
 * One-shot skills, from the policy set's `manifest.json` (and `robotd-params` builtin_skills): a
 * constant zero twist for `duration` seconds, head and body zeroed. `chain`: a held button
 * starts another when one ends. None of these carries its own action scale in the manifest.
 */
export interface SkillDef {
  name: string;
  file: string;
  duration: number;
  chain: boolean;
}

export const SKILLS: readonly SkillDef[] = [
  { name: "roulade", file: "roulade.onnx", duration: 1.0, chain: true },
  { name: "kick_left", file: "ball_kick_left.onnx", duration: 0.5, chain: false },
  { name: "kick_right", file: "ball_kick_right.onnx", duration: 0.5, chain: false },
];

/** The manifest's ground pick: phase-encoded, `period_s` 4, `end_phase` 0.7; scale 1.0 (control.rs). */
export const GROUND_PICK = { file: "alpha_ground_pick.onnx", period: 4.0, endPhase: 0.7, actionScale: 1.0 } as const;

/** The manifest's sit↔stand: posture flag on twist.vx (1 sit, 0 stand), `ramp_s` 2, `unwind_s` (the rise) 1. */
export const SITSTAND = { file: "alpha_sitstand.onnx", ramp: 2.0, rise: 1.0 } as const;

/** The walk slot's default since set v5 (`robotd-params` resolved_with, Mode::Walk). No standing net. */
export const WALK_FILE = "velstand.onnx";

/** Joint ranges, rad, from `kinematics/assets/alpha/robot_walk.xml`; the mouth from MOUTH_*. */
export const JOINT_RANGE: readonly (readonly [number, number])[] = [
  [-0.4363, 0.5236],
  [-0.384, 0.384],
  [-1.5708, 1.5708],
  [-1.5708, 1.5708],
  [-1.5708, 1.5708],
  [-1.5708, 1.0472],
  [-1.5708, 1.5708],
  [-2.9671, 2.9671],
  [-0.4363, 0.4363],
  [MOUTH_CLOSED, MOUTH_OPEN],
  [-0.5236, 0.4363],
  [-0.384, 0.384],
  [-1.5708, 1.5708],
  [-1.5708, 1.5708],
  [-1.5708, 1.5708],
];
