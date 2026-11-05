/**
 * Two pilots. One proves the gate course can be flown: bank towards the target, then ask for the
 * load factor that holds the climb angle it needs. It works the aircraft hard, which is why the
 * other one flies behind the title screen: a wide, level orbit that shows the aircraft off.
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
  const roll = (wantRoll - flight.get("phi_deg")) * 0.022;
  flight.setControls(pitchFor(flight, wantGamma, 0.32, 7), roll, 0, throttleFor(flight, speed));
}

function pitchFor(flight: Flight, wantGamma: number, gain: number, limit: number): number {
  const gamma = flight.get("gamma_deg");
  const phi = flight.get("phi_deg") / DEG;
  const banked = Math.cos(gamma / DEG) / Math.max(Math.cos(phi), 0.3);
  const wantNz = clamp(banked + (wantGamma - gamma) * gain, 0, limit);
  return (wantNz - flight.get("nz_g")) * 0.16 + (wantNz - 1) * 0.11;
}

function throttleFor(flight: Flight, speed: number): number {
  return clamp(flight.u[3] + (speed - flight.get("tas_mps")) * 0.0012, 0.05, 0.77);
}

export interface Orbit {
  north: number;
  east: number;
  radius: number;
  alt: number;
}

/** Clockwise round a point, held on the circle by small bank changes. */
export function flyOrbit(flight: Flight, orbit: Orbit, speed: number, ground: (north: number, east: number) => number): void {
  const north = flight.north();
  const east = flight.east();
  const dn = north - orbit.north;
  const de = east - orbit.east;
  const psi = flight.get("psi_deg") / DEG;
  const tas = flight.get("tas_mps");
  // Along the tangent, leaning in or out by how far off the circle the aircraft is.
  const drift = clamp((Math.hypot(dn, de) - orbit.radius) / 9000, -0.3, 0.3);
  const want = Math.atan2(de, dn) + Math.PI / 2 + drift;
  const off = Math.atan2(Math.sin(want - psi), Math.cos(want - psi)) * DEG;
  const circle = Math.atan((tas * tas) / (orbit.radius * 9.81)) * DEG;
  const wantRoll = clamp(circle + clamp(off * 0.8, -12, 12), -24, 24);

  let floor = 0;
  for (const seconds of [4, 8, 14]) {
    floor = Math.max(floor, ground(north + tas * seconds * Math.cos(psi), east + tas * seconds * Math.sin(psi)));
  }
  const wantAlt = Math.max(orbit.alt, floor + 350);
  const wantGamma = clamp((wantAlt - flight.get("alt_m")) * 0.012, -3, 5);
  const roll = (wantRoll - flight.get("phi_deg")) * 0.012;
  flight.setControls(pitchFor(flight, wantGamma, 0.12, 1.6), roll, 0, throttleFor(flight, speed));
}
