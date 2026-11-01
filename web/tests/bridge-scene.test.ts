import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import type { Binding, SegmentBinding } from "../src/contracts/model";
import { transformPoint, type Vec3 } from "../src/scene/pose";
import { resolveScene, type ResolvedScene } from "../src/scene/resolve";
import { parseSdf } from "../src/scene/sdf";
import { planarPoint, segmentAxis } from "../src/scene/segment";

/**
 * The `bridge` example draws every truss bar and deck slab as a visual stretched between two truss nodes
 * by a segment binding. Before a run (no samples yet) the viewer shows the visuals where the SDF puts them,
 * so the scene must put each one at its rest place: on the line between its two nodes of the undeformed
 * truss, at full length. A scene that parks them out of sight (they used to sit 20 m under the ground)
 * shows the banks, the river and the lorry but no bridge until a run streams the node positions.
 */

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const example = path.join(repoRoot, "examples", "bridge");
/** Node coordinates of the Warren truss (`design.json`) and of the two-span bridge on a pier (`design_pier.json`). */
function designNodes(file: string): [number, number][] {
  return (JSON.parse(readFileSync(path.join(example, "design", file), "utf8")) as { xy: [number, number][] }).xy;
}
const warren = designNodes("design.json");
const pier = designNodes("design_pier.json");
/** The design a scene was written from: the `bridge-pier*` scenes come from build_pier.py. */
function nodesOf(sceneFile: string): [number, number][] {
  return path.basename(sceneFile).startsWith("bridge-pier") ? pier : warren;
}

interface ModelFile {
  scene?: { file: string };
  bindings?: Binding[];
}

function loadScene(rel: string): ResolvedScene {
  const parsed = parseSdf(readFileSync(path.join(example, rel), "utf8"), rel);
  if (parsed.scene === null) throw new Error(JSON.stringify(parsed.diagnostics));
  const resolved = resolveScene(parsed.scene);
  if (resolved.scene === null) throw new Error(JSON.stringify(resolved.diagnostics));
  return resolved.scene;
}

/** Rest position of the node a signal such as `Truss/x[12]` reads (1-based, as in the model). */
function restCoordinate(signal: string, nodes: [number, number][]): number {
  const m = /^Truss\/([xy])\[(\d+)\]$/.exec(signal);
  if (m === null) throw new Error(`not a truss node coordinate: ${signal}`);
  const node = nodes[Number(m[2]) - 1];
  if (node === undefined) throw new Error(`no node ${String(m[2])}`);
  return m[1] === "x" ? node[0] : node[1];
}

function expectPoint(actual: Vec3, expected: Vec3, label: string): void {
  actual.forEach((c, i) => {
    expect(Math.abs(c - (expected[i] ?? NaN)), `${label} component ${String(i)}: ${String(c)} vs ${String(expected[i])}`).toBeLessThan(1e-4);
  });
}

const models = readdirSync(path.join(example, "models"))
  .filter((f) => f.endsWith(".bgmodel.json"))
  .map((f) => [f, JSON.parse(readFileSync(path.join(example, "models", f), "utf8")) as ModelFile] as const)
  .filter(([, m]) => m.scene !== undefined && (m.bindings ?? []).some((b) => b.property === "segment"));

describe("bridge example scene", () => {
  it("has bridge models with segment bindings, so the loop below is never vacuous", () => {
    expect(models.map(([f]) => f)).toEqual(expect.arrayContaining(["bridge-crossing.bgmodel.json", "bridge-failure.bgmodel.json", "bridge-pier.bgmodel.json"]));
  });

  it.each(models)("%s: every segment-bound bar and deck slab stands at its rest place before a run", (_file, model) => {
    const scene = loadScene(model.scene?.file ?? "");
    const segments = (model.bindings ?? []).filter((b): b is SegmentBinding => b.property === "segment");
    expect(segments.length).toBeGreaterThan(40);
    for (const b of segments) {
      const visual = scene.visuals.find((v) => v.ref === b.target);
      if (visual === undefined) throw new Error(`no visual ${b.target}`);
      const axis = segmentAxis(visual.geometry, b.axis);
      if (typeof axis === "string") throw new Error(`${b.target}: ${axis}`);
      const world = scene.world.get(visual.node);
      if (world === undefined) throw new Error(`no rest pose of ${b.target}`);
      const nodes = nodesOf(model.scene?.file ?? "");
      const [ua, va, ub, vb] = b.signal.map((signal) => restCoordinate(signal, nodes));
      const a = planarPoint(ua ?? NaN, va ?? NaN, b.plane, b.depth ?? 0);
      const bEnd = planarPoint(ub ?? NaN, vb ?? NaN, b.plane, b.depth ?? 0);
      // the ends of the visual's axis at scale 1 land on the two rest nodes
      const h = axis.extent / 2;
      const d = axis.dir;
      expectPoint(transformPoint(world, [-h * d[0], -h * d[1], -h * d[2]]), a, `${b.target} end A`);
      expectPoint(transformPoint(world, [h * d[0], h * d[1], h * d[2]]), bEnd, `${b.target} end B`);
    }
  });
});
