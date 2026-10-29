import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NullEngine } from "@babylonjs/core/Engines/nullEngine";
import { Matrix, Vector3 } from "@babylonjs/core/Maths/math.vector";
import { StandardMaterial } from "@babylonjs/core/Materials/standardMaterial";
import type { Mesh } from "@babylonjs/core/Meshes/mesh";
import { buildScene, type BuiltScene } from "../src/scene/build";
import { compose, fromPose, positionOf, quaternionOf, type Mat4 } from "../src/scene/pose";
import { resolveScene } from "../src/scene/resolve";
import { parseSdf } from "../src/scene/sdf";
import { entityOfMesh, ViewerScene } from "../src/viewer/viewerScene";

const here = path.dirname(fileURLToPath(import.meta.url));
const fixture = (name: string): string => readFileSync(path.join(here, "fixtures", "scenes", name), "utf8");
const H = Math.PI / 2;

const engines: NullEngine[] = [];
function viewer(onInvalidate?: () => void): ViewerScene {
  const engine = new NullEngine({
    renderWidth: 64,
    renderHeight: 64,
    textureSize: 64,
    deterministicLockstep: false,
    lockstepMaxSteps: 1,
    useHighPrecisionMatrix: true,
  });
  engines.push(engine);
  return new ViewerScene(engine, onInvalidate);
}

afterEach(() => {
  for (const e of engines.splice(0)) e.dispose();
});

function resolved(text: string) {
  const parsed = parseSdf(text, "scenes/t.sdf");
  const r = parsed.scene === null ? null : resolveScene(parsed.scene).scene;
  if (r === null) throw new Error(JSON.stringify(parsed.diagnostics));
  return r;
}

/** A GLB with one triangle, built by hand: 3 vertices, positions only. */
function triangleGlb(): Uint8Array {
  const positions = new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]);
  const bin = new Uint8Array(positions.buffer);
  const json = JSON.stringify({
    asset: { version: "2.0" },
    scene: 0,
    scenes: [{ nodes: [0] }],
    nodes: [{ mesh: 0 }],
    meshes: [{ primitives: [{ attributes: { POSITION: 0 } }] }],
    accessors: [{ bufferView: 0, componentType: 5126, count: 3, type: "VEC3", min: [0, 0, 0], max: [1, 1, 0] }],
    bufferViews: [{ buffer: 0, byteOffset: 0, byteLength: bin.length }],
    buffers: [{ byteLength: bin.length }],
  });
  const pad = (n: number) => (4 - (n % 4)) % 4;
  const jsonBytes = new TextEncoder().encode(json + " ".repeat(pad(json.length)));
  const total = 12 + 8 + jsonBytes.length + 8 + bin.length;
  const out = new Uint8Array(total);
  const dv = new DataView(out.buffer);
  dv.setUint32(0, 0x46546c67, true);
  dv.setUint32(4, 2, true);
  dv.setUint32(8, total, true);
  dv.setUint32(12, jsonBytes.length, true);
  dv.setUint32(16, 0x4e4f534a, true);
  out.set(jsonBytes, 20);
  const o = 20 + jsonBytes.length;
  dv.setUint32(o, bin.length, true);
  dv.setUint32(o + 4, 0x004e4942, true);
  out.set(bin, o + 8);
  return out;
}

function expectMat(actual: Mat4, expected: Mat4): void {
  expected.forEach((e, i) => {
    expect(Math.abs((actual[i] ?? NaN) - (e ?? 0)), `element ${i}`).toBeLessThan(1e-9);
  });
}

/** Babylon's world matrix of a node as a column-vector Mat4 in sdf_root coordinates. */
function babylonLocalWorld(viewerScene: ViewerScene, scene: BuiltScene, ref: string): Mat4 {
  const node = scene.nodeOf(ref);
  if (!node) throw new Error(`no node ${ref}`);
  node.computeWorldMatrix(true);
  viewerScene.root.computeWorldMatrix(true);
  const rel = node.getWorldMatrix().multiply(viewerScene.root.getWorldMatrix().clone().invert());
  const m = rel.m;
  // Babylon: row vectors, translation in the last row; transpose to the column convention
  return [m[0]!, m[4]!, m[8]!, m[12]!, m[1]!, m[5]!, m[9]!, m[13]!, m[2]!, m[6]!, m[10]!, m[14]!, 0, 0, 0, 1];
}

