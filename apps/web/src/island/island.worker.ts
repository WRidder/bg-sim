/** Builds the island off the main thread: the page stays alive for the seconds this takes. */

import { computeGrid, computeShadow, type Grid } from "../engine/heightfield";
import { EXTENT, islandHeight, islandMask } from "./island";

export interface IslandRequest {
  size: number;
  sun: { x: number; y: number; z: number };
}

export interface IslandReply {
  /** Only with the first reply: a later request just moves the sun. */
  grid?: Grid;
  shadow: Float32Array;
}

let grid: Grid | undefined;

self.onmessage = (event: MessageEvent<IslandRequest>) => {
  const first = grid === undefined;
  grid ??= computeGrid(event.data.size, EXTENT, islandHeight, islandMask);
  const shadow = computeShadow(grid, event.data.sun);
  const reply: IslandReply = { shadow, ...(first ? { grid } : {}) };
  // The worker keeps its heights for the next sun, so only the shadow moves across.
  (self as unknown as Worker).postMessage(reply, [shadow.buffer]);
};
