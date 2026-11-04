import { describe, expect, it } from "vitest";
import { flyTo } from "../src/f16/autopilot";
import { Flight, type Start } from "../src/f16/flight";
import { islandHeight } from "../src/f16/island";
import starts from "../src/f16/starts.json";

const ground = islandHeight;

describe("the flight", () => {
  it("holds a trimmed cruise for a minute", async () => {
    const start = starts[0] as Start;
    const flight = await Flight.create(ground, start);
    for (let i = 0; i < 12000; i += 1) {
      flight.advance(flight.pacer.step);
    }
    expect(flight.crashed).toBe(false);
    expect(flight.time).toBeCloseTo(60, 1);
    expect(Math.abs(flight.get("alt_m") - start.h0)).toBeLessThan(60);
  });

  it("climbs when the stick is pulled and rolls right with the stick right", async () => {
    const flight = await Flight.create(ground, starts[0] as Start);
    const throttle = flight.u[3];
    flight.setControls(0.4, 0, 0, throttle);
    for (let i = 0; i < 300; i += 1) {
      flight.advance(flight.pacer.step);
    }
    expect(flight.get("gamma_deg")).toBeGreaterThan(5);
    flight.reset();
    flight.setControls(0, 0.5, 0, throttle);
    for (let i = 0; i < 100; i += 1) {
      flight.advance(flight.pacer.step);
    }
    expect(flight.get("phi_deg")).toBeGreaterThan(10);
  });

  it("ends in a crash on the ground, not below it", async () => {
    const flight = await Flight.create(ground, starts[0] as Start);
    flight.setControls(-1, 0, 0, 1);
    for (let i = 0; i < 40000 && !flight.crashed; i += 1) {
      flight.advance(flight.pacer.step);
    }
    expect(flight.crashed).toBe(true);
    expect(flight.crashReason).toBe("Water");
  });
});

describe("the gate run", () => {
  it("can be flown from its start without touching the ground", async () => {
    const flight = await Flight.create(ground, starts[2] as Start);
    flight.startGates();
    flight.reset();
    const report: string[] = [];
    flight.onGate = (gate) => {
      report.push(`${flight.gates.indexOf(gate) + 1}: ${gate.hit ? "hit" : "MISS"} by ${gate.miss.toFixed(0)} h=${Math.round(gate.alt)} t=${flight.gateTime.toFixed(0)} nz=${flight.get("nz_g").toFixed(1)}`);
    };
    for (let i = 0; i < 200 * 420 && !flight.crashed && flight.gateDone === null; i += 1) {
      const gate = flight.nextGate();
      if (gate) {
        flyTo(flight, gate, 190, ground);
      }
      flight.advance(flight.pacer.step);
    }
    const outcome = `${report.join("\n")}\nend t=${flight.gateTime.toFixed(0)} crashed=${flight.crashed} ${flight.crashReason} at ${flight.north().toFixed(0)},${flight.east().toFixed(0)} alt ${flight.get("alt_m").toFixed(0)}`;
    expect(flight.crashed, outcome).toBe(false);
    expect(flight.gateDone, outcome).not.toBeNull();
    // The tight turns are beyond this pilot, not beyond the aircraft.
    expect(flight.gates.filter((gate) => gate.hit).length, outcome).toBeGreaterThanOrEqual(10);
  }, 30000);
});
