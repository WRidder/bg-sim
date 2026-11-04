/**
 * A pilot for the title screen, and for the test that proves the gate course can be flown: bank
 * towards the target, then ask for the load factor that holds the climb angle it needs.
 */

import type { Flight } from "./flight";

const DEG = 180 / Math.PI;
const clamp = (value: number, low: number, high: number): number => Math.max(low, Math.min(high, value));

export interface Waypoint {
  north: number;
  east: number;
  alt: number;
  /** The direction to go through it, in degrees. */
  heading: number;
}

export function flyTo(flight: Flight, target: Waypoint, speed: number, ground: (north: number, east: number) => number): void {
  const north = flight.north();
  const east = flight.east();
  const alt = flight.get("alt_m");
  const psi = flight.get("psi_deg") / DEG;
  const range = Math.hypot(target.north - north, target.east - east);
  // Aim short of the target on its centre line, so the aircraft arrives going the right way.
  const lead = Math.min(range * 0.42, 1400);
  const through = target.heading / DEG;
  const dn = target.north - lead * Math.cos(through) - north;
  const de = target.east - lead * Math.sin(through) - east;
  const bearing = Math.atan2(de, dn);
  const off = Math.atan2(Math.sin(bearing - psi), Math.cos(bearing - psi)) * DEG;
  const wantRoll = clamp(off * 3.2, -72, 72);

  // Terrain ahead overrides the line to the target.
  const tas = flight.get("tas_mps");
  let floor = 0;
  for (const seconds of [1, 2, 3, 4.5, 6, 8]) {
    const reach = Math.min(tas * seconds, Math.max(range, 200));
    floor = Math.max(floor, ground(north + reach * Math.cos(psi), east + reach * Math.sin(psi)));
  }
  const margin = clamp(range / 40, 40, 110);
  const wantAlt = Math.max(target.alt, floor + margin);
  const wantGamma = clamp(Math.atan2(wantAlt - alt, Math.max(range, 700)) * DEG * 1.4, -14, 24);
  const gamma = flight.get("gamma_deg");
  const phi = flight.get("phi_deg") / DEG;
  const banked = Math.cos(gamma / DEG) / Math.max(Math.cos(phi), 0.3);
  const wantNz = clamp(banked + (wantGamma - gamma) * 0.32, 0, 7);

  const pitch = (wantNz - flight.get("nz_g")) * 0.16 + (wantNz - 1) * 0.11;
  const roll = (wantRoll - flight.get("phi_deg")) * 0.022;
  const throttle = clamp(flight.u[3] + (speed - tas) * 0.0012, 0.05, 0.77);
  flight.setControls(pitch, roll, 0, throttle);
}
