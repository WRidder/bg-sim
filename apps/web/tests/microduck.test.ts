// The microduck demo's policy loop, against the contract in pollen-robotics/microduck: the
// observation cases mirror duck-control/src/obs.rs's tests, the scaling and filters
// robotd/src/control.rs, the pad pad-map/src/mapper.rs, and one test runs the published
// velstand.onnx through ONNX Runtime.

import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { describe, expect, it } from "vitest";
import { type Brain, CommandFilter, Controller, DEFAULT_TUNING, lowPass, scaleTargets, willStand } from "../src/microduck/controller";
import type { FmuModel } from "../src/engine/fmu";
import { FMU_INTERFACE, FmuPlant, findModel, missingVariables, stopReason } from "../src/microduck/fmuPlant";
import { Kinematics, SITES } from "../src/microduck/kinematics";
import { DuckLoop, TRAINING_VELOCITY_LAG } from "../src/microduck/loop";
import { buildObservation, type Command, gatherAction, scatterAction, twistMagnitude, zeroCommand } from "../src/microduck/obs";
import { BUTTON, evaluate, modeFromDpad, readPad, stickCommand } from "../src/microduck/pad";
import { describeStop, projectedGravity, StandInPlant } from "../src/microduck/plant";
import { OnnxBrain } from "../src/microduck/policy";
import { ACTION_LEN, COMMAND_LEN, DEFAULT_POSITION, JOINT_NAMES, MOUTH_INDEX, NUM_JOINTS, OBS_LEN } from "../src/microduck/robot";
import * as THREE from "three";

const POLICIES = resolve(import.meta.dirname, "../src/microduck/policies");
/** The yaw of a trunk quaternion (w, x, y, z), rad. */
const heading = ([w, x, y, z]: readonly number[] | Float64Array): number => Math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z));
const HAS_MODEL = existsSync(resolve(import.meta.dirname, "../src/microduck/model.gen.ts"));

// ---- Observation (obs.rs) -----------------------------------------------------------------------

const imu = { gyro: [1, 2, 3], gravity: [4, 5, 6] };
const command = (): Command => ({ twist: [0.1, 0.2, 0.3], head: [0.4, 0.5, 0.6, 0.7], body: { z: 0.8, roll: 0.9, pitch: 1.0 } });
const buildWith = (positions: number[], lastAction: ArrayLike<number>): Float32Array =>
  buildObservation({ ...imu, positions, velocities: new Array(NUM_JOINTS).fill(0) }, DEFAULT_POSITION, lastAction, command());

