import { afterEach, describe, expect, it } from "vitest";
import { NullEngine } from "@babylonjs/core/Engines/nullEngine";
import type { AbstractMesh } from "@babylonjs/core/Meshes/abstractMesh";
import type { Binding, ModeShapeBinding } from "../src/contracts/model";
import { buildScene, type BuiltScene } from "../src/scene/build";
import { resolveScene } from "../src/scene/resolve";
import { parseSdf, type SdfGeometry } from "../src/scene/sdf";
import { BindingApplier, boundSignalIds, type ApplyTarget } from "../src/viewer/bindingsApply";
import { MAX_MESH_MODES, signalCount, validateBindingRows, validateBindings, type SceneLookup, type SignalUnits } from "../src/viewer/bindingsValidate";
import { modalBlocks, modalSignals } from "../src/viewer/modalBlocks";
import { SignalBuffer } from "../src/viewer/timeline";
import { ViewerScene } from "../src/viewer/viewerScene";
import { modalDelta, modalGlb } from "./modalGlb";

const GEOMETRY: Record<string, SdfGeometry> = {
  "visual:bracket": { kind: "mesh", uri: "bracket.glb", scale: [1, 1, 1] },
  "visual:plain": { kind: "mesh", uri: "plain.glb", scale: [1, 1, 1] },
  "visual:beam": { kind: "box", size: [1, 0.08, 0.04] },
};
const MORPHS: Record<string, number> = { "visual:bracket": 4, "visual:plain": 0 };

const scene: SceneLookup = {
  has: (ref) => ref in GEOMETRY || ref === "link:body",
  joint: () => null,
  visualGeometry: (ref) => GEOMETRY[ref] ?? null,
  morphTargetCount: (ref) => (GEOMETRY[ref]?.kind === "mesh" ? (MORPHS[ref] ?? 0) : null),
};

const signals: SignalUnits = new Map<string, string | null>([
  ["P/Bracket/eta[1]", "m"],
  ["P/Bracket/eta[2]", "m"],
  ["P/Bracket/eta[3]", "m"],
  ["P/Bracket/eta[4]", "m"],
  ["P/Bracket/eta[5]", "m"],
  ["P/Mm/eta[1]", "mm"],
  ["P/plain", null],
  ["P/volt", "V"],
]);

function modes(over: Partial<ModeShapeBinding> = {}): ModeShapeBinding {
  return { target: "visual:bracket", property: "mode-shapes", signal: ["P/Bracket/eta[1]", "P/Bracket/eta[2]"], ...over };
}

const codes = (b: Binding[], s: SignalUnits | null = signals, lookup: SceneLookup = scene): string[] => validateBindings(b, lookup, s).map((d) => d.code);

