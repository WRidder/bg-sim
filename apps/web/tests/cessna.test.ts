import { describe, expect, it } from "vitest";
import { circuitGates, coastGates, coastStart, DOWNWIND_START, LINE_UP, RUNWAY_START, SHORT_FINAL_START } from "../src/cessna/course";
import { DATUM, Flight, runwayCoordinates, type Start, surfaceAt, type Touchdown } from "../src/cessna/flight";
import { markLanding, verdict } from "../src/island/landing";
import { Pilot } from "../src/cessna/pilot";
import starts from "../src/cessna/starts.json";
import { AIRFIELD, islandHeight } from "../src/island/island";

const ground = islandHeight;
const FINAL_START = starts[2] as Start;

function fly(flight: Flight, pilot: Pilot, seconds: number): void {
  flight.autopilot = () => pilot.fly(flight);
  for (let i = 0; i < seconds * 200 && !flight.crashed && flight.landing !== "stopped"; i += 1) {
    flight.advance(flight.pacer.step);
  }
  flight.autopilot = null;
}

const report = (f: Flight): string =>
  `t=${f.time.toFixed(0)} crashed=${f.crashed} ${f.crashReason} landing=${f.landing} at ${f.north().toFixed(0)},${f.east().toFixed(0)} alt ${f.altitude().toFixed(0)} ${JSON.stringify(f.touchdowns)}`;

describe("the aeroplane on the island", () => {
  it("stands on the runway's surface, which is where the FMU's flat ground is laid", async () => {
    const flight = await Flight.create(ground, RUNWAY_START);
    flight.reset(RUNWAY_START, LINE_UP);
    for (let i = 0; i < 1000; i += 1) {
      flight.advance(flight.pacer.step);
    }
    expect(flight.crashed).toBe(false);
    expect(flight.get("on_ground")).toBe(1);
    expect(flight.altitude() - DATUM).toBeCloseTo(1.25, 1);
    expect(DATUM).toBeGreaterThan(islandHeight(AIRFIELD.north, AIRFIELD.east));
    expect(surfaceAt(flight.north(), flight.east())).toBe("runway");
    expect(Math.abs(runwayCoordinates(flight.north(), flight.east()).along - 40)).toBeLessThan(3);
    // The island's compass, not the FMU's own: its x axis lies along runway 25.
    expect(flight.heading()).toBeCloseTo(AIRFIELD.heading + 180, 0);
  });

  it("holds a trim on any heading, at the place it was put", async () => {
    const flight = await Flight.create(ground, RUNWAY_START);
    const { start, values } = coastStart(ground);
    flight.reset(start, values);
    expect(flight.north()).toBeCloseTo(-12500, 0);
    expect(flight.east()).toBeCloseTo(10500, 0);
    expect(flight.heading()).toBeCloseTo(256, 0);
    for (let i = 0; i < 2000; i += 1) {
      flight.advance(flight.pacer.step);
    }
    expect(flight.crashed).toBe(false);
    expect(Math.abs(flight.get("phi_deg"))).toBeLessThan(10);
    expect(Math.abs(flight.heading() - 256)).toBeLessThan(20);
  });

  it("is on the sea, not on the FMU's plane, when it comes down out there", async () => {
    const flight = await Flight.create(ground, FINAL_START);
    flight.setControls(-0.6, 0, 0, 1);
    for (let i = 0; i < 8000 && !flight.crashed; i += 1) {
      flight.advance(flight.pacer.step);
    }
    expect(flight.crashed).toBe(true);
    expect(flight.crashReason).toBe("Water");
    expect(flight.get("alt_m")).toBeGreaterThan(0);
  });

  it("flies into the hills that the FMU knows nothing of", async () => {
    const flight = await Flight.create(ground, RUNWAY_START);
    const { start, values } = coastStart(ground);
    // Straight at the ridge west of the town, low and level.
    flight.reset(start, { ...values, x0: 6000, y0: 0, z0: 60 });
    flight.autopilot = () => flight.setControls(0, 0, 0, 1);
    for (let i = 0; i < 14000 && !flight.crashed; i += 1) {
      flight.advance(flight.pacer.step);
    }
    expect(flight.crashed, report(flight)).toBe(true);
    expect(flight.crashReason, report(flight)).toBe("Terrain");
  });

  it("folds the gear on a landing that is more of an arrival", async () => {
    const flight = await Flight.create(ground, SHORT_FINAL_START);
    flight.reset(SHORT_FINAL_START, { z0: 40, x0: 400 });
    flight.autopilot = () => flight.setControls(-1, 0, 0, 0);
    for (let i = 0; i < 4000 && !flight.crashed; i += 1) {
      flight.advance(flight.pacer.step);
    }
    expect(flight.crashed, report(flight)).toBe(true);
    expect(["The gear folded", "propeller strike"], report(flight)).toContain(flight.crashReason);
  });
});