describe("observation", () => {
  it("has the joint order of duck_ipc_proto, the mouth at 9", () => {
    expect(JOINT_NAMES[MOUTH_INDEX]).toBe("mouth");
    expect(JOINT_NAMES.length).toBe(15);
    expect(JOINT_NAMES[10]).toBe("right_hip_yaw");
  });

  it("the layout widths sum to the declared input", () => {
    expect(3 + 3 + ACTION_LEN * 3 + COMMAND_LEN).toBe(OBS_LEN);
  });

  it("every block lands at its documented offset", () => {
    const positions = [...DEFAULT_POSITION];
    positions[0] += 0.25;
    const last = new Float32Array(ACTION_LEN);
    last[0] = -0.5;
    last[ACTION_LEN - 1] = 0.75;
    const d = buildWith(positions, last);
    expect(Array.from(d.slice(0, 3))).toEqual([1, 2, 3]);
    expect(Array.from(d.slice(3, 6))).toEqual([4, 5, 6]);
    expect(d[6]).toBeCloseTo(0.25, 6);
    expect(d[20]).toBe(0);
    expect(d[34]).toBe(-0.5);
    expect(d[47]).toBe(0.75);
    expect(Array.from(d.slice(48, 51))).toEqual(Array.from(Float32Array.of(0.1, 0.2, 0.3)));
    expect(Array.from(d.slice(51, 55))).toEqual(Array.from(Float32Array.of(0.4, 0.5, 0.6, 0.7)));
  });

  it("keeps the unbound body axes at zero", () => {
    const d = buildWith([...DEFAULT_POSITION], new Float32Array(ACTION_LEN));
    expect([d[55], d[56], d[60]]).toEqual([0, 0, 0]);
  });

  it("orders the body block z, roll, pitch", () => {
    const d = buildWith([...DEFAULT_POSITION], new Float32Array(ACTION_LEN));
    expect(Array.from(d.slice(57, 60))).toEqual(Array.from(Float32Array.of(0.8, 0.9, 1.0)));
  });

  it("observes joint positions relative to the home pose", () => {
    const d = buildWith([...DEFAULT_POSITION], new Float32Array(ACTION_LEN));
    for (const v of d.slice(6, 20)) expect(Math.abs(v)).toBeLessThan(1e-7);
  });

  it("leaves the mouth out of the observation", () => {
    const positions = [...DEFAULT_POSITION];
    positions[MOUTH_INDEX] += 1;
    const velocities = new Array(NUM_JOINTS).fill(0);
    velocities[MOUTH_INDEX] = 5;
    const d = buildObservation({ ...imu, positions, velocities }, DEFAULT_POSITION, new Float32Array(ACTION_LEN), zeroCommand());
    for (const v of d.slice(6, 34)) expect(Math.abs(v)).toBeLessThan(1e-7);
  });

  it("scatters an action round the mouth, and gathers it back", () => {
    const action = Float32Array.from({ length: ACTION_LEN }, (_, i) => i + 1);
    const joints = scatterAction(action);
    expect(joints[MOUTH_INDEX]).toBe(0);
    expect(joints[0]).toBe(1);
    expect(joints[8]).toBe(9);
    expect(joints[10]).toBe(10);
    expect(joints[NUM_JOINTS - 1]).toBe(ACTION_LEN);
    expect(Array.from(gatherAction(joints))).toEqual(Array.from(action));
  });

  it("measures the twist alone for walk against stand", () => {
    const c = zeroCommand();
    c.head = [1, 1, 1, 1];
    c.body = { z: 1, roll: 1, pitch: 1 };
    expect(twistMagnitude(c)).toBe(0);
    c.twist = [3, 4, 0];
    expect(twistMagnitude(c)).toBeCloseTo(5, 12);
  });
});

// ---- Scaling, filters and the network choice (control.rs) ------------------------------------

/** A brain that answers a fixed action and remembers what it was asked. */
function fakeBrain(nets: string[], answer: (call: number) => number[]): Brain & { calls: { net: string; obs: Float32Array; fresh: boolean }[] } {
  const calls: { net: string; obs: Float32Array; fresh: boolean }[] = [];
  return {
    calls,
    has: (net) => nets.includes(net),
    infer: async (net, obs, fresh) => {
      calls.push({ net, obs: Float32Array.from(obs), fresh });
      return Float32Array.from(answer(calls.length - 1));
    },
  };
}

const home = { gyro: [0, 0, 0], gravity: [0, 0, -1], positions: [...DEFAULT_POSITION], velocities: new Array(NUM_JOINTS).fill(0) };

