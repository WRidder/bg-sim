/**
 * A PS5 DualSense (or any pad the browser reports with the standard mapping) and a keyboard, turned
 * into what the robot is asked to do. The stick mapping is the real robot's, re-implemented from
 * `pad-map/src/mapper.rs` and `robotd-params/src/pad_axes.rs` of pollen-robotics/microduck
 * (Apache-2.0): the D-pad picks what the sticks mean, the dead zone is a plain cut at 0.1 with no
 * rescaling, and each axis scales linearly onto its own limit either side of centre.
 *
 * One difference in convention: the robot reads the pad through gilrs, where a stick pushed up is
 * positive; the Gamepad API reports up as −1, so `readPad` flips both Y axes once, here.
 */

import { type Command, zeroCommand } from "./obs";
import { BODY_LIMITS, DRIVE_LIMITS, HEAD_LIMITS, PAD_DEADZONE } from "./robot";

/** D-pad left, up, right, down on the robot. */
export type PadMode = "drive" | "head" | "headDrive" | "body";

export const MODE_NAMES: Record<PadMode, string> = {
  drive: "Move",
  head: "Head",
  headDrive: "Head + move",
  body: "Body + head",
};

/** Sticks as gilrs reports them, which is what the robot's mapping is written for: x right positive, y up positive. */
export interface Sticks {
  lx: number;
  ly: number;
  rx: number;
  ry: number;
}

/** Standard-mapping button indices (https://w3c.github.io/gamepad/#remapping), DualSense names. */
export const BUTTON = {
  cross: 0,
  circle: 1,
  square: 2,
  triangle: 3,
  l1: 4,
  r1: 5,
  l2: 6,
  r2: 7,
  create: 8,
  options: 9,
  l3: 10,
  r3: 11,
  up: 12,
  down: 13,
  left: 14,
  right: 15,
  ps: 16,
} as const;

export interface PadFrame {
  sticks: Sticks;
  lt: number;
  rt: number;
  /** Indexed as BUTTON. */
  held: boolean[];
}

/** `AxisBinding::evaluate`: below the dead zone nothing, above it the value as it is. */
export function evaluate(value: number, deadzone = PAD_DEADZONE, invert = false): number {
  if (!Number.isFinite(value) || Math.abs(value) < deadzone) {
    return 0;
  }
  return Math.max(-1, Math.min(1, invert ? -value : value));
}

/** `PadDriveParams::scale`: positive deflection towards `max`, negative towards `min`. */
export const scaleAxis = (deflection: number, min: number, max: number): number => (deflection >= 0 ? deflection * max : -deflection * min);

export interface StickCommand {
  command: Command;
  /** Body + head mode holds the body pose: the twist is zero and the body block is live. */
  bodyActive: boolean;
}

/** `stick_frame`: what the sticks ask for in `mode`. */
export function stickCommand(mode: PadMode, s: Sticks, deadzone = PAD_DEADZONE): StickCommand {
  const v = (value: number, invert = false): number => evaluate(value, deadzone, invert);
  const L = DRIVE_LIMITS;
  const H = HEAD_LIMITS;
  const command = zeroCommand();
  const walk = (vx: number, vy: number, vyaw: number): void => {
    command.twist = [scaleAxis(vx, L.vxMin, L.vxMax), scaleAxis(vy, L.vyMin, L.vyMax), scaleAxis(vyaw, L.vyawMin, L.vyawMax)];
  };
  switch (mode) {
    case "drive": // vx: LeftY; vy: LeftX inverted; vyaw: RightX inverted
      walk(v(s.ly), v(s.lx, true), v(s.rx, true));
      return { command, bodyActive: false };
    case "head": // neck: RightY; head_pitch: LeftY inv; head_yaw: LeftX inv; head_roll: RightX
      command.head = [v(s.ry) * H.neckPitch, v(s.ly, true) * H.headPitch, v(s.lx, true) * H.headYaw, v(s.rx) * H.headRoll];
      return { command, bodyActive: false };
    case "headDrive": // vx: LeftY; vyaw: LeftX inv; head_pitch: RightY inv; head_yaw: RightX inv
      walk(v(s.ly), 0, v(s.lx, true));
      command.head = [0, v(s.ry, true) * H.headPitch, v(s.rx, true) * H.headYaw, 0];
      return { command, bodyActive: false };
    case "body": // z: LeftY; roll: LeftX; head_pitch: RightY inv; head_yaw: RightX inv
      command.body = { z: scaleAxis(v(s.ly), BODY_LIMITS.zMin, BODY_LIMITS.zMax), roll: v(s.lx) * BODY_LIMITS.rollMax, pitch: 0 };
      command.head = [0, v(s.ry, true) * H.headPitch, v(s.rx, true) * H.headYaw, 0];
      return { command, bodyActive: true };
  }
}

