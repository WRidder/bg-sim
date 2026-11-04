import * as THREE from "three";
import { describe, expect, it, vi } from "vitest";
import { attitude } from "../src/engine/frames";
import { buildCourse, type Gate, GateRun } from "../src/engine/gates";
import { mapAxis, shape } from "../src/engine/input";
import { Pacer } from "../src/engine/pacer";
import { BestTime, clock } from "../src/engine/ui";

describe("Pacer", () => {
  it("carries the remainder from frame to frame", () => {
    const pacer = new Pacer(0.005);
    const steps = [0.0166, 0.0166, 0.0168].map((dt) => pacer.stepsFor(dt));
    expect(steps).toEqual([3, 3, 4]);
    expect(pacer.fraction).toBeCloseTo(0, 6);
  });

  it("drops a backlog rather than spiralling", () => {
    const pacer = new Pacer(0.005, 24);
    expect(pacer.stepsFor(1)).toBe(24);
    expect(pacer.behind).toBe(1);
  });
});

describe("axes", () => {
  it("has a dead zone, and still reaches full deflection", () => {
    expect(shape(0.03, 0.04, 0.3)).toBe(0);
    expect(shape(1, 0.04, 0.3)).toBeCloseTo(1, 9);
    expect(shape(-1, 0.04, 0.3)).toBeCloseTo(-1, 9);
  });

  it("is softer than linear in the middle", () => {
    expect(shape(0.5, 0, 0.3)).toBeLessThan(0.5);
  });

  it("maps a lever that reads -1..1 onto 0..1", () => {
    const lever = { axis: 0, invert: true, deadzone: 0, expo: 0, unipolar: true };
    expect(mapAxis(1, lever)).toBe(0);
    expect(mapAxis(-1, lever)).toBe(1);
  });
});

describe("frames", () => {
  const up = new THREE.Vector3(0, 0, 1);
  const forward = new THREE.Vector3(1, 0, 0);

  it("points a level mesh north with its top up", () => {
    const q = attitude(1, 0, 0, 0, new THREE.Quaternion());
    expect(forward.clone().applyQuaternion(q).z).toBeCloseTo(-1, 9);
    expect(up.clone().applyQuaternion(q).y).toBeCloseTo(1, 9);
  });

  it("turns east for a heading of 90 degrees", () => {
    const half = Math.PI / 4;
    const q = attitude(Math.cos(half), 0, 0, Math.sin(half), new THREE.Quaternion());
    expect(forward.clone().applyQuaternion(q).x).toBeCloseTo(1, 9);
  });

  it("drops the right wing for a positive bank", () => {
    const half = Math.PI / 12;
    const q = attitude(Math.cos(half), Math.sin(half), 0, 0, new THREE.Quaternion());
    const rightWing = new THREE.Vector3(0, -1, 0).applyQuaternion(q);
    expect(rightWing.y).toBeLessThan(0);
  });
});

describe("the gate run", () => {
  const gate = (over: Partial<Gate> = {}): Gate => ({
    north: 1000, east: 0, alt: 500, heading: 0, radius: 50, passed: false, hit: false, miss: 0, ...over,
  });

  it("counts a crossing through the ring as a hit", () => {
    const run = new GateRun();
    run.start([gate()]);
    run.step(0.1, [990, 10, 500], [1010, 10, 500]);
    expect(run.gates[0].hit).toBe(true);
    expect(run.gates[0].miss).toBeCloseTo(10, 6);
    expect(run.done).toBeCloseTo(0.1, 9);
  });

  it("adds the penalty for a gate passed outside the ring", () => {
    const run = new GateRun(5);
    run.start([gate()]);
    run.step(2, [990, 300, 500], [1010, 300, 500]);
    expect(run.gates[0].passed).toBe(true);
    expect(run.gates[0].hit).toBe(false);
    expect(run.score()).toBe(7);
  });

  it("ignores a crossing against the course or far off to the side", () => {
    const run = new GateRun(5, 800);
    run.start([gate()]);
    run.step(0.1, [1010, 0, 500], [990, 0, 500]);
    run.step(0.1, [990, 2000, 500], [1010, 2000, 500]);
    expect(run.gates[0].passed).toBe(false);
  });

  it("tells about each gate once, in order", () => {
    const run = new GateRun();
    const seen = vi.fn();
    run.onGate = seen;
    run.start([gate(), gate({ north: 2000 })]);
    run.step(0.1, [990, 0, 500], [1010, 0, 500]);
    run.step(0.1, [1010, 0, 500], [1020, 0, 500]);
    run.step(0.1, [1990, 0, 500], [2010, 0, 500]);
    expect(seen).toHaveBeenCalledTimes(2);
    expect(run.done).not.toBeNull();
  });

  it("builds gates above the ground, and low ones as asked", () => {
    const ground = (north: number): number => (north > 1250 ? 300 : 10);
    const [first, second] = buildCourse([[1000, 0, 170], [2000, 0, 70]], ground, 60);
    expect(first.alt).toBe(470); // the ridge just past the gate counts
    expect(second.alt).toBe(370);
    expect(first.heading).toBeCloseTo(0, 9);
  });
});

describe("the menus' small things", () => {
  it("writes a clock", () => {
    expect(clock(83.26)).toBe("1:23.3");
    expect(clock(5)).toBe("0:05.0");
  });

  it("keeps the lowest time and survives having no storage", () => {
    const best = new BestTime("test");
    // Node has no localStorage: reads give nothing and an offer still counts as a record.
    expect(best.get()).toBeNull();
    expect(best.offer(10)).toBe(true);
  });
});
