/**
 * The pure parts of an XY plot (one signal against another): the time window, the axis ranges
 * (padded, optionally equal aspect), the screen-space thinning of the drawn path, the nearest
 * point under the pointer and the point at the inspect time.
 *
 * Why its own thinning: a plot against time is min/max decimated per pixel column, which keeps
 * every signal's envelope but can combine samples of different instants in one row. An XY plot
 * pairs x and y sample by sample, so it is drawn from whole recorded rows (the store asks for raw
 * `/data` and an exact live tail while an XY plot is open) and thinned on the screen instead: a
 * sample is drawn only when it moves at least `tolerance` device pixels away from the last drawn
 * one. The path therefore stays within that tolerance of the full-resolution curve at any zoom,
 * costs O(n) per draw, and a trajectory that dwells on a few pixels (a slow phase portrait, a
 * converged limit cycle drawn many times over) collapses to a few hundred segments.
 */

/** The inclusive index range of `time` inside a window; null when the window holds no sample. */
export function windowIndices(
  time: ArrayLike<number>,
  window: { t0: number; t1: number } | null,
): [number, number] | null {
  const n = time.length;
  if (n === 0) {
    return null;
  }
  if (window === null) {
    return [0, n - 1];
  }
  // First index with time >= t0, last index with time <= t1.
  let lo = 0;
  let hi = n;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if ((time[mid] as number) < window.t0) lo = mid + 1;
    else hi = mid;
  }
  const first = lo;
  lo = first;
  hi = n;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if ((time[mid] as number) <= window.t1) lo = mid + 1;
    else hi = mid;
  }
  const last = lo - 1;
  return last >= first ? [first, last] : null;
}

export interface Extent {
  min: number;
  max: number;
}

/** Extend `extent` by the finite values of `values[i0..i1]`. */
export function extendExtent(
  extent: Extent | null,
  values: ArrayLike<number> | undefined,
  i0: number,
  i1: number,
): Extent | null {
  if (values === undefined) {
    return extent;
  }
  let min = extent?.min ?? Infinity;
  let max = extent?.max ?? -Infinity;
  const end = Math.min(i1, values.length - 1);
  for (let i = Math.max(0, i0); i <= end; i += 1) {
    const v = values[i] as number;
    if (v < min) min = v;
    if (v > max) max = v;
  }
  return min <= max ? { min, max } : extent;
}

/** A padded axis range; a flat or missing extent gets a unit-sized range around its value. */
export function paddedRange(extent: Extent | null, padding = 0.05): Extent {
  if (extent === null || !Number.isFinite(extent.min) || !Number.isFinite(extent.max)) {
    return { min: -1, max: 1 };
  }
  const span = extent.max - extent.min;
  if (!(span > 0)) {
    const delta = Math.abs(extent.min) > 0 ? Math.abs(extent.min) * 0.1 : 1;
    return { min: extent.min - delta, max: extent.max + delta };
  }
  return { min: extent.min - span * padding, max: extent.max + span * padding };
}

/**
 * Equal aspect: widen the x or the y range (about its centre) until one unit is as long on both
 * axes for a plot area of `width` x `height` pixels. Both ranges only ever grow, so the data stays
 * in view. A degenerate size returns the ranges unchanged.
 */
export function equalAspectRanges(
  x: Extent,
  y: Extent,
  width: number,
  height: number,
): { x: Extent; y: Extent } {
  const spanX = x.max - x.min;
  const spanY = y.max - y.min;
  if (!(width > 0) || !(height > 0) || !(spanX > 0) || !(spanY > 0)) {
    return { x, y };
  }
  const perPixel = Math.max(spanX / width, spanY / height);
  const halfX = (perPixel * width) / 2;
  const halfY = (perPixel * height) / 2;
  const cx = (x.min + x.max) / 2;
  const cy = (y.min + y.max) / 2;
  return {
    x: { min: cx - halfX, max: cx + halfX },
    y: { min: cy - halfY, max: cy + halfY },
  };
}

/** A linear map from data values to pixels: `pixel = offset + (value - min) * scale`. */
export interface AxisMap {
  min: number;
  offset: number;
  scale: number;
}

/** The map of a scale `[min, max]` onto a pixel span; `flip` puts `min` at the far end (y). */
export function axisMap(min: number, max: number, start: number, length: number, flip: boolean): AxisMap {
  const range = max - min;
  const scale = range !== 0 ? length / range : 0;
  return flip ? { min, offset: start + length, scale: -scale } : { min, offset: start, scale };
}

/** The drawn points of one series, in device pixels, with their source rows. */
export interface ThinnedPath {
  /** Number of drawn points (the arrays may be longer). */
  count: number;
  /** Source row of each drawn point. */
  rows: Int32Array;
  px: Float32Array;
  py: Float32Array;
  /** True for a point that starts a new run after a gap (a non-finite sample). */
  breaks: Uint8Array;
}

/**
 * Thin `xs[i0..i1]`/`ys[i0..i1]` in screen space: keep a sample when it is at least `tolerance`
 * pixels (along either axis) from the last kept one, always keep the first and the last sample
 * and the samples around a gap (a non-finite x or y breaks the line). The kept polyline stays
 * within `tolerance` of the full-resolution one.
 */
