/**
 * Steering wheel and pedals from a keyboard or a pad. The engine's controls are a pilot's: this has
 * two one-way pedals, and a steering range that closes as the speed rises. At 250 km/h the same key
 * must not ask for the lock of a hairpin, or nobody could drive with one.
 *
 * A gamepad is laid out as in Gran Turismo: the left stick (or the D-pad) steers, R2 is the
 * accelerator and L2 the brake, Circle the handbrake, Triangle reverse, L1 looks behind, R1 changes
 * the view, the right stick looks round and Options pauses. Cross answers a menu, Create restarts.
 */

import { type AxisMap, mapAxis, PAD, PadState } from "../engine/input";

const PAD_STEER: AxisMap = { axis: 0, invert: false, deadzone: 0.07, expo: 0.45 };

export interface Pressed {
  steer: number;
  throttle: number;
  brake: number;
  handbrake: number;
}

export class Pedals {
  readonly value: Pressed = { steer: 0, throttle: 0, brake: 0, handbrake: 0 };
  /** Called once per press of these pad buttons. */
  onButton: (name: "view" | "pause" | "reverse" | "reset" | "confirm") => void = () => {};
  deviceName = "";
  /** The pad's right stick, -1..1 each way, and whether L1 is held to look behind. */
  readonly look = { x: 0, y: 0, behind: false };
  private readonly pad = new PadState();
  private readonly held = new Set<string>();
  private board = 0;
  private device: "keys" | "pad" = "keys";

  constructor() {
    addEventListener("keydown", (event) => {
      this.held.add(event.code);
      this.device = "keys";
      if (event.code.startsWith("Arrow") || event.code === "Space") {
        event.preventDefault();
      }
    });
    addEventListener("keyup", (event) => this.held.delete(event.code));
    addEventListener("blur", () => this.held.clear());
  }

  private any(...codes: string[]): boolean {
    return codes.some((code) => this.held.has(code));
  }

  /** Reads the pad, once a frame in every phase: its buttons work in the menus too. */
  poll(): void {
    const pad = this.pad;
    pad.update();
    this.look.x = pad.axis(2);
    this.look.y = pad.axis(3);
    this.look.behind = pad.held(PAD.LB);
    if (!pad.connected) {
      return;
    }
    this.deviceName = pad.id;
    if (pad.pressed(PAD.RB)) {
      this.onButton("view");
    }
    if (pad.pressed(PAD.START)) {
      this.onButton("pause");
    }
    if (pad.pressed(PAD.Y)) {
      this.onButton("reverse");
    }
    if (pad.pressed(PAD.BACK)) {
      this.onButton("reset");
    }
    if (pad.pressed(PAD.A)) {
      this.onButton("confirm");
    }
  }

  /** `reach` is the share of full lock that is still useful at this speed. */
  update(dt: number, reach: number): void {
    const left = this.any("ArrowLeft", "KeyA");
    const right = this.any("ArrowRight", "KeyD");
    const up = this.any("ArrowUp", "KeyW");
    const down = this.any("ArrowDown", "KeyS");
    const hand = this.any("Space");
    const wanted = left === right ? 0 : left ? -1 : 1;
    // Quicker back to the centre than out of it, as a driver's hands are.
    const rate = wanted === 0 || wanted * this.board < 0 ? 7 : 3.4;
    const step = rate * dt;
    this.board = Math.abs(wanted - this.board) <= step ? wanted : this.board + Math.sign(wanted - this.board) * step;
    const v = this.value;
    const eased = (from: number, to: number, seconds: number): number => from + Math.max(-dt / seconds, Math.min(dt / seconds, to - from));
    let steer = this.board * reach;
    let throttle = eased(v.throttle, up ? 1 : 0, up ? 0.18 : 0.06);
    let brake = eased(v.brake, down ? 1 : 0, down ? 0.1 : 0.06);
    let handbrake = hand ? 1 : 0;

    const pad = this.pad;
    if (pad.connected) {
      // The D-pad steers as the stick does at full throw, as it does in Gran Turismo.
      const cross = (pad.held(PAD.RIGHT) ? 1 : 0) - (pad.held(PAD.LEFT) ? 1 : 0);
      const stick = cross !== 0 ? cross : mapAxis(pad.rawAxis(0), PAD_STEER);
      const gas = pad.value(PAD.RT);
      const stop = pad.value(PAD.LT);
      if (Math.abs(stick) > 0.02 || gas > 0.02 || stop > 0.02) {
        this.device = "pad";
      }
      if (this.device === "pad") {
        steer = stick * Math.min(1, reach * 1.3);
        throttle = gas;
        brake = stop;
        handbrake = pad.held(PAD.B) ? 1 : handbrake;
      }
    }
    v.steer = steer;
    v.throttle = throttle;
    v.brake = brake;
    v.handbrake = handbrake;
  }

  reset(): void {
    this.board = 0;
    Object.assign(this.value, { steer: 0, throttle: 0, brake: 0, handbrake: 0 });
  }
}
