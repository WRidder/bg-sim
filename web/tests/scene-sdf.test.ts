import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { forwardKinematics, resolveScene, type ResolvedScene } from "../src/scene/resolve";
import { parseSdf } from "../src/scene/sdf";
import {
  compose, fromPose, fromPose7, inverse, jointMotion, positionOf, quaternionOf, rotationAxisAngle, toPose7, transformPoint,
  type Mat4,
} from "../src/scene/pose";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(root, "..");
const fixture = (name: string): string => readFileSync(path.join(root, "tests", "fixtures", "scenes", name), "utf8");

function load(text: string, file = "scenes/t.sdf") {
  const parsed = parseSdf(text, file);
  if (parsed.scene === null) return { scene: null, diagnostics: parsed.diagnostics };
  const resolved = resolveScene(parsed.scene);
  return { scene: resolved.scene, diagnostics: [...parsed.diagnostics, ...resolved.diagnostics] };
}

function mustLoad(text: string): ResolvedScene {
  const { scene, diagnostics } = load(text);
  if (scene === null) throw new Error(JSON.stringify(diagnostics));
  return scene;
}

function expectMat(actual: Mat4 | undefined, expected: readonly number[]): void {
  expect(actual).toBeDefined();
  expect(actual).toHaveLength(16);
  expected.forEach((e, i) => {
    expect(Math.abs((actual?.[i] ?? NaN) - e), `element ${i}: ${String(actual?.[i])} vs ${e}`).toBeLessThan(1e-9);
  });
}

const H = Math.PI / 2;

describe("pose maths", () => {
  it("composes roll, pitch and yaw as Rz(yaw) Ry(pitch) Rx(roll)", () => {
    expectMat(fromPose(1, 2, 3, H, 0, 0), [1, 0, 0, 1, 0, 0, -1, 2, 0, 1, 0, 3, 0, 0, 0, 1]);
    // (0,1,0): Rx(pi/2) -> (0,0,1), then Ry(pi/2) -> (1,0,0)
    const p = transformPoint(fromPose(0, 0, 0, H, H, 0), [0, 1, 0]);
    expect(p[0]).toBeCloseTo(1, 12);
    expect(p[1]).toBeCloseTo(0, 12);
    expect(p[2]).toBeCloseTo(0, 12);
    const yawLast = transformPoint(fromPose(0, 0, 0, 0, 0, H), [1, 0, 0]);
    expect(yawLast[1]).toBeCloseTo(1, 12);
  });

  it("round-trips a pose through the (qw, qx, qy, qz, x, y, z) chart", () => {
    const m = fromPose(0.3, -0.2, 0.9, 0.4, -1.1, 2.5);
    expectMat(fromPose7(toPose7(m)), m);
    expect(Math.hypot(...quaternionOf(m))).toBeCloseTo(1, 12);
    expect(positionOf(fromPose7(toPose7(m)))[2]).toBeCloseTo(0.9, 12);
  });

  it("inverts rigid transforms and moves along a prismatic axis", () => {
    const m = fromPose(1, 2, 3, 0.1, 0.2, 0.3);
    expectMat(compose(m, inverse(m)), fromPose(0, 0, 0, 0, 0, 0));
    expectMat(jointMotion("prismatic", [0, 2, 0], 0.5), [1, 0, 0, 0, 0, 1, 0, 0.5, 0, 0, 1, 0, 0, 0, 0, 1]);
    expectMat(jointMotion("revolute", [0, 0, 5], H), rotationAxisAngle([0, 0, 1], H));
    expectMat(jointMotion("fixed", [0, 0, 1], 3), fromPose(0, 0, 0, 0, 0, 0));
  });
});