/** A Gamepad as the robot's mapping reads it: Y flipped to up-positive, triggers as 0..1. */
export function readPad(pad: Pick<Gamepad, "axes" | "buttons">): PadFrame {
  const axis = (i: number): number => pad.axes[i] ?? 0;
  const held = Array.from({ length: 17 }, (_, i) => pad.buttons[i]?.pressed ?? false);
  return {
    sticks: { lx: axis(0), ly: -axis(1), rx: axis(2), ry: -axis(3) },
    lt: pad.buttons[BUTTON.l2]?.value ?? 0,
    rt: pad.buttons[BUTTON.r2]?.value ?? 0,
    held,
  };
}

/** The D-pad selects (does not toggle): the last arrow pressed this frame wins, in the robot's order. */
export function modeFromDpad(pressed: (button: number) => boolean, current: PadMode): PadMode {
  let mode = current;
  for (const [button, next] of [
    [BUTTON.up, "head"],
    [BUTTON.right, "headDrive"],
    [BUTTON.left, "drive"],
    [BUTTON.down, "body"],
  ] as const) {
    if (pressed(button)) {
      mode = next;
    }
  }
  return mode;
}

/** One-shot actions the face buttons and bumpers ask for. */
export type Action = "sit" | "groundPick" | "roulade" | "kickLeft" | "kickRight" | "policy" | "reset" | "camera";

/** The demo's buttons. Robot defaults where the robot has the feature; the rest is said on screen. */
export const BUTTON_ACTIONS: readonly [number, Action][] = [
  [BUTTON.cross, "sit"], // robot: A, sit ↔ stand
  [BUTTON.circle, "groundPick"], // robot: B, ground pick
  [BUTTON.square, "roulade"], // robot: X, free; held re-sends, which chains the roulade
  [BUTTON.l1, "kickLeft"], // robot: LB, "yes" emotion; no emotions here
  [BUTTON.r1, "kickRight"], // robot: RB, "no" emotion
  [BUTTON.options, "policy"], // robot: Start, stand up / policy on-off
  [BUTTON.create, "reset"], // robot: Select held, rest; here, back to the start
  [BUTTON.triangle, "camera"], // robot: Y, "excited" emotion
];

/** What the keyboard does; the same actions and the same four sticks. */
export const KEYS = {
  lyUp: ["KeyW"],
  lyDown: ["KeyS"],
  lxLeft: ["KeyA"],
  lxRight: ["KeyD"],
  ryUp: ["ArrowUp"],
  ryDown: ["ArrowDown"],
  rxLeft: ["ArrowLeft", "KeyQ"],
  rxRight: ["ArrowRight", "KeyE"],
  modes: { Digit1: "drive", Digit2: "head", Digit3: "headDrive", Digit4: "body" } as Record<string, PadMode>,
  actions: {
    Space: "sit",
    KeyG: "groundPick",
    KeyV: "roulade",
    KeyZ: "kickLeft",
    KeyX: "kickRight",
    Enter: "policy",
    KeyR: "reset",
    KeyC: "camera",
  } as Record<string, Action>,
  mouth: ["KeyB"],
};

/** A key has no travel: held, the stick ramps out; let go, it springs back. */
function ramp(value: number, minus: boolean, plus: boolean, dt: number): number {
  if (plus !== minus) {
    return Math.max(-1, Math.min(1, value + (plus ? 1 : -1) * 3 * dt));
  }
  const step = 5 * dt;
  return Math.abs(value) <= step ? 0 : value - Math.sign(value) * step;
}

