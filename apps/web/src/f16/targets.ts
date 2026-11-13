/**
 * The tactical layer of the F-16 interception mode, without three.js: the target drones, their
 * spawn/respawn rule and the seeker cue. It mirrors `apps/f16-sim/src/f16sim/tactical.py`, with
 * the web game's world coordinates (north and east in metres, altitude up).
 */

export const MAX_DRONES = 3;
export const SPAWN_DELAY = 4;
export const SEEKER_FOV_DEG = 90;
export const SEEKER_HALF_DEG = SEEKER_FOV_DEG * 0.5;
export const SEEKER_RANGE_M = 7000;
export const SEEKER_TRACK_S = 1;

export interface Drone {
  id: number;
  north: number;
  east: number;
  alt: number;
  heading: number;
  speed: number;
  turnRate: number;
  turnAt: number;
  age: number;
  alive: boolean;
}

export interface Contact {
  id: number;
  north: number;
  east: number;
  alt: number;
  range: number;
  selected: boolean;
  locked: boolean;
}

export interface LockState {
  selectedId: number | null;
  locked: boolean;
  progress: number;
  angleDeg: number;
  rangeM: number;
  inFov: boolean;
  reason: string;
}

type Ground = (north: number, east: number) => number;

/** Small deterministic generator, so a unit test gets the same drones on every run. */
function generator(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (Math.imul(1664525, state) + 1013904223) >>> 0;
    return state / 0x100000000;
  };
}

export class DroneManager {
  readonly drones: Drone[] = [];
  private nextId = 1;
  private respawnIn = 0;
  private random = generator(17);
  private own = { north: 0, east: 0, alt: 1000, heading: 0 };

  constructor(
    private readonly ground: Ground,
    readonly max = MAX_DRONES,
  ) {}

  reset(north: number, east: number, alt: number, heading: number): void {
    this.drones.length = 0;
    this.nextId = 1;
    this.respawnIn = 0;
    this.random = generator(17);
    this.own = { north, east, alt, heading };
    for (let k = 0; k < this.max; k += 1) {
      this.spawn(north, east, alt, heading, k);
    }
  }

  clear(): void {
    this.drones.length = 0;
    this.respawnIn = 0;
  }

  spawn(north: number, east: number, alt: number, heading: number, slot?: number): Drone | null {
    if (this.alive().length >= this.max) {
      return null;
    }
    const at = slot ?? this.alive().length;
    const bearings = [0, -32, 32, -58, 58];
    let bearing = heading + bearings[at % bearings.length];
    if (at > 0) {
      bearing += this.random() * 12 - 6;
    }
    const distance = 1500 + 500 * (at % 3) + this.random() * 250 - 100;
    const radians = (bearing * Math.PI) / 180;
    const n = north + distance * Math.cos(radians);
    const e = east + distance * Math.sin(radians);
    const h = Math.max(
      alt + (at > 0 ? this.random() * 240 - 120 : 0),
      350,
      this.ground(n, e) + 350,
    );
    const drone: Drone = {
      id: this.nextId,
      north: n,
      east: e,
      alt: h,
      heading: bearing + (at > 0 ? this.random() * 24 - 12 : 0),
      speed: 85 + this.random() * 30,
      turnRate: this.random() < 0.5 ? -1.4 : 1.4,
      turnAt: 6 + this.random() * 5,
      age: 0,
      alive: true,
    };
    this.nextId += 1;
    this.drones.push(drone);
    return drone;
  }

  step(dt: number, north: number, east: number, alt: number, heading: number): void {
    this.own = { north, east, alt, heading };
    for (const drone of this.drones) {
      if (!drone.alive) {
        continue;
      }
      drone.age += dt;
      if (drone.age >= drone.turnAt) {
        drone.heading += drone.turnRate * dt;
      }
      const radians = (drone.heading * Math.PI) / 180;
      drone.north += drone.speed * Math.cos(radians) * dt;
      drone.east += drone.speed * Math.sin(radians) * dt;
    }
    if (this.alive().length < this.max) {
      this.respawnIn -= dt;
      if (this.respawnIn <= 0) {
        this.spawn(north, east, alt, heading);
        this.respawnIn = SPAWN_DELAY;
      }
    }
  }

  kill(id: number): Drone | null {
    const drone = this.byId(id);
    if (drone && drone.alive) {
      drone.alive = false;
      this.respawnIn = SPAWN_DELAY;
      return drone;
    }
    return null;
  }

