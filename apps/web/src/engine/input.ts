/**
 * Pilot inputs: keyboard with spring-back sticks, and whatever the Gamepad API offers. Per control
 * the input touched last wins, so a pad that sits centred never locks the keyboard out. A held key
 * ramps the stick rather than jumping it, because a keyboard has no travel of its own.
 */

export type Control = "pitch" | "roll" | "yaw" | "throttle";
const CONTROLS: readonly Control[] = ["pitch", "roll", "yaw", "throttle"];

export interface AxisMap {
  axis: number;
  invert: boolean;
  deadzone: number;
  expo: number;
  /** A lever that reads 0..1 rather than -1..1. */
  unipolar?: boolean;
  /** Part of a device's name; empty for the first device. */
  device?: string;
  /** Only for a device without the browser's standard mapping: a stick, not a gamepad. */
  stickOnly?: boolean;
}

export type Bindings = Partial<Record<Control, AxisMap>>;

/** Dead zone, rescaled so full deflection stays full, and expo: linear blended with cubic. */
export function shape(value: number, deadzone: number, expo: number): number {
  const v = Math.max(-1, Math.min(1, value));
  const a = Math.abs(v);
  if (a <= deadzone) {
    return 0;
  }
  const r = (a - deadzone) / (1 - deadzone);
  const curved = (1 - expo) * r + expo * r ** 3;
  return v > 0 ? curved : -curved;
}

export function mapAxis(raw: number, map: AxisMap): number {
  const value = map.invert ? -raw : raw;
  return map.unipolar ? Math.min(1, Math.max(0, 0.5 * (value + 1))) : shape(value, map.deadzone, map.expo);
}

export interface KeyMap {
  pull: string[];
  push: string[];
  left: string[];
  right: string[];
  yawLeft: string[];
  yawRight: string[];
  throttleUp: string[];
  throttleDown: string[];
}

export const STANDARD_PAD: Bindings = {
  roll: { axis: 0, invert: false, deadzone: 0.08, expo: 0.35 },
  pitch: { axis: 1, invert: true, deadzone: 0.08, expo: 0.35 },
  yaw: { axis: 2, invert: false, deadzone: 0.1, expo: 0.3 },
};

/** Button numbers of a gamepad with the browser's standard mapping (Xbox names; PlayStation in the comments). */
export const PAD = {
  A: 0,      // Cross
  B: 1,      // Circle
  X: 2,      // Square
  Y: 3,      // Triangle
  LB: 4,     // L1
  RB: 5,     // R1
  LT: 6,     // L2
  RT: 7,     // R2
  BACK: 8,   // Create
  START: 9,  // Options
  L3: 10,
  R3: 11,
  UP: 12,
  DOWN: 13,
  LEFT: 14,
  RIGHT: 15,
} as const;

/** Pad buttons that move a control the way held keys do. The triggers are analogue: half way is half the rate. */
export interface PadButtons {
  yawLeft?: number;
  yawRight?: number;
  throttleUp?: number;
  throttleDown?: number;
}

/**
 * The stick and trigger layout of Ace Combat 7 with expert handling: the left stick pitches and
 * rolls (back is nose up), the bumpers yaw, the right trigger adds throttle and the left one takes
 * it off. The right stick is left free for the camera. A device without the standard mapping (a
 * flight stick) keeps its twist axis for the rudder.
 */
export const ACE_PAD: Bindings = {
  roll: { axis: 0, invert: false, deadzone: 0.1, expo: 0.35 },
  pitch: { axis: 1, invert: false, deadzone: 0.1, expo: 0.35 },
  yaw: { axis: 2, invert: false, deadzone: 0.1, expo: 0.3, stickOnly: true },
};
export const ACE_BUTTONS: PadButtons = { yawLeft: PAD.LB, yawRight: PAD.RB, throttleUp: PAD.RT, throttleDown: PAD.LT };

/** The first gamepad with the standard mapping, read once a frame: how far a button is in, and which went down this frame. */
export class PadState {
  id = "";
  connected = false;
  private values: number[] = [];
  private before: number[] = [];
  private axes: readonly number[] = [];

  update(): void {
    const pad = (navigator.getGamepads?.() ?? []).find((p) => p && p.connected && p.mapping === "standard");
    [this.before, this.values] = [this.values, this.before];
    this.connected = Boolean(pad);
    this.id = pad?.id ?? "";
    this.values.length = 0;
    if (pad) {
      for (const button of pad.buttons) {
        this.values.push(Math.max(button.value, button.pressed ? 1 : 0));
      }
    }
    this.axes = pad?.axes ?? [];
  }

  /** 0..1: how far the button is in. */
  value(button: number | undefined): number {
    return button === undefined ? 0 : this.values[button] ?? 0;
  }

  held(button: number | undefined): boolean {
    return this.value(button) > 0.5;
  }

  /** True in the one frame the button went down. */
  pressed(button: number): boolean {
    return this.held(button) && !((this.before[button] ?? 0) > 0.5);
  }

