import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import { NullEngine } from "@babylonjs/core/Engines/nullEngine";
import { VertexBuffer } from "@babylonjs/core/Buffers/buffer";
import type { Mesh } from "@babylonjs/core/Meshes/mesh";
import { Vector3 } from "@babylonjs/core/Maths/math.vector";
import {
  beamFrame, buildBeamMesh, defaultBeamAxis, deformBeamMesh, ringStrains, BEAM_SEGMENTS, STRIPE_SHADE, type BeamFrame,
} from "../src/scene/beamMesh";
import { buildScene, type BeamConfig, type BuiltScene } from "../src/scene/build";
import { resolveScene } from "../src/scene/resolve";
import { parseSdf, type SdfGeometry } from "../src/scene/sdf";
import {
  bendingShape, deformPoint, outerStrain, sectionRotation, sectionState, torsionShape, type ModalSet,
} from "../src/viewer/beamModes";
import { ViewerScene } from "../src/viewer/viewerScene";

const here = path.dirname(fileURLToPath(import.meta.url));
const BOX: SdfGeometry = { kind: "box", size: [1, 0.08, 0.04] };
const ROD: SdfGeometry = { kind: "cylinder", radius: 0.025, length: 0.8 };

function frameOf(g: SdfGeometry, beam: Parameters<typeof beamFrame>[1]): BeamFrame {
  const f = beamFrame(g, beam);
  if (typeof f === "string") throw new Error(f);
  return f;
}