describe("targets", () => {
  it("are home plus the scaled action, the mouth at home", () => {
    const action = new Array(ACTION_LEN).fill(1);
    const t = scaleTargets(action, 0.9);
    expect(t[0]).toBeCloseTo(DEFAULT_POSITION[0] + 0.9, 12);
    expect(t[MOUTH_INDEX]).toBe(DEFAULT_POSITION[MOUTH_INDEX]);
    expect(t[14]).toBeCloseTo(DEFAULT_POSITION[14] + 0.9, 12);
  });

  it("low-pass the head at 0.5 and the legs at 0.7, the mouth not at all, the first tick not at all", () => {
    const fresh = Float64Array.from({ length: NUM_JOINTS }, () => 1);
    expect(Array.from(lowPass(Float64Array.from(fresh), null, DEFAULT_TUNING))).toEqual(Array.from(fresh));
    const t = lowPass(Float64Array.from(fresh), new Float64Array(NUM_JOINTS), DEFAULT_TUNING);
    for (const j of [0, 1, 2, 3, 4, 10, 11, 12, 13, 14]) expect(t[j]).toBeCloseTo(0.7, 12);
    for (const j of [5, 6, 7, 8]) expect(t[j]).toBeCloseTo(0.5, 12);
    expect(t[MOUTH_INDEX]).toBe(1);
  });

  it("feed back the RAW action, and filter scaled targets against the previous filtered ones", async () => {
    const a = [0.2, -0.4];
    const brain = fakeBrain(["walk"], (i) => new Array(ACTION_LEN).fill(a[i] ?? 0));
    const c = new Controller(brain);
    const walk: Command = { ...zeroCommand(), twist: [0.3, 0, 0] };
    const first = await c.step(home, walk);
    const second = await c.step(home, walk);
    // The second observation carries the first raw output, not 0.9 × it.
    expect(brain.calls[1].obs[34]).toBeCloseTo(0.2, 6);
    expect(brain.calls[1].obs[47]).toBeCloseTo(0.2, 6);
    expect(first.targets[2]).toBeCloseTo(DEFAULT_POSITION[2] + 0.9 * 0.2, 6);
    const raw = DEFAULT_POSITION[2] + 0.9 * -0.4;
    expect(second.targets[2]).toBeCloseTo(0.7 * raw + 0.3 * first.targets[2], 6);
    const rawHead = DEFAULT_POSITION[6] + 0.9 * -0.4;
    expect(second.targets[6]).toBeCloseTo(0.5 * rawHead + 0.5 * first.targets[6], 6);
    expect(second.label).toBe("walk");
  });
});

describe("walk or stand", () => {
  it("stands at a twist of 0.05 or less, only with a standing network", () => {
    expect(willStand(true, 0.05)).toBe(true);
    expect(willStand(true, 0.0501)).toBe(false);
    expect(willStand(false, 0)).toBe(false);
  });

  it("switches network and scale on the threshold when there is a standing network", async () => {
    const c = new Controller(fakeBrain(["walk", "stand"], () => new Array(ACTION_LEN).fill(1)));
    const still = await c.step(home, { ...zeroCommand(), twist: [0.03, 0.03, 0] });
    expect(still.label).toBe("stand");
    expect(still.scale).toBe(1.0);
    const moving = await c.step(home, { ...zeroCommand(), twist: [0.04, 0.04, 0] });
    expect(moving.label).toBe("walk");
    expect(moving.scale).toBe(0.9);
  });

  it("walks at every speed with velstand, which has no standing network", async () => {
    const c = new Controller(fakeBrain(["walk"], () => new Array(ACTION_LEN).fill(0)));
    expect((await c.step(home, zeroCommand())).label).toBe("walk");
    expect((await c.step(home, zeroCommand())).scale).toBe(0.9);
  });

  it("runs a kick for 0.5 s on a zero command, then walks again", async () => {
    const brain = fakeBrain(["walk", "kick_left"], () => new Array(ACTION_LEN).fill(0));
    const c = new Controller(brain);
    expect(c.startSkill("kick_left")).toBeNull();
    expect(c.startSkill("kick_right")).toMatch(/no kick_right/);
    const labels: string[] = [];
    for (let i = 0; i < 27; i += 1) labels.push((await c.step(home, { ...zeroCommand(), twist: [0.3, 0, 0] })).label);
    expect(labels.filter((l) => l === "kick_left").length).toBe(25);
    expect(labels.at(-1)).toBe("walk");
    expect(brain.calls[0].obs[48]).toBe(0); // the kick's twist is zero whatever the stick says
    expect(brain.calls[0].fresh).toBe(true);
  });

  it("sits on the posture flag, refuses to stand mid-glide, rises for 1 s", async () => {
    const brain = fakeBrain(["walk", "sitstand"], () => new Array(ACTION_LEN).fill(0));
    const c = new Controller(brain);
    expect(c.sitToggle()).toBeNull();
    const sit = await c.step(home, zeroCommand());
    expect(sit.label).toBe("sit");
    expect(brain.calls[0].obs[48]).toBe(1);
    expect(c.sitToggle()).toBe("still sitting down");
    expect(c.startSkill("roulade")).not.toBeNull();
    for (let i = 0; i < 100; i += 1) await c.step(home, zeroCommand());
    expect(c.sitToggle()).toBeNull();
    const labels: string[] = [];
    for (let i = 0; i < 52; i += 1) labels.push((await c.step(home, zeroCommand())).label);
    expect(labels.filter((l) => l === "rise").length).toBe(50);
    expect(labels.at(-1)).toBe("walk");
  });

  it("smooths the command with robotd's per-tick EMA", () => {
    const f = new CommandFilter();
    const target: Command = { ...zeroCommand(), twist: [1, 0, 0], head: [1, 0, 0, 0] };
    f.update(target, false);
    expect(f.value.twist[0]).toBeCloseTo(0.2, 12);
    f.update(target, false);
    expect(f.value.twist[0]).toBeCloseTo(0.36, 12);
    expect(f.value.head[0]).toBeCloseTo(0.36, 12);
    f.update({ ...zeroCommand(), body: { z: 0.01, roll: 0, pitch: 0 } }, true);
    expect(f.value.body.z).toBeCloseTo(0.002, 12);
    f.update(zeroCommand(), false);
    expect(f.value.body.z).toBe(0);
  });
});

