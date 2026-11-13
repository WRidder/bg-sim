import { describe, expect, it } from "vitest";
import { localToWorld, MissileSystem, targetInput } from "../src/f16/missiles";
import type { Drone } from "../src/f16/targets";

function drone(north: number, east: number, alt: number, heading: number, speed: number): Drone {
  return { id: 1, north, east, alt, heading, speed, turnRate: 0, turnAt: 99, age: 0, alive: true };
}

describe("the AIM-9X Wasm", () => {
  it("gets launch-relative target data and gives the local point back", () => {
    const frame = { north: 1000, east: 2000, alt: 3000, heading: 90 };
    const target = drone(3000, 2000, 3100, 90, 150);
    const input = targetInput(frame, target);
    expect(input[0]).toBeCloseTo(0, 6);
    expect(input[1]).toBeCloseTo(-2000, 6);
    expect(input[2]).toBeCloseTo(-3100, 6);
    const [north, east, alt] = localToWorld(frame, input[0], -input[1], -input[2]);
    expect(north).toBeCloseTo(target.north, 6);
    expect(east).toBeCloseTo(target.east, 6);
    expect(alt).toBeCloseTo(target.alt, 6);
  });

  it("flies from a wingtip and lights the fuze", async () => {
    const system = await MissileSystem.create();
    const frame = { north: 0, east: 0, alt: 3000, heading: 0 };
    const target = drone(2000, 0, 3000, 0, 150);
    const missile = system.fire(0, frame, target, 400);
    expect(missile).not.toBeNull();
    for (let i = 0; i < 1600 && missile && !missile.done; i += 1) {
      system.advance(0.005);
    }
    expect(missile?.done).toBe(true);
    expect(missile?.get("north_m")).toBeGreaterThan(1000);
    expect(missile?.time).toBeLessThan(6);
  }, 30000);

  it("keeps two instances independent", async () => {
    const system = await MissileSystem.create();
    const a = system.fire(0, { north: 0, east: 0, alt: 3000, heading: 0 }, drone(2000, 0, 3000, 0, 150), 400);
    const b = system.fire(1, { north: 0, east: 0, alt: 3000, heading: 180 }, drone(-2000, 0, 3000, 180, 150), 400);
    for (let i = 0; i < 300; i += 1) {
      system.advance(0.005);
    }
    expect(a?.get("north_m")).toBeGreaterThan(100);
    expect(b?.get("north_m")).toBeGreaterThan(100);
  }, 30000);
});