export function thinXYPath(
  xs: ArrayLike<number>,
  ys: ArrayLike<number>,
  i0: number,
  i1: number,
  mapX: AxisMap,
  mapY: AxisMap,
  tolerance = 0.5,
): ThinnedPath {
  const last = Math.min(i1, xs.length - 1, ys.length - 1);
  const capacity = Math.max(0, last - i0 + 1);
  const rows = new Int32Array(capacity);
  const px = new Float32Array(capacity);
  const py = new Float32Array(capacity);
  const breaks = new Uint8Array(capacity);
  let count = 0;
  let lastX = 0;
  let lastY = 0;
  let open = false;
  // The last sample seen but not kept; flushed before a gap so a run ends on its real end.
  let pendingRow = -1;
  let pendingX = 0;
  let pendingY = 0;
  for (let i = i0; i <= last; i += 1) {
    const vx = xs[i] as number;
    const vy = ys[i] as number;
    if (!Number.isFinite(vx) || !Number.isFinite(vy)) {
      if (pendingRow >= 0) {
        rows[count] = pendingRow;
        px[count] = pendingX;
        py[count] = pendingY;
        count += 1;
        pendingRow = -1;
      }
      open = false;
      continue;
    }
    const x = mapX.offset + (vx - mapX.min) * mapX.scale;
    const y = mapY.offset + (vy - mapY.min) * mapY.scale;
    if (!open) {
      rows[count] = i;
      px[count] = x;
      py[count] = y;
      breaks[count] = 1;
      count += 1;
      lastX = x;
      lastY = y;
      open = true;
      pendingRow = -1;
      continue;
    }
    if (Math.abs(x - lastX) >= tolerance || Math.abs(y - lastY) >= tolerance) {
      rows[count] = i;
      px[count] = x;
      py[count] = y;
      count += 1;
      lastX = x;
      lastY = y;
      pendingRow = -1;
    } else {
      pendingRow = i;
      pendingX = x;
      pendingY = y;
    }
  }
  if (pendingRow >= 0) {
    rows[count] = pendingRow;
    px[count] = pendingX;
    py[count] = pendingY;
    count += 1;
  }
  return { count, rows, px, py, breaks };
}

/** The drawn point nearest to (`x`, `y`) in pixels, over several paths: [path, point] or null. */
export function nearestDrawnPoint(
  paths: readonly (ThinnedPath | null)[],
  x: number,
  y: number,
): { path: number; point: number; distance: number } | null {
  let bestPath = -1;
  let bestPoint = -1;
  let bestD2 = Infinity;
  for (let index = 0; index < paths.length; index += 1) {
    const path = paths[index];
    if (path === null || path === undefined) {
      continue;
    }
    for (let k = 0; k < path.count; k += 1) {
      const dx = (path.px[k] as number) - x;
      const dy = (path.py[k] as number) - y;
      const d2 = dx * dx + dy * dy;
      if (d2 < bestD2) {
        bestD2 = d2;
        bestPath = index;
        bestPoint = k;
      }
    }
  }
  return bestPath < 0 ? null : { path: bestPath, point: bestPoint, distance: Math.sqrt(bestD2) };
}

/**
 * The (x, y) point of a trajectory at time `t`, linear between samples, so it lies on the drawn
 * segment; the right limit at an event instant. `t` null is the newest sample (the live head).
 * Null outside `[time[i0], time[i1]]` or at a gap.
 */
export function pointAtTime(
  time: ArrayLike<number>,
  xs: ArrayLike<number>,
  ys: ArrayLike<number>,
  t: number | null,
  i0 = 0,
  i1 = time.length - 1,
): { x: number; y: number; t: number } | null {
  const last = Math.min(i1, time.length - 1, xs.length - 1, ys.length - 1);
  if (last < i0) {
    return null;
  }
  if (t === null) {
    for (let k = last; k >= i0; k -= 1) {
      const x = xs[k] as number;
      const y = ys[k] as number;
      if (Number.isFinite(x) && Number.isFinite(y)) {
        return { x, y, t: time[k] as number };
      }
    }
    return null;
  }
  if (t < (time[i0] as number) || t > (time[last] as number)) {
    return null;
  }
  // The last index with time <= t (the right limit of an event pair).
  let lo = i0;
  let hi = last;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if ((time[mid] as number) <= t) lo = mid;
    else hi = mid - 1;
  }
  const t0 = time[lo] as number;
  const x0 = xs[lo] as number;
  const y0 = ys[lo] as number;
  if (!Number.isFinite(x0) || !Number.isFinite(y0)) {
    return null;
  }
  if (t0 === t || lo >= last) {
    return { x: x0, y: y0, t };
  }
  const t1 = time[lo + 1] as number;
  const x1 = xs[lo + 1] as number;
  const y1 = ys[lo + 1] as number;
  if (!(t1 > t0) || !Number.isFinite(x1) || !Number.isFinite(y1)) {
    return { x: x0, y: y0, t };
  }
  const f = (t - t0) / (t1 - t0);
  return { x: x0 + (x1 - x0) * f, y: y0 + (y1 - y0) * f, t };
}

/** The axis title of an XY axis: the signal and its unit for one signal, else the unit. */
export function xyAxisLabel(
  signals: readonly { id: string; unit: string | null }[],
  fallback: string,
): string {
  if (signals.length === 0) {
    return fallback;
  }
  const unit = signals[0]?.unit?.trim() ?? "";
  if (signals.length === 1) {
    return unit.length > 0 ? `${signals[0]!.id} [${unit}]` : signals[0]!.id;
  }
  return unit.length > 0 ? `[${unit}]` : fallback;
}