// ---- The pad (pad-map) --------------------------------------------------------------------------

const pad = (axes: number[], pressed: number[] = []) => ({
  axes,
  buttons: Array.from({ length: 17 }, (_, i) => ({ pressed: pressed.includes(i), touched: false, value: pressed.includes(i) ? 1 : 0 })),
});

describe("gamepad mapping", () => {
  it("flips the Gamepad API's Y so up is positive, as gilrs has it", () => {
    const f = readPad(pad([0.5, -1, -0.25, 1]));
    expect(f.sticks).toEqual({ lx: 0.5, ly: 1, rx: -0.25, ry: -1 });
  });

  it("cuts below the dead zone of 0.1 and does not rescale above it", () => {
    expect(evaluate(0.099)).toBe(0);
    expect(evaluate(0.1)).toBe(0.1);
    expect(evaluate(0.5, 0.1, true)).toBe(-0.5);
    expect(evaluate(Number.NaN)).toBe(0);
  });

  it("drives as the robot does: left stick walks and strafes, right stick turns", () => {
    const up = stickCommand("drive", readPad(pad([0, -1, 0, 0])).sticks).command.twist;
    expect(up).toEqual([0.4, 0, 0]);
    const back = stickCommand("drive", readPad(pad([0, 1, 0, 0])).sticks).command.twist;
    expect(back[0]).toBeCloseTo(-0.3, 12);
    const left = stickCommand("drive", readPad(pad([-1, 0, 0, 0])).sticks).command.twist;
    expect(left[1]).toBeCloseTo(0.3, 12);
    const turnRight = stickCommand("drive", readPad(pad([0, 0, 1, 0])).sticks).command.twist;
    expect(turnRight[2]).toBeCloseTo(-1, 12);
  });

  it("holds the body still while the sticks pose the head", () => {
    const s = stickCommand("head", readPad(pad([1, -1, 1, -1])).sticks);
    expect(s.command.twist).toEqual([0, 0, 0]);
    // Right stick up: neck +; left stick up: head_pitch − (inverted); left: head_yaw −; right x: roll +.
    expect(s.command.head).toEqual([2.5, -2.5, -2.5, 2.5]);
    expect(s.bodyActive).toBe(false);
  });

  it("walks and turns on the left stick in head + move, and looks with the right", () => {
    const s = stickCommand("headDrive", readPad(pad([-1, -1, 0, -1])).sticks).command;
    expect(s.twist[0]).toBeCloseTo(0.4, 12);
    expect(s.twist[1]).toBe(0);
    expect(s.twist[2]).toBeCloseTo(1, 12);
    expect(s.head[1]).toBeCloseTo(-2.5, 12); // right stick up, head_pitch inverted
  });

  it("crouches and leans in body + head, with the body pose active", () => {
    const s = stickCommand("body", readPad(pad([1, 1, 0, 0])).sticks);
    expect(s.bodyActive).toBe(true);
    expect(s.command.twist).toEqual([0, 0, 0]);
    expect(s.command.body.z).toBeCloseTo(-0.025, 12);
    expect(s.command.body.roll).toBeCloseTo(0.2618, 12);
  });

  it("lets the D-pad select a mode, the last arrow of a frame winning in the robot's order", () => {
    const pressed = (set: number[]) => (b: number) => set.includes(b);
    expect(modeFromDpad(pressed([BUTTON.up]), "drive")).toBe("head");
    expect(modeFromDpad(pressed([BUTTON.up, BUTTON.down]), "drive")).toBe("body");
    expect(modeFromDpad(pressed([]), "headDrive")).toBe("headDrive");
  });
});

