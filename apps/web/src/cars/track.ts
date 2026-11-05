/**
 * A closed route over the ground, and everything that follows from where a wheel is on it. The
 * centre line is a periodic cubic spline sampled every metre; per sample and per side the route
 * knows its kerb, paved run-off, gravel and where the barrier stands. What the tyres feel and what
 * the road shader paints read these same arrays, so a kerb is where it looks to be.
 *
 * All in the FMU's frame: x and y on the ground, left of the direction of travel is positive.
 */

export type Kind = "racecar" | "buggy";

/** What a wheel can stand on. */
export const SURFACES = ["asphalt", "kerb", "runoff", "gravel", "grass", "dirt", "loose", "scrub"] as const;
export type Surface = (typeof SURFACES)[number];

/** Friction scale of each surface, the FMU's `mu_*` inputs. */
export const GRIP: Record<Surface, number> = {
  asphalt: 1, kerb: 0.86, runoff: 0.94, gravel: 0.5, grass: 0.58,
  dirt: 1, loose: 0.84, scrub: 0.68,
};

/** Brake a surface drags on the wheels: gravel swallows a car, and the FMU has no input for that. */
export const DRAG: Partial<Record<Surface, number>> = { gravel: 0.22, grass: 0.03, scrub: 0.03 };

export interface Widening {
  /** Arc-length range in metres; `from` may be above `to` to run through the line. */
  from: number;
  to: number;
  side: 1 | -1;
  /** Paved width added to that side. */
  paved: number;
}

export interface TrackDefinition {
  id: string;
  name: string;
  blurb: string;
  car: Kind;
  points: readonly (readonly [number, number])[];
  halfWidth: number;
  /** Where the seed for the world's noise comes from. */
  seed: number;
  widen?: readonly Widening[];
  /** Medal times of a lap, in seconds: gold, silver, bronze. */
  medals: readonly [number, number, number];
  /** Where the grid box sits behind the line, metres. */
  gridBack: number;
}

export interface Place {
  /** Nearest centre-line sample. */
  index: number;
  /** Arc length of the point, m. */
  s: number;
  /** Lateral offset, left positive, m. */
  d: number;
}

function solvePeriodic(diagonal: Float64Array, off: Float64Array, right: Float64Array): Float64Array {
  // Gauss-Seidel: the system is strongly diagonal, and a track has at most a few dozen points.
  const n = right.length;
  const x = new Float64Array(n);
  for (let sweep = 0; sweep < 400; sweep += 1) {
    for (let i = 0; i < n; i += 1) {
      const before = (i + n - 1) % n;
      x[i] = (right[i] - off[before] * x[before] - off[i] * x[(i + 1) % n]) / diagonal[i];
    }
  }
  return x;
}

/** The closed curve through `points`, chord-length parametrised, densely evaluated. */
function spline(points: readonly (readonly [number, number])[], rows: number): [Float64Array, Float64Array] {
  const n = points.length;
  const lengths = new Float64Array(n);
  for (let i = 0; i < n; i += 1) {
    const [a, b] = [points[i], points[(i + 1) % n]];
    lengths[i] = Math.hypot(b[0] - a[0], b[1] - a[1]);
  }
  const diagonal = new Float64Array(n);
  const off = new Float64Array(n);
  const moments = [0, 1].map((axis) => {
    const right = new Float64Array(n);
    for (let i = 0; i < n; i += 1) {
      const before = (i + n - 1) % n;
      diagonal[i] = (lengths[before] + lengths[i]) / 3;
      off[i] = lengths[i] / 6;
      right[i] = (points[(i + 1) % n][axis] - points[i][axis]) / lengths[i] - (points[i][axis] - points[before][axis]) / lengths[before];
    }
    return solvePeriodic(diagonal, off, right);
  });
  const total = lengths.reduce((sum, value) => sum + value, 0);
  const xs = new Float64Array(rows);
  const ys = new Float64Array(rows);
  let segment = 0;
  let start = 0;
  for (let k = 0; k < rows; k += 1) {
    const u = (k / rows) * total;
    while (u >= start + lengths[segment] && segment < n - 1) {
      start += lengths[segment];
      segment += 1;
    }
    const h = lengths[segment];
    const b = (u - start) / h;
    const a = 1 - b;
    const next = (segment + 1) % n;
    const value = (axis: 0 | 1): number =>
      a * points[segment][axis] + b * points[next][axis]
      + (((a ** 3 - a) * moments[axis][segment] + (b ** 3 - b) * moments[axis][next]) * h * h) / 6;
    xs[k] = value(0);
    ys[k] = value(1);
  }
  return [xs, ys];
}

