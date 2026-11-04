/** Deterministic noise for worlds: the same seed gives the same island on every machine. */

export function hash2(x: number, y: number, seed: number): number {
  let h = Math.imul(x, 374761393) + Math.imul(y, 668265263) + Math.imul(seed, 2147483647 - 18);
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}

function fade(t: number): number {
  return t * t * t * (t * (t * 6 - 15) + 10);
}

/** Value noise in 0..1. */
export function noise2(x: number, y: number, seed: number): number {
  const ix = Math.floor(x);
  const iy = Math.floor(y);
  const fx = fade(x - ix);
  const fy = fade(y - iy);
  const a = hash2(ix, iy, seed);
  const b = hash2(ix + 1, iy, seed);
  const c = hash2(ix, iy + 1, seed);
  const d = hash2(ix + 1, iy + 1, seed);
  return a + (b - a) * fx + (c - a) * fy + (a - b - c + d) * fx * fy;
}

/** Fractal noise in about 0..1. */
export function fbm(x: number, y: number, octaves: number, seed: number): number {
  let sum = 0;
  let amplitude = 0.5;
  let total = 0;
  for (let i = 0; i < octaves; i += 1) {
    sum += amplitude * noise2(x, y, seed + i);
    total += amplitude;
    amplitude *= 0.5;
    const rotated = 1.6 * x - 1.2 * y;
    y = 1.2 * x + 1.6 * y;
    x = rotated;
  }
  return sum / total;
}

/** Ridged fractal noise: sharp crests, where each octave is damped in the valleys of the last. */
export function ridged(x: number, y: number, octaves: number, seed: number): number {
  let sum = 0;
  let amplitude = 0.5;
  let weight = 1;
  let total = 0;
  for (let i = 0; i < octaves; i += 1) {
    const n = 1 - Math.abs(2 * noise2(x, y, seed + i) - 1);
    const ridge = n * n;
    sum += amplitude * ridge * weight;
    total += amplitude;
    weight = Math.min(1, ridge * 2);
    amplitude *= 0.5;
    const rotated = 1.6 * x - 1.2 * y;
    y = 1.2 * x + 1.6 * y;
    x = rotated;
  }
  return sum / total;
}

export function smoothstep(edge0: number, edge1: number, x: number): number {
  const t = Math.min(1, Math.max(0, (x - edge0) / (edge1 - edge0)));
  return t * t * (3 - 2 * t);
}
