/**
 * One control tick, as the robot runs it at 50 Hz: the pad's command through `robotd`'s smoothing,
 * the observation from the plant's sensors, the policy, the targets, and the plant held at those
 * targets for 20 ms. No DOM here, so the whole loop runs in a test.
 */

import { CommandFilter, type Controller, type Step } from "./controller";
import type { Sensors } from "./obs";
import type { StickCommand } from "./pad";
import type { Plant } from "./plant";
import { CONTROL_DT, DEFAULT_POSITION, MOUTH_INDEX, mouthTarget, NUM_JOINTS, TUNING } from "./robot";

export interface Tick {
  /** Which network drove, "off" with the policy off, or "stopped" once the plant has stopped. */
  label: string;
  targets: Float64Array;
  /** The servos' P gain register for the tick (the robot's running gain when the policy is off). */
  gain: number;
  step: Step | null;
}

export const sensorsOf = (plant: Plant, velocities: ArrayLike<number> = plant.state.qd): Sensors => ({
  gyro: plant.state.gyro,
  gravity: plant.state.gravity,
  positions: plant.state.q,
  velocities,
});

/**
 * How many control ticks old the joint velocities the policy reads are. Training feeds them one
 * tick late (microduck_rl `microduck_velocity_env_cfg.py`: `joint_vel` with `delay_min_lag =
 * delay_max_lag = 1`, "the Dynamixel firmware computes present_velocity via a moving-average over
 * the previous position-sample window"), and mjlab's delay buffer returns the current value until
 * it holds enough ticks. The real robot needs no lag added: its servos report the old value.
 */
export const TRAINING_VELOCITY_LAG = 1;

export class DuckLoop {
  /** Off, the joints go to the home pose and hold, as the robot does when its policy is toggled off. */
  enabled = true;
  readonly filter = new CommandFilter();
  /** The trunk's measured twist, forward, left (in the heading frame), yaw rate; smoothed over ~0.3 s. */
  readonly actual = new Float64Array(3);
  /** The previous tick's plant pose, for drawing between ticks. */
  readonly before = { q: Float64Array.from(DEFAULT_POSITION), position: new Float64Array(3), quaternion: Float64Array.of(1, 0, 0, 0) };
  ticks = 0;
  lastTick: Tick | null = null;
  /** The joint velocities of the last `velocityLag` ticks, oldest first (what the policy reads). */
  private readonly pastVelocities: Float64Array[] = [];

  /**
   * @param velocityLag joint-velocity lag in control ticks (`TRAINING_VELOCITY_LAG` by default, as
   *   velstand was trained; 0 feeds the plant's present velocities).
   */
  constructor(
    public plant: Plant,
    readonly controller: Controller,
    readonly velocityLag: number = TRAINING_VELOCITY_LAG,
  ) {}

  reset(): void {
    this.plant.reset();
    this.controller.reset();
    this.filter.reset();
    this.actual.fill(0);
    this.keep();
    this.ticks = 0;
    this.pastVelocities.length = 0;
  }

  /** The velocities the policy reads this tick, and this tick's into the lag line. */
  private observedVelocities(): ArrayLike<number> {
    const now = Float64Array.from(this.plant.state.qd);
    if (this.velocityLag <= 0) return now;
    this.pastVelocities.push(now);
    // mjlab clamps the lag while its buffer fills: the oldest value it has
    const seen = this.pastVelocities.length > this.velocityLag ? this.pastVelocities.shift()! : this.pastVelocities[0];
    return seen;
  }

  setEnabled(on: boolean): void {
    if (on && !this.enabled) {
      // As the robot re-enables: no stale action in the observation, no filter anchored elsewhere.
      this.controller.reset();
      this.filter.reset();
    }
    this.enabled = on;
  }

  private keep(): void {
    const s = this.plant.state;
    this.before.q.set(s.q);
    this.before.position.set(s.position);
    this.before.quaternion.set(s.quaternion);
  }

  async tick(asked: StickCommand, mouth: number): Promise<Tick> {
    const dt = CONTROL_DT;
    let tick: Tick;
    if (!this.plant.healthy) {
      // A stopped plant's state is frozen at its last good step: the policy is not fed a state
      // that no longer changes, and nothing is stepped until `reset`.
      tick = { label: "stopped", targets: Float64Array.from(this.plant.state.q), gain: this.lastTick?.gain ?? TUNING.gain, step: null };
      this.lastTick = tick;
      return tick;
    }
    const velocities = this.observedVelocities();
    if (this.enabled) {
      const command = this.filter.update(asked.command, asked.bodyActive);
      const step = await this.controller.step(sensorsOf(this.plant, velocities), command, asked.bodyActive, dt);
      tick = { label: step.label, targets: step.targets, gain: step.gain, step };
      // Only a gait's twist is a speed: the sit-stand flag and the ground pick's phase ride in the
      // same slots, and a skill's is zero.
      const gait = step.label === "walk" || step.label === "stand";
      const stand = this.plant as Plant & { twist?: Float64Array };
      stand.twist?.set(gait ? step.effective.twist : [0, 0, 0]);
    } else {
      tick = { label: "off", targets: Float64Array.from(DEFAULT_POSITION), gain: TUNING.gain, step: null };
      (this.plant as Plant & { twist?: Float64Array }).twist?.fill(0);
    }
    tick.targets[MOUTH_INDEX] = mouthTarget(mouth);
    this.keep();
    this.plant.step(tick.targets, dt, tick.gain);
    this.measure(dt);
    this.ticks += 1;
    this.lastTick = tick;
    return tick;
  }

  private measure(dt: number): void {
    const s = this.plant.state;
    const [w, x, y, z] = s.quaternion;
    const yaw = Math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z));
    const dx = (s.position[0] - this.before.position[0]) / dt;
    const dy = (s.position[1] - this.before.position[1]) / dt;
    const c = Math.cos(yaw);
    const n = Math.sin(yaw);
    const a = 1 - Math.exp(-dt / 0.3);
    const now = [c * dx + n * dy, -n * dx + c * dy, s.gyro[2]];
    for (let i = 0; i < 3; i += 1) {
      this.actual[i] += a * (now[i] - this.actual[i]);
    }
  }

  /** Joint angles between the last two ticks, for drawing. */
  drawnJoints(fraction: number, out: Float64Array): Float64Array {
    const q = this.plant.state.q;
    for (let j = 0; j < NUM_JOINTS; j += 1) {
      out[j] = this.before.q[j] + (q[j] - this.before.q[j]) * fraction;
    }
    return out;
  }
}