  alive(): Drone[] {
    return this.drones.filter((drone) => drone.alive);
  }

  byId(id: number | null): Drone | null {
    if (id === null) {
      return null;
    }
    return this.drones.find((drone) => drone.id === id) ?? null;
  }

  contacts(selectedId: number | null, locked: boolean): Contact[] {
    return this.alive().map((drone) => ({
      id: drone.id,
      north: drone.north,
      east: drone.east,
      alt: drone.alt,
      range: Math.hypot(drone.north - this.own.north, drone.east - this.own.east, drone.alt - this.own.alt),
      selected: drone.id === selectedId,
      locked: drone.id === selectedId && locked,
    }));
  }
}

export class LockOn {
  selectedId: number | null = null;
  progress = 0;
  locked = false;
  angleDeg = 180;
  rangeM = 0;
  inFov = false;
  reason = "NO TARGET";

  constructor(
    readonly fovHalfDeg = SEEKER_HALF_DEG,
    readonly maxRangeM = SEEKER_RANGE_M,
    readonly trackS = SEEKER_TRACK_S,
  ) {}

  reset(): void {
    this.selectedId = null;
    this.progress = 0;
    this.locked = false;
    this.angleDeg = 180;
    this.rangeM = 0;
    this.inFov = false;
    this.reason = "NO TARGET";
  }

  private geometry(drone: Drone, own: readonly [number, number, number], nose: readonly [number, number, number]): [number, number] {
    const dn = drone.north - own[0];
    const de = drone.east - own[1];
    const dh = drone.alt - own[2];
    const range = Math.hypot(dn, de, dh);
    if (range < 1) {
      return [180, 0];
    }
    const los = [dn / range, de / range, -dh / range];
    const dot = Math.max(-1, Math.min(1, los[0] * nose[0] + los[1] * nose[1] + los[2] * nose[2]));
    return [(Math.acos(dot) * 180) / Math.PI, range];
  }

  update(
    dt: number,
    own: readonly [number, number, number],
    nose: readonly [number, number, number],
    drones: DroneManager,
  ): LockState {
    const selected = drones.byId(this.selectedId);
    if (!selected || !selected.alive) {
      this.selectedId = null;
      this.progress = 0;
    }
    if (this.selectedId === null) {
      let best: { id: number; angle: number } | null = null;
      for (const drone of drones.alive()) {
        const [angle, range] = this.geometry(drone, own, nose);
        if (range <= this.maxRangeM && angle <= this.fovHalfDeg && (!best || angle < best.angle)) {
          best = { id: drone.id, angle };
        }
      }
      if (best) {
        this.selectedId = best.id;
        this.progress = 0;
      }
    }
    if (this.selectedId === null) {
      this.locked = false;
      this.reason = "NO TARGET";
      return this.state();
    }
    const target = drones.byId(this.selectedId);
    if (!target) {
      this.selectedId = null;
      this.locked = false;
      this.reason = "NO TARGET";
      return this.state();
    }
    [this.angleDeg, this.rangeM] = this.geometry(target, own, nose);
    this.inFov = this.angleDeg <= this.fovHalfDeg && this.rangeM <= this.maxRangeM;
    if (this.inFov) {
      this.progress = Math.min(1, this.progress + dt / this.trackS);
      this.reason = this.progress >= 1 ? "LOCK" : "SEEKER";
    } else {
      this.progress = Math.max(0, this.progress - 3 * dt);
      this.reason = this.rangeM <= this.maxRangeM ? "OUT OF FOV" : "TOO FAR";
    }
    this.locked = this.progress >= 1;
    return this.state();
  }

  state(): LockState {
    return {
      selectedId: this.selectedId,
      locked: this.locked,
      progress: this.progress,
      angleDeg: this.angleDeg,
      rangeM: this.rangeM,
      inFov: this.inFov,
      reason: this.reason,
    };
  }

  cycle(drones: DroneManager): void {
    const ids = drones.alive().map((drone) => drone.id).sort((a, b) => a - b);
    if (ids.length === 0) {
      this.reset();
      return;
    }
    const at = this.selectedId === null ? -1 : ids.indexOf(this.selectedId);
    this.selectedId = ids[(at + 1) % ids.length];
    this.progress = 0;
    this.locked = false;
  }

  consume(): void {
    this.progress = 0;
    this.locked = false;
  }
}