describe("relative_to resolution", () => {
  const scene = mustLoad(fixture("frames.sdf"));
  const at = (ref: string): readonly number[] => {
    const w = scene.world.get(ref);
    if (!w) throw new Error(`no world for ${ref}`);
    return positionOf(w);
  };

  it("defaults a link to the model frame, the model pose included", () => {
    expect(at("link:a")).toEqual([11, 2, 3]);
  });

  it("resolves a frame attached to a link, a link relative to a frame, a link and the world", () => {
    expect(at("frame:f")).toEqual([11, 2, 4]);
    expect(at("link:c")).toEqual([11, 3, 4]);
    expectMat(scene.world.get("link:b"), compose(fromPose(12, 2, 3, 0, 0, 0), fromPose(0, 0, 0, 0, 0, H)));
    expect(at("link:d")).toEqual([0, 0, 5]);
  });

  it("puts a joint on its child link by default and nests models", () => {
    expect(at("joint:prism")).toEqual([10, 0, 0]);
    expect(at("link:sub.inner")).toEqual([10.5, 0, 2]);
    expect(scene.tree[0]?.label).toBe("rig");
    const labels = (scene.tree[0]?.children ?? []).map((c) => `${c.kind}:${c.label}`);
    expect(labels).toEqual(["link:a", "link:b", "link:c", "link:d", "link:slider", "joint:prism", "frame:f", "model:sub"]);
  });

  it("names visuals by their own name when that is unique", () => {
    expect(scene.visuals.map((v) => v.ref)).toEqual(["visual:a_box", "visual:slider_visual", "visual:inner_visual"]);
  });

  it("reports E305 for a relative_to that names nothing", () => {
    const { scene: s, diagnostics } = load(
      '<sdf version="1.7"><model name="m"><link name="a"><pose relative_to="ghost">0 0 0 0 0 0</pose></link></model></sdf>',
    );
    expect(s).toBeNull();
    expect(diagnostics.map((d) => d.code)).toEqual(["E305"]);
    expect(diagnostics[0]?.message).toContain("ghost");
    expect(diagnostics[0]?.path).toBe("link:a");
    expect(diagnostics[0]?.hint).toBeTruthy();
  });

  it("reports E305 for a relative_to cycle and for a kinematic loop", () => {
    const cycle = load(
      '<sdf version="1.7"><model name="m"><link name="a"><pose relative_to="b">0 0 0 0 0 0</pose></link><link name="b"><pose relative_to="a">0 0 0 0 0 0</pose></link></model></sdf>',
    );
    expect(cycle.scene).toBeNull();
    expect(cycle.diagnostics[0]?.code).toBe("E305");
    expect(cycle.diagnostics[0]?.message).toContain("depends on itself");
    const loop = load(
      `<sdf version="1.7"><model name="m"><link name="a"/><link name="b"/>
        <joint name="j1" type="revolute"><parent>a</parent><child>b</child></joint>
        <joint name="j2" type="revolute"><parent>b</parent><child>a</child></joint></model></sdf>`,
    );
    expect(loop.scene).toBeNull();
    expect(loop.diagnostics.some((d) => d.code === "E305" && /loop/.test(d.message))).toBe(true);
  });
});

describe("kinematic tree", () => {
  const scene = mustLoad(fixture("chain.sdf"));

  it("builds jointFrame, jointMotion, child link with the planned local transforms", () => {
    const byId = new Map(scene.nodes.map((n) => [n.id, n] as const));
    expect(byId.get("joint:j2#frame")?.parent).toBe("link:l1");
    expect(byId.get("joint:j2#motion")?.parent).toBe("joint:j2#frame");
    expect(byId.get("link:l2")?.parent).toBe("joint:j2#motion");
    // j2: parent l1 at (0,0,1), child l2 at (1,0,1), joint 0.5 above l2 -> frame at (1,0,1.5), so relative to l1 (1,0,0.5)
    expectMat(byId.get("joint:j2#frame")?.local, [1, 0, 0, 1, 0, 1, 0, 0, 0, 0, 1, 0.5, 0, 0, 0, 1]);
    expectMat(byId.get("link:l2")?.local, [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, -0.5, 0, 0, 0, 1]);
    // the root link hangs under the model node
    expect(byId.get("link:base")?.parent).toBe("model:chain");
  });

  it("matches hand-computed world matrices of the two-joint chain (1e-9)", () => {
    const rest = forwardKinematics(scene, {});
    expectMat(rest.get("link:l1"), [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 1, 0, 0, 0, 1]);
    expectMat(rest.get("link:l2"), [1, 0, 0, 1, 0, 1, 0, 0, 0, 0, 1, 1, 0, 0, 0, 1]);

    // q1 = q2 = pi/2.  l1 = T(0,0,1) Rz(q1).  l2 = l1 * T(1,0,0.5) * Ry(q2) * T(0,0,-0.5)
    //   Rz(pi/2) Ry(pi/2) = [[0,-1,0],[0,0,1],[-1,0,0]]
    //   position: (0,0,1) + Rz(pi/2)(1,0,0.5) + R(0,0,-0.5) = (0,0,1) + (0,1,0.5) + (0,-0.5,0) = (0,0.5,1.5)
    const moved = forwardKinematics(scene, { "joint:j1": H, "joint:j2": H });
    expectMat(moved.get("link:l1"), [0, -1, 0, 0, 1, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 1]);
    expectMat(moved.get("link:l2"), [0, -1, 0, 0, 0, 0, 1, 0.5, -1, 0, 0, 1.5, 0, 0, 0, 1]);
    expectMat(moved.get("link:base"), [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]);
  });

  it("slides a prismatic joint along its axis", () => {
    const frames = mustLoad(fixture("frames.sdf"));
    const moved = forwardKinematics(frames, { "joint:prism": 0.25 });
    expect(positionOf(moved.get("link:slider") ?? [])).toEqual([10.25, 0, 0]);
    expect(positionOf(moved.get("link:a") ?? [])).toEqual([11, 2, 3]);
  });
});