/** A running mean over a ring, repeated: tapers what a sample-by-sample rule would switch hard. */
function smooth(values: Float32Array, radius: number, passes = 2): void {
  const n = values.length;
  const copy = new Float32Array(n);
  for (let pass = 0; pass < passes; pass += 1) {
    let sum = 0;
    for (let i = -radius; i <= radius; i += 1) {
      sum += values[(i + n) % n];
    }
    for (let i = 0; i < n; i += 1) {
      copy[i] = sum / (2 * radius + 1);
      sum += values[(i + radius + 1) % n] - values[(i - radius + n) % n];
    }
    values.set(copy);
  }
}

/** The largest value within `radius` samples: a band that holds as long as anything in it needs it. */
function widen(values: Float32Array, radius: number): void {
  const n = values.length;
  const copy = values.slice();
  for (let i = 0; i < n; i += 1) {
    let top = 0;
    for (let j = -radius; j <= radius; j += 1) {
      top = Math.max(top, copy[(i + j + n) % n]);
    }
    values[i] = top;
  }
}

export interface Side {
  kerb: Float32Array;
  paved: Float32Array;
  gravel: Float32Array;
  /** Distance of the barrier from the centre line, m. */
  wall: Float32Array;
  /** How far the ribbon of road surface may reach on this side before it would fold over itself. */
  reach: Float32Array;
}

export class Track {
  readonly n: number;
  readonly length: number;
  readonly x: Float32Array;
  readonly y: Float32Array;
  /** Unit tangent. The left normal is (-ty, tx). */
  readonly tx: Float32Array;
  readonly ty: Float32Array;
  /** Signed curvature, left positive, 1/m. */
  readonly curvature: Float32Array;
  readonly left: Side;
  readonly right: Side;
  readonly width: number;

  constructor(readonly definition: TrackDefinition) {
    const [roughX, roughY] = spline(definition.points, 24000);
    const rough = roughX.length;
    const arc = new Float64Array(rough + 1);
    for (let i = 0; i < rough; i += 1) {
      const j = (i + 1) % rough;
      arc[i + 1] = arc[i] + Math.hypot(roughX[j] - roughX[i], roughY[j] - roughY[i]);
    }
    this.length = arc[rough];
    this.n = Math.round(this.length);
    const n = this.n;
    this.x = new Float32Array(n);
    this.y = new Float32Array(n);
    let walk = 0;
    for (let k = 0; k < n; k += 1) {
      const target = (k / n) * this.length;
      while (arc[walk + 1] < target) {
        walk += 1;
      }
      const f = (target - arc[walk]) / (arc[walk + 1] - arc[walk]);
      const after = (walk + 1) % rough;
      this.x[k] = roughX[walk] + (roughX[after] - roughX[walk]) * f;
      this.y[k] = roughY[walk] + (roughY[after] - roughY[walk]) * f;
    }
    this.tx = new Float32Array(n);
    this.ty = new Float32Array(n);
    this.curvature = new Float32Array(n);
    for (let k = 0; k < n; k += 1) {
      const dx = this.x[(k + 1) % n] - this.x[(k + n - 1) % n];
      const dy = this.y[(k + 1) % n] - this.y[(k + n - 1) % n];
      const h = Math.hypot(dx, dy);
      this.tx[k] = dx / h;
      this.ty[k] = dy / h;
    }
    for (let k = 0; k < n; k += 1) {
      const a = (k + n - 2) % n;
      const b = (k + 2) % n;
      this.curvature[k] = (this.tx[a] * this.ty[b] - this.ty[a] * this.tx[b]) / 4;
    }
    smooth(this.curvature, 4, 2);
    this.width = definition.halfWidth;
    this.left = this.layOut(1);
    this.right = this.layOut(-1);
  }

