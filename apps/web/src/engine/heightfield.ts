/**
 * The land as one grid: what the crash check reads and what the terrain draws are the same numbers.
 * Coordinates are metres north and east of the world's centre. The texture holds, per texel:
 * height (m), sun shadow (0..1, raymarched once for the fixed sun), and a biome mask (0..1).
 */

import * as THREE from "three";

export type HeightFunction = (north: number, east: number) => number;
export type MaskFunction = (north: number, east: number, height: number) => number;

/** Height and mask of every texel, row by row from the south-west. */
export interface Grid {
  size: number;
  extent: number;
  heights: Float32Array;
  masks: Float32Array;
}

export function computeGrid(size: number, extent: number, height: HeightFunction, mask: MaskFunction): Grid {
  const heights = new Float32Array(size * size);
  const masks = new Float32Array(size * size);
  const half = extent / 2;
  const cell = extent / (size - 1);
  for (let row = 0; row < size; row += 1) {
    const north = -half + row * cell;
    for (let column = 0; column < size; column += 1) {
      const east = -half + column * cell;
      const at = row * size + column;
      heights[at] = height(north, east);
      masks[at] = mask(north, east, heights[at]);
    }
  }
  return { size, extent, heights, masks };
}

/** Marches from every texel towards the sun; a soft edge comes from how narrowly the ray clears. */
export function computeShadow(grid: Grid, sun: { x: number; y: number; z: number }): Float32Array {
  const { size, heights } = grid;
  const shadow = new Float32Array(size * size);
  const cell = grid.extent / (size - 1);
  const horizontal = Math.hypot(sun.x, sun.z) || 1e-6;
  // World x is east, z is minus north: the grid's row runs against z.
  const stepColumn = sun.x / horizontal;
  const stepRow = -sun.z / horizontal;
  const rise = (sun.y / horizontal) * cell;
  const reach = Math.min(160, Math.ceil(2400 / Math.max(rise, 0.5)));
  for (let row = 0; row < size; row += 1) {
    for (let column = 0; column < size; column += 1) {
      const at = row * size + column;
      const start = Math.max(heights[at], 0);
      let light = 1;
      for (let i = 1; i < reach; i += 1) {
        const r = Math.round(row + stepRow * i);
        const c = Math.round(column + stepColumn * i);
        if (r < 0 || c < 0 || r >= size || c >= size) {
          break;
        }
        const clearance = start + rise * i - heights[r * size + c];
        light = Math.min(light, Math.max(0, clearance / (i * cell * 0.04) + 1) * (clearance < 0 ? 0 : 1));
        if (light <= 0) {
          break;
        }
      }
      shadow[at] = light;
    }
  }
  return shadow;
}

export class Heightfield {
  readonly size: number;
  /** The width of the square in metres. */
  readonly extent: number;
  readonly heights: Float32Array;
  readonly texture: THREE.DataTexture;
  private readonly data: Uint16Array;

  constructor(grid: Grid, shadow: Float32Array) {
    this.size = grid.size;
    this.extent = grid.extent;
    this.heights = grid.heights;
    const { size } = grid;
    this.data = new Uint16Array(size * size * 4);
    for (let at = 0; at < size * size; at += 1) {
      this.data[at * 4] = THREE.DataUtils.toHalfFloat(grid.heights[at]);
      this.data[at * 4 + 2] = THREE.DataUtils.toHalfFloat(grid.masks[at]);
      this.data[at * 4 + 3] = THREE.DataUtils.toHalfFloat(1);
    }
    this.texture = new THREE.DataTexture(this.data, size, size, THREE.RGBAFormat, THREE.HalfFloatType);
    this.texture.magFilter = THREE.LinearFilter;
    this.texture.minFilter = THREE.LinearFilter;
    this.texture.wrapS = THREE.ClampToEdgeWrapping;
    this.texture.wrapT = THREE.ClampToEdgeWrapping;
    this.setShadow(shadow);
  }

  /** Bilinear height in metres; outside the grid the seabed. */
  at(north: number, east: number): number {
    const cell = this.extent / (this.size - 1);
    const y = (north + this.extent / 2) / cell;
    const x = (east + this.extent / 2) / cell;
    if (x < 0 || y < 0 || x >= this.size - 1 || y >= this.size - 1) {
      return -60;
    }
    const ix = Math.floor(x);
    const iy = Math.floor(y);
    const fx = x - ix;
    const fy = y - iy;
    const at = iy * this.size + ix;
    const a = this.heights[at];
    const b = this.heights[at + 1];
    const c = this.heights[at + this.size];
    const d = this.heights[at + this.size + 1];
    return a + (b - a) * fx + (c - a) * fy + (a - b - c + d) * fx * fy;
  }

  setShadow(shadow: Float32Array): void {
    for (let at = 0; at < shadow.length; at += 1) {
      this.data[at * 4 + 1] = THREE.DataUtils.toHalfFloat(shadow[at]);
    }
    this.texture.needsUpdate = true;
  }
}
