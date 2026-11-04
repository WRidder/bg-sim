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
      if (pad && map.axis < pad.axes.length) {
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
    const pressed: Record<Control, boolean> = {
      pitch: this.any(k.pull) || this.any(k.push),
      roll: this.any(k.left) || this.any(k.right),
      yaw: this.any(k.yawLeft) || this.any(k.yawRight),
      throttle: this.any(k.throttleUp) || this.any(k.throttleDown),
    };
    const board = this.keyboard;
    board.pitch = this.axis(board.pitch, this.any(k.push), this.any(k.pull), dt);
    board.roll = this.axis(board.roll, this.any(k.left), this.any(k.right), dt);
    board.yaw = this.axis(board.yaw, this.any(k.yawLeft), this.any(k.yawRight), dt);
    const step = this.rates.throttle * dt;
    if (this.any(k.throttleUp)) {
      board.throttle = Math.min(1, board.throttle + step);
    }
    if (this.any(k.throttleDown)) {
      board.throttle = Math.max(0, board.throttle - step);
    }
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