describe("section kinematics", () => {
  const L = 1.2;
  const eta = 0.01;
  const cfY: ModalSet = { family: "bending-y", basis: "clamped-free", eta: [eta] };

  it("deflection, slope and curvature are the mode shape times eta", () => {
    for (const xi of [0, 0.3, 1]) {
      const [f, df, d2f] = bendingShape("clamped-free", 1, xi);
      const st = sectionState([cfY], xi * L, L);
      expect(st.wy).toBeCloseTo(f * eta, 12);
      expect(st.slopeY).toBeCloseTo((df / L) * eta, 12);
      expect(st.curvY).toBeCloseTo((d2f / (L * L)) * eta, 12);
      expect(st.wz).toBe(0);
      expect(st.theta).toBe(0);
    }
    // the cantilever tip of mode 1 deflects by 2 eta
    expect(sectionState([cfY], L, L).wy).toBeCloseTo(2 * eta, 8);
  });

  it("the tip section stays perpendicular to the deflected axis", () => {
    const st = sectionState([cfY], L, L);
    const R = sectionRotation(st);
    const t = new Vector3(1, st.slopeY, 0).normalize();
    // the section normal (rotated x) is the tangent; the section y turns by atan(w') about z
    expect(R[0]).toBeCloseTo(t.x, 12);
    expect(R[3]).toBeCloseTo(t.y, 12);
    expect(R[6]).toBeCloseTo(0, 12);
    expect(Math.atan2(R[3], R[0])).toBeCloseTo(Math.atan(st.slopeY), 12);
    // a point of the section 5 cm off the axis in y moves with the section
    const [x, y, z] = deformPoint(st, R, L, 0.05, 0);
    expect(x).toBeCloseTo(L - 0.05 * Math.sin(Math.atan(st.slopeY)), 12);
    expect(y).toBeCloseTo(st.wy + 0.05 * Math.cos(Math.atan(st.slopeY)), 12);
    expect(z).toBeCloseTo(0, 12);
  });

  it("bending z turns the section about y by -w_z'", () => {
    const st = sectionState([{ family: "bending-z", basis: "free-free", eta: [0, 0.02] }], 0.9, L);
    const R = sectionRotation(st);
    expect(R[6]).toBeCloseTo(st.slopeZ / Math.hypot(1, st.slopeZ), 12);
    // small slope: rotation about y by -w_z' maps x to (1, 0, w_z')
    const [px, , pz] = deformPoint(st, R, 0.9, 0, 0.01);
    expect(pz).toBeCloseTo(st.wz + 0.01 / Math.hypot(1, st.slopeZ), 12);
    expect(px).toBeCloseTo(0.9 - (0.01 * st.slopeZ) / Math.hypot(1, st.slopeZ), 12);
  });

  it("torsion turns the section about the axis by theta(s)", () => {
    const set: ModalSet = { family: "torsion", basis: "clamped-free", eta: [0.3] };
    const st = sectionState([set], L, L);
    const theta = torsionShape("clamped-free", 1, 1)[0] * 0.3;
    expect(st.theta).toBeCloseTo(theta, 12);
    const [x, y, z] = deformPoint(st, sectionRotation(st), L, 0, 0.02);
    expect([x, y, z].map((v) => Number(v.toFixed(12)))).toEqual([L, Number((-0.02 * Math.sin(theta)).toFixed(12)), Number((0.02 * Math.cos(theta)).toFixed(12))]);
  });

  it("families compose: bending y, bending z and torsion at once", () => {
    const sets: ModalSet[] = [
      { family: "bending-y", basis: "clamped-free", eta: [0.01, -0.002] },
      { family: "bending-z", basis: "clamped-free", eta: [0.004] },
      { family: "torsion", basis: "clamped-free", eta: [0.2] },
    ];
    const st = sectionState(sets, 0.6, L);
    const xi = 0.5;
    expect(st.wy).toBeCloseTo(bendingShape("clamped-free", 1, xi)[0] * 0.01 + bendingShape("clamped-free", 2, xi)[0] * -0.002, 12);
    expect(st.wz).toBeCloseTo(bendingShape("clamped-free", 1, xi)[0] * 0.004, 12);
    expect(st.theta).toBeCloseTo(torsionShape("clamped-free", 1, xi)[0] * 0.2, 12);
    const R = sectionRotation(st);
    // a proper rotation
    const det = R[0] * (R[4] * R[8] - R[5] * R[7]) - R[1] * (R[3] * R[8] - R[5] * R[6]) + R[2] * (R[3] * R[7] - R[4] * R[6]);
    expect(det).toBeCloseTo(1, 12);
    // its x column is the tangent of the deflected axis
    const t = new Vector3(1, st.slopeY, st.slopeZ).normalize();
    expect([R[0], R[3], R[6]].map((v) => v.toFixed(10))).toEqual([t.x, t.y, t.z].map((v) => v.toFixed(10)));
  });

  it("scale multiplies every coordinate (the exaggeration)", () => {
    const a = sectionState([cfY], 0.7, L, 100);
    const b = sectionState([{ ...cfY, eta: [eta * 100] }], 0.7, L);
    expect(a).toEqual(b);
  });

  it("beyond L the shape continues rigidly with the end section", () => {
    const end = sectionState([cfY], L, L);
    const past = sectionState([cfY], L + 0.1, L);
    expect(past.wy).toBeCloseTo(end.wy + end.slopeY * 0.1, 12);
    expect(past.slopeY).toBe(end.slopeY);
    expect(past.curvY).toBe(0);
  });

  it("outer fibre strain: rectangle adds both directions, a circle takes the resultant", () => {
    const st = sectionState([{ family: "bending-y", basis: "clamped-free", eta: [0.01] }, { family: "bending-z", basis: "clamped-free", eta: [0.01] }], 0, L);
    expect(outerStrain(st, { round: false, cy: 0.04, cz: 0.02 })).toBeCloseTo(0.04 * Math.abs(st.curvY) + 0.02 * Math.abs(st.curvZ), 12);
    expect(outerStrain(st, { round: true, cy: 0.03, cz: 0.03 })).toBeCloseTo(0.03 * Math.hypot(st.curvY, st.curvZ), 12);
  });
});

