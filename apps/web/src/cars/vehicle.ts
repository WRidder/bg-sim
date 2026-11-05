/**
 * A car on a route, without any drawing: the FMU, the surface under each wheel, the barrier, the
 * clock. The FMU owns the ground (the race car's flat plane, the buggy's hills) and takes a friction
 * scale per wheel; a barrier is not in the FMU at all, so hitting one ends the drive here and the
 * car is put back by a fresh start.
 */

import type { FmuModel } from "../engine/fmu";
import { Fmu } from "../engine/fmu";
import { Sim } from "../engine/sim";
import { model as buggyModel } from "./buggy.gen";
import { hills } from "./hills";
import { model as racecarModel } from "./racecar.gen";
import { DRAG, GRIP, type Kind, type Place, type Surface, type Track } from "./track";

export const INPUTS = ["steer", "throttle", "brake", "reverse", "handbrake", "mu_fl", "mu_fr", "mu_rl", "mu_rr"] as const;
export const CORNERS = ["fl", "fr", "rl", "rr"] as const;
export type Corner = (typeof CORNERS)[number];

const POSE = ["px", "py", "pz", "qw", "qx", "qy", "qz"] as const;

export const OUTPUTS = [
  ...POSE.map((k) => `chassis_${k}` as const),
  "speed", "kmh", "u", "v", "ax_g", "ay_g", "yaw", "pitch", "roll", "yaw_rate", "beta",
  ...CORNERS.flatMap((c) => [
    ...POSE.map((k) => `${c}_${k}` as const),
    `${c}_spin`, `${c}_omega`, `${c}_fz`, `${c}_kappa`, `${c}_alpha`, `${c}_travel`, `${c}_xc`, `${c}_yc`, `${c}_zc`,
  ] as const),
  "steer_fl", "steer_fr", "motor_r_rpm", "motor_r_torque", "motor_r_tlim", "motor_r_power", "motor_r_regen",
  "soc", "battery_v", "battery_a", "battery_w",
] as const;
export type Output = (typeof OUTPUTS)[number];

export interface CarData {
  model: FmuModel;
  /** Chassis origin over the ground at rest, m. */
  rideHeight: number;
  /** Axle positions in the chassis frame, m. */
  front: number;
  rear: number;
  track: number;
  wheelRadius: number;
  /** Road-wheel angle at full lock, rad. */
  lock: number;
  wheelbase: number;
}

export const CARS: Record<Kind, CarData> = {
  racecar: { model: racecarModel, rideHeight: 0.3, front: 1.665, rear: -1.135, track: 1.6, wheelRadius: 0.33, lock: (20 * Math.PI) / 180, wheelbase: 2.8 },
  buggy: { model: buggyModel, rideHeight: 0.75, front: 1.553, rear: -1.147, track: 1.75, wheelRadius: 0.42, lock: (30 * Math.PI) / 180, wheelbase: 2.7 },
};

/** Height of the FMU's ground. */
export function groundOf(kind: Kind, x: number, y: number): number {
  return kind === "buggy" ? hills(x, y) : 0;
}

export type Sector = 0 | 1 | 2;

export interface Lap {
  time: number;
  valid: boolean;
  sectors: number[];
}