describe("parse diagnostics", () => {
  it("reports E305 for malformed XML, naming the file and what to do", () => {
    const { scene, diagnostics } = parseSdf("<sdf><model name='m'></sdf>", "scenes/bad.sdf");
    expect(scene).toBeNull();
    expect(diagnostics).toHaveLength(1);
    expect(diagnostics[0]).toMatchObject({ code: "E305", severity: "error", path: null });
    expect(diagnostics[0]?.message).toContain("scenes/bad.sdf");
    expect(diagnostics[0]?.hint).toMatch(/fix the XML/);
  });

  it("reports E305 for a missing <sdf> root and bad numbers", () => {
    expect(parseSdf("<model name='m'/>", "s.sdf").diagnostics[0]?.code).toBe("E305");
    const bad = parseSdf('<sdf version="1.7"><model name="m"><link name="a"><pose>1 2</pose></link></model></sdf>', "s.sdf");
    expect(bad.scene).toBeNull();
    expect(bad.diagnostics[0]?.code).toBe("E305");
  });

  it("skips a ball joint with E306 and keeps the scene", () => {
    const { scene, diagnostics } = load(
      `<sdf version="1.7"><model name="m"><link name="a"/><link name="b"/>
        <joint name="shoulder" type="ball"><parent>a</parent><child>b</child></joint></model></sdf>`,
    );
    expect(diagnostics).toHaveLength(1);
    expect(diagnostics[0]).toMatchObject({ code: "E306", severity: "error" });
    expect(diagnostics[0]?.path).toBe("joint:shoulder");
    expect(diagnostics[0]?.message).toContain("shoulder");
    expect(diagnostics[0]?.message).toContain("ball");
    expect(diagnostics[0]?.hint).toMatch(/revolute/);
    expect(scene?.joints).toHaveLength(0);
    expect(scene?.nodes.filter((n) => n.kind === "link")).toHaveLength(2);
  });

  it("skips non-GLB meshes and unknown geometry with E306, and ignores collision, inertial, sensor and plugin silently", () => {
    const stl = load(fixture("unsupported/mesh-stl.sdf"));
    expect(stl.diagnostics.map((d) => d.code)).toEqual(["E306"]);
    expect(stl.diagnostics[0]?.message).toContain("old.stl");
    expect(stl.scene?.visuals.map((v) => v.name)).toEqual(["shell"]);
    const odd = load(
      `<sdf version="1.7"><model name="m"><link name="a">
        <visual name="v"><geometry><plane><normal>0 0 1</normal></plane></geometry></visual>
        <collision name="c"><geometry><box><size>1 1 1</size></box></geometry></collision>
        <inertial><mass>2</mass></inertial><sensor name="s" type="imu"/></link><plugin name="p" filename="x"/></model></sdf>`,
    );
    expect(odd.diagnostics.map((d) => d.code)).toEqual(["E306"]);
    expect(odd.diagnostics[0]?.message).toContain("plane");
    expect(odd.diagnostics[0]?.path).toBe("visual:v");
  });
});

describe("scene files in the repository", () => {
  const files: string[] = [];
  const fixtures = path.join(root, "tests", "fixtures", "scenes");
  for (const f of readdirSync(fixtures)) if (f.endsWith(".sdf")) files.push(path.join(fixtures, f));
  const examples = path.join(repoRoot, "examples");
  for (const ex of readdirSync(examples, { withFileTypes: true })) {
    if (!ex.isDirectory()) continue;
    const dir = path.join(examples, ex.name, "scenes");
    try {
      for (const f of readdirSync(dir)) if (f.endsWith(".sdf")) files.push(path.join(dir, f));
    } catch {
      // an example without scenes
    }
  }

  it("finds the fixtures, so the loop below is never vacuous", () => {
    expect(files.filter((f) => f.startsWith(fixtures)).length).toBeGreaterThanOrEqual(2);
  });

  it.each(files.map((f) => [path.relative(repoRoot, f).replaceAll("\\", "/"), f] as const))("%s parses and resolves without E305 or E306", (rel, file) => {
    const { scene, diagnostics } = load(readFileSync(file, "utf8"), rel);
    expect(diagnostics.filter((d) => d.code === "E305" || d.code === "E306").map((d) => d.message)).toEqual([]);
    expect(scene).not.toBeNull();
    expect(scene?.nodes.some((n) => n.kind === "link")).toBe(true);
  });
});
