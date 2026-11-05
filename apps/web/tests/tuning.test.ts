import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { FmuParameter } from "../src/engine/fmu";
import { everyKnob, roundStep, Tuning } from "../src/engine/tuning";

const PARAMETERS: FmuParameter[] = [
  { name: "MotorR/T_max", start: 300, min: 50, max: 400, unit: "N*m" },
  { name: "Aero/ClA", start: 2.6, min: 0, max: 4 },
  { name: "x0", start: 0, min: -1000, max: 1000 },
  { name: "Heli/Wow/lower", start: 0 },
];

/** A browser's store, for the runs that need one. */
function store(): Map<string, string> {
  const data = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => data.set(key, value),
  });
  return data;
}

describe("Tuning", () => {
  beforeEach(() => {
    store();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("offers only what has a range", () => {
    expect(new Tuning("m", PARAMETERS).settable.map((p) => p.name)).toEqual(["MotorR/T_max", "Aero/ClA", "x0"]);
  });

  it("hands the FMU nothing until something is set, so a stock run stays the model's own", () => {
    expect(new Tuning("m", PARAMETERS).changed).toEqual({});
  });

  it("holds a value to the range, because the FMU refuses one outside it", () => {
    const tuning = new Tuning("m", PARAMETERS);
    tuning.set("MotorR/T_max", 9000);
    expect(tuning.changed).toEqual({ "MotorR/T_max": 400 });
    tuning.set("MotorR/T_max", -1);
    expect(tuning.changed).toEqual({ "MotorR/T_max": 50 });
  });

  it("ignores a name the model does not have, and what is not a number", () => {
    const tuning = new Tuning("m", PARAMETERS);
    tuning.set("nothing", 1);
    tuning.set("Aero/ClA", Number.NaN);
    tuning.set("Heli/Wow/lower", 1);
    expect(tuning.changed).toEqual({});
  });

  it("forgets a value set back to stock", () => {
    const tuning = new Tuning("m", PARAMETERS);
    tuning.set("Aero/ClA", 3);
    tuning.set("Aero/ClA", 2.6);
    expect(tuning.changed).toEqual({});
  });

  it("says when the running model differs, until the model starts again", () => {
    const tuning = new Tuning("m", PARAMETERS);
    expect(tuning.pending).toBe(false);
    tuning.set("Aero/ClA", 3);
    expect(tuning.pending).toBe(true);
    expect(tuning.value("Aero/ClA")).toBe(3);
    expect(tuning.inUse("Aero/ClA")).toBe(2.6);
    tuning.started();
    expect(tuning.pending).toBe(false);
    expect(tuning.inUse("Aero/ClA")).toBe(3);
    tuning.reset();
    expect(tuning.pending).toBe(true);
    expect(tuning.value("Aero/ClA")).toBe(2.6);
  });

  it("tells its listeners, until they leave", () => {
    const tuning = new Tuning("m", PARAMETERS);
    let heard = 0;
    const leave = tuning.listen(() => {
      heard += 1;
    });
    tuning.set("Aero/ClA", 3);
    leave();
    tuning.set("Aero/ClA", 2);
    expect(heard).toBe(1);
  });

  it("comes back as it was left", () => {
    new Tuning("m", PARAMETERS).set("Aero/ClA", 3.25);
    const again = new Tuning("m", PARAMETERS);
    expect(again.changed).toEqual({ "Aero/ClA": 3.25 });
    expect(again.pending).toBe(false);
  });

  it("keeps each model apart", () => {
    new Tuning("a", PARAMETERS).set("Aero/ClA", 3.25);
    expect(new Tuning("b", PARAMETERS).changed).toEqual({});
  });

  it("drops what no longer fits the model, or the FMU would refuse to start", () => {
    const data = store();
    data.set("tuning:m", JSON.stringify({ "MotorR/T_max": 9000, gone: 1, "Aero/ClA": "3", x0: 5 }));
    expect(new Tuning("m", PARAMETERS).changed).toEqual({ x0: 5 });
  });

  it("survives a browser that keeps nothing, or something unreadable", () => {
    vi.stubGlobal("localStorage", {
      getItem: () => {
        throw new Error("denied");
      },
      setItem: () => {
        throw new Error("denied");
      },
    });
    const tuning = new Tuning("m", PARAMETERS);
    tuning.set("Aero/ClA", 3);
    expect(tuning.changed).toEqual({ "Aero/ClA": 3 });
    const data = store();
    data.set("tuning:m", "not json");
    expect(new Tuning("m", PARAMETERS).changed).toEqual({});
  });
});

describe("the steps of a slider", () => {
  it("are round, and at least 200 to the range", () => {
    expect(roundStep(350)).toBe(2);
    expect(roundStep(280000)).toBeCloseTo(2000, 6);
    expect(roundStep(0.29)).toBeCloseTo(0.002, 9);
    expect(roundStep(200)).toBeCloseTo(1, 9);
    expect(roundStep(4)).toBeCloseTo(0.02, 9);
  });
});

describe("the knobs of a game with none of its own", () => {
  it("leaves out the start values, which belong to the game", () => {
    vi.stubGlobal("localStorage", undefined);
    expect(everyKnob(new Tuning("m", PARAMETERS)).map((k) => k.name)).toEqual(["MotorR/T_max", "Aero/ClA"]);
    vi.unstubAllGlobals();
  });
});