export class Vehicle extends Sim<Output> {
  /** Clock of the run: survives a recovery, which starts the FMU's own clock again. */
  clock = 0;
  /** Set when the car is through a barrier or has stopped being a car. */
  crashed = false;
  crashReason = "";
  /** Set once the run's clock is going. */
  running = false;
  readonly surfaces: Surface[] = ["asphalt", "asphalt", "asphalt", "asphalt"];
  readonly laps: Lap[] = [];
  best: number | null = null;
  lapStart = 0;
  lapValid = true;
  /** Distance travelled along the route this lap: a lap counts only if it went round. */
  progress = 0;
  /** Arc length of the chassis now. */
  s = 0;
  /** Lateral offset of the chassis now. */
  d = 0;
  /** Seconds with every wheel past the track's edge. */
  outside = 0;
  sectorStart = 0;
  sector: Sector = 0;
  sectors: number[] = [];
  /** Called on the run's events; the game makes them sound and show. */
  onLap: (lap: Lap) => void = () => {};
  onSector: (sector: number, time: number) => void = () => {};
  onInvalid: () => void = () => {};
  /** Called every step with the lap time, for the ghost. */
  onStep: (lapTime: number) => void = () => {};
  /** When set, drives the car: it runs before every step. */
  autopilot: ((car: Vehicle) => void) | null = null;
  /** Whatever a surface drags, on top of the driver's brake. */
  private pedal = 0;
  private hints: number[] = [-1, -1, -1, -1];
  private hint = -1;
  private previousS = 0;
  private flipped = 0;

  private constructor(
    fmu: Fmu,
    readonly kind: Kind,
    public track: Track,
  ) {
    super(fmu, INPUTS, OUTPUTS);
  }

  static async create(kind: Kind, track: Track): Promise<Vehicle> {
    return new Vehicle(await Fmu.load(CARS[kind].model), kind, track);
  }

  /** The chassis height for a start: on the highest ground under the wheels, plus a little. */
  private startHeight(x: number, y: number, yaw: number): number {
    const car = CARS[this.kind];
    const [c, s] = [Math.cos(yaw), Math.sin(yaw)];
    let top = -Infinity;
    for (const along of [car.front, car.rear]) {
      for (const across of [car.track / 2, -car.track / 2]) {
        top = Math.max(top, groundOf(this.kind, x + c * along - s * across, y + s * along + c * across));
      }
    }
    return top + car.rideHeight + 0.01;
  }

  /** Puts the car at rest at `s`, `d` along the route, with the charge it has. */
  place(s: number, d = 0, soc = 0.95): void {
    const { x, y, yaw } = this.track.pose(s, d);
    this.restart({ x0: x, y0: y, z0: this.startHeight(x, y, yaw), yaw0: yaw, soc0: Math.max(soc, 0.06) }, () => {
      this.u.fill(1, 5);
    });
    this.crashed = false;
    this.crashReason = "";
    this.flipped = 0;
    this.pedal = 0;
    this.outside = 0;
    this.hint = -1;
    this.hints.fill(-1);
    const place = this.track.locate(x, y);
    this.previousS = place.s;
    this.s = place.s;
    this.d = place.d;
  }

  /** Back to the grid, with the clock and the lap count at zero. */
  startRun(): void {
    const { gridBack } = this.track.definition;
    const side = this.track.width * 0.36 * (this.track.definition.car === "racecar" ? 1 : 0);
    this.place(this.track.length - gridBack, side);
    this.clock = 0;
    this.running = false;
    this.laps.length = 0;
    this.best = null;
    this.lapStart = 0;
    this.lapValid = true;
    this.progress = 0;
    this.sector = 0;
    this.sectorStart = 0;
    this.sectors = [];
  }

  /** The clock runs from here on. */
  go(): void {
    this.running = true;
  }

  /** After a crash: at rest on the route, facing the right way, with the clock still going. */
  recover(s: number): void {
    const soc = this.get("soc");
    this.lapValid = false;
    this.place(s, 0, soc);
  }

  setControls(steer: number, throttle: number, brake: number, handbrake = 0): void {
    this.u[0] = Math.max(-1, Math.min(1, steer));
    this.u[1] = Math.max(0, Math.min(1, throttle));
    this.pedal = Math.max(0, Math.min(1, brake));
    this.u[2] = this.pedal;
    this.u[4] = Math.max(0, Math.min(1, handbrake));
  }

  get reversing(): boolean {
    return this.u[3] > 0.5;
  }

