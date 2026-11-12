/**
 * From a command and the sensors to joint targets, once a control tick: which network drives, the
 * observation, the action, the scaling and the low-pass. Re-implemented from `robotd/src/control.rs`
 * (`Controller::step`) and the command smoothing in `robotd/src/main.rs` of pollen-robotics/microduck
 * (Apache-2.0). The order matters and is theirs:
 *
 *   network  ← skill > ground pick > sit/rise > stand-by-magnitude > walk
 *   action   ← ONNX, on an observation whose previous action is the RAW last output
 *   targets  ← home + scale × action (the mouth skipped)
 *   filters  ← target = a·target + (1−a)·previous filtered target; a = 0.5 head, 0.7 legs;
 *              none on the first tick, so the filter starts from reality
 *
 * The ONNX session is behind `Brain`, so this file runs in a unit test with a fake.
 */

import { buildObservation, type Command, scatterAction, type Sensors, twistMagnitude, zeroCommand } from "./obs";
import {
  ACTION_LEN,
  CMD_ALPHA,
  CONTROL_DT,
  DEFAULT_POSITION,
  GROUND_PICK,
  HEAD_ALPHA,
  HEAD_JOINTS,
  LEG_JOINTS,
  NUM_JOINTS,
  OBS_LEN,
  SITSTAND,
  SKILLS,
  type SkillDef,
  STANDING_THRESHOLD,
  TUNING,
} from "./robot";

/** The networks by slot: `walk`, `stand`, `sitstand`, `ground_pick`, or a skill's name. */
export interface Brain {
  has(net: string): boolean;
  /** One inference. `fresh` says the network was not the one that ran last (recurrent memory resets). */
  infer(net: string, obs: Float32Array, fresh: boolean): Promise<Float32Array>;
}

export interface Tuning {
  actionScale: number;
  standingActionScale: number;
  headLowpass: number | null;
  legsLowpass: number | null;
  standingThreshold: number;
}

export const DEFAULT_TUNING: Tuning = {
  actionScale: TUNING.actionScale,
  standingActionScale: TUNING.standingActionScale,
  headLowpass: TUNING.headLowpass,
  legsLowpass: TUNING.legsLowpass,
  standingThreshold: STANDING_THRESHOLD,
};

type Sit = { kind: "up" } | { kind: "sitting" } | { kind: "rising"; remaining: number };

interface ActiveSkill {
  def: SkillDef;
  remaining: number;
  /** Seconds a held button still counts as held (`CHAIN_WINDOW`). */
  chain: number;
}

/** `control.rs` CHAIN_WINDOW: a request this recent at the end of a chaining skill starts another. */
const CHAIN_WINDOW = 0.15;

export interface Step {
  targets: Float64Array;
  /** Which network drove: walk, stand, sit, rise, ground_pick or a skill's name. */
  label: string;
  /** The raw action, 14 wide. */
  action: Float32Array;
  scale: number;
  /**
   * The servos' Position P Gain register for this tick, as `control.rs` picks it with the scale: the
   * walking gain, or 0.8 of it when the tick is standing-tuned (160). A plant that has a gain input
   * applies it; the robot writes it to every servo each tick.
   */
  gain: number;
  /** The command the network saw. */
  effective: Command;
}

/** Whether the standing network would be chosen (`policy.rs` will_stand). */
export function willStand(hasStanding: boolean, magnitude: number, threshold = STANDING_THRESHOLD): boolean {
  return hasStanding && magnitude <= threshold;
}

/** home + scale × scattered action; the mouth stays at home. */
export function scaleTargets(action: ArrayLike<number>, scale: number, home: readonly number[] = DEFAULT_POSITION): Float64Array {
  const offsets = scatterAction(action);
  const targets = new Float64Array(NUM_JOINTS);
  for (let j = 0; j < NUM_JOINTS; j += 1) {
    targets[j] = home[j] + scale * offsets[j];
  }
  return targets;
}

