/**
 * Recorded signal samples and their interpolation (spec "Viewer loop"): a growing columnar
 * buffer, binary search for the bracketing samples, lerp for scalars and a shortest-path,
 * normalised slerp for quaternions. The ends are held, nothing is ever extrapolated.
 */

/** Frames of the stream format: Float64 little-endian `[t, v1 ... vn]`. */
export const FRAME_BYTES = 8;

/**
 * Split a binary stream message into frames. The message holds whole frames of `n + 1`
 * Float64 values (`[t, v1 ... vn]`), `n` the number of signals of the handshake.
 */
export function decodeFrames(message: ArrayBuffer, signalCount: number): Float64Array {
  const width = signalCount + 1;
  if (message.byteLength % (FRAME_BYTES * width) !== 0) {
    throw new Error(
      `a stream message of ${message.byteLength} bytes is not a whole number of frames of ${width} values; ` +
        "the viewer and the backend disagree on the handshake, reload the page",
    );
  }
  // Copy to an aligned buffer; the platform is little-endian like the stream.
  return new Float64Array(message.slice(0));
}

/** The two samples around a time and the blend between them. */
export interface Bracket {
  /** Index of the sample at or before `t` (clamped). */
  readonly lo: number;
  /** Index of the sample after it (equal to `lo` at either end). */
  readonly hi: number;
  /** 0 at `lo`, 1 at `hi`. */
  readonly frac: number;
}

/**
 * Binary search `times[0..length)` (ascending) for the samples around `t`. Before the first and after
 * the last sample the bracket holds that sample (`lo === hi`, `frac === 0`). `length` of 0 gives null.
 */
export function bracket(times: ArrayLike<number>, length: number, t: number): Bracket | null {
  if (length <= 0) return null;
  const first = times[0] ?? 0;
  const last = times[length - 1] ?? 0;
  if (!(t > first)) return { lo: 0, hi: 0, frac: 0 };
  if (t >= last) return { lo: length - 1, hi: length - 1, frac: 0 };
  let lo = 0;
  let hi = length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if ((times[mid] ?? 0) <= t) lo = mid;
    else hi = mid;
  }
  const t0 = times[lo] ?? 0;
  const span = (times[hi] ?? t0) - t0;
  return { lo, hi, frac: span > 0 ? (t - t0) / span : 0 };
}

export function lerp(a: number, b: number, f: number): number {
  return a + (b - a) * f;
}

export type Quat = readonly [number, number, number, number];

/** Unit quaternion `(w, x, y, z)`; the identity for a zero or non-finite input. */
export function normalizeQuat(q: Quat): Quat {
  const n = Math.hypot(q[0], q[1], q[2], q[3]);
  if (!(n > 0) || !Number.isFinite(n)) return [1, 0, 0, 0];
  return [q[0] / n, q[1] / n, q[2] / n, q[3] / n];
}

/**
 * Spherical interpolation along the shorter arc (q and -q are the same rotation, so a negative dot flips
 * the second operand); nearly parallel inputs fall back to a normalised lerp. The result is a unit quaternion.
 */
export function slerp(a: Quat, b: Quat, f: number): Quat {
  let dot = a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3];
  const s = dot < 0 ? -1 : 1;
  dot *= s;
  const bw = b[0] * s;
  const bx = b[1] * s;
  const by = b[2] * s;
  const bz = b[3] * s;
  let ka: number;
  let kb: number;
  if (dot > 0.9995) {
    ka = 1 - f;
    kb = f;
  } else {
    const theta = Math.acos(Math.min(1, dot));
    const sin = Math.sin(theta);
    ka = Math.sin((1 - f) * theta) / sin;
    kb = Math.sin(f * theta) / sin;
  }
  return normalizeQuat([ka * a[0] + kb * bw, ka * a[1] + kb * bx, ka * a[2] + kb * by, ka * a[3] + kb * bz]);
}

/**
 * Samples of an ordered signal list over time, appended as frames arrive. Column `i` holds the
 * signal `ids[i]`. Capacity doubles; `time` and `column` return views of the filled part only.
 */
export class SignalBuffer {
  private times: Float64Array;
  private cols: Float64Array[];
  private count = 0;

  constructor(readonly ids: readonly string[], capacity = 1024) {
    this.times = new Float64Array(capacity);
    this.cols = ids.map(() => new Float64Array(capacity));
  }

  get length(): number {
    return this.count;
  }

  /** First and last sample time, or null while empty. */
  get span(): { readonly t0: number; readonly t1: number } | null {
    return this.count === 0 ? null : { t0: this.times[0] ?? 0, t1: this.times[this.count - 1] ?? 0 };
  }

  /** Spacing of the last two samples, or null with fewer than two. */
  get interval(): number | null {
    if (this.count < 2) return null;
    return (this.times[this.count - 1] ?? 0) - (this.times[this.count - 2] ?? 0);
  }

  /** Append decoded frames (see {@link decodeFrames}); frames that do not advance time are dropped. */
  append(frames: Float64Array): void {
    const width = this.ids.length + 1;
    const n = Math.floor(frames.length / width);
    this.reserve(this.count + n);
    for (let f = 0; f < n; f++) {
      const t = frames[f * width] ?? Number.NaN;
      if (!Number.isFinite(t)) continue;
      if (this.count > 0 && t <= (this.times[this.count - 1] ?? 0)) continue;
      this.times[this.count] = t;
      for (let c = 0; c < this.cols.length; c++) {
        const col = this.cols[c];
        if (col !== undefined) col[this.count] = frames[f * width + 1 + c] ?? Number.NaN;
      }
      this.count += 1;
    }
  }

  clear(): void {
    this.count = 0;
  }

  /** The sample times. */
  get time(): Float64Array {
    return this.times;
  }

  /** The values of column `i`; valid up to `length`. */
  column(i: number): Float64Array | undefined {
    return this.cols[i];
  }

  /** Time of the sample at `i`. */
  timeAt(i: number): number {
    return this.times[i] ?? 0;
  }

  /** Interpolated value of column `col` at time `t`, or null while empty or for an unknown column. */
  valueAt(col: number, t: number): number | null {
    const column = this.cols[col];
    const b = bracket(this.times, this.count, t);
    if (column === undefined || b === null) return null;
    return lerp(column[b.lo] ?? 0, column[b.hi] ?? 0, b.frac);
  }

  /** Interpolated unit quaternion from four columns, or null. */
  quatAt(cols: readonly [number, number, number, number], t: number): Quat | null {
    const b = bracket(this.times, this.count, t);
    if (b === null) return null;
    const at = (i: number): Quat => [
      this.cols[cols[0]]?.[i] ?? 1,
      this.cols[cols[1]]?.[i] ?? 0,
      this.cols[cols[2]]?.[i] ?? 0,
      this.cols[cols[3]]?.[i] ?? 0,
    ];
    return slerp(normalizeQuat(at(b.lo)), normalizeQuat(at(b.hi)), b.frac);
  }

  private reserve(needed: number): void {
    if (needed <= this.times.length) return;
    let capacity = this.times.length;
    while (capacity < needed) capacity *= 2;
    const grow = (old: Float64Array): Float64Array => {
      const next = new Float64Array(capacity);
      next.set(old.subarray(0, this.count));
      return next;
    };
    this.times = grow(this.times);
    this.cols = this.cols.map(grow);
  }
}
