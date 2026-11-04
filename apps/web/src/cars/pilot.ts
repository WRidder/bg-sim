/**
 * The scripted driver of the title screen and the tests: pure pursuit along the racing line, with
 * the pedals on the planned speed and a driver's feel for the friction circle, as in the desktop
 * app's scripts.
 */

import type { Line } from "./line";
import type { Track } from "./track";
import { CARS, type Vehicle } from "./vehicle";

export class Pilot {
  /** Share of the planned speed to drive at. */
  pace = 0.97;
  private index = -1;
  private steer = 0;

  constructor(
    private readonly track: Track,
    private readonly line: Line,
  ) {}

  reset(): void {
    this.index = -1;
    this.steer = 0;
  }

  /** Sets the car's controls for the next step. */
  drive(car: Vehicle): void {
    const { line, track } = this;
    const { n } = track;
    const data = CARS[car.kind];
    const x = car.get("chassis_px");
    const y = car.get("chassis_py");
    const speed = car.get("speed");
    const yaw = car.get("yaw");
    this.index = track.locate(x, y, this.index).index;
    const reach = Math.round(7 + 0.42 * speed);
    const j = (this.index + reach) % n;
    const dx = line.x[j] - x;
    const dy = line.y[j] - y;
    const [c, s] = [Math.cos(yaw), Math.sin(yaw)];
    const lx = c * dx + s * dy;
    const ly = -s * dx + c * dy;
    const delta = Math.atan2(2 * data.wheelbase * ly, lx * lx + ly * ly);
    const aloft = car.get("fl_fz") + car.get("fr_fz") < 200;
    // Hands still in the air: a wheel turned for the landing throws the car over.
    const steer = (this.steer += ((aloft ? 0 : -delta / data.lock) - this.steer) * 0.2);

    let wanted = Infinity;
    for (let k = 2; k < 12 + speed * 0.5; k += 3) {
      wanted = Math.min(wanted, line.speed[(this.index + k) % n]);
    }
    wanted *= this.pace;
    const error = wanted - speed;
    let throttle = error > -0.5 ? Math.min(1, 0.35 * error + 0.15) : 0;
    const brake = error < -0.8 ? Math.min(1, -0.22 * error) : 0;
    const grip = car.kind === "racecar" ? 1.5 : 0.85;
    throttle *= Math.max(0.1, Math.min(1, (grip + 0.2 - Math.abs(car.get("ay_g"))) / 0.4));
    if (speed > 4) {
      throttle *= Math.max(0, Math.min(1, 1 - (Math.abs(car.get("beta")) - 0.03) / 0.05));
    }
    car.setControls(steer, throttle, brake);
  }
}
