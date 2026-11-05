import { describe, expect, it } from "vitest";
import { flyOrbit, flyTo } from "../src/f16/autopilot";
import { Flight, gateCourse, type Start } from "../src/f16/flight";
import { islandHeight } from "../src/island/island";
import starts from "../src/f16/starts.json";

const ground = islandHeight;

describe("the flight", () => {
  it("takes a mass from the setup at the next start, and flies it heavier", async () => {
    const light = await Flight.create(ground, starts[0] as Start);
    const heavy = await Flight.create(ground, starts[0] as Start);
    heavy.tuning.set("mass", 13000);
    heavy.reset();
    for (let i = 0; i < 400; i += 1) {
      light.advance(light.pacer.step);
      heavy.advance(heavy.pacer.step);
    }
    expect(heavy.tuning.pending).toBe(false);
    expect(heavy.get("alt_m")).toBeLessThan(light.get("alt_m") - 1);
  });

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

describe("the title screen's flight", () => {
  it("is a calm orbit: shallow banks, no rocking, clear of the ground", async () => {
    const orbit = { north: 6000, east: 1500, radius: 30000, alt: 1500 };
    const flight = await Flight.create(ground, starts[2] as Start);
    flight.origin = { north: orbit.north, east: orbit.east - orbit.radius };
    flight.reset();
    let bank = 0;
    let rate = 0;
    let gamma = 0;
    let lowest = Infinity;
    for (let i = 0; i < 200 * 600 && !flight.crashed; i += 1) {
      flyOrbit(flight, orbit, 190, ground);
      flight.advance(flight.pacer.step);
      // The first half minute settles from the trim's speed and height.
      if (i > 200 * 30) {
        bank = Math.max(bank, Math.abs(flight.get("phi_deg")));
        rate = Math.max(rate, Math.abs(flight.get("p_dps")));
        gamma = Math.max(gamma, Math.abs(flight.get("gamma_deg")));
        lowest = Math.min(lowest, flight.altitudeAboveGround());
      }
    }
    const outcome = `bank ${bank.toFixed(1)} rate ${rate.toFixed(1)} gamma ${gamma.toFixed(1)} lowest ${lowest.toFixed(0)}`;
    expect(flight.crashed, outcome).toBe(false);
    expect(bank, outcome).toBeLessThan(25);
    expect(rate, outcome).toBeLessThan(6);
    expect(gamma, outcome).toBeLessThan(6);
    expect(lowest, outcome).toBeGreaterThan(250);
  }, 30000);
});

describe("the gate run", () => {
  it("can be flown from its start without touching the ground", async () => {
    const flight = await Flight.create(ground, starts[2] as Start);
    const { run } = flight;
    run.start(gateCourse(ground));
    const report: string[] = [];
    run.onGate = (gate) => {
      report.push(`${run.gates.indexOf(gate) + 1}: ${gate.hit ? "hit" : "MISS"} by ${gate.miss.toFixed(0)} h=${Math.round(gate.alt)} t=${run.time.toFixed(0)} nz=${flight.get("nz_g").toFixed(1)}`);
    };
    for (let i = 0; i < 200 * 420 && !flight.crashed && run.done === null; i += 1) {
      const gate = run.next();
      if (gate) {
        flyTo(flight, gate, 190, ground);
      }
      flight.advance(flight.pacer.step);
    }
    const outcome = `${report.join("\n")}\nend t=${run.time.toFixed(0)} crashed=${flight.crashed} ${flight.crashReason} at ${flight.north().toFixed(0)},${flight.east().toFixed(0)} alt ${flight.get("alt_m").toFixed(0)}`;
    expect(flight.crashed, outcome).toBe(false);
    expect(run.done, outcome).not.toBeNull();
    // The tight turns are beyond this pilot, not beyond the aircraft.
    expect(run.gates.filter((gate) => gate.hit).length, outcome).toBeGreaterThanOrEqual(10);
  }, 30000);
});
