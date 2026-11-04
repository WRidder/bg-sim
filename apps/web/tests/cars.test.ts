import { describe, expect, it } from "vitest";
import { Line } from "../src/cars/line";
import { Pilot } from "../src/cars/pilot";
import { trackFor, TRACKS } from "../src/cars/tracks";
import { Vehicle } from "../src/cars/vehicle";

/** Drives until `laps` are done, restarting from a recovery as the game does. */
async function drive(id: string, laps: number): Promise<{ car: Vehicle; rescued: number }> {
  const track = trackFor(id);
  const car = await Vehicle.create(track.definition.car, track);
  const pilot = new Pilot(track, new Line(track));
  car.startRun();
  car.go();
  let rescued = 0;
  for (let step = 0; step < 200 * 240 * laps && car.laps.length < laps; step += 1) {
    pilot.drive(car);
    car.advance(car.pacer.step);
    if (car.crashed) {
      rescued += 1;
      car.recover(car.s);
      pilot.reset();
    }
  }
  return { car, rescued };
}

describe.each(TRACKS.map((t) => [t.id] as const))("the scripted driver on %s", (id) => {
  it("completes a clean lap on the FMU, slower than gold", async () => {
    const { car, rescued } = await drive(id, 2);
    expect(rescued).toBe(0);
    expect(car.laps.length).toBe(2);
    const flying = car.laps[1];
    expect(flying.valid).toBe(true);
    const medals = trackFor(id).definition.medals;
    // Gold is what the script does; a medal nobody can see is no aim.
    expect(flying.time).toBeGreaterThan(medals[0] * 0.95);
    expect(flying.time).toBeLessThan(medals[0] + 1);
  }, 120000);
});

describe("the barrier and the clock", () => {
  it("a car driven off the road hits a wall the FMU does not know, and comes back on the road", async () => {
    const track = trackFor("harbour");
    const car = await Vehicle.create("racecar", track);
    car.startRun();
    car.go();
    for (let step = 0; step < 200 * 40 && !car.crashed; step += 1) {
      car.setControls(0.25, 1, 0, 0);
      car.advance(car.pacer.step);
    }
    expect(car.crashed).toBe(true);
    const clock = car.clock;
    car.recover(car.s);
    expect(car.crashed).toBe(false);
    expect(Math.abs(car.d)).toBeLessThan(track.width);
    expect(car.clock).toBeGreaterThanOrEqual(clock);
    expect(car.lapValid).toBe(false);
  }, 60000);
});
