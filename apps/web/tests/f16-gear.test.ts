/** The F-16 on its wheels: the frame on the runway, a take-off, a landing, and what ends one. */

import { describe, expect, it } from "vitest";
import { FINAL_START, Flight, RUNWAY_START, type Start } from "../src/f16/flight";
import { AIM_POINT, DATUM, LANDING_HEADING, lift, runwayCoordinates, surfaceAt, THRESHOLD } from "../src/island/airfield";
import { markLanding } from "../src/island/landing";

/** The island as far as these flights care: low land, and the sea beyond the airfield. */
const ground = (north: number, east: number): number => (surfaceAt(north, east) === "none" ? -5 : 6);
const clamp = (v: number, low: number, high: number): number => Math.max(low, Math.min(high, v));

/** A scripted pilot's hold of a climb angle, a speed and the centre line. */
function hold(f: Flight, gamma: number, speed: number | null, throttle = 0): void {
  const { across } = runwayCoordinates(f.north(), f.east());
  const off = ((f.heading() - LANDING_HEADING + 540) % 360) - 180;
  const wantBank = clamp(-across * 0.25 - off * 2, -15, 15);
  const banked = Math.cos((f.get("gamma_deg") * Math.PI) / 180) / Math.cos((f.get("phi_deg") * Math.PI) / 180);
  const wantNz = banked + (gamma - f.get("gamma_deg")) * 0.08;
  const power = speed === null ? throttle : clamp(f.u[3] + (speed - f.get("tas_mps")) * 0.0002, 0, 0.77);
  f.setControls((wantNz - 1) * 0.3 + (wantNz - f.get("nz_g")) * 0.04 - f.get("q_dps") * 0.012, (wantBank - f.get("phi_deg")) * 0.03, 0, power);
}

function roll(f: Flight, stick = 0): void {
  const { across } = runwayCoordinates(f.north(), f.east());
  const off = ((f.heading() - LANDING_HEADING + 540) % 360) - 180;
  f.setControls(stick, 0, clamp(-across * 0.05 - off * 0.15, -1, 1), f.u[3]);
}

/** Down the glide path, on to a last climb angle from a given height, the wheels on, and the brakes. */
function land(f: Flight, flare = -0.4, from = 7): void {
  for (let i = 0; i < 40000 && !f.crashed && f.landing !== "stopped"; i += 1) {
    const height = f.get("alt_m") - 1.7;
    if (f.touchdowns.length > 0) {
      roll(f, 0);
      f.setControls(f.u[0], f.u[1], f.u[2], 0);
      f.setBrakes(f.get("tas_mps") < 70 ? 1 : 0);
    } else if (height > from) {
      hold(f, -3, 76);
    } else {
      hold(f, flare, null, 0);
    }
    f.advance(f.pacer.step);
  }
}

describe("the F-16's frame", () => {
  it("stands on the runway past the threshold, going down it", async () => {
    const f = await Flight.create(ground, RUNWAY_START);
    const { along, across } = runwayCoordinates(f.north(), f.east());
    expect(along).toBeCloseTo(60, 1);
    expect(across).toBeCloseTo(0, 1);
    expect(f.heading()).toBeCloseTo(LANDING_HEADING, 0);
    expect(f.altitude()).toBeCloseTo(DATUM + RUNWAY_START.h0, 3);
    expect(f.altitudeAboveGround()).toBeCloseTo(RUNWAY_START.h0, 3);
    expect(f.onGround).toBe(true);
  });

  it("keeps its start out at sea, with nothing to lift", async () => {
    expect(lift(-27000, -5000)).toBe(0);
    expect(lift(THRESHOLD.north, THRESHOLD.east)).toBe(DATUM);
    const f = await Flight.create(ground, { label: "", vt0: 152.4, h0: 500, alpha0: 3.4, el0: -0.65, thtl0: 0.16, xcg: 0.35 });
    expect(f.altitude()).toBe(f.get("alt_m"));
    expect(f.heading()).toBeCloseTo(0, 0);
  });

  it("starts the final on the glide path, gear down", async () => {
    const f = await Flight.create(ground, FINAL_START);
    expect(f.get("gear_pos")).toBeCloseTo(1, 3);
    const { along } = runwayCoordinates(f.north(), f.east());
    expect(along).toBeLessThan(-2000);
    const ahead = (AIM_POINT - along) * Math.tan((3 * Math.PI) / 180);
    expect(f.get("alt_m") - 1.7).toBeCloseTo(ahead, 0);
  });
});