  /** The inside of a bend, then room for barriers where the route passes near itself. */
  private layOut(side: 1 | -1): Side {
    const { n, definition } = this;
    const racing = definition.car === "racecar";
    const kerb = new Float32Array(n);
    const paved = new Float32Array(n);
    const gravel = new Float32Array(n);
    const wall = new Float32Array(n);
    const reach = new Float32Array(n);
    for (let i = 0; i < n; i += 1) {
      const c = this.curvature[i];
      const radius = 1 / Math.max(Math.abs(c), 1e-5);
      const outside = c * side < 0;
      if (racing) {
        kerb[i] = radius < 260 ? (outside ? 1.1 : 1.6) : 0;
        if (outside && radius < 130) {
          paved[i] = 4;
          gravel[i] = 13 + 90 / Math.max(radius, 20) * 14;
        } else if (outside && radius < 320) {
          paved[i] = 11;
        }
      } else {
        // The berm thrown up on the outside of a bend, and loose stuff along every edge.
        kerb[i] = 1.2 + (outside ? Math.min(2.4, 60 / radius) : 0);
      }
    }
    widen(kerb, racing ? 6 : 3);
    widen(paved, 18);
    widen(gravel, 24);
    for (const span of definition.widen ?? []) {
      if (span.side !== side) {
        continue;
      }
      const stop = span.to >= span.from ? span.to : span.to + n;
      for (let s = span.from; s < stop; s += 1) {
        paved[Math.floor(s) % n] = Math.max(paved[Math.floor(s) % n], span.paved);
      }
    }
    smooth(kerb, 3, 1);
    smooth(paved, 8);
    smooth(gravel, 10);
    if (racing) {
      // A kerb tapers out of the ground, and in between it is not worth a sliver.
      for (let i = 0; i < n; i += 1) {
        kerb[i] = kerb[i] < 0.12 ? 0 : kerb[i];
      }
    }
    const clear = this.clearance(side);
    for (let i = 0; i < n; i += 1) {
      const room = definition.halfWidth + kerb[i] + paved[i] + gravel[i];
      wall[i] = Math.min(room + (racing ? (gravel[i] > 1 ? 3 : 6) : 26), clear[i]);
    }
    // Walls bend slowly, and never step in: a jump in the limit would be a car hit from the side.
    smooth(wall, 12);
    for (let i = 0; i < n; i += 1) {
      const c = this.curvature[i];
      // The inside of a bend ends at its centre of curvature.
      const fold = c * side > 0 ? 0.92 / Math.abs(c) : 1e4;
      const limit = Math.min(fold, clear[i]);
      reach[i] = Math.min(limit, wall[i] + 18);
    }
    widenDown(reach, 8);
    return { kerb, paved, gravel, wall, reach };
  }

  /** Half the distance to any other part of the route, on one side of each sample. */
  private clearance(side: 1 | -1): Float32Array {
    const { n } = this;
    const out = new Float32Array(n).fill(1e4);
    for (let i = 0; i < n; i += 2) {
      for (let j = 0; j < n; j += 6) {
        const gap = Math.abs(i - j);
        if (Math.min(gap, n - gap) < 70) {
          continue;
        }
        const dx = this.x[j] - this.x[i];
        const dy = this.y[j] - this.y[i];
        const lateral = -this.ty[i] * dx + this.tx[i] * dy;
        const along = this.tx[i] * dx + this.ty[i] * dy;
        if (lateral * side > 0 && Math.abs(along) < Math.abs(lateral)) {
          const half = Math.hypot(dx, dy) / 2;
          out[i] = Math.min(out[i], half);
          out[(i + 1) % n] = Math.min(out[(i + 1) % n], half);
        }
      }
    }
    return out;
  }

