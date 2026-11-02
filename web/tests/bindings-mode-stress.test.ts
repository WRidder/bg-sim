import { afterEach, describe, expect, it } from "vitest";
import { NullEngine } from "@babylonjs/core/Engines/nullEngine";
import { VertexBuffer } from "@babylonjs/core/Buffers/buffer";
import type { AbstractMesh } from "@babylonjs/core/Meshes/abstractMesh";
import type { Color3 } from "@babylonjs/core/Maths/math.color";
import type { Binding, ModeShapeBinding, StressColor } from "../src/contracts/model";
import { buildScene, type BuiltScene } from "../src/scene/build";
import { resolveScene } from "../src/scene/resolve";
import { parseSdf } from "../src/scene/sdf";
import { stressConfigs } from "../src/viewer/bindingsApply";
import { colormapColor } from "../src/viewer/bindingsColormaps";
import { validateBindings, type SceneLookup } from "../src/viewer/bindingsValidate";
import { readStressTable, vonMises } from "../src/viewer/glbStress";
import { ViewerScene } from "../src/viewer/viewerScene";
import { modalGlb, modalStress } from "./modalGlb";

/** von Mises of the test table under eta: vertex v has xx = 1e6 (v + 1) a, vertex 2 also xy = 1e6 a, a = sum (k + 1) eta_k. */
function expectedVm(v: number, eta: readonly number[]): number {
  const a = eta.reduce((s, e, k) => s + (k + 1) * e, 0);
  const xx = 1e6 * (v + 1) * a;
  const xy = v === 2 ? 1e6 * a : 0;
  return Math.sqrt(xx * xx + 3 * xy * xy);
}

describe("the GLB stress table", () => {
  it("reads vertices, modes and the values in (vertex, mode, component) order", () => {
    const table = readStressTable(modalGlb(4, { stress: 4 }));
    expect(table).not.toBeNull();
    if (table === null) return;
    expect(table.vertices).toBe(3);
    expect(table.modes).toBe(4);
    expect(table.data.length).toBe(3 * 4 * 6);
    for (let v = 0; v < 3; v++) for (let k = 0; k < 4; k++) for (let c = 0; c < 6; c++) expect(table.data[(v * 4 + k) * 6 + c]).toBe(modalStress(v, k, c));
  });

  it("is null without a table, for a table that does not fit its bufferView, and for no GLB", () => {
    expect(readStressTable(modalGlb(4))).toBeNull();
    expect(readStressTable(modalGlb(4, { stress: 4, stressViewLength: 3 * 4 * 6 * 4 - 4 }))).toBeNull();
    expect(readStressTable(new Uint8Array(64))).toBeNull();
  });

  it("superposes the modes, then takes von Mises", () => {
    const table = readStressTable(modalGlb(4, { stress: 4 }));
    if (table === null) throw new Error("no table");
    const eta = [1e-5, -2e-5, 3e-6];
    const vm = vonMises(table, eta);
    for (let v = 0; v < 3; v++) expect(vm[v]).toBeCloseTo(expectedVm(v, eta), 0);
    // coordinates beyond the table are ignored
    expect([...vonMises(table, [0, 0, 0, 0, 1, 1])]).toEqual([0, 0, 0]);
    // a pure shear state gives sqrt(3) |xy|
    const shear = { vertices: 1, modes: 1, data: new Float32Array([0, 0, 0, 0, 0, 2e6]) };
    expect(vonMises(shear, [1])[0]).toBeCloseTo(Math.sqrt(3) * 2e6, 0);
  });
});

