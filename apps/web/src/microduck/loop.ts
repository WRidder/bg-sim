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

export const sensorsOf = (plant: Plant): Sensors => ({
  gyro: plant.state.gyro,
  gravity: plant.state.gravity,
  positions: plant.state.q,
  velocities: plant.state.qd,
});

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

  constructor(
    public plant: Plant,
    readonly controller: Controller,
  ) {}

  reset(): void {
    this.plant.reset();
    this.controller.reset();
    this.filter.reset();
    this.actual.fill(0);
    this.keep();
    this.ticks = 0;
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
    if (this.enabled) {
      const command = this.filter.update(asked.command, asked.bodyActive);
      const step = await this.controller.step(sensorsOf(this.plant), command, asked.bodyActive, dt);
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