  /** Forward or reverse, only at a standstill: true when it changed. */
  toggleReverse(): boolean {
    if (this.get("speed") > 1.5) {
      return false;
    }
    this.u[3] = this.u[3] > 0.5 ? 0 : 1;
    return true;
  }

  /** The time so far on the lap in progress. */
  get lapTime(): number {
    return this.clock - this.lapStart;
  }

  protected override beforeStep(): void {
    this.autopilot?.(this);
    let drag = 0;
    CORNERS.forEach((corner, i) => {
      const place: Place = this.track.locate(this.get(`${corner}_xc`), this.get(`${corner}_yc`), this.hints[i]);
      this.hints[i] = place.index;
      const surface = this.track.surface(place);
      this.surfaces[i] = surface;
      this.u[5 + i] = GRIP[surface];
      drag += (DRAG[surface] ?? 0) / 4;
    });
    this.u[2] = Math.min(1, this.pedal + (this.get("speed") > 2 ? drag : 0));
  }

  protected override afterStep(healthy: boolean): void {
    if (!healthy) {
      this.crash("The car stopped making sense");
      return;
    }
    const dt = this.fmu.step;
    if (this.running) {
      this.clock += dt;
    }
    const place = this.track.locate(this.get("chassis_px"), this.get("chassis_py"), this.hint);
    this.hint = place.index;
    this.s = place.s;
    this.d = place.d;
    this.follow(place);
    if (this.track.throughWall(place) > 0) {
      this.crash("barrier");
    }
    // Upside down, or on its side, and staying there.
    const [w, x, y] = [this.get("chassis_qw"), this.get("chassis_qx"), this.get("chassis_qy")];
    const up = 1 - 2 * (x * x + y * y);
    this.flipped = up < 0.25 && w === w ? this.flipped + dt : 0;
    if (this.flipped > 1.6) {
      this.crash("rolled");
    }
    if (this.running) {
      this.onStep(this.lapTime);
    }
  }

  /** The lap count, from the arc length alone: a forward crossing after most of a lap. */
  private follow(place: Place): void {
    const { length } = this.track;
    let ds = place.s - this.previousS;
    let crossed = false;
    if (ds < -0.5 * length) {
      ds += length;
      crossed = true;
    } else if (ds > 0.5 * length) {
      ds -= length;
    }
    this.previousS = place.s;
    this.progress += ds;
    if (!this.running) {
      return;
    }
    // A wheel on the kerb is fine; a lap that left the circuit does not count.
    const racing = this.kind === "racecar";
    const off = this.surfaces.every((surface) => surface === "grass" || surface === "gravel" || surface === "runoff" || (!racing && surface === "scrub"));
    this.outside = off ? this.outside + this.fmu.step : 0;
    if (this.outside > 0.25 && this.lapValid) {
      this.lapValid = false;
      this.onInvalid();
    }
    const next = this.sector + 1;
    if (next < 3 && place.s > (next / 3) * length && place.s < ((next + 0.2) / 3) * length && ds > 0) {
      const time = this.clock - this.sectorStart;
      this.sectors.push(time);
      this.sectorStart = this.clock;
      this.sector = next as Sector;
      this.onSector(next - 1, time);
    }
    if (crossed && this.progress > 0.6 * length) {
      this.finishLap();
    }
  }

  private finishLap(): void {
    const time = this.lapTime;
    this.sectors.push(this.clock - this.sectorStart);
    const lap: Lap = { time, valid: this.lapValid, sectors: this.sectors };
    this.laps.push(lap);
    if (lap.valid && (this.best === null || time < this.best)) {
      this.best = time;
    }
    this.lapStart = this.clock;
    this.sectorStart = this.clock;
    this.sectors = [];
    this.sector = 0;
    this.lapValid = true;
    this.progress = 0;
    this.onLap(lap);
  }

  private crash(reason: string): void {
    this.crashed = true;
    this.crashReason = reason;
    this.stopped = true;
  }
}
