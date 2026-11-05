/**
 * The landing spots and the missions over them. A pad's numbers live here and its look in
 * `scenery.ts`, so the tests can fly a mission with no picture. Every height comes from the ground
 * function a game passes in, the one its terrain draws, so a pad sits on the land it is seen on.
 */

import { AIRFIELD, TOWN } from "../island/island";
import type { Block, Ground, Surface } from "./surface";

export type PadKind = "apron" | "ship" | "clearing" | "roof" | "ledge";

export interface Pad {
  id: PadKind;
  name: string;
  /** One line for the leg that ends here. */
  job: string;
  north: number;
  east: number;
  /** Height of the deck above the sea. */
  top: number;
  /** The circle that counts as on the pad. */
  radius: number;
  /** Which way the way in runs, in degrees. */
  heading: number;
  /** The height of what it stands on, for the picture. */
  base: number;
}

/** Along and across the runway to north and east, as in island.ts. */
function onAirfield(along: number, across: number): [number, number] {
  const a = (AIRFIELD.heading * Math.PI) / 180;
  return [AIRFIELD.north + along * Math.cos(a) - across * Math.sin(a), AIRFIELD.east + along * Math.sin(a) + across * Math.cos(a)];
}

function highestWithin(ground: Ground, north: number, east: number, radius: number): number {
  let height = ground(north, east);
  for (const r of [radius * 0.5, radius]) {
    for (let i = 0; i < 16; i += 1) {
      height = Math.max(height, ground(north + r * Math.cos((i * Math.PI) / 8), east + r * Math.sin((i * Math.PI) / 8)));
    }
  }
  return height;
}

/** A survey ship at anchor, bow to the south-east, so the way in from the airfield is over the stern. */
export const SHIP = { north: -12600, east: 11000, heading: 130, length: 104, beam: 19, deck: 8.6, stern: -38 };
/** The hospital, the tallest thing in town. */
export const TOWER = { north: TOWN.north + 60, east: TOWN.east - 40, wide: 19, tall: 92 };
const LEDGE = { north: -6840, east: 3180 };
const CLEARING = { north: -7400, east: 9800 };

export function layPads(ground: Ground): Pad[] {
  const a = (SHIP.heading * Math.PI) / 180;
  const [apronNorth, apronEast] = onAirfield(-120, -300);
  const clearingBase = highestWithin(ground, CLEARING.north, CLEARING.east, 8);
  const towerBase = ground(TOWER.north, TOWER.east);
  return [
    {
      id: "apron", name: "Airfield apron", job: "Lift off and take the crew out to the ship.",
      north: apronNorth, east: apronEast, top: AIRFIELD.elevation + 1.3, radius: 12, heading: 72, base: AIRFIELD.elevation,
    },
    {
      id: "ship", name: "Survey ship", job: "Land on the stern deck. Keep clear of the bridge.",
      north: SHIP.north + SHIP.stern * Math.cos(a), east: SHIP.east + SHIP.stern * Math.sin(a),
      top: SHIP.deck + 2.6, radius: 10, heading: SHIP.heading, base: 0,
    },
    {
      id: "clearing", name: "Forest clearing", job: "A fire crew is waiting among the trees. Come down straight.",
      ...CLEARING, top: clearingBase + 0.4, radius: 10, heading: 0, base: clearingBase,
    },
    {
      id: "roof", name: "Hospital roof", job: "The tallest roof in town. Mind the air around its corners.",
      north: TOWER.north, east: TOWER.east, top: towerBase + TOWER.tall, radius: 11, heading: 280, base: towerBase,
    },
    {
      id: "ledge", name: "Mountain ledge", job: "A climber on the rock wall above the town. Nowhere else to land.",
      ...LEDGE, top: highestWithin(ground, LEDGE.north, LEDGE.east, 15) + 1.4, radius: 11, heading: 355, base: ground(LEDGE.north, LEDGE.east),
    },
  ];
}

export interface Mission {
  id: string;
  name: string;
  /** The first is where it starts. */
  pads: PadKind[];
}

export const MISSIONS: Mission[] = [
  { id: "round", name: "Island round", pads: ["apron", "ship", "clearing", "roof", "ledge"] },
  { id: "town", name: "Town hop", pads: ["apron", "roof", "ledge"] },
];

/** Everything that stands up from the land at a pad. */
export function padBlocks(pad: Pad): Block[] {
  const deck = (radius: number): Block => ({ north: pad.north, east: pad.east, long: radius, wide: radius, heading: 0, top: pad.top, round: true });
  switch (pad.id) {
    case "apron":
      return [deck(15)];
    case "clearing":
      return [deck(12)];
    case "ledge":
      return [deck(15.5)];
    case "roof":
      return [{ north: pad.north, east: pad.east, long: TOWER.wide, wide: TOWER.wide, heading: 0, top: pad.top - 0.5 }, deck(13.5)];
    case "ship": {
      const a = (SHIP.heading * Math.PI) / 180;
      const part = (at: number, long: number, wide: number, top: number): Block => ({
        north: SHIP.north + at * Math.cos(a), east: SHIP.east + at * Math.sin(a), long, wide, heading: SHIP.heading, top,
      });
      return [
        part(0, SHIP.length / 2, SHIP.beam / 2, SHIP.deck),
        deck(11.5),
        part(2, 13, 8, SHIP.deck + 8.5),
        part(6, 4.5, 8.8, SHIP.deck + 11.5),
      ];
    }
  }
}

/** The paving and sheds of island/world.ts, which stand a little proud of the land. */
export function airfieldBlocks(): Block[] {
  const heading = AIRFIELD.heading;
  const block = (along: number, across: number, long: number, wide: number, top: number): Block => {
    const [north, east] = onAirfield(along, across);
    return { north, east, long, wide, heading, top };
  };
  const paved = AIRFIELD.elevation + 1.15;
  const blocks = [
    block(0, 0, (AIRFIELD.length + 240) / 2, 30, paved),
    block(0, -150, 750, 11.5, paved),
    block(0, -280, 450, 150, paved),
    ...[-650, 0, 650].map((along) => block(along, -80, 11.5, 65, paved)),
    block(560, -440, 45, 22, AIRFIELD.elevation + 12),
    block(-560, -430, 6, 6, AIRFIELD.elevation + 42),
  ];
  for (let i = 0; i < 7; i += 1) {
    blocks.push(block(-390 + i * 130, -452, 26, 31, AIRFIELD.elevation + 24));
  }
  return blocks;
}

/** Puts the pads and the airfield on a surface. */
export function furnish(surface: Surface, pads: readonly Pad[]): void {
  for (const block of airfieldBlocks()) {
    surface.addBlock(block);
  }
  for (const pad of pads) {
    for (const block of padBlocks(pad)) {
      surface.addBlock(block);
    }
  }
}