describe("stress colouring on a GLB mesh visual", () => {
  const engines: NullEngine[] = [];
  afterEach(() => {
    for (const e of engines.splice(0)) e.dispose();
  });

  const SDF = `<sdf version="1.9"><model name="m"><link name="body">
    <visual name="bracket"><geometry><mesh><uri>bracket.glb</uri></mesh></geometry></visual>
    <visual name="nostress"><geometry><mesh><uri>nostress.glb</uri></mesh></geometry></visual>
    <visual name="box"><geometry><box><size>1 1 1</size></box></geometry></visual>
  </link></model></sdf>`;
  const MODES = 4;
  const HEAT: StressColor = { colormap: "heat", range: [0, 2e7] };

  async function build(): Promise<BuiltScene> {
    const engine = new NullEngine({ renderWidth: 64, renderHeight: 64, textureSize: 64, deterministicLockstep: false, lockstepMaxSteps: 1, useHighPrecisionMatrix: true });
    engines.push(engine);
    const parsed = parseSdf(SDF, "scenes/t.sdf");
    const resolved = parsed.scene === null ? null : resolveScene(parsed.scene).scene;
    if (resolved === null) throw new Error(JSON.stringify(parsed.diagnostics));
    const { scene: built, diagnostics } = await buildScene(new ViewerScene(engine), resolved, {
      loadMesh: (uri) => Promise.resolve(uri === "bracket.glb" ? modalGlb(MODES, { stress: MODES }) : modalGlb(MODES)),
    });
    expect(diagnostics).toEqual([]);
    return built;
  }

  function meshOf(built: BuiltScene, ref: string): AbstractMesh {
    const m = (built.nodeOf(ref)?.getChildMeshes() ?? []).find((x) => x.getTotalVertices() === 3);
    if (m === undefined) throw new Error(`no mesh in ${ref}`);
    return m;
  }

  function albedo(mesh: AbstractMesh): Color3 {
    return (mesh.material as unknown as { albedoColor: Color3 }).albedoColor;
  }

  function expectColours(colours: ArrayLike<number> | null, eta: readonly number[], c: StressColor): void {
    expect(colours).not.toBeNull();
    for (let v = 0; v < 3; v++) {
      const want = colormapColor(c.colormap, expectedVm(v, eta), c.range);
      for (let i = 0; i < 3; i++) expect(colours?.[4 * v + i]).toBeCloseTo(want[i] ?? 0, 5);
      expect(colours?.[4 * v + 3]).toBe(1);
    }
  }

  it("the glTF loader keeps the POSITION order and count, so table vertex v is mesh vertex v", async () => {
    const built = await build();
    const mesh = meshOf(built, "visual:bracket");
    expect([...(mesh.getVerticesData(VertexBuffer.PositionKind) ?? [])]).toEqual([0, 0, 0, 1, 0, 0, 0, 1, 0]);
    expect(built.stressModeCount("visual:bracket")).toBe(MODES);
    expect(built.stressModeCount("visual:nostress")).toBe(0);
    expect(built.stressModeCount("visual:box")).toBeNull();
    expect(built.stressModeCount("visual:nope")).toBeNull();
  });

  it("colours the vertices by von Mises of the true coordinates, independent of the exaggeration", async () => {
    const built = await build();
    const mesh = meshOf(built, "visual:bracket");
    const before = albedo(mesh).clone();
    built.configureStress(new Map([["visual:bracket", HEAT]]));
    // at rest: zero stress everywhere, the low end of the map
    expectColours(mesh.getVerticesData(VertexBuffer.ColorKind), [], HEAT);
    expect(albedo(mesh).asArray()).toEqual([1, 1, 1]);
    const eta = [1e-3, 2e-3];
    built.setModeShapes("visual:bracket", eta);
    expectColours(mesh.getVerticesData(VertexBuffer.ColorKind), eta, HEAT);
    expectColours(built.stressColorsOf("visual:bracket"), eta, HEAT);
    built.setExaggeration(100);
    expectColours(mesh.getVerticesData(VertexBuffer.ColorKind), eta, HEAT);
    // another colouring of the same visual
    const cool: StressColor = { colormap: "coolwarm", range: [0, 1e7] };
    built.configureStress(new Map([["visual:bracket", cool]]));
    expectColours(mesh.getVerticesData(VertexBuffer.ColorKind), eta, cool);
    // reset: rest shape, zero stress, still coloured
    built.reset();
    expectColours(mesh.getVerticesData(VertexBuffer.ColorKind), [], cool);
    // off: the plain material comes back and the vertex colours go
    built.configureStress(new Map());
    expect(mesh.isVerticesDataPresent(VertexBuffer.ColorKind)).toBe(false);
    expect(albedo(mesh).asArray()).toEqual(before.asArray());
    expect(built.stressColorsOf("visual:bracket")).toBeNull();
  });

  it("leaves a mesh without a stress table alone", async () => {
    const built = await build();
    const mesh = meshOf(built, "visual:nostress");
    built.configureStress(new Map([["visual:nostress", HEAT]]));
    built.setModeShapes("visual:nostress", [1e-3]);
    expect(mesh.isVerticesDataPresent(VertexBuffer.ColorKind)).toBe(false);
    expect(built.stressColorsOf("visual:nostress")).toBeNull();
  });

  it("validation against the built scene: E301 without a table, E304 for more coordinates than the table has", async () => {
    const built = await build();
    const b = (over: Partial<ModeShapeBinding>): ModeShapeBinding => ({ target: "visual:bracket", property: "mode-shapes", signal: ["P/B/eta[1]"], stress: HEAT, ...over });
    expect(validateBindings([b({})], built, null)).toEqual([]);
    const none = validateBindings([b({ target: "visual:nostress" })], built, null);
    expect(none.map((d) => d.code)).toEqual(["E301"]);
    expect(none[0]?.message).toMatch(/no stress table/);
    expect(none[0]?.hint).toMatch(/BGSimFEM/);
    // without the colouring the same mesh is fine
    const { stress: _s, ...plain } = b({ target: "visual:nostress" });
    void _s;
    expect(validateBindings([plain], built, null)).toEqual([]);
  });
});