// ---- Kinematics, plant, FMU interface ----------------------------------------------------------

describe("plant", () => {
  it("puts the soles 117 mm under the trunk at home, mirrored", () => {
    const k = new Kinematics().update(DEFAULT_POSITION);
    const l = k.site(SITES.leftFoot, new THREE.Vector3());
    const r = k.site(SITES.rightFoot, new THREE.Vector3());
    expect(l.z).toBeCloseTo(-0.117, 3);
    expect(r.z).toBeCloseTo(l.z, 6);
    expect(r.y).toBeCloseTo(-l.y, 6);
  });

  it("works gravity out of a quaternion as the IMU does", () => {
    expect(Array.from(projectedGravity([1, 0, 0, 0])).map((v) => +v.toFixed(9))).toEqual([0, 0, -1]);
    const pitched = projectedGravity([Math.cos(0.25), 0, Math.sin(0.25), 0]); // 0.5 rad nose down
    expect(pitched[0]).toBeCloseTo(Math.sin(0.5), 9);
  });

  it("names every FMU variable once, and fits engine/fmu's 256 a call", () => {
    const names = [...FMU_INTERFACE.targets, ...FMU_INTERFACE.positions, ...FMU_INTERFACE.velocities, ...FMU_INTERFACE.gyro, ...FMU_INTERFACE.quaternion, ...FMU_INTERFACE.position, ...FMU_INTERFACE.optional.gravity, ...FMU_INTERFACE.optional.contact];
    expect(new Set(names).size).toBe(names.length);
    expect(names.length).toBeLessThanOrEqual(256);
    const refs = Object.fromEntries(names.map((n, i) => [n, i]));
    expect(missingVariables(refs)).toEqual([]);
    delete refs.mouth_target;
    delete refs.mouth_q;
    delete refs.mouth_qd;
    delete refs.gravity_x;
    expect(missingVariables(refs)).toEqual([]);
    delete refs.left_knee_q;
    expect(missingVariables(refs)).toEqual(["left_knee_q"]);
  });

  it("finds the FMU exactly when model.gen.ts has been generated", async () => {
    // model.gen.ts is generated (build_wasm.py microduck <fmu>) and gitignored: both cases are fine.
    expect((await findModel()) !== null).toBe(HAS_MODEL);
  });

  it("follows its targets with a lag and keeps a sole on the floor", () => {
    const plant = new StandInPlant();
    const targets = Float64Array.from(DEFAULT_POSITION);
    targets[3] += 0.2;
    plant.step(targets, 0.02);
    expect(plant.state.q[3]).toBeGreaterThan(DEFAULT_POSITION[3]);
    expect(plant.state.q[3]).toBeLessThan(DEFAULT_POSITION[3] + 0.2);
    for (let i = 0; i < 20; i += 1) plant.step(targets, 0.02);
    expect(plant.state.q[3]).toBeCloseTo(DEFAULT_POSITION[3] + 0.2, 3);
    expect(Math.max(...plant.state.contact!)).toBe(1);
    expect(Array.from(plant.state.gravity)).toEqual([0, 0, -1]);
  });
});

// ---- The real policy ----------------------------------------------------------------------------