describe("beam frame of a shape", () => {
  it("maps a box along x with end A at -x", () => {
    const f = frameOf(BOX, { axis: "+x" });
    expect(f.extent).toBe(1);
    expect(f.length).toBe(1);
    expect(f.basis).toEqual([[1, 0, 0], [0, 1, 0], [0, 0, 1]]);
    expect(f.section).toEqual({ round: false, cy: 0.04, cz: 0.02 });
  });

  it("keeps the frame right-handed for any axis and y", () => {
    const f = frameOf(BOX, { axis: "-y", y: "+x", length: 0.5 });
    expect(f.basis[2]).toEqual([0, 0, 1]);
    expect(f.extent).toBe(0.08);
    expect(f.length).toBe(0.5);
    const g = frameOf(ROD, { axis: "+z" });
    expect(g.basis).toEqual([[0, 0, 1], [0, 1, 0], [-1, 0, 0]]);
    expect(g.section.round).toBe(true);
  });

  it("refuses shapes and mappings that are no beam", () => {
    expect(beamFrame({ kind: "sphere", radius: 1 }, { axis: "+x" })).toMatch(/sphere is not a beam/);
    expect(beamFrame({ kind: "mesh", uri: "a.glb", scale: [1, 1, 1] }, { axis: "+x" })).toMatch(/mesh is not a beam/);
    expect(beamFrame(ROD, { axis: "+x" })).toMatch(/cylinder's axis is its local z/);
    expect(beamFrame(BOX, { axis: "+x", y: "-x" })).toMatch(/perpendicular/);
  });

  it("suggests the longest side of a box, a cylinder's own axis", () => {
    expect(defaultBeamAxis(BOX)).toBe("+x");
    expect(defaultBeamAxis({ kind: "box", size: [0.1, 0.2, 2] })).toBe("+z");
    expect(defaultBeamAxis(ROD)).toBe("+z");
  });
});

/** Winding sign of every triangle against its vertex normal: Babylon's builders wind clockwise (negative). */
function windings(positions: Float32Array, normals: Float32Array, indices: Uint32Array): Set<number> {
  const signs = new Set<number>();
  for (let t = 0; t < indices.length; t += 3) {
    const [a, b, c] = [indices[t] ?? 0, indices[t + 1] ?? 0, indices[t + 2] ?? 0];
    const p = (i: number) => new Vector3(positions[3 * i] ?? 0, positions[3 * i + 1] ?? 0, positions[3 * i + 2] ?? 0);
    const n = new Vector3(normals[3 * a] ?? 0, normals[3 * a + 1] ?? 0, normals[3 * a + 2] ?? 0);
    const cr = Vector3.Cross(p(b).subtract(p(a)), p(c).subtract(p(a)));
    if (cr.length() > 1e-12) signs.add(Math.sign(Vector3.Dot(cr, n)));
  }
  return signs;
}

describe("beam mesh", () => {
  it("at rest is the plain box, with rings along the beam and Babylon's winding", () => {
    const f = frameOf(BOX, { axis: "+x" });
    const m = buildBeamMesh(f, false);
    let min = [Infinity, Infinity, Infinity];
    let max = [-Infinity, -Infinity, -Infinity];
    for (let k = 0; k < m.vertexCount; k++) {
      const p = [m.positions[3 * k] ?? 0, m.positions[3 * k + 1] ?? 0, m.positions[3 * k + 2] ?? 0];
      min = min.map((v, i) => Math.min(v, p[i] ?? 0));
      max = max.map((v, i) => Math.max(v, p[i] ?? 0));
    }
    expect(min.map((v) => Number(v.toFixed(6)))).toEqual([-0.5, -0.04, -0.02]);
    expect(max.map((v) => Number(v.toFixed(6)))).toEqual([0.5, 0.04, 0.02]);
    expect(m.ringS.length).toBe(BEAM_SEGMENTS + 1);
    expect(windings(m.positions, m.normals, m.indices)).toEqual(new Set([-1]));
    // no stripes without torsion
    expect([...m.shade].every((s) => s === 1)).toBe(true);
  });

  it("torsion stripes: a dark band on every side of a box, four lines on a cylinder", () => {
    const box = buildBeamMesh(frameOf(BOX, { axis: "+x" }), true);
    const darkBox = [...box.shade].filter((s) => s === Math.fround(STRIPE_SHADE)).length;
    expect(darkBox).toBe(4 * 2 * (BEAM_SEGMENTS + 1));
    expect(box.colors[4 * box.shade.indexOf(Math.fround(STRIPE_SHADE))]).toBeCloseTo(STRIPE_SHADE, 6);
    const rod = buildBeamMesh(frameOf(ROD, { axis: "+z" }), true);
    expect([...rod.shade].filter((s) => s === Math.fround(STRIPE_SHADE)).length).toBe(4 * 2 * (BEAM_SEGMENTS + 1));
    expect(windings(rod.positions, rod.normals, rod.indices)).toEqual(new Set([-1]));
  });

  it("deforms the vertices with the section formulas, in shape coordinates", () => {
    // a cylinder along its z: beam x = shape z, beam y = shape y, beam z = -shape x
    const f = frameOf(ROD, { axis: "+z" });
    const m = buildBeamMesh(f, false);
    const sets: ModalSet[] = [
      { family: "bending-y", basis: "free-free", eta: [0.01] },
      { family: "torsion", basis: "free-free", eta: [0.1] },
    ];
    const pos = new Float32Array(m.positions.length);
    const nor = new Float32Array(m.normals.length);
    deformBeamMesh(m, f, sets, 10, pos, nor);
    for (const k of [0, 17, 300, m.vertexCount - 1]) {
      const r = m.ring[k] ?? 0;
      const s = m.ringS[r] ?? 0;
      const st = sectionState(sets, s, f.length, 10);
      const [bx, by, bz] = deformPoint(st, sectionRotation(st), s, m.sy[k] ?? 0, m.sz[k] ?? 0);
      // shape = (-bz, by, bx - E/2)
      expect(pos[3 * k]).toBeCloseTo(-bz, 5);
      expect(pos[3 * k + 1]).toBeCloseTo(by, 5);
      expect(pos[3 * k + 2]).toBeCloseTo(bx - 0.4, 5);
      expect(Math.hypot(nor[3 * k] ?? 0, nor[3 * k + 1] ?? 0, nor[3 * k + 2] ?? 0)).toBeCloseTo(1, 5);
    }
    // still wound the Babylon way after bending and twisting
    expect(windings(pos, nor, m.indices)).toEqual(new Set([-1]));
  });

  it("deformed normals follow the deformed surface (bent and twisted hard)", () => {
    const f = frameOf(BOX, { axis: "+x" });
    const m = buildBeamMesh(f, true);
    const sets: ModalSet[] = [
      { family: "bending-y", basis: "clamped-free", eta: [0.002] },
      { family: "bending-z", basis: "clamped-free", eta: [0.001] },
      { family: "torsion", basis: "clamped-free", eta: [0.02] },
    ];
    const pos = new Float32Array(m.positions.length);
    const nor = new Float32Array(m.normals.length);
    deformBeamMesh(m, f, sets, 100, pos, nor);
    let worst = 1;
    for (let t = 0; t < m.indices.length; t += 3) {
      const [a, b, c] = [m.indices[t] ?? 0, m.indices[t + 1] ?? 0, m.indices[t + 2] ?? 0];
      const p = (i: number) => new Vector3(pos[3 * i] ?? 0, pos[3 * i + 1] ?? 0, pos[3 * i + 2] ?? 0);
      // Babylon winds clockwise about the outward normal
      const g = Vector3.Cross(p(c).subtract(p(a)), p(b).subtract(p(a)));
      if (g.length() < 1e-9) continue;
      g.normalize();
      for (const i of [a, b, c]) worst = Math.min(worst, Vector3.Dot(g, new Vector3(nor[3 * i] ?? 0, nor[3 * i + 1] ?? 0, nor[3 * i + 2] ?? 0)));
    }
    expect(worst).toBeGreaterThan(0.9);
  });

  it("strain per ring comes from the bending families only, never exaggerated", () => {
    const f = frameOf(BOX, { axis: "+x" });
    const m = buildBeamMesh(f, false);
    const sets: ModalSet[] = [
      { family: "bending-y", basis: "clamped-free", eta: [0.001] },
      { family: "torsion", basis: "clamped-free", eta: [1] },
    ];
    const eps = ringStrains(m, f, sets);
    expect(eps[0]).toBeCloseTo(0.04 * Math.abs(bendingShape("clamped-free", 1, 0)[2]) * 0.001, 12);
    expect(eps[BEAM_SEGMENTS]).toBeCloseTo(0, 9);
  });
});

describe("neutral axis offset (a part of a built-up section)", () => {
  // the top flange of an I-beam, h = 0.1, tf = 0.0057, as its own box: the beam y points down,
  // so the neutral axis of the whole section lies (h - tf)/2 along +beam y from the flange's centre
  const FLANGE: SdfGeometry = { kind: "box", size: [2, 0.055, 0.0057] };
  const off = (0.1 - 0.0057) / 2;
  const sets: ModalSet[] = [{ family: "bending-y", basis: "clamped-free", eta: [0.01, -0.001, 0.0002] }];

  it("defaults to the centre line, and reports a non-finite offset", () => {
    const plain = frameOf(FLANGE, { axis: "+x", y: "-z" });
    expect(plain.neutral).toEqual([0, 0]);
    expect(plain.fibre).toEqual(plain.section);
    expect(beamFrame(FLANGE, { axis: "+x", y: "-z", neutral: [Number.NaN, 0] })).toMatch(/neutral axis/);
  });

  it("the outer fibre is the offset plus the half size: the flange's strain is the I-beam's h/2 strain", () => {
    const f = frameOf(FLANGE, { axis: "+x", y: "-z", neutral: [off, 0] });
    expect(f.section.cy).toBeCloseTo(0.0057 / 2, 12);
    expect(f.fibre.cy).toBeCloseTo(0.05, 12);
    expect(f.fibre.cz).toBeCloseTo(0.0275, 12);
    const m = buildBeamMesh(f, false);
    const eps = ringStrains(m, f, sets);
    const curv0 = Math.abs(sectionState(sets, 0, 2).curvY);
    expect(eps[0]).toBeCloseTo(0.05 * curv0, 12);
    // a negative offset (the bottom flange) gives the same fibre distance
    expect(frameOf(FLANGE, { axis: "+x", y: "-z", neutral: [-off, 0] }).fibre.cy).toBeCloseTo(0.05, 12);
    // a round shape adds the length of the offset to its radius
    expect(frameOf(ROD, { axis: "+z", neutral: [0.03, 0.04] }).fibre.cy).toBeCloseTo(0.025 + 0.05, 12);
  });

  it("the sections turn about the neutral axis: the flange slides along the beam by the offset times the slope", () => {
    const f = frameOf(FLANGE, { axis: "+x", y: "-z", neutral: [off, 0] });
    const plain = frameOf(FLANGE, { axis: "+x", y: "-z" });
    const m = buildBeamMesh(f, false);
    const pos = new Float32Array(m.positions.length);
    const nor = new Float32Array(m.normals.length);
    const posPlain = new Float32Array(m.positions.length);
    deformBeamMesh(m, f, sets, 1, pos, nor);
    deformBeamMesh(m, plain, sets, 1, posPlain, new Float32Array(m.normals.length));
    for (const k of [0, 17, 300, m.vertexCount - 1]) {
      const s = m.ringS[m.ring[k] ?? 0] ?? 0;
      const st = sectionState(sets, s, 2);
      const [bx, by, bz] = deformPoint(st, sectionRotation(st), s, (m.sy[k] ?? 0) - off, m.sz[k] ?? 0);
      // beam (x, y, z) = shape (x + 1, -z, y): shape = (bx - 1, bz, -(by + off))
      expect(pos[3 * k]).toBeCloseTo(bx - 1, 5);
      expect(pos[3 * k + 1]).toBeCloseTo(bz, 5);
      expect(pos[3 * k + 2]).toBeCloseTo(-(by + off), 5);
    }
    // the same deflection as the plain mapping (to second order), but at the tip the top flange
    // (above the neutral axis, at beam y = -off from it) sits off * sin(slope) farther from the wall:
    // a cantilever bent down stretches its top fibres
    const tipRing = BEAM_SEGMENTS;
    const tip = sectionState(sets, 2, 2);
    for (let k = 0; k < m.vertexCount; k++) {
      if (m.ring[k] !== tipRing) continue;
      const dzPlain = (pos[3 * k + 2] ?? 0) - (posPlain[3 * k + 2] ?? 0);
      expect(dzPlain).toBeCloseTo(0, 4);
      const dx = (pos[3 * k] ?? 0) - (posPlain[3 * k] ?? 0);
      expect(dx).toBeCloseTo(off * Math.sin(Math.atan(tip.slopeY)), 4);
    }
  });
});

const engines: NullEngine[] = [];
afterEach(() => {
  for (const e of engines.splice(0)) e.dispose();
});

async function built(): Promise<BuiltScene> {
  const engine = new NullEngine({ renderWidth: 64, renderHeight: 64, textureSize: 64, deterministicLockstep: false, lockstepMaxSteps: 1, useHighPrecisionMatrix: true });
  engines.push(engine);
  const viewer = new ViewerScene(engine);
  const parsed = parseSdf(readFileSync(path.join(here, "fixtures", "scenes", "beam.sdf"), "utf8"), "scenes/beam.sdf");
  const resolved = parsed.scene === null ? null : resolveScene(parsed.scene).scene;
  if (resolved === null) throw new Error("beam.sdf does not resolve");
  return (await buildScene(viewer, resolved)).scene;
}

function tipY(mesh: Mesh): number {
  const p = mesh.getVerticesData(VertexBuffer.PositionKind) ?? [];
  let y = -Infinity;
  for (let k = 0; k < p.length; k += 3) if ((p[k] ?? 0) > 0.45) y = Math.max(y, p[k + 1] ?? 0);
  return y;
}

describe("BuiltScene beams", () => {
  const CONFIG: BeamConfig = { beam: { axis: "+x" }, stripes: true, strain: null };

  it("puts a beam mesh in place of the primitive, deforms it, exaggerates it and gives the primitive back", async () => {
    const scene = await built();
    expect(scene.visualGeometry("visual:beam_box")).toEqual({ kind: "box", size: [1, 0.08, 0.04] });
    scene.configureBeams(new Map([["visual:beam_box", CONFIG]]));
    const mesh = scene.beamMeshOf("visual:beam_box");
    expect(mesh).not.toBeNull();
    if (mesh === null) return;
    const primitive = scene.nodeOf("visual:beam_box")?.getChildMeshes(true).find((m) => m !== mesh);
    expect(primitive?.isEnabled(false)).toBe(false);
    expect(tipY(mesh)).toBeCloseTo(0.04, 6);

    const sets: ModalSet[] = [{ family: "bending-y", basis: "clamped-free", eta: [0.001] }];
    expect(scene.setDeformation("visual:beam_box", sets)).toBe(true);
    expect(tipY(mesh)).toBeCloseTo(0.002 + 0.04, 4);
    scene.setExaggeration(100);
    expect(scene.exaggeration).toBe(100);
    expect(tipY(mesh)).toBeGreaterThan(0.2 + 0.03);
    // the bounding box follows, so picking and culling see the bent beam
    expect(mesh.getBoundingInfo().boundingBox.maximum.y).toBeGreaterThan(0.2);

    scene.reset();
    expect(tipY(mesh)).toBeCloseTo(0.04, 6);

    // unchanged configuration: same mesh; dropped: the primitive is back
    scene.configureBeams(new Map([["visual:beam_box", { ...CONFIG }]]));
    expect(scene.beamMeshOf("visual:beam_box")).toBe(mesh);
    scene.configureBeams(new Map());
    expect(scene.beamMeshOf("visual:beam_box")).toBeNull();
    expect(mesh.isDisposed()).toBe(true);
    expect(primitive?.isEnabled(false)).toBe(true);
    expect(scene.setDeformation("visual:beam_box", sets)).toBe(false);
  });

  it("ignores visuals that are no beam, and the rigid pose still moves the bent beam", async () => {
    const scene = await built();
    scene.configureBeams(new Map([["visual:ball", CONFIG], ["visual:rod", { beam: { axis: "+x" }, stripes: false, strain: null }]]));
    expect(scene.beamMeshOf("visual:ball")).toBeNull();
    expect(scene.beamMeshOf("visual:rod")).toBeNull();
    scene.configureBeams(new Map([["visual:rod", { beam: { axis: "+z" }, stripes: false, strain: null }]]));
    const rod = scene.beamMeshOf("visual:rod");
    expect(rod).not.toBeNull();
    scene.setDeformation("visual:rod", [{ family: "bending-z", basis: "free-free", eta: [0.01] }]);
    // a pose binding of the link moves the bent rod as a whole
    rod?.computeWorldMatrix(true);
    const before = rod?.getBoundingInfo().boundingBox.centerWorld.clone();
    expect(scene.setPose("link:beam", [1, 0, 0, 0, 0.3, 0, 0.45])).toBe(true);
    rod?.computeWorldMatrix(true);
    const after = rod?.getBoundingInfo().boundingBox.centerWorld;
    // the scene root turns SDF z-up into Babylon y-up: a 0.3 m move along SDF x is a move along Babylon x
    expect((after?.x ?? 0) - (before?.x ?? 0)).toBeCloseTo(0.3, 6);
  });

  it("strain colouring paints the vertex colours from the colormap and whitens the material", async () => {
    const scene = await built();
    scene.configureBeams(new Map([["visual:beam_box", { beam: { axis: "+x" }, stripes: false, strain: { colormap: "heat", range: [0, 0.001] } }]]));
    const mesh = scene.beamMeshOf("visual:beam_box");
    const colours = () => [...(mesh?.getVerticesData(VertexBuffer.ColorKind) ?? [])];
    const rest = colours();
    scene.setDeformation("visual:beam_box", [{ family: "bending-y", basis: "clamped-free", eta: [0.005] }]);
    const bent = colours();
    expect(bent).not.toEqual(rest);
    // the exaggeration does not change the strain colours
    scene.setExaggeration(1000);
    expect(colours()).toEqual(bent);
    const material = mesh?.material as { diffuseColor?: { r: number } } | null;
    expect(material?.diffuseColor?.r).toBe(1);
    scene.configureBeams(new Map());
    expect(material?.diffuseColor?.r).toBeCloseTo(0.85, 6);
  });
});