describe("stress colouring: validation without a scene and the binding configs", () => {
  const lookup = (morphs: number, table: number): SceneLookup => ({
    has: () => true,
    joint: () => null,
    visualGeometry: () => ({ kind: "mesh", uri: "b.glb", scale: [1, 1, 1] }),
    morphTargetCount: () => morphs,
    stressModeCount: () => table,
  });
  const sig = (n: number): ModeShapeBinding["signal"] => Array.from({ length: n }, (_, k) => `P/B/eta[${String(k + 1)}]`) as ModeShapeBinding["signal"];
  const bind = (n: number, stress?: StressColor): ModeShapeBinding => ({ target: "visual:b", property: "mode-shapes", signal: sig(n), ...(stress ? { stress } : {}) });
  const codes = (b: Binding[], l: SceneLookup): string[] => validateBindings(b, l, null).map((d) => d.code);

  it("E304 when the table has fewer modes than the binding's coordinates (only with the colouring)", () => {
    const heat: StressColor = { colormap: "heat", range: [0, 5e7] };
    expect(codes([bind(6, heat)], lookup(8, 6))).toEqual([]);
    const many = validateBindings([bind(7, heat)], lookup(8, 6), null);
    expect(many.map((d) => d.code)).toEqual(["E304"]);
    expect(many[0]?.message).toMatch(/stress table .* 6 modes.* 7 modal coordinates/);
    expect(codes([bind(7)], lookup(8, 6))).toEqual([]);
    // unknown table (mesh not loaded): not checked
    expect(codes([bind(7, heat)], { ...lookup(8, 6), stressModeCount: () => null })).toEqual([]);
  });

  it("E301 for a range that is not low < high", () => {
    expect(codes([bind(2, { colormap: "heat", range: [5e7, 0] })], lookup(8, 8))).toEqual(["E301"]);
    expect(codes([bind(2, { colormap: "heat", range: [0, Number.NaN] })], lookup(8, 8))).toEqual(["E301"]);
  });

  it("stressConfigs: the colouring of each mode-shapes visual, first binding wins", () => {
    const heat: StressColor = { colormap: "heat", range: [0, 1] };
    const cool: StressColor = { colormap: "coolwarm", range: [0, 2] };
    const out = stressConfigs([bind(2), { ...bind(2, heat), target: "visual:c" }, { ...bind(1, cool), target: "visual:c" }, { target: "visual:d", property: "color", signal: "P/x", colormap: "heat", range: [0, 1] }]);
    expect([...out.entries()]).toEqual([["visual:c", heat]]);
  });
});