describe("velstand.onnx under ONNX Runtime", () => {
  it("returns 14 finite actions for the home pose", async () => {
    const ort = await import("onnxruntime-web");
    ort.env.wasm.numThreads = 1;
    const brain = new OnnxBrain(ort);
    await brain.load("walk", readFileSync(resolve(POLICIES, "velstand.onnx")));
    const obs = buildObservation(home, DEFAULT_POSITION, new Float32Array(ACTION_LEN), zeroCommand());
    const action = await brain.infer("walk", obs, true);
    expect(action.length).toBe(14);
    expect(action.every(Number.isFinite)).toBe(true);
    expect(Math.max(...action.map(Math.abs))).toBeLessThan(5);
  });

  it("runs the whole loop on the stand-in plant: still at zero command, stepping when asked to move", async () => {
    const ort = await import("onnxruntime-web");
    ort.env.wasm.numThreads = 1;
    const brain = new OnnxBrain(ort);
    await brain.load("walk", readFileSync(resolve(POLICIES, "velstand.onnx")));
    const run = async (ly: number) => {
      const plant = new StandInPlant();
      plant.setCarry("foot");
      const loop = new DuckLoop(plant, new Controller(brain));
      loop.reset();
      let deviation = 0;
      let swaps = 0;
      let stance = plant.stanceFoot;
      for (let i = 0; i < 200; i += 1) {
        const tick = await loop.tick(stickCommand("drive", { lx: 0, ly, rx: 0, ry: 0 }), 0);
        expect(tick.label).toBe("walk");
        expect(tick.targets.every(Number.isFinite)).toBe(true);
        if (i >= 50) {
          for (let j = 0; j < NUM_JOINTS; j += 1) deviation = Math.max(deviation, Math.abs(plant.state.q[j] - DEFAULT_POSITION[j]));
          swaps += plant.stanceFoot === stance ? 0 : 1;
        }
        stance = plant.stanceFoot;
      }
      return { deviation, swaps, x: plant.state.position[0], y: plant.state.position[1], ticks: loop.ticks };
    };
    const still = await run(0);
    const forward = await run(1);
    console.log(`stand-in, 3 s after 1 s of settling: zero command ${JSON.stringify(still)}; full forward ${JSON.stringify(forward)}`);
    expect(still.ticks).toBe(200);
    expect(still.deviation).toBeLessThan(0.3);
    expect(still.swaps).toBe(0);
    expect(forward.swaps).toBeGreaterThan(10);
  });
});

// ---- The real policy on the bg-sim model (only when model.gen.ts has been built) ----------------

describe("joint-velocity lag", () => {
  // What the policy reads at slots 20..34 per tick, against what the plant reported at the start of
  // the tick. The stand-in plant moves its joints, so its velocities change from tick to tick.
  const observedVelocities = async (lag?: number) => {
    const seen: number[][] = [];
    const brain: Brain = {
      has: (net) => net === "walk",
      infer: async (_net, obs) => {
        seen.push(Array.from(obs.slice(20, 34)));
        return new Float32Array(ACTION_LEN).fill(0.3 * Math.sin(seen.length));
      },
    };
    const plant = new StandInPlant();
    const loop = lag === undefined ? new DuckLoop(plant, new Controller(brain)) : new DuckLoop(plant, new Controller(brain), lag);
    loop.reset();
    const reported: number[][] = [];
    for (let i = 0; i < 6; i += 1) {
      reported.push(Array.from(gatherAction(plant.state.qd)));
      await loop.tick(stickCommand("drive", { lx: 0, ly: 1, rx: 0, ry: 0 }), 0);
    }
    return { seen, reported, loop };
  };

  it("defaults to training's one tick: the policy reads the previous tick's velocities", async () => {
    const { seen, reported, loop } = await observedVelocities();
    expect(loop.velocityLag).toBe(1);
    expect(reported.slice(2).some((v) => v.some((x) => Math.abs(x) > 1e-3))).toBe(true);
    expect(seen[0]).toEqual(reported[0].map((x) => Math.fround(x))); // mjlab: the current value until the line fills
    for (let i = 1; i < seen.length; i += 1) {
      expect(seen[i]).toEqual(reported[i - 1].map((x) => Math.fround(x)));
    }
  });

  it("with lag 0 reads the present velocities, and reset empties the line", async () => {
    const { seen, reported } = await observedVelocities(0);
    for (let i = 0; i < seen.length; i += 1) expect(seen[i]).toEqual(reported[i].map((x) => Math.fround(x)));
    const again = await observedVelocities(1);
    again.loop.reset();
    const before = Array.from(gatherAction(again.loop.plant.state.qd));
    await again.loop.tick(stickCommand("drive", { lx: 0, ly: 1, rx: 0, ry: 0 }), 0);
    expect(again.seen[again.seen.length - 1]).toEqual(before.map((x) => Math.fround(x)));
  });
});