describe("mode-shapes binding validation", () => {
  it("accepts a mesh visual with enough morph targets", () => {
    expect(signalCount("mode-shapes")).toEqual([1, MAX_MESH_MODES]);
    expect(codes([modes()])).toEqual([]);
    expect(codes([modes({ signal: ["P/Bracket/eta[1]", "P/Bracket/eta[2]", "P/Bracket/eta[3]", "P/Bracket/eta[4]"] })])).toEqual([]);
    expect(codes([modes({ signal: ["P/plain"] })])).toEqual([]);
  });

  it("E301: a primitive, a link, an unknown visual, a mesh without morph targets", () => {
    const box = validateBindings([modes({ target: "visual:beam" })], scene, signals);
    expect(box.map((d) => d.code)).toEqual(["E301"]);
    expect(box[0]?.message).toMatch(/box, not a mesh/);
    expect(box[0]?.path).toBe("visual:beam");
    expect(codes([modes({ target: "link:body" })])).toEqual(["E301"]);
    expect(codes([modes({ target: "visual:nope" })])).toEqual(["E301"]);
    const plain = validateBindings([modes({ target: "visual:plain" })], scene, signals);
    expect(plain.map((d) => d.code)).toEqual(["E301"]);
    expect(plain[0]?.message).toMatch(/no morph targets/);
  });

  it("E301: two mode-shapes bindings of one visual", () => {
    const rows = validateBindingRows([modes(), modes({ signal: ["P/Bracket/eta[3]"] })], scene, signals);
    expect(rows[0]).toEqual([]);
    expect(rows[1]?.map((d) => d.code)).toEqual(["E301"]);
    expect(rows[1]?.[0]?.message).toMatch(/two mode-shapes bindings/);
  });

  it("E304: 1 to 64 signals as a list, and no more than the mesh has morph targets", () => {
    expect(codes([modes({ signal: [] as unknown as ModeShapeBinding["signal"] })], null)).toEqual(["E304"]);
    expect(codes([modes({ signal: "P/Bracket/eta[1]" as unknown as ModeShapeBinding["signal"] })], null)).toEqual(["E304"]);
    const many = modalSignals("P/Bracket", MAX_MESH_MODES + 1) as ModeShapeBinding["signal"];
    const lookupAny: SceneLookup = { ...scene, morphTargetCount: () => 100 };
    expect(codes([modes({ signal: many })], null, lookupAny)).toEqual(["E304"]);
    expect(codes([modes({ signal: many.slice(0, MAX_MESH_MODES) as ModeShapeBinding["signal"] })], null, lookupAny)).toEqual([]);
    const five = validateBindings([modes({ signal: modalSignals("P/Bracket", 5) as ModeShapeBinding["signal"] })], scene, signals);
    expect(five.map((d) => d.code)).toEqual(["E304"]);
    expect(five[0]?.message).toMatch(/has 4 morph targets .* lists 5 modal coordinates/);
    expect(five[0]?.hint).toMatch(/eta\[4\]/);
    // without a loaded mesh the count is not checked
    const { morphTargetCount: _drop, ...noCount } = scene;
    void _drop;
    expect(codes([modes({ signal: modalSignals("P/Bracket", 5) as ModeShapeBinding["signal"] })], signals, noCount)).toEqual([]);
  });

  it("E302 and E303: unknown coordinates, and coordinates that are no length", () => {
    expect(codes([modes({ signal: ["P/Bracket/eta[1]", "P/Bracket/eta[9]"] })])).toEqual(["E302"]);
    expect(codes([modes({ signal: ["P/volt"] })])).toEqual(["E303"]);
    expect(codes([modes({ signal: ["P/Mm/eta[1]"] })])).toEqual(["E303"]);
    expect(codes([modes({ signal: ["P/Mm/eta[1]"], gain: 0.001 })])).toEqual([]);
    expect(validateBindings([modes({ signal: ["P/volt"] })], scene, signals)[0]?.message).toMatch(/m \(modal coordinate\)/);
  });
});

describe("modal blocks among the signals", () => {
  it("finds the blocks with eta[1..n] and counts the gap-free run", () => {
    const s: SignalUnits = new Map([
      ["P/A/eta[1]", "m"],
      ["P/A/eta[2]", "m"],
      ["P/A/eta[3]", "m"],
      ["P/B/eta[2]", "m"],
      ["P/C/eta[1]", "m"],
      ["P/C/eta[3]", "m"],
      ["P/A/eta_y[1]", "m"],
    ]);
    expect(modalBlocks(s)).toEqual([
      { block: "P/A", count: 3 },
      { block: "P/C", count: 1 },
    ]);
    expect(modalBlocks(null)).toEqual([]);
    expect(modalSignals("P/A", 2)).toEqual(["P/A/eta[1]", "P/A/eta[2]"]);
  });
});

class Recorder implements ApplyTarget {
  modes: [string, number[]][] = [];
  setJointPosition(): boolean {
    return true;
  }
  setPose(): boolean {
    return true;
  }
  setVisualScale(): boolean {
    return true;
  }
  setVisualColor(): boolean {
    return true;
  }
  setVisible(): boolean {
    return true;
  }
  setModeShapes(ref: string, eta: readonly number[]): boolean {
    this.modes.push([ref, [...eta]]);
    return true;
  }
  reset(): void {
    /* nothing */
  }
}

