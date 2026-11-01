import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import type { Binding, DeformationBinding } from "../src/contracts/model";
import type { BeamConfig } from "../src/scene/build";
import type { SdfGeometry } from "../src/scene/sdf";
import type { ModalSet } from "../src/viewer/beamModes";
import { BindingApplier, beamConfigs, boundSignalIds, type ApplyTarget } from "../src/viewer/bindingsApply";
import { validateBindingRows, validateBindings, type SceneLookup, type SignalUnits } from "../src/viewer/bindingsValidate";
import { ViewerPlayback } from "../src/viewer/playbackController";
import { SignalBuffer } from "../src/viewer/timeline";

const GEOMETRY: Record<string, SdfGeometry> = {
  "visual:beam": { kind: "box", size: [1, 0.08, 0.04] },
  "visual:rod": { kind: "cylinder", radius: 0.02, length: 0.8 },
  "visual:ball": { kind: "sphere", radius: 0.05 },
  "visual:part": { kind: "mesh", uri: "meshes/part.glb", scale: [1, 1, 1] },
};

const scene: SceneLookup = {
  has: (ref) => ref in GEOMETRY || ref === "link:arm",
  joint: () => null,
  visualGeometry: (ref) => GEOMETRY[ref] ?? null,
};

const signals: SignalUnits = new Map<string, string | null>([
  ["B/eta_y[1]", "m"],
  ["B/eta_y[2]", "m"],
  ["B/eta_y[3]", "m"],
  ["B/eta_z[1]", "m"],
  ["B/eta_t[1]", "rad"],
  ["B/eta_mm", "mm"],
  ["B/plain", null],
  ["B/volt", "V"],
]);

function deform(over: Partial<DeformationBinding> = {}): DeformationBinding {
  return { target: "visual:beam", property: "deformation", family: "bending-y", basis: "clamped-free", beam: { axis: "+x" }, signal: ["B/eta_y[1]"], ...over };
}

const codes = (b: Binding[], s: SignalUnits | null = signals): string[] => validateBindings(b, scene, s).map((d) => d.code);