describe("the F-16 on its wheels", () => {
  it("sits still on the runway at idle", async () => {
    const f = await Flight.create(ground, RUNWAY_START);
    for (let i = 0; i < 2000; i += 1) {
      f.setBrakes(1);
      f.advance(f.pacer.step);
    }
    expect(f.crashed).toBe(false);
    expect(f.get("alt_m")).toBeCloseTo(RUNWAY_START.h0, 1);
    expect(Math.abs(runwayCoordinates(f.north(), f.east()).along - 60)).toBeLessThan(1);
  });

  it("takes off, raises the gear and leaves the wheels behind", async () => {
    const f = await Flight.create(ground, RUNWAY_START);
    let liftOff: number | null = null;
    for (let i = 0; i < 20000 && !f.crashed; i += 1) {
      f.setControls(0, 0, 0, 1);
      if (f.onGround) {
        roll(f, f.get("cas_mps") > 72 ? 1 : 0);
        f.setControls(f.u[0], 0, f.u[2], 1);
      } else {
        if (liftOff === null) {
          liftOff = f.get("cas_mps") * 1.94384;
        }
        hold(f, 8, null, 1);
        if (f.get("alt_m") > 30 && f.gearDown) {
          f.toggleGear();
        }
      }
      f.advance(f.pacer.step);
      if (f.get("alt_m") > 150 && f.get("gear_pos") < 0.001) {
        break;
      }
    }
    expect(f.crashReason).toBe("");
    expect(liftOff).toBeGreaterThan(145);
    expect(liftOff).toBeLessThan(190);
    expect(f.get("gear_pos")).toBeLessThan(0.001);
    expect(f.landing).toBe("air");
    expect(runwayCoordinates(f.north(), f.east()).along).toBeLessThan(3000 + 4000);
  });

  it("lands from the final and stops on the runway, and that gets a fair mark", async () => {
    const f = await Flight.create(ground, FINAL_START);
    land(f);
    expect(f.crashReason).toBe("");
    expect(f.landing).toBe("stopped");
    expect(f.stoppedAt?.surface).toBe("runway");
    const [first] = f.touchdowns;
    expect(first.surface).toBe("runway");
    expect(first.noseFirst).toBe(false);
    expect(first.sink).toBeLessThan(350);
    expect(first.along).toBeGreaterThan(100);
    expect(markLanding(f.touchdowns, f.stoppedAt, 0, f.scraped, { sink: [100, 600], pitch: 9 }).total).toBeGreaterThan(50);
  });

  it("does not forgive a landing with the gear up", async () => {
    const f = await Flight.create(ground, FINAL_START);
    f.toggleGear();
    land(f);
    expect(f.crashReason).toBe("A belly landing");
  });

  it("folds the gear past what the legs take", async () => {
    const f = await Flight.create(ground, FINAL_START);
    land(f, -8, 14);
    expect(f.crashReason).toBe("The gear folded");
  });

  it("is a crash off the airfield, whatever the wheels think of it", async () => {
    const off: Start = { ...RUNWAY_START, north0: -700 };
    const f = await Flight.create((north, east) => (surfaceAt(north, east) === "none" ? -5 : 6), off);
    f.advance(f.pacer.step);
    expect(f.crashed).toBe(true);
    expect(f.crashReason).toBe("Water");
  });
});
