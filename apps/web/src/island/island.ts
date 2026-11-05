/**
 * The island: a mountain range over a coastal plain, with an airfield on the plain. The FMU's ground
 * is flat at 0 m, which is the sea. Everything above it belongs to this file, which is why the crash
 * check reads the same heightfield the terrain draws.
 */

import { fbm, noise2, ridged, smoothstep } from "../engine/noise";

/** North, east of the runway's centre (m), and its heading. */
export const AIRFIELD = { north: -10400, east: 8800, heading: 72, length: 3000, width: 45, elevation: 6 };
export const TOWN = { north: -9200, east: 4300 };
export const EXTENT = 96_000;
const SEED = 11;

function rotated(north: number, east: number): [number, number] {
  const a = (AIRFIELD.heading * Math.PI) / 180;
  const dn = north - AIRFIELD.north;
  const de = east - AIRFIELD.east;
  return [dn * Math.cos(a) + de * Math.sin(a), -dn * Math.sin(a) + de * Math.cos(a)];
}

/** 1 on the airfield, 0 beyond a ramp that blends it into the land around. */
function airfieldMask(north: number, east: number): number {
  const [along, across] = rotated(north, east);
  const a = Math.max(Math.abs(along) - AIRFIELD.length / 2 - 300, 0);
  const c = Math.max(Math.abs(across + 180) - 420, 0);
  return 1 - smoothstep(0, 1400, Math.hypot(a, c));
}

export function islandHeight(north: number, east: number): number {
  // The open sea, far from any coast, is most of the grid and needs no noise.
  if (Math.hypot((north - 6000) / 58000, (east - 1500) / 58000) > 1.05) {
    return -70;
  }
  const warpN = (fbm(north * 0.00005 + 3, east * 0.00005, 4, SEED) - 0.5) * 16000;
  const warpE = (fbm(north * 0.00005, east * 0.00005 + 7, 4, SEED + 5) - 0.5) * 16000;
  // An elongated island, longest from south-west to north-east, with a broken coast.
  const n = north - 6000 + warpN;
  const e = east - 1500 + warpE;
  const along = (n * 0.82 + e * 0.57) / 34000;
  const across = (-n * 0.57 + e * 0.82) / 19000;
  const shape = 1 - Math.hypot(along, across);
  const coast = shape + (fbm(north * 0.00022, east * 0.00022, 5, SEED + 9) - 0.5) * 0.42;
  const land = smoothstep(0, 0.03, coast);
  const inland = smoothstep(0.1, 0.62, coast);

  const hills = fbm(north * 0.00016, east * 0.00016, 6, SEED + 2) * 260;
  const crests = ridged(north * 0.000105 + 11, east * 0.000105 + 3, 8, SEED + 3);
  const peaks = Math.pow(crests, 1.45) * 2500 * inland;
  const seabed = -70 + 69.5 * smoothstep(-0.34, 0, coast);
  let height = seabed * (1 - land) + land * (9 + hills * smoothstep(0.0, 0.34, coast) + peaks);

  const flat = airfieldMask(north, east);
  height += (AIRFIELD.elevation - height) * flat;
  const pad = townMask(north, east);
  height += (14 - height) * pad * 0.9;
  return height;
}

function townMask(north: number, east: number): number {
  return 1 - smoothstep(1500, 3200, Math.hypot(north - TOWN.north, east - TOWN.east));
}

/** Where the ground is paved or built on: the airfield's apron and the town. */
export function islandMask(north: number, east: number, height: number): number {
  if (height < 1) {
    return 0;
  }
  const [along, across] = rotated(north, east);
  const apron = Math.abs(along) < 900 && across < -70 && across > -420 ? 0.55 : 0;
  const town = townMask(north, east) * smoothstep(0.35, 0.6, noise2(north * 0.002, east * 0.002, 3));
  return Math.max(apron, town * 0.7);
}
