/** The island, built by its worker: the grid once, a new shadow for each sun. */

import { sunDirection, type Sun } from "../engine/atmosphere";
import type { LandSource } from "../engine/stage";
import type { IslandReply, IslandRequest } from "./island.worker";
import IslandWorker from "./island.worker?worker&inline";

export class Island implements LandSource {
  private readonly worker = new IslandWorker();
  private waiting: ((reply: IslandReply) => void) | null = null;

  constructor(private readonly size: number) {
    this.worker.onmessage = (event: MessageEvent<IslandReply>) => this.waiting?.(event.data);
  }

  request(sun: Sun): Promise<IslandReply> {
    return new Promise((resolve) => {
      this.waiting = resolve;
      const { x, y, z } = sunDirection(sun);
      this.worker.postMessage({ size: this.size, sun: { x, y, z } } satisfies IslandRequest);
    });
  }
}
