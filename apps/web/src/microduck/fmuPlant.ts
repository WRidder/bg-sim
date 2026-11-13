/**
 * The microduck as the bg-sim model exports it: an FMU compiled to WebAssembly by `build_wasm.py`
 * into `src/microduck/model.gen.ts`, driven on its own step by `engine/sim.ts`, one control period
 * (20 ms) at a time. Wiring a new export is filling in `FMU_INTERFACE` with the export's variable
 * names and running `uv run build_wasm.py microduck <the .fmu>`; nothing else in the app knows a name.
 *
 * The model is `examples/microduck/models/microduck-policy`, exported by `examples/export_microduck.jl`
 * (14 `<joint>_target` and `kp` in; joints, trunk sensors and sole loads out; no mouth joint).
 * Without a `model.gen.ts` (it is generated and gitignored) the page says so and runs the stand-in
 * plant instead.
 */

import type { FmuModel } from "../engine/fmu";
import { Fmu } from "../engine/fmu";
import { Sim } from "../engine/sim";
import { emptyState, type Plant, type PlantState, type PlantStop, projectedGravity } from "./plant";
import { DEFAULT_POSITION, JOINT_NAMES, MOUTH_INDEX, NUM_JOINTS, TUNING } from "./robot";

/**
 * THE mapping table: every FMU variable the app reads or writes, by role. Units SI (rad, rad/s, m),
 * frames MuJoCo's (world and trunk: x forward, y left, z up), quaternion trunk → world, w first.
 * `optional` roles may be missing from the export; the app then works them out or goes without.
 */
export const FMU_INTERFACE = {
  /** Inputs, rad: position targets, held for the 20 ms between control ticks. */
  targets: JOINT_NAMES.map((j) => `${j}_target`),
  /** Outputs, rad and rad/s. */
  positions: JOINT_NAMES.map((j) => `${j}_q`),
  velocities: JOINT_NAMES.map((j) => `${j}_qd`),
  /** Trunk angular velocity in the trunk frame (what the IMU's gyro reads), rad/s. */
  gyro: ["trunk_wx", "trunk_wy", "trunk_wz"],
  /** Trunk orientation, trunk → world, w x y z. */
  quaternion: ["trunk_qw", "trunk_qx", "trunk_qy", "trunk_qz"],
  /** Trunk origin (the MJCF's trunk_base) in the world, m. */
  position: ["trunk_x", "trunk_y", "trunk_z"],
  optional: {
    /** Input: the servos' Position P Gain register (200 walking, 160 standing), set every tick. */
    gain: "kp",
    /** Gravity's direction in the trunk frame; worked out from the quaternion when absent. */
    gravity: ["gravity_x", "gravity_y", "gravity_z"],
    /** Foot contact, 0 or 1, or a normal force in N (touching above `CONTACT_FORCE_N`), left and right. */
    contact: ["left_foot_contact", "right_foot_contact"],
  },
} as const;

/**
 * A sole touches above this normal force, N (0.7 % of the robot's 7.2 N weight). The model's contact
 * is smooth: a lifted sole still reports about 1e-15 N, so "above 0" never saw a foot leave the floor.
 */
export const CONTACT_FORCE_N = 0.05;

/** The mouth is in no policy, so a model without a mouth joint may leave its three variables out. */
const MOUTH_VARIABLES = new Set([FMU_INTERFACE.targets[MOUTH_INDEX], FMU_INTERFACE.positions[MOUTH_INDEX], FMU_INTERFACE.velocities[MOUTH_INDEX]]);

/** What an export lacks, as variable names: required roles only; empty means it fits. */
export function missingVariables(refs: Record<string, number>): string[] {
  return [
    ...FMU_INTERFACE.targets,
    ...FMU_INTERFACE.positions,
    ...FMU_INTERFACE.velocities,
    ...FMU_INTERFACE.gyro,
    ...FMU_INTERFACE.quaternion,
    ...FMU_INTERFACE.position,
  ].filter((name) => !MOUTH_VARIABLES.has(name) && !(name in refs));
}

/**
 * What an `fmi2DoStep` status means for this page. The Wasm shim drops the FMU's log messages, so the
 * status is all the page learns; `examples/export_microduck_check.py` and fmpy show the message.
 */
export function stopReason(status: number): string {
  switch (status) {
    case 0:
      return "an output is no longer a finite number";
    case 1:
      return "the FMU returned a warning (fmi2Warning), and the page stops on anything but OK";
    case 2:
      return "the model stopped itself (fmi2Discard: a stop block, or a check after the step)";
    case 3:
      return "the FMU's solver could not complete the step (fmi2Error)";
    default:
      return `the FMU failed (fmi2 status ${status})`;
  }
}

/** The generated model, if `build_wasm.py microduck …` has been run; null otherwise. */
export async function findModel(): Promise<FmuModel | null> {
  // A glob, not an import: a missing file is an empty match instead of a build error.
  const found = import.meta.glob<{ model: FmuModel }>("./model.gen.ts");
  const load = found["./model.gen.ts"];
  return load ? (await load()).model : null;
}

export class FmuPlant extends Sim<string> implements Plant {
  readonly kind = "fmu";
  readonly label: string;
  readonly state: PlantState = emptyState();
  private readonly outputs: string[];
  private readonly slot: Record<string, number>;
  private readonly targetIndex: number[];
  private readonly hasGravity: boolean;
  private readonly hasContact: boolean;
  /** Index of the gain in `u`, or -1 when the export has no gain input. */
  private readonly gainSlot: number;
  /** Wall time of the FMU's work per control tick, ms: the last one, the running mean and the largest. */
  readonly timing = { lastMs: 0, meanMs: 0, maxMs: 0, ticks: 0, totalMs: 0 };
  private readonly lastTargets = Float64Array.from(DEFAULT_POSITION);

