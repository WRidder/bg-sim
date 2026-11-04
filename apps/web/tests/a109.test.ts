import { describe, expect, it } from "vitest";
import { Flight, type Start } from "../src/a109/flight";
import { Run } from "../src/a109/mission";
import { furnish, layPads, MISSIONS, type Pad } from "../src/a109/pads";
import { Assist, Autopilot, bodySpeeds } from "../src/a109/pilot";
import { Surface } from "../src/a109/surface";
import starts from "../src/a109/starts.json";
import { islandHeight } from "../src/island/island";

const ground = islandHeight;
const parked = starts[0] as Start;

function world(): { surface: Surface; pads: Pad[] } {
  const surface = new Surface(ground);
  const pads = layPads(ground);
  furnish(surface, pads);
  return { surface, pads };
}

const on = (pad: Pad, heading = pad.heading) => ({ north: pad.north, east: pad.east, floor: pad.top, heading });

describe("the mission", () => {
  it("can be flown pad to pad, with every landing on the deck", async () => {
    const { surface, pads } = world();
    const route = MISSIONS[0].pads.map((id) => pads.find((pad) => pad.id === id) as Pad);
    const flight = await Flight.create(surface, parked, on(route[0]));
    const pilot = new Autopilot(route, surface);
    const run = new Run();
    run.start(route);
    flight.pilot = pilot.fly;
    pilot.begin(flight);
    run.onLanding = () => pilot.next(flight);
    let lowest = 200;
    for (let i = 0; i < 200 * 1200 && !flight.crashed && !run.done; i += 1) {
      flight.advance(flight.pacer.step);
      run.update(flight, flight.pacer.step);
      lowest = Math.min(lowest, flight.get("rotor_pct"));
    }
    const outcome = `${flight.crashReason} t=${run.time.toFixed(0)} ${run.landings.map((l) => `${l.pad.id} ${l.grade} ${l.score}`).join(", ")}`;
    expect(flight.crashed, outcome).toBe(false);
    expect(run.done, outcome).toBe(true);
    expect(run.landings.length).toBe(route.length - 1);
    expect(Math.min(...run.landings.map((l) => l.score)), outcome).toBeGreaterThanOrEqual(75);
    expect(lowest, outcome).toBeGreaterThan(92);
  }, 30000);

  it("counts a landing only on the pad it asked for", async () => {
    const { surface, pads } = world();
    const route = [pads[0], pads[1]];
    const flight = await Flight.create(surface, parked, on(pads[3]));
    const run = new Run();
    run.start(route);
    const pilot = new Assist();
    pilot.reset(flight);
    flight.pilot = pilot.fly;
    let landed = 0;
    run.onLanding = () => {
      landed += 1;
    };
    run.update(flight, 3);
    for (let t = 0; t < 4; t += flight.pacer.step) {
      flight.advance(flight.pacer.step);
      run.update(flight, flight.pacer.step);
    }
    expect(flight.crashed).toBe(false);
    expect(landed).toBe(0);
  });
});

describe("the autohover", () => {
  it("lifts off, holds height, flies, brakes and sets down by keys alone", async () => {
    const { surface, pads } = world();
    const flight = await Flight.create(surface, parked, on(pads[0]));
    const pilot = new Assist();
    pilot.reset(flight);
    flight.pilot = pilot.fly;
    const hold = (seconds: number): void => {
      for (let t = 0; t < seconds && !flight.crashed; t += flight.pacer.step) {
        flight.advance(flight.pacer.step);
      }
    };
    pilot.sticks.lift = 1;
    hold(14);
    const up = flight.radar();
    expect(up, "the climb key lifts it off").toBeGreaterThan(12);
    pilot.sticks.lift = 0;
    hold(10);
    const held = flight.altitude();
    hold(10);
    expect(Math.abs(flight.altitude() - held), "hands off, it holds height").toBeLessThan(1);
    expect(flight.groundSpeed(), "hands off, it stays put").toBeLessThan(1.5);
    pilot.sticks.fore = 1;
    hold(18);
    pilot.sticks.fore = 0;
    expect(flight.get("kts"), "the up arrow makes speed").toBeGreaterThan(65);
    hold(4);
    expect(flight.get("kts"), "and it stays when let go").toBeGreaterThan(65);
    pilot.sticks.side = 1;
    hold(7);
    pilot.sticks.side = 0;
    pilot.brake = true;
    hold(36);
    pilot.brake = false;
    expect(flight.groundSpeed(), "the brake stops it").toBeLessThan(2);
    pilot.sticks.lift = -1;
    let sink = 0;
    for (let t = 0; t < 90 && !flight.crashed && !flight.onGround; t += flight.pacer.step) {
      flight.advance(flight.pacer.step);
      sink = Math.max(sink, flight.touchdown?.sink ?? 0);
    }
    expect(flight.crashed, flight.crashReason).toBe(false);
    expect(flight.onGround, "the descent key sets it down").toBe(true);
    expect(sink, "softly").toBeLessThan(2);
  }, 30000);
});