describe("applying mode-shapes bindings", () => {
  const ids = ["P/Bracket/eta[1]", "P/Bracket/eta[2]", "P/Bracket/eta[3]"];
  function buffer(): SignalBuffer {
    const b = new SignalBuffer(ids);
    // t = 0 and 1: eta[1] 0 -> 0.002, eta[2] 0 -> -0.004, eta[3] 0 -> 0.01
    b.append(new Float64Array([0, 0, 0, 0, 1, 0.002, -0.004, 0.01]));
    return b;
  }

  it("hands the modal coordinates of a visual to the scene in one call, times the gain", () => {
    const bindings: Binding[] = [modes({ signal: ["P/Bracket/eta[1]", "P/Bracket/eta[2]", "P/Bracket/eta[3]"], gain: 2 })];
    expect(boundSignalIds(bindings)).toEqual(ids);
    const rec = new Recorder();
    const applier = new BindingApplier(rec, bindings, ids);
    expect(applier.count).toBe(1);
    expect(applier.apply(buffer(), 0.5)).toBe(1);
    expect(rec.modes).toHaveLength(1);
    const [ref, eta] = rec.modes[0] ?? ["", []];
    expect(ref).toBe("visual:bracket");
    expect(eta[0]).toBeCloseTo(0.002, 12);
    expect(eta[1]).toBeCloseTo(-0.004, 12);
    expect(eta[2]).toBeCloseTo(0.01, 12);
    expect(applier.applied.get("visual:bracket#mode-shapes")).toBeCloseTo(0.002, 12);
  });

  it("skips a binding with an unknown signal or no signals", () => {
    const rec = new Recorder();
    expect(new BindingApplier(rec, [modes({ signal: ["P/Bracket/eta[1]", "P/missing"] })], ids).count).toBe(0);
    expect(new BindingApplier(rec, [modes({ signal: [] as unknown as ModeShapeBinding["signal"] })], ids).count).toBe(0);
  });
});