describe("a stopped plant", () => {
  it("is not stepped and its frozen state is not fed to the policy", async () => {
    let stepped = 0;
    const plant = new StandInPlant();
    const stopped = Object.assign(Object.create(plant) as StandInPlant, {
      healthy: false,
      stop: { from: 0.7, to: 0.72, reason: stopReason(3) },
      step: () => {
        stepped += 1;
      },
    });
    const brain: Brain = {
      has: () => true,
      infer: () => {
        throw new Error("the policy was run on a stopped plant");
      },
    };
    const loop = new DuckLoop(stopped, new Controller(brain));
    const tick = await loop.tick(stickCommand("drive", { lx: 0, ly: 1, rx: 0, ry: 0 }), 0);
    expect(tick.label).toBe("stopped");
    expect(tick.step).toBeNull();
    expect(stepped).toBe(0);
    expect(loop.ticks).toBe(0);
    expect(describeStop(stopped.stop!)).toBe("stopped in the step from 0.700 s to 0.720 s: the FMU's solver could not complete the step (fmi2Error)");
  });

  it("names every fmi2 status it can get", () => {
    expect(stopReason(2)).toContain("fmi2Discard");
    expect(stopReason(0)).toContain("finite");
    expect(stopReason(7)).toContain("7");
  });
});

/**
 * velstand.onnx drives the microduck-policy FMU (examples/microduck) through the page's own loop, at
 * zero, half and full forward command. Nothing here says the duck walks: a run is reported, not
 * judged (a fall is a result). It checks that the loop runs, every value stays finite and the FMU
 * does not stop (no failed step in any run), and logs per command the trunk's height, tilt, travel
 * and speed against the commanded speed, and the FMU's wall time per 20 ms tick. MICRODUCK_SECONDS
 * sets the run length (default 3 s), MICRODUCK_TRACE a file for the per-tick trace (JSON),
 * MICRODUCK_COMMANDS the forward sticks (comma-separated, 0..1, full stick = 0.4 m/s; default
 * 0,0.5,1), MICRODUCK_LAG the joint-velocity lag in ticks (default training's 1) and
 * MICRODUCK_MODEL another generated model module (build_wasm.py microduck <fmu> <name>.gen.ts) in
 * place of src/microduck/model.gen.ts.
 */
