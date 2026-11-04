/**
 * Where the flights go. Hills stand under the approach to runway 07, so this island is landed on
 * one way: runway 25, in from the sea. That also puts the circuit to the left over the bay, with
 * the desktop's trims still good for it.
 */

import { buildCourse, type Gate } from "../engine/gates";
import { DATUM, FRAME, type Start, THRESHOLD_X } from "./flight";
import starts from "./starts.json";

const DEG = Math.PI / 180;
type Ground = (north: number, east: number) => number;

export const RUNWAY_START = starts[0] as Start;
export const DOWNWIND_START = starts[1] as Start;
export const SHORT_FINAL_START = starts[3] as Start;
const CRUISE_START = starts[4] as Start;

/** FMU x and east to the island's north and east. */
export function fromFrame(x: number, east: number): [number, number] {
  const h = FRAME.heading * DEG;
  return [FRAME.north + x * Math.cos(h) - east * Math.sin(h), FRAME.east + x * Math.sin(h) + east * Math.cos(h)];
}

/** The island's north and east to FMU x and east. */
export function toFrame(north: number, east: number): [number, number] {
  const h = FRAME.heading * DEG;
  const n = north - FRAME.north;
  const e = east - FRAME.east;
  return [n * Math.cos(h) + e * Math.sin(h), -n * Math.sin(h) + e * Math.cos(h)];
}

/** The line-up, just past the threshold, with the whole runway ahead. */
export const LINE_UP = { x0: THRESHOLD_X + 40 };

/**
 * The rings of a circuit, in the FMU's frame: x, east, height. A left-hand circuit at 700 ft. The
 * last two sit on the three-degree path to the aiming point, and they are the approach the player
 * is judged on, so they get tighter.
 */
const CIRCUIT: readonly (readonly [number, number, number])[] = [
  [1650, 0, 90],
  [2650, -440, 178],
  [1540, -1120, 210],
  [-250, -950, 210],
  [-1850, -620, 180],
  [-1250, 0, 70],
  [-520, 0, 33],
];

export function circuitGates(ground: Ground): Gate[] {
  const gates = buildCourse(CIRCUIT.map(([x, east, height]) => [...fromFrame(x, east), height] as const), ground, 42);
  // The fixed heights are above the runway, not above whatever is below them.
  gates.forEach((gate, i) => {
    gate.alt = CIRCUIT[i][2] + DATUM;
  });
  gates[gates.length - 2].radius = 34;
  gates[gates.length - 1].radius = 24;
  gates[gates.length - 2].heading = FRAME.heading;
  gates[gates.length - 1].heading = FRAME.heading;
  return gates;
}

/**
 * The coast run: north, east and height above the ground. Along the south shore, round the
 * headland and through the town, then down the runway as low as you dare: the last ring is the line.
 */
const COAST: readonly (readonly [number, number, number])[] = [
  [-12900, 8800, 70],
  [-13600, 5500, 60],
  [-13300, 3600, 90],
  [-11600, 2700, 90],
  [-9700, 3400, 125],
  [-10250, 5000, 90],
  [-10864, 7373, 26],
  [-10400, 8800, 20],
  [-9936, 10227, 20],
];

export function coastGates(ground: Ground): Gate[] {
  const gates = buildCourse(COAST, ground, 62, 40);
  gates[gates.length - 3].radius = 24;
  gates[gates.length - 2].radius = 16;
  gates[gates.length - 1].radius = 16;
  return gates;
}

export const COAST_ENTRY = { north: -12500, east: 10500, heading: 256, height: 90 };

/** A cruise trim moved out over the bay, low and heading for the first ring. */
export function coastStart(ground: Ground): { start: Start; values: Record<string, number> } {
  const { north, east, heading, height } = COAST_ENTRY;
  const [x, fmuEast] = toFrame(north, east);
  // The trim's body-frame state is good on any heading: turn its attitude about the vertical.
  const { qw0, qx0, qy0, qz0 } = CRUISE_START.values;
  const turn = (((heading - FRAME.heading - 90) * DEG) / 2) * -1;
  const w = Math.cos(turn);
  const z = Math.sin(turn);
  return {
    start: CRUISE_START,
    values: {
      x0: x,
      y0: -fmuEast,
      z0: Math.max(ground(north, east), 0) + height - DATUM,
      qw0: w * qw0 - z * qz0,
      qx0: w * qx0 - z * qy0,
      qy0: w * qy0 + z * qx0,
      qz0: w * qz0 + z * qw0,
    },
  };
}