  private constructor(fmu: Fmu, inputs: string[], targetIndex: number[], outputs: string[], refs: Record<string, number>) {
    super(fmu, inputs, outputs);
    this.label = `bg-sim model: ${fmu.name}`;
    this.outputs = outputs;
    this.targetIndex = targetIndex;
    this.slot = Object.fromEntries(outputs.map((name, i) => [name, i]));
    this.hasGravity = FMU_INTERFACE.optional.gravity.every((n) => n in refs);
    this.hasContact = FMU_INTERFACE.optional.contact.every((n) => n in refs);
    this.gainSlot = inputs.indexOf(FMU_INTERFACE.optional.gain);
  }

  static async create(model: FmuModel): Promise<FmuPlant> {
    const missing = missingVariables(model.refs);
    if (missing.length > 0) {
      throw new Error(`the FMU lacks ${missing.length} variables the app needs, first ${missing.slice(0, 4).join(", ")}`);
    }
    const has = (name: string): boolean => name in model.refs;
    const inputs: string[] = [];
    const targetIndex: number[] = [];
    FMU_INTERFACE.targets.forEach((name, joint) => {
      if (has(name)) {
        inputs.push(name);
        targetIndex.push(joint);
      }
    });
    if (has(FMU_INTERFACE.optional.gain)) {
      inputs.push(FMU_INTERFACE.optional.gain);
    }
    const outputs = [
      ...FMU_INTERFACE.positions,
      ...FMU_INTERFACE.velocities,
      ...FMU_INTERFACE.gyro,
      ...FMU_INTERFACE.quaternion,
      ...FMU_INTERFACE.position,
      ...FMU_INTERFACE.optional.gravity,
      ...FMU_INTERFACE.optional.contact,
    ].filter(has);
    // engine/fmu.ts moves at most 256 values a call.
    if (inputs.length > 256 || outputs.length > 256) {
      throw new Error("more than 256 variables in one call");
    }
    const plant = new FmuPlant(await Fmu.load(model), inputs, targetIndex, outputs, model.refs);
    plant.reset();
    return plant;
  }

  get healthy(): boolean {
    return !this.stopped;
  }

  /** Why and when the FMU stopped; null while it runs. */
  stop: PlantStop | null = null;

  protected afterStep(healthy: boolean): void {
    if (!healthy && this.stop === null) {
      const to = this.fmu.time; // the time has moved on even when the step failed
      this.stop = { from: to - this.fmu.step, to, reason: stopReason(this.fmu.lastStatus) };
    }
    super.afterStep(healthy);
  }

  reset(): void {
    this.stop = null;
    // The targets start at the home pose, which is where the policy starts the robot from.
    this.lastTargets.set(DEFAULT_POSITION);
    this.restart({}, () => {
      this.targetIndex.forEach((joint, i) => (this.u[i] = DEFAULT_POSITION[joint]));
      if (this.gainSlot >= 0) this.u[this.gainSlot] = TUNING.gain;
    });
    this.read();
    Object.assign(this.timing, { lastMs: 0, meanMs: 0, maxMs: 0, ticks: 0, totalMs: 0 });
  }

  step(targets: ArrayLike<number>, dt: number, gain: number = TUNING.gain): void {
    this.lastTargets.set(Array.from(targets).slice(0, NUM_JOINTS));
    this.targetIndex.forEach((joint, i) => {
      this.u[i] = targets[joint];
    });
    if (this.gainSlot >= 0) this.u[this.gainSlot] = gain;
    const started = performance.now();
    this.advance(dt);
    const ms = performance.now() - started;
    const t = this.timing;
    t.lastMs = ms;
    t.ticks += 1;
    t.totalMs += ms;
    t.meanMs = t.totalMs / t.ticks;
    t.maxMs = Math.max(t.maxMs, ms);
    // A stopped FMU's outputs are whatever its last failed step left: keep the last good state.
    if (this.healthy) this.read();
  }

  private value(name: string, otherwise = 0): number {
    const i = this.slot[name];
    return i === undefined ? otherwise : this.y[i];
  }

  private read(): void {
    const s = this.state;
    for (let j = 0; j < NUM_JOINTS; j += 1) {
      // A joint the model does not have (the mouth, perhaps) is drawn where it was asked to be.
      s.q[j] = this.value(FMU_INTERFACE.positions[j], this.lastTargets[j]);
      s.qd[j] = this.value(FMU_INTERFACE.velocities[j]);
    }
    FMU_INTERFACE.gyro.forEach((n, i) => (s.gyro[i] = this.value(n)));
    FMU_INTERFACE.quaternion.forEach((n, i) => (s.quaternion[i] = this.value(n, i === 0 ? 1 : 0)));
    FMU_INTERFACE.position.forEach((n, i) => (s.position[i] = this.value(n)));
    if (this.hasGravity) {
      FMU_INTERFACE.optional.gravity.forEach((n, i) => (s.gravity[i] = this.value(n)));
    } else {
      projectedGravity(s.quaternion, s.gravity);
    }
    s.contact = this.hasContact ? Float64Array.from(FMU_INTERFACE.optional.contact, (n) => (this.value(n) > CONTACT_FORCE_N ? 1 : 0)) : null;
    s.time = this.time;
  }

  /** For the smoke tests and the README: what is read, in order. */
  get variables(): readonly string[] {
    return this.outputs;
  }
}