describe("the landing", () => {
  it("can be flown in calm air from a full circuit, ring by ring", async () => {
    const flight = await Flight.create(ground, RUNWAY_START);
    flight.reset(RUNWAY_START, LINE_UP, circuitGates(ground));
    fly(flight, new Pilot("roll"), 400);
    const outcome = `${report(flight)} rings: ${flight.run.gates.map((g) => `${g.hit ? "hit" : "miss"} ${g.miss.toFixed(0)}`)}`;
    expect(flight.crashed, outcome).toBe(false);
    expect(flight.landing, outcome).toBe("stopped");
    expect(flight.run.gates.filter((g) => g.hit).length, outcome).toBeGreaterThanOrEqual(6);
    expect(flight.touchdowns.length, outcome).toBe(1);
    expect(flight.touchdowns[0].surface, outcome).toBe("runway");
    const sheet = markLanding(flight.touchdowns, flight.stoppedAt);
    expect(sheet.total, JSON.stringify(sheet)).toBeGreaterThanOrEqual(75);
  }, 30000);

  it("can be flown from short final with a 15 kt crosswind", async () => {
    const flight = await Flight.create(ground, SHORT_FINAL_START);
    flight.wind = { head: 2.5, cross: 7, gusts: 0 };
    fly(flight, new Pilot("final"), 120);
    expect(flight.crashed, report(flight)).toBe(false);
    expect(flight.landing, report(flight)).toBe("stopped");
    expect(flight.stoppedAt?.surface === "runway" || flight.stoppedAt?.surface === "paved", report(flight)).toBe(true);
    expect(Math.abs(flight.touchdowns[0].across), report(flight)).toBeLessThan(22);
  }, 20000);

  it("can be flown with the engine stopped, from abeam the runway", async () => {
    const flight = await Flight.create(ground, DOWNWIND_START);
    const pilot = new Pilot("glide");
    flight.autopilot = () => {
      if (flight.time > 3 && !flight.engineOut) {
        flight.cutEngine();
      }
      pilot.fly(flight);
    };
    for (let i = 0; i < 200 * 200 && !flight.crashed && flight.landing !== "stopped"; i += 1) {
      flight.advance(flight.pacer.step);
    }
    expect(flight.crashed, report(flight)).toBe(false);
    expect(flight.get("rpm"), report(flight)).toBeLessThan(100);
    expect(flight.landing, report(flight)).toBe("stopped");
    expect(flight.touchdowns[0].surface, report(flight)).toBe("runway");
  }, 30000);

  it("marks a good landing above a poor one", () => {
    const good: Touchdown = { sink: 110, kias: 52, along: 340, across: 1, pitch: 6, bank: 0.5, surface: "runway", noseFirst: false, bounce: false };
    const poor: Touchdown = { ...good, sink: 640, along: 900, across: -14, pitch: 1, bank: 6 };
    const best = markLanding([good], { surface: "runway" });
    expect(best.total).toBe(100);
    expect(best.verdict).toBe(verdict(100));
    const bad = markLanding([poor, { ...poor, bounce: true }], { surface: "runway" });
    expect(bad.total).toBeLessThan(35);
    expect(bad.lines.map((l) => l.label)).toContain("Bounces");
    expect(markLanding([{ ...good, noseFirst: true }], null).lines[3].points).toBe(0);
    expect(markLanding([{ ...good, surface: "grass" }], { surface: "grass" }).total).toBe(70);
  });
});

describe("the coast run", () => {
  it("can be flown from its start without touching anything", async () => {
    const flight = await Flight.create(ground, RUNWAY_START);
    const { start, values } = coastStart(ground);
    const gates = coastGates(ground);
    flight.reset(start, values, gates);
    const pilot = new Pilot("route");
    flight.autopilot = () => {
      pilot.fly(flight);
      const gate = flight.run.next();
      if (gate) {
        pilot.route(flight, gate, ground);
      }
    };
    for (let i = 0; i < 200 * 420 && !flight.crashed && flight.run.done === null; i += 1) {
      flight.advance(flight.pacer.step);
    }
    const outcome = `${report(flight)} rings: ${gates.map((g) => `${g.hit ? "hit" : "miss"} ${g.miss.toFixed(0)}`)}`;
    expect(flight.crashed, outcome).toBe(false);
    expect(flight.run.done, outcome).not.toBeNull();
    expect(gates.filter((g) => g.hit).length, outcome).toBeGreaterThanOrEqual(7);
    expect(flight.run.done as number, outcome).toBeLessThan(330);
  }, 30000);

  it("keeps every ring clear of the ground it stands over", () => {
    for (const gate of [...coastGates(ground), ...circuitGates(ground)]) {
      expect(gate.alt - gate.radius, `${gate.north},${gate.east}`).toBeGreaterThan(Math.max(ground(gate.north, gate.east), 0));
    }
  });
});
