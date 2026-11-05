/**
 * The pilot's hands. Two hands on a keyboard fit a helicopter better than one: the arrows are the
 * cyclic, W and S the lever, A and D the pedals. Unlike the fixed-wing games the lever needs its own
 * memory, and the cyclic a trim: a real one stays where it is left, so Space moves the centre the
 * sticks spring back to. A gamepad's left stick is the cyclic, the right stick the pedals and lever,
 * the triggers the lever too. Per control the input touched last wins, as in the other games.
 */

import { shape } from "../engine/input";
import type { Sticks } from "./pilot";

const KEYS = {
  fore: ["ArrowUp"],
  aft: ["ArrowDown"],
  left: ["ArrowLeft"],
  right: ["ArrowRight"],
  yawLeft: ["KeyA", "KeyQ", "KeyZ"],
  yawRight: ["KeyD", "KeyE", "KeyX"],
  up: ["KeyW", "PageUp", "Equal", "NumpadAdd"],
  down: ["KeyS", "PageDown", "Minus", "NumpadSubtract"],
};

const CAPTURED = new Set(["Space", "PageUp", "PageDown"]);
const STICK = 1.7;
const SPRING = 3.4;
/** The lever's speed from a key or a stick, in full travel per second. */
const LEVER = 0.28;
const MOVE = 0.08;

export class Controls {
  /** Each -1..1, after the trim. */
  readonly sticks: Sticks = { fore: 0, side: 0, pedals: 0, lift: 0 };
  /** Where the lever stands, 0..1, for when nothing flies it. */
  lever = 0;
  trimFore = 0;
  trimSide = 0;
  deviceName = "";
  private readonly held = new Set<string>();
  private readonly board = { fore: 0, side: 0, pedals: 0, lift: 0 };
  private readonly usingPad = { fore: false, side: false, pedals: false, lift: false };
  private readonly pad = { fore: 0, side: 0, pedals: 0, lift: 0 };
  private padPressed = new Set<number>();
  /** Called as a pad's button goes down. */
  onButton: (button: number) => void = () => {};

  constructor() {
    addEventListener("keydown", (event) => {
      this.held.add(event.code);
      if (event.code.startsWith("Arrow") || CAPTURED.has(event.code)) {
        event.preventDefault();
      }
    });
    addEventListener("keyup", (event) => this.held.delete(event.code));
    addEventListener("blur", () => this.held.clear());
  }

  private any(codes: readonly string[]): boolean {
    return codes.some((code) => this.held.has(code));
  }

  get braking(): boolean {
    return this.held.has("Space") || this.padPressed.has(0);
  }

  private axis(value: number, minus: boolean, plus: boolean, dt: number): number {
    if (plus !== minus) {
      return Math.max(-1, Math.min(1, value + (plus ? 1 : -1) * STICK * dt));
    }
    const step = SPRING * dt;
    return Math.abs(value) <= step ? 0 : value - Math.sign(value) * step;
  }

  /** The middle of the cyclic moves to where it is now. */
  forceTrim(): void {
    this.trimFore = this.clamp(this.trimFore + this.board.fore);
    this.trimSide = this.clamp(this.trimSide + this.board.side);
    this.board.fore = 0;
    this.board.side = 0;
  }

  private clamp(value: number): number {
    return Math.max(-1, Math.min(1, value));
  }

  reset(lever: number): void {
    this.lever = lever;
    this.trimFore = 0;
    this.trimSide = 0;
    this.board.fore = this.board.side = this.board.pedals = this.board.lift = 0;
  }

  private readPad(): boolean {
    const pad = (navigator.getGamepads?.() ?? []).find((p) => p);
    if (!pad || pad.axes.length < 2) {
      return false;
    }
    this.deviceName = pad.id;
    this.pad.side = shape(pad.axes[0], 0.08, 0.35);
    this.pad.fore = shape(-pad.axes[1], 0.08, 0.35);
    this.pad.pedals = pad.axes.length > 2 ? shape(pad.axes[2], 0.1, 0.3) : 0;
    const triggers = (pad.buttons[7]?.value ?? 0) - (pad.buttons[6]?.value ?? 0);
    this.pad.lift = Math.abs(triggers) > 0.05 ? triggers : pad.axes.length > 3 ? shape(-pad.axes[3], 0.1, 0.3) : 0;
    const down = new Set<number>();
    pad.buttons.forEach((button, i) => {
      if (button.pressed) {
        down.add(i);
        if (!this.padPressed.has(i)) {
          this.onButton(i);
        }
      }
    });
    this.padPressed = down;
    return true;
  }

  update(dt: number): void {
    const k = KEYS;
    const board = this.board;
    board.fore = this.axis(board.fore, this.any(k.aft), this.any(k.fore), dt);
    board.side = this.axis(board.side, this.any(k.left), this.any(k.right), dt);
    board.pedals = this.axis(board.pedals, this.any(k.yawLeft), this.any(k.yawRight), dt);
    // The lever's key is on or off: a ramp would only delay it.
    board.lift = (this.any(k.up) ? 1 : 0) - (this.any(k.down) ? 1 : 0);
    const pressed = {
      fore: this.any(k.fore) || this.any(k.aft),
      side: this.any(k.left) || this.any(k.right),
      pedals: this.any(k.yawLeft) || this.any(k.yawRight),
      lift: this.any(k.up) || this.any(k.down),
    };
    const hasPad = this.readPad();
    for (const control of ["fore", "side", "pedals", "lift"] as const) {
      if (hasPad && pressed[control]) {
        this.usingPad[control] = false;
      } else if (hasPad && Math.abs(this.pad[control]) > MOVE) {
        this.usingPad[control] = true;
      }
      this.sticks[control] = this.usingPad[control] ? this.pad[control] : board[control];
    }
    this.sticks.fore = this.clamp(this.sticks.fore + this.trimFore);
    this.sticks.side = this.clamp(this.sticks.side + this.trimSide);
    this.lever = Math.max(0, Math.min(1, this.lever + this.sticks.lift * LEVER * dt));
  }
}
