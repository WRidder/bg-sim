/**
 * The island's airfield for an aeroplane on its wheels. An FMU's ground is a plane, flat everywhere,
 * and the runway is the one place that plane is honest: this file says where that is, what is under
 * a wheel, and how a touchdown is written down.
 */

import { smoothstep } from "../engine/noise";
import { AIRFIELD } from "./island";

/** The runway surface above the sea: the height of an FMU's z = 0 on the island. */
export const DATUM = AIRFIELD.elevation + 1.2;
/** The runway's heading in the direction the games land on it: in from the sea. */
export const LANDING_HEADING = AIRFIELD.heading + 180;
/** The aiming point: the first pair of bars painted on the runway, from the threshold. */
export const AIM_POINT = 330;

const HN = Math.cos((LANDING_HEADING * Math.PI) / 180);
const HE = Math.sin((LANDING_HEADING * Math.PI) / 180);

/** Runway 25's threshold on the island. */
export const THRESHOLD = {
  north: AIRFIELD.north - (AIRFIELD.length / 2) * HN,
  east: AIRFIELD.east - (AIRFIELD.length / 2) * HE,
};

/** A surface an FMU's plane may stand for. */
export type Surface = "runway" | "paved" | "grass" | "none";

/** Along the runway from its threshold, and across it to the right of the landing direction. */
export function runwayCoordinates(north: number, east: number): { along: number; across: number } {
  const dn = north - THRESHOLD.north;
  const de = east - THRESHOLD.east;
  return { along: dn * HN + de * HE, across: -dn * HE + de * HN };
}

export function surfaceAt(north: number, east: number): Surface {
  const { along, across } = runwayCoordinates(north, east);
  if (along >= 0 && along <= AIRFIELD.length && Math.abs(across) <= AIRFIELD.width / 2) {
    return "runway";
  }
  if (along >= -120 && along <= AIRFIELD.length + 120 && Math.abs(across) <= 30) {
    return "paved";
  }
  // The island's flat block round the runway: see airfieldMask in island.ts. Its apron and hangars
  // are on the side of `across` that is positive here, because the runway's own heading is the
  // other way. Past the apron stand the hangars, and those are not to be taxied through.
  const middle = Math.abs(along - AIRFIELD.length / 2);
  if ((middle <= 450 && across >= 130 && across <= 425) || (middle <= 750 && Math.abs(across - 150) <= 12)) {
    return "paved";
  }
  if (along >= -300 && along <= AIRFIELD.length + 300 && across >= -240 && across <= 425) {
    return "grass";
  }
  return "none";
}

/** How far out the height of an FMU's plane eases from the runway's down to the sea's, m. */
const EASE = 3000;

/**
 * What to add to the height of an FMU whose plane is the sea out on the open water and the runway
 * at the airfield. Spread over kilometres it is far less than anything a pilot could see, and
 * the sea stays exactly where it is drawn wherever a flight can reach it at speed.
 */
export function lift(north: number, east: number): number {
  const { along, across } = runwayCoordinates(north, east);
  const beyondAlong = Math.max(-300 - along, along - AIRFIELD.length - 300, 0);
  const beyondAcross = Math.max(-240 - across, across - 425, 0);
  return DATUM * (1 - smoothstep(0, EASE, Math.hypot(beyondAlong, beyondAcross)));
}

export interface Touchdown {
  /** Feet a minute, positive down. */
  sink: number;
  /** Indicated knots. */
  kias: number;
  /** Past the threshold, and right of the centre line. */
  along: number;
  across: number;
  pitch: number;
  bank: number;
  surface: Surface;
  noseFirst: boolean;
  bounce: boolean;
}

export type LandingState = "air" | "rolling" | "stopped";

/** The steady wind on the runway, with the part that dies away near the ground. */
export interface Wind {
  /** Metres a second on the nose of a landing. */
  head: number;
  /** Metres a second from the right of a landing. */
  cross: number;
  gusts: number;
}

export const CALM: Wind = { head: 0, cross: 0, gusts: 0 };
