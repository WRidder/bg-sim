/** Colormaps of colour bindings (spec: `heat`, `viridis`, `coolwarm`): piecewise-linear ramps over control stops. */

import type { Colormap } from "../contracts/model";

export type Rgb = readonly [number, number, number];

const STOPS: Record<Colormap, readonly Rgb[]> = {
  // dark red -> red -> orange -> yellow -> white
  heat: [
    [0.1, 0, 0],
    [0.75, 0.05, 0],
    [1, 0.45, 0],
    [1, 0.85, 0.1],
    [1, 1, 0.85],
  ],
  // matplotlib viridis, 9 stops
  viridis: [
    [0.267, 0.005, 0.329],
    [0.283, 0.141, 0.458],
    [0.254, 0.265, 0.53],
    [0.207, 0.372, 0.553],
    [0.164, 0.471, 0.558],
    [0.128, 0.567, 0.551],
    [0.135, 0.659, 0.518],
    [0.267, 0.749, 0.441],
    [0.478, 0.821, 0.318],
    [0.741, 0.873, 0.15],
    [0.993, 0.906, 0.144],
  ],
  // diverging blue - light grey - red
  coolwarm: [
    [0.23, 0.299, 0.754],
    [0.553, 0.69, 0.996],
    [0.865, 0.865, 0.865],
    [0.957, 0.604, 0.481],
    [0.706, 0.016, 0.15],
  ],
};

/** The colour of `value` on a map spanning `range`; values outside are clamped, a degenerate range gives the low end. */
export function colormapColor(map: Colormap, value: number, range: readonly [number, number]): Rgb {
  const stops = STOPS[map];
  const span = range[1] - range[0];
  let u = span !== 0 && Number.isFinite(span) ? (value - range[0]) / span : 0;
  if (!Number.isFinite(u)) u = 0;
  u = Math.min(1, Math.max(0, u));
  const x = u * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(x));
  const f = x - i;
  const a = stops[i] ?? [0, 0, 0];
  const b = stops[i + 1] ?? a;
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
}

/** CSS `linear-gradient` of a map, for the binding editor's swatch. */
export function colormapGradient(map: Colormap): string {
  const stops = STOPS[map];
  const parts = stops.map((c, i) => {
    const pct = (i / (stops.length - 1)) * 100;
    return `rgb(${String(Math.round(c[0] * 255))} ${String(Math.round(c[1] * 255))} ${String(Math.round(c[2] * 255))}) ${pct.toFixed(0)}%`;
  });
  return `linear-gradient(to right, ${parts.join(", ")})`;
}

export const COLORMAPS: readonly Colormap[] = ["heat", "viridis", "coolwarm"];
