/** The land of the route in play, from its worker. The stage holds one field, so a change of route rewrites it. */

import * as THREE from "three";
import { sunDirection, type Sun } from "../engine/atmosphere";
import type { Grid, Heightfield } from "../engine/heightfield";
import type { LandSource } from "../engine/stage";
import type { LandAnswer, LandRequest } from "./land.worker";
import LandWorker from "./land.worker?worker&inline";

interface Kept {
  grid: Grid;
  sink: Float32Array;
}

export class Land implements LandSource {
  private readonly worker = new LandWorker();
  private waiting: ((reply: LandAnswer) => void) | null = null;
  private readonly kept = new Map<string, Kept>();

  constructor(
    public track: string,
    private readonly size: number,
  ) {
    this.worker.onmessage = (event: MessageEvent<LandAnswer>) => this.waiting?.(event.data);
  }

  private ask(track: string, sun: Sun): Promise<LandAnswer> {
    return new Promise((resolve) => {
      this.waiting = resolve;
      const { x, y, z } = sunDirection(sun);
      this.worker.postMessage({ track, size: this.size, sun: { x, y, z } } satisfies LandRequest);
    });
  }

  /** What the stage asks for: the grid the first time, a shadow for a new sun after that. */
  async request(sun: Sun): Promise<{ grid?: Grid; shadow: Float32Array }> {
    const reply = await this.ask(this.track, sun);
    if (reply.grid && reply.sink) {
      this.kept.set(reply.track, { grid: reply.grid, sink: reply.sink });
    }
    return { grid: reply.grid, shadow: reply.shadow };
  }

  grid(): Grid {
    return (this.kept.get(this.track) as Kept).grid;
  }

  sink(): Float32Array {
    return (this.kept.get(this.track) as Kept).sink;
  }

  /** Moves the stage's field to another route. */
  async change(track: string, sun: Sun, field: Heightfield): Promise<void> {
    this.track = track;
    const { shadow } = await this.request(sun);
    const { grid, sink } = this.kept.get(track) as Kept;
    writeField(field, grid, sink);
    field.setShadow(shadow);
  }
}

/** Puts heights, mask and sink into a field's texture; `Heightfield` only ever writes its shadow. */
export function writeField(field: Heightfield, grid: Grid, sink: Float32Array): void {
  field.heights.set(grid.heights);
  const data = field.texture.image.data as unknown as Uint16Array;
  const half = THREE.DataUtils.toHalfFloat;
  for (let at = 0; at < grid.heights.length; at += 1) {
    data[at * 4] = half(grid.heights[at]);
    data[at * 4 + 2] = half(grid.masks[at]);
    data[at * 4 + 3] = half(sink[at]);
  }
  field.texture.needsUpdate = true;
}