describe("from the keyboard", () => {
  it.each([["calm air", 0], ["a strong wind", 12]])("flies the town hop on the autohover in %s, with nothing but what the keys can ask for", async (_, wind) => {
    const { surface, pads } = world();
    const route = (MISSIONS.find((m) => m.id === "town") as (typeof MISSIONS)[number]).pads.map((id) => pads.find((pad) => pad.id === id) as Pad);
    const flight = await Flight.create(surface, parked, on(route[0]));
    flight.wind = { north: wind * 0.62, east: wind * 0.78 };
    const hands = new Assist();
    hands.reset(flight);
    flight.pilot = hands.fly;
    const run = new Run();
    run.start(route);
    const clamp = (x: number, low: number, high: number): number => Math.max(low, Math.min(high, x));
    const press = (x: number): number => (Math.abs(x) < 0.15 ? 0 : clamp(x, -1, 1));
    for (let i = 0; i < 200 * 900 && !flight.crashed && !run.done; i += 1) {
      const pad = run.next as Pad;
      const n = pad.north - flight.north();
      const e = pad.east - flight.east();
      const distance = Math.hypot(n, e);
      const bearing = (Math.atan2(e, n) * 180) / Math.PI;
      const psi = flight.get("psi_deg");
      const off = ((bearing - psi + 540) % 360) - 180;
      const along = (n * Math.cos((psi * Math.PI) / 180) + e * Math.sin((psi * Math.PI) / 180));
      const across = (-n * Math.sin((psi * Math.PI) / 180) + e * Math.cos((psi * Math.PI) / 180));
      const [forward, sideways] = bodySpeeds(flight);
      const height = flight.altitude() - pad.top;
      const sticks = hands.sticks;
      sticks.fore = sticks.side = sticks.pedals = 0;
      sticks.lift = 0;
      hands.brake = false;
      if (distance > 30) {
        sticks.lift = height < 70 ? 1 : height > 90 ? -0.4 : 0;
        if (height > 25) {
          sticks.pedals = press(off / 25);
          const stop = (forward * forward) / 2.6 + 25;
          if (Math.abs(off) < 12) {
            if (distance < stop) {
              hands.brake = forward > 1;
            } else {
              sticks.fore = forward < 50 ? 1 : 0;
            }
          }
        }
      } else {
        // Over the deck: the arrows' lightest touch, then the descent key.
        sticks.fore = clamp((along - forward * 3) / 14, -0.6, 0.6);
        sticks.side = clamp((across - sideways * 3) / 8, -0.6, 0.6);
        const settled = distance < 3 && Math.hypot(forward, sideways) < 1.2;
        sticks.lift = settled ? -1 : height > 18 ? -0.5 : 0;
      }
      flight.advance(flight.pacer.step);
      run.update(flight, flight.pacer.step);
    }
    const outcome = `${flight.crashReason} t=${run.time.toFixed(0)} leg ${run.leg} at ${flight.north().toFixed(0)},${flight.east().toFixed(0)} radar ${flight.radar().toFixed(1)} ${run.landings.map((l) => `${l.pad.id} ${l.grade} ${l.score}`).join(", ")}`;
    expect(flight.crashed, outcome).toBe(false);
    expect(run.done, outcome).toBe(true);
    expect(Math.min(...run.landings.map((l) => l.score)), outcome).toBeGreaterThanOrEqual(55);
  }, 30000);
});

describe("the ground is honest", () => {
  const until = (flight: Flight, seconds: number): void => {
    for (let t = 0; t < seconds && !flight.crashed; t += flight.pacer.step) {
      flight.advance(flight.pacer.step);
    }
  };

  it("takes a dropped helicopter as a broken one", async () => {
    const { surface, pads } = world();
    const flight = await Flight.create(surface, starts[2] as Start, on(pads[0]));
    flight.setControls(0, 0, 0, 0);
    until(flight, 8);
    expect(flight.crashed).toBe(true);
  });

  it("ends a flight into the sea, and into the mountain", async () => {
    const { surface } = world();
    const cruise = starts.find((s) => s.label.toLowerCase().includes("cruise"));
    const sea = await Flight.create(surface, (cruise ?? starts[2]) as Start, { north: -9000, east: 16000, floor: 0, heading: 0 });
    sea.setControls(0.05, 0.4, 0, 0);
    until(sea, 30);
    expect(sea.crashed).toBe(true);
    expect(sea.crashReason).toBe("Water");
    const hill = await Flight.create(surface, starts[2] as Start, { north: -6840, east: 3180, floor: ground(-6840, 3180) - 40, heading: 0 });
    hill.setControls(0.95, 0, 0, 0);
    until(hill, 30);
    expect(hill.crashed || hill.radar() > 0).toBe(true);
  });

  it("stands level on a deck high above the sea", async () => {
    const { surface, pads } = world();
    const ship = pads.find((pad) => pad.id === "ship") as Pad;
    const flight = await Flight.create(surface, parked, on(ship));
    until(flight, 6);
    expect(flight.crashed, flight.crashReason).toBe(false);
    expect(flight.datum).toBeCloseTo(ship.top, 0);
    expect(flight.gearLoad()).toBeGreaterThan(0.5);
  });
});
