import { describe, expect, it } from "vitest";
import { DroneManager, LockOn, MAX_DRONES, SPAWN_DELAY } from "../src/f16/targets";

const ground = () => 0;

describe("the target drones", () => {
  it("never has more than three, and replaces one after a kill", () => {
    const drones = new DroneManager(ground);
    drones.reset(0, 0, 3000, 0);
    expect(drones.alive()).toHaveLength(MAX_DRONES);
    expect(drones.spawn(0, 0, 3000, 0)).toBeNull();
    const first = drones.alive()[0];
    drones.kill(first.id);
    expect(drones.alive()).toHaveLength(MAX_DRONES - 1);
    for (let i = 0; i < SPAWN_DELAY / 0.005 + 10; i += 1) {
      drones.step(0.005, 0, 0, 3000, 0);
    }
    expect(drones.alive()).toHaveLength(MAX_DRONES);
    expect(drones.byId(first.id)?.alive).toBe(false);
  });

  it("builds a one-second lock inside 45 degrees and breaks outside it", () => {
    const drones = new DroneManager(ground);
    drones.reset(0, 0, 3000, 0);
    const lock = new LockOn();
    const own = [0, 0, 3000] as const;
    let state = lock.update(0.005, own, [1, 0, 0], drones);
    for (let i = 0; i < 250; i += 1) {
      state = lock.update(0.005, own, [1, 0, 0], drones);
    }
    expect(state.locked).toBe(true);
    expect(state.selectedId).not.toBeNull();
    expect(state.angleDeg).toBeLessThan(5);
    for (let i = 0; i < 250; i += 1) {
      state = lock.update(0.005, own, [0, 0, 1], drones);
    }
    expect(state.locked).toBe(false);
    expect(["OUT OF FOV", "TOO FAR"]).toContain(state.reason);
  });

  it("cycles the designation to the next live drone", () => {
    const drones = new DroneManager(ground);
    drones.reset(0, 0, 3000, 0);
    const lock = new LockOn();
    lock.update(0.005, [0, 0, 3000], [1, 0, 0], drones);
    const first = lock.selectedId;
    lock.cycle(drones);
    expect(lock.selectedId).not.toBe(first);
    expect(lock.locked).toBe(false);
  });
});