const ALT_MODEL = process.env.MICRODUCK_MODEL;
describe.skipIf(!HAS_MODEL && !ALT_MODEL)("velstand.onnx on the bg-sim FMU", () => {
  const seconds = Number(process.env.MICRODUCK_SECONDS ?? 3);
  const sticks = (process.env.MICRODUCK_COMMANDS ?? "0,0.5,1").split(",").map(Number);
  const lag = Number(process.env.MICRODUCK_LAG ?? TRAINING_VELOCITY_LAG);
  const runName = (ly: number) => ({ 0: "zero", 0.5: "half-forward", 1: "full-forward" })[ly] ?? `ly=${ly}`;
  it(`runs ${seconds} s at zero command, half and full forward, and the FMU does not stop`, { timeout: 1_800_000 }, async () => {
    const ort = await import("onnxruntime-web");
    ort.env.wasm.numThreads = 1;
    const brain = new OnnxBrain(ort);
    await brain.load("walk", readFileSync(resolve(POLICIES, "velstand.onnx")));
    const model = ALT_MODEL ? ((await import(pathToFileURL(resolve(ALT_MODEL)).href)) as { model: FmuModel }).model : (await findModel())!;
    const plant = await FmuPlant.create(model);
    const trace: Record<string, unknown[]> = {};
    const run = async (name: string, ly: number) => {
      const loop = new DuckLoop(plant, new Controller(brain), lag);
      loop.reset();
      const rows: number[][] = [];
      // What the plant was given each tick (15 targets, the gain): enough to replay the run in fmpy.
      const sent: number[][] = [];
      let fellAt: number | null = null;
      let stopped: string | null = null;
      let minZ = Infinity;
      let maxTilt = 0;
      let commanded = 0;
      const z0 = plant.state.position[2];
      // the forward speed over the second half of the run, from the trunk's travel
      const half = Math.round(seconds * 25);
      let xHalf = NaN;
      let yHalf = NaN;
      let tHalf = NaN;
      let headingHalf = NaN;
      const liftOffs = [0, 0];
      const down = [1, 1];
      for (let i = 0; i < Math.round(seconds * 50); i += 1) {
        const tick = await loop.tick(stickCommand("drive", { lx: 0, ly, rx: 0, ry: 0 }), 0);
        const s = plant.state;
        sent.push([...tick.targets, tick.gain]);
        expect(tick.targets.every(Number.isFinite)).toBe(true);
        if (!plant.healthy) {
          stopped = plant.stop ? describeStop(plant.stop) : "stopped";
          break;
        }
        commanded = loop.filter.value.twist[0];
        const tilt = Math.acos(Math.min(1, Math.max(-1, -s.gravity[2])));
        minZ = Math.min(minZ, s.position[2]);
        maxTilt = Math.max(maxTilt, tilt);
        if (fellAt === null && (tilt > 0.8 || s.position[2] < 0.5 * z0)) fellAt = s.time;
        if (i === half) {
          xHalf = s.position[0];
          yHalf = s.position[1];
          tHalf = s.time;
          headingHalf = heading(s.quaternion);
        }
        // a sole leaving the floor, as the page sees it (CONTACT_FORCE_N)
        s.contact?.forEach((c, k) => {
          if (c === 0 && down[k] === 1) liftOffs[k] += 1;
          down[k] = c;
        });
        rows.push([s.time, ...s.position, tilt, ...(s.contact ?? [NaN, NaN]), loop.actual[0], plant.timing.lastMs, ...FMU_INTERFACE.optional.contact.map((n) => plant.get(n))]);
      }
      const s = plant.state;
      trace[name] = rows;
      trace[`${name}:inputs`] = sent;
      return {
        name,
        model: model.name,
        velocityLag: lag,
        seconds,
        tEnd: +s.time.toFixed(2),
        z0: +z0.toFixed(4),
        zEnd: +s.position[2].toFixed(4),
        minZ: +minZ.toFixed(4),
        maxTiltDeg: +((maxTilt * 180) / Math.PI).toFixed(2),
        fellAt,
        stopped,
        travel: [+s.position[0].toFixed(3), +s.position[1].toFixed(3)],
        distance: +Math.hypot(s.position[0], s.position[1]).toFixed(3),
        headingDeg: +((heading(s.quaternion) * 180) / Math.PI).toFixed(1),
        // the turn rate over the second half (rad/s), from the heading (unwrapped once)
        yawRateSecondHalf: +(Math.atan2(Math.sin(heading(s.quaternion) - headingHalf), Math.cos(heading(s.quaternion) - headingHalf)) / (s.time - tHalf)).toFixed(4),
        commandedVx: +commanded.toFixed(3),
        meanForward: +(s.position[0] / s.time).toFixed(3),
        forwardSecondHalf: +((s.position[0] - xHalf) / (s.time - tHalf)).toFixed(3),
        speedSecondHalf: +(Math.hypot(s.position[0] - xHalf, s.position[1] - yHalf) / (s.time - tHalf)).toFixed(3),
        msPerTick: +plant.timing.meanMs.toFixed(2),
        maxMsPerTick: +plant.timing.maxMs.toFixed(2),
        liftOffs,
        realTimeFactor: +(plant.timing.meanMs / 20).toFixed(3),
      };
    };
    const results = [];
    for (const ly of sticks) results.push(await run(runName(ly), ly));
    console.log(`velstand on the FMU:\n${results.map((r) => JSON.stringify(r)).join("\n")}`);
    if (process.env.MICRODUCK_TRACE) {
      writeFileSync(process.env.MICRODUCK_TRACE, JSON.stringify({ columns: ["t", "x", "y", "z", "tilt", "contactL", "contactR", "vxMeasured", "msTick", "forceL", "forceR"], ...trace }));
    }
    // The claim of this test: the FMU completes every step of every run (a fall is not a failure).
    for (const r of results) {
      expect(r.stopped, `${r.name}: ${r.stopped}`).toBeNull();
      expect(r.tEnd).toBeCloseTo(seconds, 6);
    }
  });
});