/** The trained low-pass, in place, against the previous filtered targets. */
export function lowPass(targets: Float64Array, previous: ArrayLike<number> | null, tuning: Pick<Tuning, "headLowpass" | "legsLowpass">): Float64Array {
  if (!previous) {
    return targets;
  }
  if (tuning.headLowpass !== null) {
    const a = tuning.headLowpass;
    for (const j of HEAD_JOINTS) {
      targets[j] = a * targets[j] + (1 - a) * previous[j];
    }
  }
  if (tuning.legsLowpass !== null) {
    const a = tuning.legsLowpass;
    for (const j of LEG_JOINTS) {
      targets[j] = a * targets[j] + (1 - a) * previous[j];
    }
  }
  return targets;
}

export class Controller {
  lastAction = new Float32Array(ACTION_LEN);
  previous: Float64Array | null = null;
  private sit: Sit = { kind: "up" };
  private sitSettle = 0;
  private groundPick: number | null = null;
  private active: ActiveSkill | null = null;
  private lastNet: string | null = null;
  private readonly obs = new Float32Array(OBS_LEN);

  constructor(
    private readonly brain: Brain,
    readonly tuning: Tuning = DEFAULT_TUNING,
    private readonly skills: readonly SkillDef[] = SKILLS,
  ) {}

  /** Back to a robot standing at home: the feedback state and every move forgotten. */
  reset(): void {
    this.lastAction.fill(0);
    this.previous = null;
    this.lastNet = null;
    this.sit = { kind: "up" };
    this.sitSettle = 0;
    this.groundPick = null;
    this.active = null;
  }

  get sitting(): boolean {
    return this.sit.kind === "sitting";
  }

  get busy(): boolean {
    return this.groundPick !== null || this.active !== null || this.sit.kind === "rising";
  }

  /** `control.rs` move_blocked: one move at a time, and none from the seat. */
  private blocked(): string | null {
    if (this.groundPick !== null) return "a ground pick is running";
    if (this.active) return "a move is already running";
    if (this.sit.kind === "sitting") return "sitting: stand up first";
    if (this.sit.kind === "rising") return "standing up";
    return null;
  }

  startGroundPick(): string | null {
    if (!this.brain.has("ground_pick")) return "no ground-pick policy loaded";
    const why = this.blocked();
    if (!why) this.groundPick = 0;
    return why;
  }

  /** Starts a skill, or keeps a running chaining one going (a held button). */
  startSkill(name: string): string | null {
    const def = this.skills.find((s) => s.name === name);
    if (!def || !this.brain.has(name)) return `no ${name} policy loaded`;
    if (this.active && this.active.def === def && def.chain) {
      this.active.chain = CHAIN_WINDOW;
      return null;
    }
    const why = this.blocked();
    if (!why) this.active = { def, remaining: def.duration, chain: 0 };
    return why;
  }

  sitToggle(): string | null {
    if (this.groundPick !== null) return "a ground pick is running";
    if (this.active) return "a move is already running";
    if (this.sit.kind === "up") {
      if (!this.brain.has("sitstand")) return "no sit-stand policy loaded";
      this.sit = { kind: "sitting" };
      this.sitSettle = SITSTAND.ramp;
      return null;
    }
    if (this.sit.kind === "sitting") {
      if (this.sitSettle > 0) return "still sitting down";
      this.sit = { kind: "rising", remaining: SITSTAND.rise };
      return null;
    }
    return "already standing up";
  }

