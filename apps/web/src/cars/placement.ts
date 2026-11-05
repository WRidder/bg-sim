/**
 * Where things stand, worked out the same way in the worker that bakes their shadows and on the main
 * thread that draws them. Nothing here touches the DOM.
 */

import { hash2 } from "../engine/noise";
import type { Tall } from "./land";
import type { Track } from "./track";

export interface Tree extends Tall {
  variant: number;
}

const placed = new Map<string, Tree[]>();

/** Clear of the route and its barrier, and not in the sea. */
function clearOf(track: Track, x: number, y: number, room: number): boolean {
  for (let i = 0; i < track.n; i += 7) {
    const dx = track.x[i] - x;
    const dy = track.y[i] - y;
    const r = Math.max(track.left.wall[i], track.right.wall[i]) + room;
    if (dx * dx + dy * dy < r * r) {
      return false;
    }
  }
  return true;
}

/** Trees, or on a stage the few bushes big enough to throw a shadow. */
export function trees(track: Track): Tree[] {
  const kept = placed.get(track.definition.id);
  if (kept) {
    return kept;
  }
  const { seed, car } = track.definition;
  const found: Tree[] = [];
  const racing = car === "racecar";
  const wanted = racing ? 1500 : 500;
  for (let group = 0; group < 900 && found.length < wanted; group += 1) {
    const cx = (hash2(group, 1, seed) - 0.5) * 3000;
    const cy = (hash2(group, 2, seed) - 0.5) * 3000 + (racing ? 460 : 0);
    if (!clearOf(track, cx, cy, 16)) {
      continue;
    }
    const spread = 18 + 70 * hash2(group, 3, seed);
    const members = 3 + Math.floor(22 * hash2(group, 4, seed));
    for (let i = 0; i < members; i += 1) {
      const angle = hash2(group, i + 7, seed) * Math.PI * 2;
      const reach = spread * Math.sqrt(hash2(group, i + 300, seed));
      const x = cx + Math.cos(angle) * reach;
      const y = cy + Math.sin(angle) * reach;
      if (clearOf(track, x, y, 12)) {
        const size = 0.7 + 0.8 * hash2(i, group, seed + 9);
        found.push({ x, y, height: (racing ? 13 : 2.2) * size, radius: (racing ? 4 : 1.6) * size, variant: i % 3 });
      }
    }
  }
  placed.set(track.definition.id, found);
  return found;
}

export interface Structure {
  kind: "stand" | "pits" | "tent";
  s: number;
  side: 1 | -1;
  /** Length along the road, depth away from it, and height, m. */
  length: number;
  depth: number;
  height: number;
  /** Distance of the near face from the centre line. */
  d: number;
}

/** The sharpest bends of a route, as arc lengths at their apex, most severe first. */
export function bends(track: Track, count: number): { s: number; side: 1 | -1 }[] {
  const { n, curvature } = track;
  const found: { index: number; size: number }[] = [];
  for (let i = 0; i < n; i += 1) {
    const size = Math.abs(curvature[i]);
    if (size < 1 / 220) {
      continue;
    }
    let peak = true;
    for (let j = -40; j <= 40 && peak; j += 1) {
      peak = Math.abs(curvature[(i + j + n) % n]) <= size;
    }
    if (peak) {
      found.push({ index: i, size });
    }
  }
  found.sort((a, b) => b.size - a.size);
  return found.slice(0, count).map(({ index }) => ({ s: (index / n) * track.length, side: curvature[index] > 0 ? 1 : -1 }));
}

/** Grandstands by the straight and the big stops, the pits along the straight. */
export function structures(track: Track): Structure[] {
  const out: Structure[] = [];
  const racing = track.definition.car === "racecar";
  const atWall = (s: number, side: 1 | -1, gap: number, span = 40): number => {
    const i = Math.floor(((s + track.length) % track.length) / track.length * track.n);
    const row = side > 0 ? track.left.wall : track.right.wall;
    let top = 0;
    for (let k = -span; k <= span; k += 4) {
      top = Math.max(top, row[(i + k + track.n) % track.n]);
    }
    return top + gap;
  };
  if (racing) {
    out.push({ kind: "stand", s: 70, side: -1, length: 120, depth: 22, height: 15, d: atWall(70, -1, 5, 70) });
    out.push({ kind: "stand", s: 210, side: -1, length: 90, depth: 22, height: 15, d: atWall(210, -1, 5, 60) });
    out.push({ kind: "pits", s: track.length - 70, side: 1, length: 260, depth: 20, height: 11, d: atWall(track.length - 70, 1, 3, 90) });
    for (const bend of bends(track, 3)) {
      const outside = -bend.side as 1 | -1;
      const clear = (outside > 0 ? track.left.wall : track.right.wall)[Math.floor(bend.s / track.length * track.n)];
      if (clear > 18) {
        out.push({ kind: "stand", s: bend.s, side: outside, length: 60, depth: 16, height: 11, d: atWall(bend.s, outside, 6, 30) });
      }
    }
  } else {
    for (const bend of bends(track, 4)) {
      const outside = -bend.side as 1 | -1;
      out.push({ kind: "tent", s: bend.s, side: outside, length: 9, depth: 6, height: 3.4, d: atWall(bend.s, outside, 5, 6) });
    }
  }
  return out.map((block) => seated(track, block)).filter((block): block is Structure => block !== null);
}

/** A building is straight and the road is not: moves it back until it clears, or gives up on it. */
function seated(track: Track, block: Structure): Structure | null {
  const roof = 3;
  const free = (d: number): boolean => {
    const centre = track.pose(block.s, block.side * (d + block.depth / 2));
    const tx = Math.cos(centre.yaw);
    const ty = Math.sin(centre.yaw);
    for (let along = -block.length / 2 - roof; along <= block.length / 2 + roof; along += 6) {
      for (let across = -block.depth / 2 - roof; across <= block.depth / 2 + roof; across += 4) {
        const place = track.locate(centre.x + tx * along - ty * across, centre.y + ty * along + tx * across);
        if (Math.abs(place.d) < (place.d > 0 ? track.left : track.right).wall[place.index] + 2) {
          return false;
        }
      }
    }
    return true;
  };
  for (let d = block.d; d < block.d + 70; d += 3) {
    if (free(d)) {
      return { ...block, d };
    }
  }
  return null;
}

/** Everything that throws a shadow on the land. */
export function talls(track: Track): Tall[] {
  const blocks: Tall[] = [];
  for (const block of structures(track)) {
    for (let along = -block.length / 2; along <= block.length / 2; along += 3) {
      for (let across = 0; across <= block.depth; across += 3) {
        const p = track.pose(block.s + along, block.side * (block.d + across));
        blocks.push({ x: p.x, y: p.y, height: block.height * (block.kind === "stand" ? 0.4 + 0.6 * across / block.depth : 1), radius: 2 });
      }
    }
  }
  // Bushes are too small for a grid of two metres: as casters they only make black blotches.
  return track.definition.car === "racecar" ? [...trees(track), ...blocks] : blocks;
}