describe("deformation binding validation", () => {
  it("accepts y and z bending and torsion on one box, and a cylinder along its own axis", () => {
    const bindings: Binding[] = [
      deform({ signal: ["B/eta_y[1]", "B/eta_y[2]", "B/eta_y[3]"], strain: { colormap: "heat", range: [0, 0.001] } }),
      deform({ family: "bending-z", signal: ["B/eta_z[1]"] }),
      deform({ family: "torsion", signal: ["B/eta_t[1]"] }),
      deform({ target: "visual:rod", basis: "free-free", beam: { axis: "-z", y: "+x", length: 0.7 }, signal: ["B/plain"] }),
      deform({ target: "visual:rod", family: "bending-z", basis: "free-free", beam: { axis: "-z", y: "+x", length: 0.7 }, signal: ["B/eta_mm"], gain: 0.001 }),
    ];
    expect(validateBindings(bindings, scene, signals)).toEqual([]);
  });

  it("E301: a shape that is no beam, with the reason", () => {
    const ball = validateBindings([deform({ target: "visual:ball" })], scene, signals);
    expect(ball.map((d) => d.code)).toEqual(["E301"]);
    expect(ball[0]?.message).toMatch(/sphere is not a beam/);
    expect(ball[0]?.path).toBe("visual:ball");
    expect(codes([deform({ target: "visual:part" })])).toEqual(["E301"]);
    expect(validateBindings([deform({ target: "visual:rod" })], scene, signals)[0]?.message).toMatch(/\+z or -z/);
    expect(validateBindings([deform({ beam: { axis: "+x", y: "-x" } })], scene, signals)[0]?.message).toMatch(/perpendicular/);
  });

  it("E301: a link, a joint or an unknown visual", () => {
    expect(codes([deform({ target: "link:arm" })])).toEqual(["E301"]);
    expect(codes([deform({ target: "visual:nope" })])).toEqual(["E301"]);
  });

  it("E301: two bindings of one family, or beam mappings that differ, on one visual", () => {
    const rows = validateBindingRows([deform(), deform({ signal: ["B/eta_y[2]"] }), deform({ family: "torsion", signal: ["B/eta_t[1]"], beam: { axis: "+x", length: 0.9 } })], scene, signals);
    expect(rows[0]).toEqual([]);
    expect(rows[1]?.map((d) => d.code)).toEqual(["E301"]);
    expect(rows[1]?.[0]?.message).toMatch(/two bending-y/);
    expect(rows[2]?.[0]?.message).toMatch(/beam mapping/);
    // another visual is independent
    expect(codes([deform(), deform({ target: "visual:rod", beam: { axis: "+z" } })])).toEqual([]);
  });

  it("E304: one to three modal coordinates, as a list", () => {
    expect(codes([deform({ signal: [] as unknown as DeformationBinding["signal"] })], null)).toEqual(["E304"]);
    expect(codes([deform({ signal: ["B/eta_y[1]", "B/eta_y[2]", "B/eta_y[3]", "B/eta_z[1]"] as unknown as DeformationBinding["signal"] })], null)).toEqual(["E304"]);
    expect(codes([deform({ signal: "B/eta_y[1]" as unknown as DeformationBinding["signal"] })], null)).toEqual(["E304"]);
    const d = validateBindings([deform({ signal: [] as unknown as DeformationBinding["signal"] })], scene, null)[0];
    expect(d?.message).toMatch(/needs 1 to 3 signals/);
  });

  it("linear basis: one twist on a torsion binding; a bending family or a second signal is refused", () => {
    const twist = deform({ target: "visual:rod", family: "torsion", basis: "linear", beam: { axis: "+z" }, signal: ["B/eta_t[1]"], gain: -1 });
    expect(validateBindings([twist], scene, signals)).toEqual([]);
    const bent = validateBindings([{ ...twist, family: "bending-y", signal: ["B/eta_y[1]"] }], scene, signals);
    expect(bent.map((d) => d.code)).toEqual(["E301"]);
    expect(bent[0]?.message).toMatch(/linear basis is the twist of a torsion spring/);
    const two = validateBindings([{ ...twist, signal: ["B/eta_t[1]", "B/plain"] }], scene, signals);
    expect(two.map((d) => d.code)).toEqual(["E304"]);
    expect(two[0]?.message).toMatch(/needs 1 signal, got 2/);
    expect(two[0]?.hint).toMatch(/twist of end B relative to end A/);
  });

  it("E302: an unknown modal coordinate", () => {
    expect(codes([deform({ signal: ["B/eta_y[1]", "B/eta_y[9]"] })])).toEqual(["E302"]);
  });

  it("E303: bending wants metres, torsion radians; no unit is unchecked, mm needs the gain", () => {
    expect(codes([deform({ signal: ["B/volt"] })])).toEqual(["E303"]);
    expect(codes([deform({ family: "torsion", signal: ["B/eta_y[1]"] })])).toEqual(["E303"]);
    expect(codes([deform({ family: "torsion", signal: ["B/plain"] })])).toEqual([]);
    expect(codes([deform({ signal: ["B/eta_mm"] })])).toEqual(["E303"]);
    expect(codes([deform({ signal: ["B/eta_mm"], gain: 0.001 })])).toEqual([]);
    const d = validateBindings([deform({ family: "bending-z", signal: ["B/eta_t[1]"] })], scene, signals)[0];
    // rad is dimensionless, which is no length
    expect(d?.message).toMatch(/m \(bending modal coordinate\)/);
  });
});

/*
 * The bindings fixtures under contracts/fixtures/bindings/semantic are schema-valid but break a rule the
 * viewer enforces (the linear basis: torsion only, one signal). Each names its code in `$comment`.
 */
const SEMANTIC_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "contracts", "fixtures", "bindings", "semantic");

describe("bindings semantic fixtures", () => {
  const files = readdirSync(SEMANTIC_DIR).filter((f) => f.endsWith(".json")).sort();
  it("exist", () => {
    expect(files.length).toBeGreaterThanOrEqual(2);
  });
  it.each(files)("%s raises the code its comment names", (file) => {
    const doc = JSON.parse(readFileSync(path.join(SEMANTIC_DIR, file), "utf8")) as { $comment: string; bindings: Binding[] };
    const code = /^expected (E\d{3}): /.exec(doc.$comment)?.[1];
    const lookup: SceneLookup = { has: () => true, joint: () => null, visualGeometry: () => ({ kind: "cylinder", radius: 0.01, length: 0.3 }) };
    expect(validateBindings(doc.bindings, lookup, null).map((d) => d.code)).toEqual([code]);
  });
});

class Recorder implements ApplyTarget {
  deformations: [string, ModalSet[]][] = [];
  configs: ReadonlyMap<string, BeamConfig> | null = null;
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
  configureBeams(configs: ReadonlyMap<string, BeamConfig>): void {
    this.configs = configs;
  }
  setDeformation(ref: string, sets: readonly ModalSet[]): boolean {
    this.deformations.push([ref, sets.map((s) => ({ ...s, eta: [...s.eta] }))]);
    return true;
  }
  reset(): void {
    /* nothing */
  }
}

