import { describe, expect, it } from "vitest";
import type { Binding } from "../src/contracts/model";
import { validateBindings, type SceneLookup, type SignalUnits } from "../src/viewer/bindingsValidate";

const scene: SceneLookup = {
  has: (ref) => ["joint:shoulder", "joint:slide", "joint:weld", "link:cart", "frame:tool", "visual:body"].includes(ref),
  joint: (ref) => (ref === "joint:shoulder" ? { type: "revolute" } : ref === "joint:slide" ? { type: "prismatic" } : ref === "joint:weld" ? { type: "fixed" } : null),
};

const signals: SignalUnits = new Map<string, string | null>([
  ["P/phi", "rad"],
  ["P/theta", "1"],
  ["P/none", null],
  ["P/x", "m"],
  ["P/v", "m/s"],
  ["P/deg", "deg"],
  ["P/mm", "mm"],
  ["P/qw", "1"],
  ["P/qx", "1"],
  ["P/qy", "1"],
  ["P/qz", "1"],
  ["P/px", "m"],
  ["P/py", "m"],
  ["P/pz", "m"],
  ["P/F", "N"],
  ["P/gen", "flow*s"],
  ["P/empty", ""],
]);

const codes = (b: Binding[], s: SignalUnits | null = signals): string[] => validateBindings(b, scene, s).map((d) => d.code);

describe("validateBindings", () => {
  it("accepts a clean set", () => {
    const bindings: Binding[] = [
      { target: "joint:shoulder", property: "position", signal: "P/phi" },
      { target: "joint:slide", property: "position", signal: "P/x" },
      { target: "link:cart", property: "pose", signal: ["P/qw", "P/qx", "P/qy", "P/qz", "P/px", "P/py", "P/pz"] },
      { target: "visual:body", property: "scale.z", signal: "P/F", gain: 0.01 },
      { target: "visual:body", property: "color", signal: "P/F", colormap: "heat", range: [0, 5] },
      { target: "link:cart", property: "visible", signal: "P/F" },
    ];
    expect(validateBindings(bindings, scene, signals)).toEqual([]);
  });

  it("E301 unknown target, with the binding target as path and a hint", () => {
    const d = validateBindings([{ target: "joint:elbow", property: "position", signal: "P/phi" }], scene, signals);
    expect(d).toHaveLength(1);
    expect(d[0]).toMatchObject({ code: "E301", severity: "error", path: "joint:elbow" });
    expect(d[0]?.hint).toMatch(/pick an existing/);
  });

  it("E301 for a property on the wrong kind of target, and for a fixed joint", () => {
    expect(codes([{ target: "link:cart", property: "position", signal: "P/phi" }])).toEqual(["E301"]);
    expect(codes([{ target: "joint:shoulder", property: "color", signal: "P/F", colormap: "heat", range: [0, 1] }])).toEqual(["E301"]);
    expect(codes([{ target: "joint:weld", property: "position", signal: "P/phi" }])).toEqual(["E301"]);
  });

  it("E302 unknown signal, once per missing signal", () => {
    expect(codes([{ target: "joint:shoulder", property: "position", signal: "P/nope" }])).toEqual(["E302"]);
    const pose: Binding = { target: "link:cart", property: "pose", signal: ["P/qw", "P/q1", "P/q2", "P/qz", "P/px", "P/py", "P/pz"] };
    expect(codes([pose])).toEqual(["E302", "E302"]);
  });

  it("E303 unit mismatch: rad and 1 pass a revolute joint and fail a prismatic one", () => {
    for (const s of ["P/phi", "P/theta"]) {
      expect(codes([{ target: "joint:shoulder", property: "position", signal: s }])).toEqual([]);
      expect(codes([{ target: "joint:slide", property: "position", signal: s }])).toEqual(["E303"]);
    }
    expect(codes([{ target: "joint:shoulder", property: "position", signal: "P/x" }])).toEqual(["E303"]);
    expect(codes([{ target: "joint:shoulder", property: "position", signal: "P/v" }])).toEqual(["E303"]);
  });

  it("an unknown unit (none, or a Generic flow*s) is unchecked: no E303 for a length or an angle", () => {
    for (const s of ["P/none", "P/empty", "P/gen"]) {
      expect(codes([{ target: "joint:shoulder", property: "position", signal: s }])).toEqual([]);
      expect(codes([{ target: "joint:slide", property: "position", signal: s }])).toEqual([]);
    }
    expect(codes([{ target: "link:cart", property: "pose", signal: ["P/qw", "P/qx", "P/qy", "P/qz", "P/none", "P/none", "P/empty"] }])).toEqual([]);
  });

  it("a reported wrong physical unit still raises E303: N for a length or an angle", () => {
    expect(codes([{ target: "joint:slide", property: "position", signal: "P/F" }])).toEqual(["E303"]);
    expect(codes([{ target: "joint:shoulder", property: "position", signal: "P/F" }])).toEqual(["E303"]);
  });

  it("accepts deg and mm only when the gain converts", () => {
    expect(codes([{ target: "joint:shoulder", property: "position", signal: "P/deg" }])).toEqual(["E303"]);
    expect(codes([{ target: "joint:shoulder", property: "position", signal: "P/deg", gain: Math.PI / 180 }])).toEqual([]);
    expect(codes([{ target: "joint:slide", property: "position", signal: "P/mm" }])).toEqual(["E303"]);
    expect(codes([{ target: "joint:slide", property: "position", signal: "P/mm", gain: 0.001 }])).toEqual([]);
  });

  it("E303 for a pose whose position is not metres or whose quaternion has a unit", () => {
    const ok = ["P/qw", "P/qx", "P/qy", "P/qz", "P/px", "P/py", "P/pz"] as const;
    expect(codes([{ target: "link:cart", property: "pose", signal: [...ok] }])).toEqual([]);
    expect(codes([{ target: "link:cart", property: "pose", signal: ["P/qw", "P/qx", "P/qy", "P/qz", "P/px", "P/F", "P/pz"] }])).toEqual(["E303"]);
    expect(codes([{ target: "link:cart", property: "pose", signal: ["P/px", "P/qx", "P/qy", "P/qz", "P/px", "P/py", "P/pz"] }])).toEqual(["E303"]);
  });

  it("E304 wrong signal count", () => {
    expect(codes([{ target: "link:cart", property: "pose", signal: ["P/qw", "P/qx", "P/qy"] }])).toEqual(["E304"]);
    expect(codes([{ target: "link:cart", property: "pose", signal: "P/qw" as unknown as [string] }])).toEqual(["E304"]);
    expect(codes([{ target: "joint:shoulder", property: "position", signal: ["P/phi", "P/theta"] as unknown as string }])).toEqual(["E304"]);
  });

  it("skips the signal checks while the signals are unknown, but still checks targets and counts", () => {
    expect(codes([{ target: "joint:shoulder", property: "position", signal: "P/anything" }], null)).toEqual([]);
    expect(codes([{ target: "joint:elbow", property: "position", signal: "P/anything" }], null)).toEqual(["E301"]);
  });
});