export interface InputState {
  mode: PadMode;
  sticks: Sticks;
  mouth: number;
  /** The pad's name, or "" with none. */
  pad: string;
  /** Raw pad, for the readout. */
  frame: PadFrame | null;
  /** Actions pressed since the last update; `roulade` also while held (the chain). */
  actions: Action[];
  rouladeHeld: boolean;
}

export class DuckInput {
  mode: PadMode = "drive";
  private readonly held = new Set<string>();
  private readonly pressedKeys: string[] = [];
  private keySticks: Sticks = { lx: 0, ly: 0, rx: 0, ry: 0 };
  private padWas: boolean[] = [];
  padName = "";
  onConnect?: (name: string, connected: boolean) => void;

  constructor(target: Window = window) {
    target.addEventListener("keydown", (event) => {
      if (event.ctrlKey || event.altKey || event.metaKey) return;
      if (!event.repeat) this.pressedKeys.push(event.code);
      this.held.add(event.code);
      if (event.code.startsWith("Arrow") || event.code === "Space") event.preventDefault();
    });
    target.addEventListener("keyup", (event) => this.held.delete(event.code));
    target.addEventListener("blur", () => this.held.clear());
    target.addEventListener("gamepadconnected", (event) => this.onConnect?.((event as GamepadEvent).gamepad.id, true));
    target.addEventListener("gamepaddisconnected", (event) => {
      this.padWas = [];
      this.onConnect?.((event as GamepadEvent).gamepad.id, false);
    });
  }

  private any(codes: readonly string[]): boolean {
    return codes.some((c) => this.held.has(c));
  }

  /** The first pad the browser reports with the standard mapping, or any pad at all. */
  static findPad(): Gamepad | null {
    const pads = (navigator.getGamepads?.() ?? []).filter((p): p is Gamepad => !!p && p.connected);
    return pads.find((p) => p.mapping === "standard") ?? pads[0] ?? null;
  }

  update(dt: number): InputState {
    const k = KEYS;
    const ks = this.keySticks;
    ks.ly = ramp(ks.ly, this.any(k.lyDown), this.any(k.lyUp), dt);
    ks.lx = ramp(ks.lx, this.any(k.lxLeft), this.any(k.lxRight), dt);
    ks.ry = ramp(ks.ry, this.any(k.ryDown), this.any(k.ryUp), dt);
    ks.rx = ramp(ks.rx, this.any(k.rxLeft), this.any(k.rxRight), dt);

    const actions: Action[] = [];
    for (const code of this.pressedKeys.splice(0)) {
      const mode = k.modes[code];
      if (mode) this.mode = mode;
      const action = k.actions[code];
      if (action) actions.push(action);
    }
    let rouladeHeld = this.held.has("KeyV");
    let mouth = this.any(k.mouth) ? 1 : 0;

    const pad = DuckInput.findPad();
    let frame: PadFrame | null = null;
    const sticks: Sticks = { ...ks };
    if (pad) {
      frame = readPad(pad);
      this.padName = pad.id;
      const was = this.padWas;
      const pressed = (b: number): boolean => frame!.held[b] && !was[b];
      this.mode = modeFromDpad(pressed, this.mode);
      for (const [button, action] of BUTTON_ACTIONS) {
        if (pressed(button)) actions.push(action);
      }
      rouladeHeld ||= frame.held[BUTTON.square];
      mouth = Math.max(mouth, frame.lt, frame.rt);
      // Per axis, a stick out of its dead zone wins over the keys.
      for (const axis of ["lx", "ly", "rx", "ry"] as const) {
        if (Math.abs(frame.sticks[axis]) >= PAD_DEADZONE) sticks[axis] = frame.sticks[axis];
      }
      this.padWas = frame.held.slice();
    } else {
      this.padName = "";
    }
    return { mode: this.mode, sticks, mouth, pad: this.padName, frame, actions, rouladeHeld };
  }
}
