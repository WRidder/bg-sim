/** Builds a land off the main thread: the grid once per route, a new shadow for each sun. */

import { computeShadow, type Grid } from "../engine/heightfield";
import { buildLand } from "./land";
import { talls } from "./placement";
import { trackFor } from "./tracks";

export interface LandRequest {
  track: string;
  size: number;
  sun: { x: number; y: number; z: number };
}

export interface LandAnswer {
  track: string;
  grid?: Grid;
  sink?: Float32Array;
  shadow: Float32Array;
}

const built = new Map<string, { grid: Grid; sink: Float32Array; caster: Grid }>();

/** The land as the sun sees it: trees and buildings stand on it, the road does not know them. */
function withTalls(id: string, grid: Grid): Grid {
  const heights = grid.heights.slice();
  const { size, extent } = grid;
  const cell = extent / (size - 1);
  for (const tall of talls(trackFor(id))) {
    const cx = Math.round((tall.x + extent / 2) / cell);
    const cy = Math.round((tall.y + extent / 2) / cell);
    const reach = Math.max(0, Math.floor(tall.radius / cell));
    for (let row = cy - reach; row <= cy + reach; row += 1) {
      for (let column = cx - reach; column <= cx + reach; column += 1) {
        if (row >= 0 && column >= 0 && row < size && column < size) {
          const at = row * size + column;
          heights[at] = Math.max(heights[at], grid.heights[cy * size + cx] + tall.height);
        }
      }
    }
  }
  return { ...grid, heights };
}

self.onmessage = (event: MessageEvent<LandRequest>) => {
  const { track, size, sun } = event.data;
  let land = built.get(track);
  const first = land === undefined;
  if (!land) {
    const { grid, sink } = buildLand(trackFor(track), size);
    land = { grid, sink, caster: withTalls(track, grid) };
    built.set(track, land);
  }
  const shadow = computeShadow(land.caster, sun);
  const reply: LandAnswer = { track, shadow, ...(first ? { grid: land.grid, sink: land.sink } : {}) };
  // The worker keeps its heights for the next sun, so only the shadow moves across.
  (self as unknown as Worker).postMessage(reply, [shadow.buffer]);
};
