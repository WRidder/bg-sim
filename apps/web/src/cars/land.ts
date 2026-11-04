/**
 * The land around a route. Near the route the ground is exactly what the car stands on: the FMU's
 * ground lifted by `BASE`, so the sea stays below it, and on a race circuit a gentle swell that is
 * only drawn. Further out the land is free: a headland above the sea for the circuits, dry ridges
 * for the stages. This file has no DOM in it: the grid is built in a worker.
 */

import type { Grid } from "../engine/heightfield";
import { fbm, ridged, smoothstep } from "../engine/noise";
import { hills } from "./hills";
import type { Kind, Track } from "./track";

export const EXTENT = 4096;
export const BASE = 9;
const FAR_LAND = 1880;

/** The swell a circuit is drawn on. The FMU's ground is flat, so the car feels none of it. */
function swell(x: number, y: number): number {
  return 2.4 * Math.cos(0.0062 * x + 0.8) * Math.cos(0.0049 * y - 0.4) + 1.3 * Math.cos(0.0035 * x - 0.0078 * y + 2);
}

/** Height of the drawn ground under a car at (x, y), in scene metres. */
export function roadHeight(kind: Kind, x: number, y: number): number {
  return BASE + (kind === "buggy" ? hills(x, y) : swell(x, y));
}

export interface Tall {
  x: number;
  y: number;
  /** Height and radius, m. */
  height: number;
  radius: number;
}

export interface LandReply {
  grid: Grid;
  /** Per texel: how far the terrain's mesh sinks under the road ribbon, 0..1. */
  sink: Float32Array;
}

/** The land of one route: heights, wild-ground density in the mask, the road's sink. */
export function buildLand(track: Track, size: number): LandReply {
  const { car, seed } = track.definition;
  const cell = EXTENT / (size - 1);
  const half = EXTENT / 2;
  // Distance to the route, coarse, for what happens far from it.
  const coarse = 128;
  const coarseCell = EXTENT / coarse;
  const far = new Float32Array(coarse * coarse);
  for (let row = 0; row < coarse; row += 1) {
    const cy = -half + (row + 0.5) * coarseCell;
    for (let column = 0; column < coarse; column += 1) {
      const cx = -half + (column + 0.5) * coarseCell;
      let least = Infinity;
      for (let i = 0; i < track.n; i += 12) {
        least = Math.min(least, (track.x[i] - cx) ** 2 + (track.y[i] - cy) ** 2);
      }
      far[row * coarse + column] = Math.sqrt(least);
    }
  }
  const distance = (x: number, y: number): number => {
    const gx = Math.max(0, Math.min(coarse - 1.001, (x + half) / coarseCell - 0.5));
    const gy = Math.max(0, Math.min(coarse - 1.001, (y + half) / coarseCell - 0.5));
    const ix = Math.floor(gx);
    const iy = Math.floor(gy);
    const fx = gx - ix;
    const fy = gy - iy;
    const at = iy * coarse + ix;
    const a = far[at] + (far[at + 1] - far[at]) * fx;
    const b = far[at + coarse] + (far[at + coarse + 1] - far[at + coarse]) * fx;
    return a + (b - a) * fy;
  };
  let south = Infinity;
  for (let i = 0; i < track.n; i += 8) {
    south = Math.min(south, track.y[i]);
  }

  const heights = new Float32Array(size * size);
  const masks = new Float32Array(size * size).fill(1);
  const sink = new Float32Array(size * size);
  for (let row = 0; row < size; row += 1) {
    const y = -half + row * cell;
    for (let column = 0; column < size; column += 1) {
      const x = -half + column * cell;
      const road = roadHeight(car, x, y);
      const away = distance(x, y);
      const free = smoothstep(70, 420, away);
      let height = road;
      if (free > 0) {
        const warp = (fbm(x * 0.0009, y * 0.0009, 3, seed) - 0.5) * 500;
        const rough = fbm((x + warp) * 0.0021, (y - warp) * 0.0021, 6, seed + 3);
        if (car === "racecar") {
          const crest = ridged((x + warp) * 0.00062, (y + warp) * 0.00062, 6, seed + 5);
          height += free * (rough * 26 - 8 + crest * crest * 190 * smoothstep(180, 900, away));
        } else {
          // Mesas: broad tops and steep sides, from noise pushed through terraces.
          const raw = fbm((x - warp) * 0.0012, (y + warp) * 0.0012, 5, seed + 7);
          const shelf = smoothstep(0.46, 0.53, raw) * 0.6 + smoothstep(0.58, 0.63, raw) * 0.4;
          height += free * (rough * 18 - 4 + shelf * 120 * smoothstep(160, 620, away));
        }
      }
      if (car === "racecar") {
        // The sea to the south, close beyond the main straight.
        const coast = south - 170 - 90 * fbm(x * 0.0016, 2.5, 4, seed + 11);
        const out = smoothstep(0, 210, coast - y);
        height += (Math.min(height, -22) - height) * out;
      }
      // Everything ends in the sea before the grid does.
      const rim = smoothstep(FAR_LAND - 460, FAR_LAND, Math.hypot(x, y) + (fbm(x * 0.0012, y * 0.0012, 4, seed + 13) - 0.5) * 520);
      height += (-40 - height) * rim;
      heights[row * size + column] = height;
    }
  }

  // The road's own cells, stamped from the centre line: sharper than the distance above.
  const reachCells = Math.ceil(70 / cell);
  const best = new Float32Array(size * size).fill(1e9);
  for (let i = 0; i < track.n; i += 1) {
    const cx = Math.round((track.x[i] + half) / cell);
    const cy = Math.round((track.y[i] + half) / cell);
    for (let row = Math.max(0, cy - reachCells); row <= Math.min(size - 1, cy + reachCells); row += 1) {
      for (let column = Math.max(0, cx - reachCells); column <= Math.min(size - 1, cx + reachCells); column += 1) {
        const dx = -half + column * cell - track.x[i];
        const dy = -half + row * cell - track.y[i];
        const squared = dx * dx + dy * dy;
        const at = row * size + column;
        if (squared >= best[at]) {
          continue;
        }
        best[at] = squared;
        const d = -dx * track.ty[i] + dy * track.tx[i];
        const place = { index: i, s: 0, d };
        const side = d > 0 ? track.left : track.right;
        const a = Math.abs(d);
        sink[at] = 1 - smoothstep(side.reach[i] - 0.5, side.reach[i] + 3, a);
        const surface = track.surface(place);
        const hard = surface === "grass" || surface === "scrub" ? 0 : 1;
        masks[at] = hard ? 0 : Math.max(smoothstep(0.5, 3, a - track.width - side.kerb[i] - side.paved[i] - side.gravel[i]), 0.05);
      }
    }
  }
  return { grid: { size, extent: EXTENT, heights, masks }, sink };
}