describe("scene root", () => {
  it("maps SDF (0,0,1) to Babylon world (0,1,0) through sdf_root", async () => {
    const v = viewer();
    const { scene } = await buildScene(v, resolved('<sdf version="1.7"><model name="m"><link name="a"><pose>0 0 1 0 0 0</pose></link></model></sdf>'));
    const node = scene.nodeOf("link:a");
    expect(node).not.toBeNull();
    node?.computeWorldMatrix(true);
    const p = node?.getAbsolutePosition() ?? Vector3.Zero();
    expect(p.x).toBeCloseTo(0, 9);
    expect(p.y).toBeCloseTo(1, 9);
    expect(p.z).toBeCloseTo(0, 9);
    // SDF +X stays +X, SDF +Y maps to world -Z
    const q = Vector3.TransformCoordinates(new Vector3(0, 1, 0), v.root.getWorldMatrix());
    expect(q.z).toBeCloseTo(-1, 9);
  });
});

describe("buildScene", () => {
  it("builds the same tree as the pure kinematics and moves it with joint positions (revolute and prismatic)", async () => {
    const v = viewer();
    const { scene, diagnostics } = await buildScene(v, resolved(fixture("chain.sdf")));
    expect(diagnostics).toEqual([]);
    expectMat(babylonLocalWorld(v, scene, "link:l2"), fromPose(1, 0, 1, 0, 0, 0));

    expect(scene.setJointPosition("joint:j1", H)).toBe(true);
    expect(scene.setJointPosition("joint:j2", H)).toBe(true);
    expectMat(babylonLocalWorld(v, scene, "link:l1"), [0, -1, 0, 0, 1, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 1]);
    expectMat(babylonLocalWorld(v, scene, "link:l2"), [0, -1, 0, 0, 0, 0, 1, 0.5, -1, 0, 0, 1.5, 0, 0, 0, 1]);
    expectMat(scene.worldOf("link:l2"), [0, -1, 0, 0, 0, 0, 1, 0.5, -1, 0, 0, 1.5, 0, 0, 0, 1]);

    const frames = await buildScene(v, resolved(fixture("frames.sdf")));
    expect(frames.scene.setJointPosition("joint:prism", 0.5)).toBe(true);
    expect(positionOf(babylonLocalWorld(v, frames.scene, "link:slider"))).toEqual([10.5, 0, 0]);
    expect(frames.scene.setJointPosition("joint:nope", 1)).toBe(false);
  });

  it("orients an SDF cylinder along Z and sizes boxes and spheres", async () => {
    const v = viewer();
    const { scene } = await buildScene(
      v,
      resolved(`<sdf version="1.7"><model name="m"><link name="a">
        <visual name="cyl"><geometry><cylinder><radius>0.1</radius><length>2</length></cylinder></geometry></visual>
        <visual name="box"><pose>5 0 0 0 0 0</pose><geometry><box><size>1 2 3</size></box></geometry></visual>
        <visual name="ball"><pose>-5 0 0 0 0 0</pose><geometry><sphere><radius>0.5</radius></sphere></geometry></visual>
      </link></model></sdf>`),
    );
    const extents = (ref: string) => {
      const node = scene.nodeOf(ref);
      const mesh = node?.getChildMeshes()[0];
      if (!mesh) throw new Error(`no mesh for ${ref}`);
      mesh.computeWorldMatrix(true);
      // object-space extents, scaled by the geometry node: in SDF axes through the mesh's own rotation
      const local = mesh.getBoundingInfo().boundingBox;
      const rot = mesh.rotationQuaternion?.toRotationMatrix(new Matrix());
      const corners = local.vectors.map((c) => (rot ? Vector3.TransformCoordinates(c, rot) : c));
      const max = corners.reduce((a, c) => new Vector3(Math.max(a.x, c.x), Math.max(a.y, c.y), Math.max(a.z, c.z)), new Vector3(-1e9, -1e9, -1e9));
      return max;
    };
    const cyl = extents("visual:cyl");
    expect(cyl.z).toBeCloseTo(1, 6);
    expect(cyl.x).toBeCloseTo(0.1, 2);
    expect(cyl.y).toBeCloseTo(0.1, 2);
    const box = extents("visual:box");
    expect([box.x, box.y, box.z]).toEqual([0.5, 1, 1.5]);
    expect(extents("visual:ball").x).toBeCloseTo(0.5, 6);
  });

  it("tags links, joints, frames and visuals so picking and highlight resolve them", async () => {
    const v = viewer();
    const { scene } = await buildScene(v, resolved(fixture("frames.sdf")));
    const mesh = scene.nodeOf("visual:a_box")?.getChildMeshes()[0];
    expect(mesh && entityOfMesh(mesh)).toBe("visual:a_box");
    expect(entityOfMesh(scene.nodeOf("link:a")!)).toBe("link:a");
    expect(entityOfMesh(scene.nodeOf("frame:f")!)).toBe("frame:f");
    v.highlight(scene.visualsOf("link:a"));
    expect((mesh as Mesh).renderOutline).toBe(true);
    expect(scene.visualsOf("joint:prism")).toEqual(["visual:slider_visual"]);
    expect(scene.visualsOf("model:rig").sort()).toEqual(["visual:a_box", "visual:inner_visual", "visual:slider_visual"]);
  });

  it("applies the material diffuse and the toon plugin", async () => {
    const v = viewer();
    const { scene } = await buildScene(v, resolved(fixture("frames.sdf")));
    const material = scene.nodeOf("visual:a_box")?.getChildMeshes()[0]?.material;
    expect(material).toBeInstanceOf(StandardMaterial);
    const m = material as StandardMaterial;
    expect([m.diffuseColor.r, m.diffuseColor.g, m.diffuseColor.b]).toEqual([0.8, 0.2, 0.1]);
    expect(m.pluginManager?.getPlugin("McfToon")).toBeTruthy();
  });

  it("sets a world pose on a link or frame, with children following", async () => {
    const v = viewer();
    const { scene } = await buildScene(v, resolved(fixture("chain.sdf")));
    // l1 moved to (0, 0, 2) turned 90 degrees about x
    const s = Math.SQRT1_2;
    expect(scene.setPose("link:l1", [s, s, 0, 0, 0, 0, 2])).toBe(true);
    expectMat(babylonLocalWorld(v, scene, "link:l1"), fromPose(0, 0, 2, H, 0, 0));
    // l2 hangs off l1 through j2 (zero motion): world = l1 * T(1,0,0.5)... * T(0,0,-0.5)
    const expected = compose(fromPose(0, 0, 2, H, 0, 0), fromPose(1, 0, 0.5, 0, 0, 0), fromPose(0, 0, -0.5, 0, 0, 0));
    expectMat(babylonLocalWorld(v, scene, "link:l2"), expected);
    expect(quaternionOf(scene.worldOf("link:l1"))[1]).toBeCloseTo(s, 12);
    expect(scene.setPose("joint:j1", [1, 0, 0, 0, 0, 0, 0])).toBe(false);
    expect(scene.setPose("link:l1", [1, 0, 0, 0, NaN, 0, 0])).toBe(false);
  });

  it("scales, colours and hides visuals and asks for a redraw each time", async () => {
    const invalidate = vi.fn();
    const v = viewer(invalidate);
    const { scene } = await buildScene(v, resolved(fixture("frames.sdf")));
    invalidate.mockClear();
    expect(scene.setVisualScale("visual:a_box", 1, 1, 3)).toBe(true);
    expect(scene.nodeOf("visual:a_box")?.scaling.z).toBe(3);
    expect(scene.setVisualColor("visual:a_box", 0, 1, 0)).toBe(true);
    const m = scene.nodeOf("visual:a_box")?.getChildMeshes()[0]?.material as StandardMaterial;
    expect(m.diffuseColor.g).toBe(1);
    expect(scene.setVisible("visual:a_box", false)).toBe(true);
    expect(scene.nodeOf("visual:a_box")?.isEnabled()).toBe(false);
    expect(scene.setVisible("visual:a_box", true)).toBe(true);
    expect(scene.setVisible("link:a", false)).toBe(true);
    expect(scene.nodeOf("visual:a_box")?.isEnabled()).toBe(false);
    // the moving link below stays visible
    expect(scene.nodeOf("visual:slider_visual")?.isEnabled()).toBe(true);
    expect(invalidate).toHaveBeenCalledTimes(5);
    expect(scene.setVisualScale("visual:nope", 1, 1, 1)).toBe(false);
    scene.reset();
    expect(scene.nodeOf("visual:a_box")?.scaling.z).toBe(1);
    expect(scene.nodeOf("visual:a_box")?.isEnabled()).toBe(true);
  });

  it("loads a GLB visual, reports a missing mesh with E305 and disposes without leaks", async () => {
    const v = viewer();
    const before = { nodes: v.scene.transformNodes.length, meshes: v.scene.meshes.length, materials: v.scene.materials.length };
    const text = `<sdf version="1.7"><model name="m"><link name="body">
      <visual name="shell"><geometry><mesh><uri>meshes/tri.glb</uri><scale>2 2 2</scale></mesh></geometry></visual>
      <visual name="gone"><geometry><mesh><uri>meshes/gone.glb</uri></mesh></geometry></visual>
      <visual name="cube"><geometry><box><size>1 1 1</size></box></geometry></visual>
    </link></model></sdf>`;
    const { scene, diagnostics } = await buildScene(v, resolved(text), {
      loadMesh: (uri) => (uri.endsWith("tri.glb") ? Promise.resolve(triangleGlb()) : Promise.reject(new Error("404 Not Found"))),
    });
    expect(diagnostics).toHaveLength(1);
    expect(diagnostics[0]).toMatchObject({ code: "E305", path: "visual:gone" });
    expect(diagnostics[0]?.message).toContain("meshes/gone.glb");
    expect(diagnostics[0]?.hint).toMatch(/upload/);
    const shell = scene.nodeOf("visual:shell");
    const glbMeshes = (shell?.getChildMeshes() ?? []).filter((m) => m.getTotalVertices() > 0);
    expect(glbMeshes).toHaveLength(1);
    expect(entityOfMesh(glbMeshes[0]!)).toBe("visual:shell");
    glbMeshes[0]?.computeWorldMatrix(true);
    expect(glbMeshes[0]?.getBoundingInfo().boundingBox.maximumWorld.x).toBeCloseTo(2, 6);
    expect(v.scene.meshes.length).toBeGreaterThan(before.meshes);

    scene.dispose();
    expect(v.scene.transformNodes.length).toBe(before.nodes);
    expect(v.scene.meshes.length).toBe(before.meshes);
    expect(v.scene.materials.length).toBe(before.materials);
    scene.dispose();
  });

  it("disposes everything when aborted while a mesh is still loading", async () => {
    const v = viewer();
    const before = { nodes: v.scene.transformNodes.length, meshes: v.scene.meshes.length, materials: v.scene.materials.length };
    const abort = new AbortController();
    let release: (b: Uint8Array) => void = () => undefined;
    const slow = new Promise<Uint8Array>((resolve) => {
      release = resolve;
    });
    const pending = buildScene(
      v,
      resolved('<sdf version="1.7"><model name="m"><link name="b"><visual name="s"><geometry><mesh><uri>meshes/tri.glb</uri></mesh></geometry></visual><visual name="c"><geometry><box><size>1 1 1</size></box></geometry></visual></link></model></sdf>'),
      { loadMesh: () => slow, signal: abort.signal },
    );
    abort.abort();
    release(triangleGlb());
    const { scene } = await pending;
    expect(scene.isDisposed).toBe(true);
    expect(v.scene.transformNodes.length).toBe(before.nodes);
    expect(v.scene.meshes.length).toBe(before.meshes);
    expect(v.scene.materials.length).toBe(before.materials);
  });
});
