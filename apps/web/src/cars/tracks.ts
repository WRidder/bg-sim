/**
 * The places to drive. The race car's ground is the flat plane of its FMU, so any layout works and
 * the land around it is free; the buggy's ground is the height function compiled into its FMU, so
 * its stages are routes laid over those hills, found by where the crests throw a buggy in the air.
 * All of them stay inside the box the FMUs accept a start in: a recovery is a start.
 */

import { Track, type TrackDefinition } from "./track";

export const TRACKS: readonly TrackDefinition[] = [
  {
    id: "merrow",
    name: "Cape Merrow",
    blurb: "Three kilometres on the headland: a long sea straight, one very hard stop and the fast Esses.",
    car: "racecar",
    seed: 3,
    halfWidth: 6.5,
    gridBack: 34,
    medals: [79, 85, 93],
    widen: [{ from: 2700, to: 300, side: 1, paved: 20 }],
    points: [
      [0, 0], [240, 0], [470, 2], [610, 14], [672, 74], [664, 170], [712, 250], [664, 332], [716, 420], [720, 520],
      [640, 582], [560, 528], [420, 470], [230, 452], [60, 476], [-92, 540], [-232, 524], [-300, 424], [-262, 332],
      [-346, 262], [-440, 170], [-424, 58], [-300, 6], [-150, 0],
    ],
  },
  {
    id: "harbour",
    name: "Merrow Harbour",
    blurb: "The old club circuit by the water: short, tight and all about the exits.",
    car: "racecar",
    seed: 8,
    halfWidth: 6,
    gridBack: 30,
    medals: [42.5, 46, 51],
    widen: [{ from: 1540, to: 200, side: 1, paved: 18 }],
    points: [
      [0, 0], [250, 0], [450, 6], [565, 45], [595, 125], [545, 195], [430, 172], [345, 118], [262, 168], [182, 240],
      [60, 252], [-62, 205], [-112, 112], [-92, 32], [-42, 3],
    ],
  },
  {
    id: "ochre",
    name: "Ochre Ridge",
    blurb: "A dirt loop over the ridges. Take the crests flat and land straight.",
    car: "buggy",
    seed: 5,
    halfWidth: 4.2,
    gridBack: 24,
    medals: [102.5, 112, 125],
    points: [
      [0, -120], [90, -128], [190, -150], [290, -120], [340, -30], [300, 60], [230, 90], [190, 170], [250, 260],
      [190, 340], [70, 320], [10, 230], [-70, 180], [-170, 240], [-280, 200], [-330, 90], [-270, -10], [-300, -120],
      [-230, -210], [-120, -170],
    ],
  },
  {
    id: "wash",
    name: "Dry Wash",
    blurb: "Down the old river bed and back along the bank: tight, rutted and quick.",
    car: "buggy",
    seed: 12,
    halfWidth: 3.8,
    gridBack: 22,
    medals: [83, 90, 101],
    points: [
      [60, -330], [150, -300], [240, -320], [320, -260], [290, -170], [190, -160], [120, -100], [170, -30], [110, 40],
      [10, 20], [-40, -70], [-130, -60], [-200, -130], [-180, -230], [-90, -240], [-30, -300],
    ],
  },
];

const built = new Map<string, Track>();

export function trackFor(id: string): Track {
  let track = built.get(id);
  if (!track) {
    const definition = TRACKS.find((t) => t.id === id);
    if (!definition) {
      throw new Error(`no track called ${id}`);
    }
    track = new Track(definition);
    built.set(id, track);
  }
  return track;
}