  /**
   * One tick. `bodyActive` is body + head mode: the twist is zeroed and the standing network, where
   * there is one, drives.
   */
  async step(sensors: Sensors, command: Command, bodyActive = false, dt = CONTROL_DT): Promise<Step> {
    if (this.active && this.active.remaining <= 0) {
      const again = this.active.def.chain && this.active.chain > 0;
      this.active = again ? { def: this.active.def, remaining: this.active.def.duration, chain: 0 } : null;
      if (again) this.lastNet = null; // a chained replay is a new episode
    }
    if (this.sit.kind === "rising" && this.sit.remaining <= 0) {
      this.sit = { kind: "up" };
    }

    let net: string;
    let label: string;
    let effective: Command;
    if (this.active) {
      effective = zeroCommand();
      net = label = this.active.def.name;
    } else if (this.groundPick !== null) {
      const angle = 2 * Math.PI * this.groundPick;
      effective = { ...zeroCommand(), twist: [Math.cos(angle), Math.sin(angle), 0] };
      net = label = "ground_pick";
    } else {
      effective = { twist: [...command.twist], head: [...command.head], body: { ...command.body } };
      if (this.sit.kind === "sitting") {
        effective.twist = [1, 0, 0];
        net = "sitstand";
        label = "sit";
      } else if (this.sit.kind === "rising") {
        effective.twist = [0, 0, 0];
        net = "sitstand";
        label = "rise";
      } else {
        if (bodyActive) effective.twist = [0, 0, 0];
        const hasStanding = this.brain.has("stand");
        const standing = willStand(hasStanding, twistMagnitude(effective), this.tuning.standingThreshold) || (bodyActive && hasStanding);
        net = label = standing ? "stand" : "walk";
      }
    }

    const fresh = net !== this.lastNet;
    this.lastNet = net;
    buildObservation(sensors, DEFAULT_POSITION, this.lastAction, effective, this.obs);
    const action = await this.brain.infer(net, this.obs, fresh);
    if (action.length !== ACTION_LEN || !action.every(Number.isFinite)) {
      throw new Error(`the ${net} policy returned ${action.length} values, not 14 finite ones`);
    }
    this.lastAction = Float32Array.from(action);

    const standingTuned =
      net === "stand" || ((this.active !== null || net === "sitstand") && willStand(this.brain.has("stand"), twistMagnitude(effective), this.tuning.standingThreshold));
    let scale: number;
    if (net === "ground_pick") scale = GROUND_PICK.actionScale;
    else if (net === "sitstand") scale = 1.0;
    else scale = standingTuned ? this.tuning.standingActionScale : this.tuning.actionScale;
    const ratio = net === "ground_pick" ? TUNING.groundPickGainRatio : standingTuned ? TUNING.standingGainRatio : 1.0;
    const gain = Math.round(TUNING.gain * ratio);

    const targets = lowPass(scaleTargets(action, scale), this.previous, this.tuning);
    this.previous = Float64Array.from(targets);

    if (this.groundPick !== null) {
      this.groundPick += dt / GROUND_PICK.period;
      if (this.groundPick >= GROUND_PICK.endPhase) this.groundPick = null;
    }
    if (this.active) {
      this.active.remaining -= dt;
      this.active.chain = Math.max(0, this.active.chain - dt);
    }
    if (this.sit.kind === "rising") this.sit.remaining -= dt;
    this.sitSettle = Math.max(0, this.sitSettle - dt);

    return { targets, label, action: this.lastAction, scale, gain, effective };
  }
}

/**
 * The per-tick EMAs `robotd` puts between a client and the policy (`main.rs`, `slew`):
 * `ema += α (target − ema)`, α 0.2 on the twist and on the head, and on the body pose while body
 * mode holds it; out of body mode the body snaps back to nominal.
 */
export class CommandFilter {
  readonly value: Command = zeroCommand();

  constructor(
    private readonly cmdAlpha = CMD_ALPHA,
    private readonly headAlpha = HEAD_ALPHA,
  ) {}

  reset(): void {
    Object.assign(this.value, zeroCommand());
  }

  update(target: Command, bodyActive: boolean): Command {
    const v = this.value;
    for (let i = 0; i < 3; i += 1) v.twist[i] += this.cmdAlpha * (target.twist[i] - v.twist[i]);
    for (let i = 0; i < 4; i += 1) v.head[i] += this.headAlpha * (target.head[i] - v.head[i]);
    if (bodyActive) {
      v.body.z += this.cmdAlpha * (target.body.z - v.body.z);
      v.body.roll += this.cmdAlpha * (target.body.roll - v.body.roll);
      v.body.pitch += this.cmdAlpha * (target.body.pitch - v.body.pitch);
    } else {
      v.body = { z: 0, roll: 0, pitch: 0 };
    }
    return v;
  }
}
