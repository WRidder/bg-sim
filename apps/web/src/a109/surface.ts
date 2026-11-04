/**
 * What a wheel or a blade can hit: the heightfield, and the things that stand on it (decks, roofs,
 * a ship, the trees). The FMU knows one flat ground; this file knows the island, and `Flight` keeps
 * the one under the other.
 */

export type Ground = (north: number, east: number) => number;

/** A box standing on the land: a building, a ship's hull, a deck. Heights are in metres above the sea. */
export interface Block {
  north: number;
  east: number;
  /** Half the length along `heading`, and half the width across it. */
  long: number;
  wide: number;
  heading: number;
  top: number;
  /** A disc of radius `long`, not a box. */
  round?: boolean;
}

interface Tree {
  north: number;
  east: number;
  base: number;
  tall: number;
}

/** Near enough to a cell to find everything that could stand in it. */
const CELL = 64;
/** A tree's cone at its base, as a share of its height: as the forest in island/world.ts draws it. */
const TREE_WIDTH = 0.22;

const key = (north: number, east: number): number => Math.floor(north / CELL) * 100_000 + Math.floor(east / CELL);

export class Surface {
  private readonly blocks = new Map<number, Block[]>();
  private readonly trees = new Map<number, Tree[]>();

  constructor(readonly ground: Ground) {}

  addBlock(block: Block): void {
    const reach = Math.hypot(block.long, block.wide);
    for (let n = block.north - reach; n < block.north + reach + CELL; n += CELL) {
      for (let e = block.east - reach; e < block.east + reach + CELL; e += CELL) {
        const k = key(n, e);
        const cell = this.blocks.get(k);
        if (cell) {
          cell.push(block);
        } else {
          this.blocks.set(k, [block]);
        }
      }
    }
  }

  addTree(north: number, east: number, base: number, tall: number): void {
    const k = key(north, east);
    const cell = this.trees.get(k);
    const tree = { north, east, base, tall };
    if (cell) {
      cell.push(tree);
    } else {
      this.trees.set(k, [tree]);
    }
  }

  /** Takes out what stands within `radius` of a point, for a clearing or a new building. */
  clear(north: number, east: number, radius: number): void {
    for (const [k, cell] of this.trees) {
      const kept = cell.filter((tree) => Math.hypot(tree.north - north, tree.east - east) > radius);
      if (kept.length !== cell.length) {
        this.trees.set(k, kept);
      }
    }
  }

  /** The height a wheel stops at: the sea, the land, or the top of what stands there. */
  at(north: number, east: number): number {
    let height = Math.max(this.ground(north, east), 0);
    const cell = this.blocks.get(key(north, east));
    if (cell) {
      for (const block of cell) {
        if (block.top > height && inside(block, north, east)) {
          height = block.top;
        }
      }
    }
    return height;
  }

  /** True over open water: nothing there to stand on. */
  water(north: number, east: number): boolean {
    return this.ground(north, east) <= 0 && this.at(north, east) <= 0;
  }

  /** True when a point is inside a tree: the ends of the blades reach out sideways into them. */
  inTree(north: number, east: number, up: number): boolean {
    const k = Math.floor(north / CELL);
    const l = Math.floor(east / CELL);
    for (let i = -1; i <= 1; i += 1) {
      for (let j = -1; j <= 1; j += 1) {
        for (const tree of this.trees.get((k + i) * 100_000 + l + j) ?? []) {
          const over = up - tree.base;
          if (over >= 0 && over <= tree.tall && Math.hypot(north - tree.north, east - tree.east) < (tree.tall - over) * TREE_WIDTH) {
            return true;
          }
        }
      }
    }
    return false;
  }

  /** The steepest rise across the ground beneath a helicopter, in degrees. */
  slope(north: number, east: number): number {
    const reach = 4;
    const n = this.at(north + reach, east) - this.at(north - reach, east);
    const e = this.at(north, east + reach) - this.at(north, east - reach);
    return (Math.atan(Math.hypot(n, e) / (2 * reach)) * 180) / Math.PI;
  }
}

function inside(block: Block, north: number, east: number): boolean {
  const dn = north - block.north;
  const de = east - block.east;
  if (block.round) {
    return Math.hypot(dn, de) <= block.long;
  }
  const a = (block.heading * Math.PI) / 180;
  return Math.abs(dn * Math.cos(a) + de * Math.sin(a)) <= block.long && Math.abs(-dn * Math.sin(a) + de * Math.cos(a)) <= block.wide;
}
