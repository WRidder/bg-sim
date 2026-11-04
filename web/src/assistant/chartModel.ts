/**
 * The arithmetic of the chat's charts: readable axis ticks, thinning to what a chart this small
 * can show, and a colour map for matrices.
 */

export const MAX_CHART_POINTS = 1200;

export interface Extent {
  min: number;
  max: number;
}

/** The extent of the finite values, widened when flat; `null` without any. */
export function extentOf(columns: readonly (readonly (number | null)[])[]): Extent | null {
  let min = Infinity;
  let max = -Infinity;
  for (const column of columns) {
    for (const value of column) {
      if (value !== null && Number.isFinite(value)) {
        min = Math.min(min, value);
        max = Math.max(max, value);
      }
    }
  }
  if (min === Infinity) {
    return null;
  }
  if (min === max) {
    const pad = min === 0 ? 1 : Math.abs(min) * 0.1;
    return { min: min - pad, max: max + pad };
  }
  return { min, max };
}

/** About `count` round tick values inside `extent`. */
export function ticks({ min, max }: Extent, count = 5): number[] {
  const rough = (max - min) / count;
  const power = 10 ** Math.floor(Math.log10(rough));
  const unit = rough / power;
  const step = (unit < 1.5 ? 1 : unit < 3 ? 2 : unit < 7 ? 5 : 10) * power;
  const values: number[] = [];
  for (let i = Math.ceil(min / step); i * step <= max + step * 1e-9; i += 1) {
    values.push(Number((i * step).toPrecision(12)));
  }
  return values;
}

/** A short engineering number for an axis, a table cell or a read-out. */
export function formatNumber(value: number | boolean | null): string {
  if (value === null) {
    return "–";
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (Number.isInteger(value) && Math.abs(value) < 1e7) {
    return String(value);
  }
  const size = Math.abs(value);
  return size !== 0 && (size >= 1e5 || size < 1e-3) ? value.toExponential(2) : String(Number(value.toPrecision(4)));
}

/** The row order that sorts `x`: charts need rising x, and `fftfreq` wraps around. */
export function sortOrder(x: readonly number[]): number[] {
  const order = x.map((_, index) => index);
  for (let i = 1; i < x.length; i += 1) {
    if (x[i]! < x[i - 1]!) {
      return order.sort((a, b) => x[a]! - x[b]!);
    }
  }
  return order;
}

/**
 * The row indices to draw: all of them when few, else the first, the last and the extremes of
 * each bucket, so a narrow peak survives the thinning.
 */
export function thin(length: number, columns: readonly (readonly (number | null)[])[], limit = MAX_CHART_POINTS): number[] {
  if (length <= limit) {
    return Array.from({ length }, (_, index) => index);
  }
  const keep = new Set<number>([0, length - 1]);
  const buckets = Math.max(1, Math.floor(limit / (2 * Math.max(1, columns.length))));
  for (let bucket = 0; bucket < buckets; bucket += 1) {
    const start = Math.floor((bucket * length) / buckets);
    const end = Math.floor(((bucket + 1) * length) / buckets);
    for (const column of columns) {
      let low = -1;
      let high = -1;
      for (let i = start; i < end; i += 1) {
        const value = column[i];
        if (value === null || value === undefined || !Number.isFinite(value)) {
          continue;
        }
        if (low < 0 || value < column[low]!) {
          low = i;
        }
        if (high < 0 || value > column[high]!) {
          high = i;
        }
      }
      if (low >= 0) {
        keep.add(low);
        keep.add(high);
      }
    }
  }
  return [...keep].sort((a, b) => a - b);
}

/** Viridis in five stops: perceptually even, and legible in both themes. */
const MAP: readonly (readonly [number, number, number])[] = [
  [68, 1, 84],
  [59, 82, 139],
  [33, 145, 140],
  [94, 201, 98],
  [253, 231, 37],
];

export function colorAt(fraction: number): [number, number, number] {
  const place = Math.min(0.9999, Math.max(0, fraction)) * (MAP.length - 1);
  const index = Math.floor(place);
  const low = MAP[index]!;
  const high = MAP[index + 1]!;
  const mix = place - index;
  return [0, 1, 2].map((c) => Math.round(low[c]! + (high[c]! - low[c]!) * mix)) as [number, number, number];
}

/** The CSS gradient of the colour bar next to a heat map. */
export const COLOR_BAR = `linear-gradient(to right, ${MAP.map(([r, g, b]) => `rgb(${r} ${g} ${b})`).join(", ")})`;