  /** The nearest sample, from a search around `hint`; a negative hint looks at the whole route. */
  locate(x: number, y: number, hint = -1): Place {
    const { n } = this;
    let best = 0;
    let bestDistance = Infinity;
    const span = hint < 0 ? n : 90;
    const from = hint < 0 ? 0 : hint - 45;
    for (let k = 0; k < span; k += 1) {
      const i = ((from + k) % n + n) % n;
      const dx = this.x[i] - x;
      const dy = this.y[i] - y;
      const distance = dx * dx + dy * dy;
      if (distance < bestDistance) {
        bestDistance = distance;
        best = i;
      }
    }
    const rx = x - this.x[best];
    const ry = y - this.y[best];
    const along = rx * this.tx[best] + ry * this.ty[best];
    return { index: best, s: ((best / n) * this.length + along + this.length) % this.length, d: -rx * this.ty[best] + ry * this.tx[best] };
  }

  surface(place: Place): Surface {
    const side = place.d > 0 ? this.left : this.right;
    const i = place.index;
    let edge = Math.abs(place.d) - this.width;
    if (this.definition.car === "buggy") {
      return edge <= 0 ? "dirt" : edge <= side.kerb[i] + 1.2 ? "loose" : "scrub";
    }
    if (edge <= 0) {
      return "asphalt";
    }
    edge -= side.kerb[i];
    if (edge <= 0) {
      return "kerb";
    }
    edge -= side.paved[i];
    if (edge <= 0) {
      return "runoff";
    }
    edge -= side.gravel[i];
    return edge <= 0 ? "gravel" : "grass";
  }

  /** How far past the barrier a point is: positive means it went through. */
  throughWall(place: Place): number {
    return Math.abs(place.d) - (place.d > 0 ? this.left : this.right).wall[place.index];
  }

  /** A point `d` to the left of arc length `s`, and the heading of the route there. */
  pose(s: number, d = 0): { x: number; y: number; yaw: number } {
    const f = (((s % this.length) + this.length) % this.length) / this.length * this.n;
    const i = Math.floor(f) % this.n;
    const j = (i + 1) % this.n;
    const t = f - Math.floor(f);
    const tx = this.tx[i] + (this.tx[j] - this.tx[i]) * t;
    const ty = this.ty[i] + (this.ty[j] - this.ty[i]) * t;
    const norm = Math.hypot(tx, ty);
    return {
      x: this.x[i] + (this.x[j] - this.x[i]) * t - (ty / norm) * d,
      y: this.y[i] + (this.y[j] - this.y[i]) * t + (tx / norm) * d,
      yaw: Math.atan2(ty, tx),
    };
  }

  /** The closest two far-apart parts of the route ever come: checks a new layout. */
  tightestGap(): number {
    let least = Infinity;
    for (let i = 0; i < this.n; i += 4) {
      for (let j = i + 80; j < this.n; j += 4) {
        if (this.n - (j - i) >= 80) {
          least = Math.min(least, Math.hypot(this.x[i] - this.x[j], this.y[i] - this.y[j]));
        }
      }
    }
    return least;
  }
}

function widenDown(values: Float32Array, radius: number): void {
  const n = values.length;
  const copy = values.slice();
  for (let i = 0; i < n; i += 1) {
    let least = Infinity;
    for (let j = -radius; j <= radius; j += 1) {
      least = Math.min(least, copy[(i + j + n) % n]);
    }
    values[i] = least;
  }
}