describe("mode shapes on a GLB mesh visual (morph targets)", () => {
  const engines: NullEngine[] = [];
  afterEach(() => {
    for (const e of engines.splice(0)) e.dispose();
  });

  const SDF = `<sdf version="1.9"><model name="m"><link name="body">
    <visual name="bracket"><geometry><mesh><uri>bracket.glb</uri></mesh></geometry></visual>
    <visual name="plain"><geometry><mesh><uri>plain.glb</uri></mesh></geometry></visual>
    <visual name="box"><geometry><box><size>1 1 1</size></box></geometry></visual>
  </link></model></sdf>`;
  /** More than the 8 targets of Babylon's vertex-attribute mode. */
  const MODES = 12;

  async function build(): Promise<BuiltScene> {
    const engine = new NullEngine({ renderWidth: 64, renderHeight: 64, textureSize: 64, deterministicLockstep: false, lockstepMaxSteps: 1, useHighPrecisionMatrix: true });
    engines.push(engine);
    const parsed = parseSdf(SDF, "scenes/t.sdf");
    const resolved = parsed.scene === null ? null : resolveScene(parsed.scene).scene;
    if (resolved === null) throw new Error(JSON.stringify(parsed.diagnostics));
    const { scene: built, diagnostics } = await buildScene(new ViewerScene(engine), resolved, {
      loadMesh: (uri) => Promise.resolve(modalGlb(uri === "bracket.glb" ? MODES : 0)),
    });
    expect(diagnostics).toEqual([]);
    return built;
  }

  function morphed(built: BuiltScene): AbstractMesh[] {
    return (built.nodeOf("visual:bracket")?.getChildMeshes() ?? []).filter((m) => m.morphTargetManager !== null);
  }

  function influences(built: BuiltScene): number[] {
    const m = morphed(built)[0]?.morphTargetManager;
    if (!m) return [];
    return Array.from({ length: m.numTargets }, (_, k) => m.getTarget(k).influence);
  }

  it("loads one morph target per mode and counts them", async () => {
    const built = await build();
    expect(built.morphTargetCount("visual:bracket")).toBe(MODES);
    expect(built.morphTargetCount("visual:plain")).toBe(0);
    expect(built.morphTargetCount("visual:box")).toBeNull();
    expect(built.morphTargetCount("visual:nope")).toBeNull();
    const meshes = morphed(built);
    expect(meshes).toHaveLength(1);
    expect(meshes[0]?.morphTargetManager?.getTarget(0).name).toBe("mode 1");
    expect(meshes[0]?.morphTargetManager?.getTarget(0).hasPositions).toBe(true);
    // Babylon stores absolute target positions: rest + delta (vertex 2 moves along z by (k + 1) cm)
    expect(meshes[0]?.morphTargetManager?.getTarget(MODES - 1).getPositions()?.[8]).toBeCloseTo(modalDelta(MODES - 1), 6);
    // the morphed shape is not in the rest bounds: never culled by them
    expect(meshes[0]?.alwaysSelectAsActiveMesh).toBe(true);
    built.dispose();
  });

  it("sets the influences to eta times the exaggeration, re-applies a new exaggeration, and resets to rest", async () => {
    const built = await build();
    expect(built.setModeShapes("visual:box", [1])).toBe(false);
    expect(built.setModeShapes("visual:plain", [1])).toBe(false);
    expect(built.setModeShapes("visual:nope", [1])).toBe(false);

    const eta = Array.from({ length: MODES }, (_, k) => (k % 2 === 0 ? 1 : -1) * 0.001 * (k + 1));
    expect(built.setModeShapes("visual:bracket", eta)).toBe(true);
    influences(built).forEach((w, k) => {
      expect(w).toBeCloseTo(eta[k] ?? NaN, 12);
    });

    built.setExaggeration(100);
    influences(built).forEach((w, k) => {
      expect(w).toBeCloseTo(100 * (eta[k] ?? NaN), 10);
    });

    // fewer coordinates than targets: the rest are 0; more than targets: the extra ones are ignored
    built.setModeShapes("visual:bracket", [0.002, Number.NaN]);
    const [w0, w1, w2] = influences(built);
    expect(w0).toBeCloseTo(0.2, 12);
    expect([w1, w2]).toEqual([0, 0]);
    built.setModeShapes("visual:bracket", Array.from({ length: MODES + 3 }, () => 0.001));
    expect(influences(built)).toHaveLength(MODES);

    built.reset();
    expect(influences(built).every((w) => w === 0)).toBe(true);
    // the exaggeration stays; new coordinates use it
    built.setModeShapes("visual:bracket", [0.001]);
    expect(influences(built)[0]).toBeCloseTo(0.1, 12);
    built.dispose();
  });

  it("validation against the built scene: E304 for more signals than morph targets, E301 without targets", async () => {
    const built = await build();
    const all = new Map(modalSignals("P/B", MODES + 1).map((id) => [id, "m"] as const));
    const ok = modes({ signal: modalSignals("P/B", MODES) as ModeShapeBinding["signal"] });
    const tooMany = modes({ signal: modalSignals("P/B", MODES + 1) as ModeShapeBinding["signal"] });
    expect(validateBindings([ok], built, all)).toEqual([]);
    expect(validateBindings([tooMany], built, all).map((d) => d.code)).toEqual(["E304"]);
    expect(validateBindings([modes({ target: "visual:plain", signal: ["P/B/eta[1]"] })], built, all).map((d) => d.code)).toEqual(["E301"]);
    expect(validateBindings([modes({ target: "visual:box", signal: ["P/B/eta[1]"] })], built, all).map((d) => d.code)).toEqual(["E301"]);
    built.dispose();
  });

  it("drives the mesh through the applier", async () => {
    const built = await build();
    const ids = ["P/B/eta[1]", "P/B/eta[2]"];
    const b = new SignalBuffer(ids);
    b.append(new Float64Array([0, 0, 0, 1, 0.004, -0.002]));
    const applier = new BindingApplier(built, [modes({ signal: ["P/B/eta[1]", "P/B/eta[2]"], gain: 0.5 })], ids);
    expect(applier.apply(b, 1)).toBe(1);
    expect(influences(built)[0]).toBeCloseTo(0.002, 12);
    expect(influences(built)[1]).toBeCloseTo(-0.001, 12);
    expect(influences(built)[2]).toBe(0);
    built.dispose();
  });
});