describe("applying deformation bindings", () => {
  const ids = ["B/eta_y[1]", "B/eta_y[2]", "B/eta_t[1]"];
  function buffer(): SignalBuffer {
    const b = new SignalBuffer(ids);
    // t = 0 and 1: eta_y[1] 0 -> 0.002, eta_y[2] 0 -> -0.001, eta_t[1] 0 -> 0.1
    b.append(new Float64Array([0, 0, 0, 0, 1, 0.002, -0.001, 0.1]));
    return b;
  }

  it("hands all families of a visual to the scene in one call, with the gain", () => {
    const bindings: Binding[] = [
      deform({ signal: ["B/eta_y[1]", "B/eta_y[2]"], gain: 2 }),
      deform({ family: "torsion", signal: ["B/eta_t[1]"] }),
    ];
    expect(boundSignalIds(bindings)).toEqual(ids);
    const rec = new Recorder();
    const applier = new BindingApplier(rec, bindings, ids);
    expect(applier.count).toBe(2);
    expect(applier.apply(buffer(), 0.5)).toBe(2);
    expect(rec.deformations).toHaveLength(1);
    const [ref, sets] = rec.deformations[0] ?? ["", []];
    expect(ref).toBe("visual:beam");
    expect(sets.map((s) => s.family)).toEqual(["bending-y", "torsion"]);
    expect(sets[0]?.eta[0]).toBeCloseTo(0.002, 12);
    expect(sets[0]?.eta[1]).toBeCloseTo(-0.001, 12);
    expect(sets[1]?.eta[0]).toBeCloseTo(0.05, 12);
    expect(applier.applied.get("visual:beam#torsion")).toBeCloseTo(0.05, 12);
  });

  it("a linear twist reaches the scene with its basis and the gain; two signals on it are skipped", () => {
    const twist = deform({ target: "visual:rod", family: "torsion", basis: "linear", beam: { axis: "+z" }, signal: ["B/eta_t[1]"], gain: -1 });
    const rec = new Recorder();
    const applier = new BindingApplier(rec, [twist], ids);
    expect(applier.apply(buffer(), 1)).toBe(1);
    expect(rec.deformations[0]).toEqual(["visual:rod", [{ family: "torsion", basis: "linear", eta: [-0.1] }]]);
    expect(new BindingApplier(new Recorder(), [{ ...twist, signal: ["B/eta_t[1]", "B/eta_y[1]"] }], ids).count).toBe(0);
  });

  it("skips a deformation binding with an unknown signal", () => {
    const rec = new Recorder();
    const applier = new BindingApplier(rec, [deform({ signal: ["B/eta_y[1]", "B/missing"] })], ids);
    expect(applier.count).toBe(0);
  });

  it("the playback configures the beams as soon as the bindings are known, before any data", () => {
    const rec = new Recorder();
    const playback = new ViewerPlayback(
      { get: () => null, set: () => undefined, subscribe: () => () => undefined },
      { now: () => 0, frames: { request: () => 1, cancel: () => undefined } },
    );
    playback.setTarget(rec);
    expect(rec.configs?.size).toBe(0);
    playback.setBindings([deform({ family: "torsion", signal: ["B/eta_t[1]"] })]);
    expect(rec.configs?.get("visual:beam")?.stripes).toBe(true);
    playback.dispose();
  });

  it("beam configs: the first mapping, stripes when torsion is bound, the strain of a bending binding", () => {
    const configs = beamConfigs([
      deform({ beam: { axis: "+x", y: "+z" } }),
      deform({ family: "torsion", signal: ["B/eta_t[1]"], beam: { axis: "-x" } }),
      deform({ family: "bending-z", strain: { colormap: "viridis", range: [0, 1e-3] } }),
      deform({ target: "visual:rod", beam: { axis: "+z" } }),
      { target: "visual:beam", property: "scale.x", signal: "B/plain" },
    ]);
    expect(configs.get("visual:beam")).toEqual({ beam: { axis: "+x", y: "+z" }, stripes: true, strain: { colormap: "viridis", range: [0, 1e-3] } });
    expect(configs.get("visual:rod")).toEqual({ beam: { axis: "+z" }, stripes: false, strain: null });
    expect(configs.size).toBe(2);
  });
});
