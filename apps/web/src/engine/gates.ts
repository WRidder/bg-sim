/** A course of gates in the air: what counts as going through one, the clock and the score. */

export interface Gate {
  north: number;
  east: number;
  alt: number;
  heading: number;
  radius: number;
  passed: boolean;
  hit: boolean;
  /** How far from the centre the aircraft went through, in metres. */
  miss: number;
}

type Ground = (north: number, east: number) => number;

/**
 * Builds gates from north, east and height above the ground. Each one faces along the course and,
 * unless it is meant to be flown low, clears the ground on the way in and out of it.
 */
export function buildCourse(points: readonly (readonly [number, number, number])[], ground: Ground, radius: number, lowest = 70): Gate[] {
  return points.map(([north, east, height], i) => {
    const before = points[Math.max(i - 1, 0)];
    const after = points[Math.min(i + 1, points.length - 1)];
    const heading = (Math.atan2(after[1] - before[1], after[0] - before[0]) * 180) / Math.PI;
    let highest = ground(north, east);
    if (height > lowest) {
      for (const [n, e] of [before, after]) {
        for (const t of [0.1, 0.2, 0.3]) {
          highest = Math.max(highest, ground(north + (n - north) * t, east + (e - east) * t));
        }
      }
    }
    return { north, east, alt: Math.max(highest, 0) + height, heading, radius, passed: false, hit: false, miss: 0 };
  });
}

export class GateRun {
  gates: Gate[] = [];
  time = 0;
  /** The clock at the last gate; null while the run is on. */
  done: number | null = null;
  /** Called once per gate, as the aircraft goes through it or past it. */
  onGate: (gate: Gate) => void = () => {};

  constructor(
    /** Seconds added for each gate missed. */
    readonly penalty = 5,
    /** Further from the centre than this, crossing a gate's plane does not count as trying. */
    private readonly reach = 1200,
  ) {}

  start(gates: Gate[]): void {
    this.gates = gates;
    this.time = 0;
    this.done = null;
  }

  stop(): void {
    this.start([]);
  }

  get active(): boolean {
    return this.gates.length > 0;
  }

  next(): Gate | undefined {
    return this.gates.find((gate) => !gate.passed);
  }

  missed(): number {
    return this.gates.filter((gate) => gate.passed && !gate.hit).length;
  }

  score(): number {
    return this.time + this.penalty * this.missed();
  }

  /** One step from point `a` to point `b`, each [north, east, alt]. */
  step(dt: number, a: readonly number[], b: readonly number[]): void {
    if (!this.active || this.done !== null) {
      return;
    }
    this.time += dt;
    const gate = this.next();
    if (!gate) {
      return;
    }
    const heading = (gate.heading * Math.PI) / 180;
    const n = Math.cos(heading);
    const e = Math.sin(heading);
    const before = (a[0] - gate.north) * n + (a[1] - gate.east) * e;
    const after = (b[0] - gate.north) * n + (b[1] - gate.east) * e;
    if (before >= 0 || after < 0) {
      return;
    }
    const t = -before / (after - before);
    const miss = Math.hypot(a[0] + (b[0] - a[0]) * t - gate.north, a[1] + (b[1] - a[1]) * t - gate.east, a[2] + (b[2] - a[2]) * t - gate.alt);
    if (miss <= this.reach) {
      gate.passed = true;
      gate.hit = miss <= gate.radius;
      gate.miss = miss;
      this.onGate(gate);
      if (this.gates.every((g) => g.passed)) {
        this.done = this.time;
      }
    }
  }
}
