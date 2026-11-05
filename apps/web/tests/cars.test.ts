import { describe, expect, it } from "vitest";
import { Line } from "../src/cars/line";
import { model as racecar } from "../src/cars/racecar.gen";
import { Pilot } from "../src/cars/pilot";
import { trackFor, TRACKS } from "../src/cars/tracks";
import { INPUTS, Vehicle } from "../src/cars/vehicle";
import { Fmu } from "../src/engine/fmu";
import { Sim } from "../src/engine/sim";

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

/** The race car on the FMU's own flat ground, with no track to hit. */
class Bench extends Sim<"kmh" | "beta"> {
  static async create(): Promise<Bench> {
    return new Bench(await Fmu.load(racecar), INPUTS, ["kmh", "beta"]);
  }

  start(): void {
    this.restart({ z0: 0.31 }, () => this.u.fill(1, 5));
  }

  drive(steer: number, throttle: number, brake = 0): void {
    this.u[0] = steer;
    this.u[1] = throttle;
    this.u[2] = brake;
    this.advance(this.pacer.step);
  }
}

describe("the setup of a car", () => {
  /** The car turning hard at about 60 km/h, then the accelerator floored: the peak body slip, deg. */
  async function floored(setup: Record<string, number>): Promise<number> {
    const car = await Bench.create();
    for (const [name, value] of Object.entries(setup)) {
      car.tuning.set(name, value);
    }
    car.start();
    while (car.get("kmh") < 60) {
      car.drive(0, 0.3);
    }
    for (let i = 0; i < 700; i += 1) {
      const error = 60 - car.get("kmh");
      car.drive(0.34 * Math.min(1, i / 400), Math.max(0, Math.min(0.45, 0.05 * error + 0.05)), Math.max(0, -0.03 * error));
    }
    let peak = 0;
    for (let i = 0; i < 600; i += 1) {
      car.drive(0.34, Math.min(1, i / 36));
      peak = Math.max(peak, Math.abs((car.get("beta") * 180) / Math.PI));
    }
    return peak;
  }

  it("reaches the FMU at the next start, not before", async () => {
    const car = await Vehicle.create("racecar", trackFor("harbour"));
    car.place(0);
    expect(car.get("motor_r_tlim")).toBeCloseTo(300, 3);
    car.tuning.set("MotorR/T_max", 150);
    car.advance(car.pacer.step);
    expect(car.get("motor_r_tlim")).toBeCloseTo(300, 3);
    car.place(0);
    expect(car.get("motor_r_tlim")).toBeCloseTo(150, 3);
  });

  it("cures the spin on the throttle with less traction control slip", async () => {
    expect(await floored({})).toBeGreaterThan(60);
    expect(await floored({ "MotorR/kappa_tc": 0.05 })).toBeLessThan(15);
  }, 60000);

  it("cures it with less torque too", async () => {
    expect(await floored({ "MotorR/T_max": 200 })).toBeLessThan(15);
  }, 60000);

  it("gives the buggy its own settings", async () => {
    const car = await Vehicle.create("buggy", trackFor(TRACKS.find((t) => t.car === "buggy")?.id as string));
    expect(car.tuning.has("Brakes/Th")).toBe(true);
    expect(car.tuning.has("Aero/ClA")).toBe(false);
  });
});

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