  /** A stick axis as the pad gives it, for a caller with a shape of its own. */
  rawAxis(index: number): number {
    return this.axes[index] ?? 0;
  }

  /** A stick axis with its dead zone taken out, -1..1. */
  axis(index: number, deadzone = 0.12): number {
    return shape(this.axes[index] ?? 0, deadzone, 0);
  }
}

/** Seconds for the camera to ease most of the way to where a pad's right stick points. */
export const LOOK_EASE = 0.3;

const MOVE = 0.05;

export class Controls {
  readonly value: Record<Control, number> = { pitch: 0, roll: 0, yaw: 0, throttle: 0 };
  /** Set by a key or a lever; held between presses. */
  private keyboard: Record<Control, number> = { pitch: 0, roll: 0, yaw: 0, throttle: 0 };
  private readonly held = new Set<string>();
  private readonly source: Partial<Record<Control, "keys" | "device">> = {};
  private readonly anchor: Partial<Record<Control, number>> = {};
  deviceName = "";

  constructor(
    private readonly keys: KeyMap,
    private readonly bindings: Bindings,
    private readonly rates = { stick: 2.6, spring: 3.6, throttle: 0.42 },
    /** A pad the game reads each frame, and which of its buttons work a control. */
    private readonly pad: PadState | null = null,
    private readonly buttons: PadButtons = {},
  ) {
    addEventListener("keydown", (event) => {
      this.held.add(event.code);
      if (event.code.startsWith("Arrow") || event.code.startsWith("Page")) {
        event.preventDefault();
      }
    });
    addEventListener("keyup", (event) => this.held.delete(event.code));
    addEventListener("blur", () => this.held.clear());
  }

  private any(codes: string[]): boolean {
    return codes.some((code) => this.held.has(code));
  }

  private axis(value: number, minus: boolean, plus: boolean, dt: number): number {
    if (plus !== minus) {
      return Math.max(-1, Math.min(1, value + (plus ? 1 : -1) * this.rates.stick * dt));
    }
    const step = this.rates.spring * dt;
    return Math.abs(value) <= step ? 0 : value - Math.sign(value) * step;
  }

  private device(): Partial<Record<Control, number>> {
    const found: Partial<Record<Control, number>> = {};
    const pads = navigator.getGamepads?.() ?? [];
    for (const control of CONTROLS) {
      const map = this.bindings[control];
      if (!map) {
        continue;
      }
      const pad = pads.find((p) => p && (!map.device || p.id.toLowerCase().includes(map.device)));
      if (pad && map.axis < pad.axes.length && !(map.stickOnly && pad.mapping === "standard")) {
        found[control] = mapAxis(pad.axes[map.axis], map);
        this.deviceName = pad.id;
      }
    }
    return found;
  }

  setThrottle(value: number): void {
    this.keyboard.throttle = value;
    this.value.throttle = value;
  }

  update(dt: number): void {
    const k = this.keys;
    const { buttons, pad } = this;
    // A pad's bumpers and triggers count as keys: they ramp a control, they do not set it.
    const yawLeft = this.any(k.yawLeft) || Boolean(pad?.held(buttons.yawLeft));
    const yawRight = this.any(k.yawRight) || Boolean(pad?.held(buttons.yawRight));
    const more = Math.max(this.any(k.throttleUp) ? 1 : 0, pad?.value(buttons.throttleUp) ?? 0);
    const less = Math.max(this.any(k.throttleDown) ? 1 : 0, pad?.value(buttons.throttleDown) ?? 0);
    const pressed: Record<Control, boolean> = {
      pitch: this.any(k.pull) || this.any(k.push),
      roll: this.any(k.left) || this.any(k.right),
      yaw: yawLeft || yawRight,
      throttle: more > 0.05 || less > 0.05,
    };
    const board = this.keyboard;
    board.pitch = this.axis(board.pitch, this.any(k.push), this.any(k.pull), dt);
    board.roll = this.axis(board.roll, this.any(k.left), this.any(k.right), dt);
    board.yaw = this.axis(board.yaw, yawLeft, yawRight, dt);
    const step = this.rates.throttle * dt;
    board.throttle = Math.max(0, Math.min(1, board.throttle + step * (more - less)));
    const devices = this.device();
    for (const control of CONTROLS) {
      const device = devices[control];
      if (device === undefined) {
        this.value[control] = board[control];
        continue;
      }
      let source = this.source[control] ?? "device";
      if (pressed[control] && source !== "keys") {
        if (control === "throttle") {
          board.throttle = device; // carry on from the lever's setting
        }
        source = "keys";
        this.anchor[control] = device;
      } else if (source === "keys" && !pressed[control] && Math.abs(device - (this.anchor[control] ?? device)) > MOVE) {
        source = "device";
      }
      this.source[control] = source;
      this.value[control] = source === "keys" ? board[control] : device;
    }
  }
}
