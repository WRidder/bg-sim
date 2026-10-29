import { afterEach, describe, expect, it } from "vitest";
import { NullEngine } from "@babylonjs/core/Engines/nullEngine";
import { Vector3 } from "@babylonjs/core/Maths/math.vector";
import { StandardMaterial } from "@babylonjs/core/Materials/standardMaterial";
import { PBRMaterial } from "@babylonjs/core/Materials/PBR/pbrMaterial";
import { CreateBox } from "@babylonjs/core/Meshes/Builders/boxBuilder";
import { TransformNode } from "@babylonjs/core/Meshes/transformNode";
import type { DirectionalLight } from "@babylonjs/core/Lights/directionalLight";
import { CAMERA_PRESETS, SDF_ROOT_NAME, ViewerScene, tagEntity, type CameraPreset } from "../src/viewer/viewerScene";
import { nearestTarget, PICK_RADIUS_PX, TAP_SLOP_PX } from "../src/viewer/picking";

const SIZE = 64;

function nullEngine(): NullEngine {
  return new NullEngine({
    renderWidth: SIZE,
    renderHeight: SIZE,
    textureSize: SIZE,
    deterministicLockstep: false,
    lockstepMaxSteps: 1,
    useHighPrecisionMatrix: true,
  });
}

const engines: NullEngine[] = [];
function make(onInvalidate?: () => void): ViewerScene {
  const engine = nullEngine();
  engines.push(engine);
  return new ViewerScene(engine, onInvalidate);
}

afterEach(() => {
  for (const e of engines.splice(0)) e.dispose();
});

function expectClose(v: Vector3, x: number, y: number, z: number): void {
  expect(v.x).toBeCloseTo(x, 9);
  expect(v.y).toBeCloseTo(y, 9);
  expect(v.z).toBeCloseTo(z, 9);
}

describe("scene constructor", () => {
  it("is right-handed with a transparent clear colour and the planned camera settings", () => {
    const s = make();
    expect(s.scene.useRightHandedSystem).toBe(true);
    expect(s.scene.clearColor.a).toBe(0);
    expect(s.scene.skipPointerMovePicking).toBe(true);
    expect(s.camera.minZ).toBe(0.01);
    expect(s.camera.lowerRadiusLimit).toBe(0.05);
    expect(s.camera.wheelDeltaPercentage).toBe(0.02);
    expect(s.camera.pinchDeltaPercentage).toBe(0.004);
    expect(s.camera.panningSensibility).toBe(2000);
    s.dispose();
  });

  it("has the key, fill and rim rig, fixed in camera space while the camera moves", () => {
    const s = make();
    const lights = s.scene.lights as DirectionalLight[];
    expect(lights.map((l) => [l.name, l.intensity])).toEqual([
      ["key", 1],
      ["fill", 0.5],
      ["rim", 0.8],
    ]);
    const before = lights.map((l) => l.direction.clone());
    s.camera.alpha += 1;
    s.scene.render();
    lights.forEach((l, i) => {
      // the rig turns with the camera: it is fixed relative to the view, not to the world
      expect(Vector3.Distance(l.direction, before[i] ?? l.direction)).toBeGreaterThan(0.1);
      expect(l.direction.length()).toBeCloseTo(1, 9);
    });
    // camera space of a right-handed view looks down -z
    const key = Vector3.TransformNormal(lights[0]?.direction ?? Vector3.Zero(), s.camera.getViewMatrix());
    expect(Vector3.Distance(key, new Vector3(0.6, -0.8, -1).normalize())).toBeLessThan(1e-6);
    s.dispose();
  });

  it("attaches the toon plugin to Standard and PBR materials", () => {
    const s = make();
    const standard = new StandardMaterial("std", s.scene);
    const pbr = new PBRMaterial("pbr", s.scene);
    expect(standard.pluginManager?.getPlugin("McfToon")).toBeTruthy();
    expect(pbr.pluginManager?.getPlugin("McfToon")).toBeTruthy();
    s.dispose();
  });
});

describe("Z-up root", () => {
  it("maps SDF (0,0,1) to world (0,1,0)", () => {
    const s = make();
    expect(s.root.name).toBe(SDF_ROOT_NAME);
    expect(s.root.rotation.x).toBe(-Math.PI / 2);
    s.root.computeWorldMatrix(true);
    const m = s.root.getWorldMatrix();
    expectClose(Vector3.TransformCoordinates(new Vector3(0, 0, 1), m), 0, 1, 0);
    // x is unchanged and SDF +Y lands on world -Z (a right-handed rotation about x)
    expectClose(Vector3.TransformCoordinates(new Vector3(1, 0, 0), m), 1, 0, 0);
    expectClose(Vector3.TransformCoordinates(new Vector3(0, 1, 0), m), 0, 0, -1);
    s.dispose();
  });

  it("carries content parented under it", () => {
    const s = make();
    const node = new TransformNode("link", s.scene);
    node.parent = s.root;
    node.position.set(0, 0, 2);
    expectClose(node.getAbsolutePosition(), 0, 2, 0);
    s.dispose();
  });
});

describe("camera", () => {
  // Model (Z-up) preset directions as scene (Y-up) directions.
  const directions: Record<CameraPreset, [number, number, number]> = {
    iso: [1, 0.8, 1],
    top: [0, 1, 0],
    front: [1, 0, 0],
    side: [0, 0, 1],
  };

  for (const preset of Object.keys(CAMERA_PRESETS) as CameraPreset[]) {
    it(`the ${preset} preset looks from the model-frame direction`, () => {
      const s = make();
      s.fit(preset);
      s.scene.render();
      const d = s.camera.position.subtract(s.camera.target).normalize();
      const want = new Vector3(...directions[preset]).normalize();
      // top is clamped away from the pole by the camera's beta limit
      expect(Vector3.Distance(d, want)).toBeLessThan(preset === "top" ? 0.02 : 1e-6);
      expect(Number.isFinite(s.camera.getViewMatrix().m[0])).toBe(true);
      s.dispose();
    });
  }

  it("fit frames the content, not the grid, and keeps the view direction", () => {
    const s = make();
    const box = CreateBox("part", { size: 1 }, s.scene);
    box.parent = s.root;
    box.position.set(10, 0, 0.5);
    tagEntity(box, "part");
    s.fit("front");
    expect(s.camera.target.x).toBeCloseTo(10, 6);
    expect(s.camera.target.y).toBeCloseTo(0.5, 6);
    const radius = s.camera.radius;
    s.camera.alpha += 0.5;
    s.camera.radius *= 3;
    s.scene.render();
    const alpha = s.camera.alpha;
    s.fit();
    expect(s.camera.radius).toBeCloseTo(radius, 6);
    expect(s.camera.alpha).toBeCloseTo(alpha, 6);
    s.dispose();
  });

  it("fit on an empty scene frames the ground around the origin", () => {
    const s = make();
    s.fit("iso");
    expectClose(s.camera.target, 0, 0.5, 0);
    expect(s.camera.radius).toBeGreaterThan(2);
    s.dispose();
  });

  it("toggles orthographic projection with a frustum that follows the radius", () => {
    const s = make();
    expect(s.orthographic).toBe(false);
    s.setOrthographic(true);
    expect(s.orthographic).toBe(true);
    const half = s.camera.radius * Math.tan(s.camera.fov / 2);
    expect(s.camera.orthoTop).toBeCloseTo(half, 9);
    expect(s.camera.orthoRight).toBeCloseTo(half, 9);
    s.setOrthographic(false);
    expect(s.orthographic).toBe(false);
    s.dispose();
  });

  it("asks for a redraw when it changes the view", () => {
    let calls = 0;
    const s = make(() => {
      calls += 1;
    });
    calls = 0;
    s.fit("top");
    s.setOrthographic(true);
    s.highlight("x");
    expect(calls).toBe(3);
    s.dispose();
  });
});

describe("picking", () => {
  function sceneWithBox(size: number): ViewerScene {
    const s = make();
    // an untagged backdrop keeps the view wide, so a small entity stays small on screen
    const backdrop = CreateBox("backdrop", { size: 4 }, s.scene);
    backdrop.parent = s.root;
    backdrop.position.set(0, 0, 0.5);
    const box = CreateBox("part", { size }, s.scene);
    box.parent = s.root;
    box.position.set(0, 0, 0.5);
    tagEntity(box, "body:part");
    s.fit("front");
    s.scene.render();
    return s;
  }

  it("picks the entity under the ray and nothing on empty space", () => {
    const s = sceneWithBox(1);
    expect(s.pickEntity(SIZE / 2, SIZE / 2)).toBe("body:part");
    expect(s.pickEntity(1, 1, 0)).toBeNull();
    s.dispose();
  });

  it("falls back to the nearest entity centre within the touch radius", () => {
    const s = sceneWithBox(0.02);
    // the box is far smaller than a pixel: a tap 6 px beside it misses the ray but is within 24 px
    expect(s.pickEntity(SIZE / 2 + 6, SIZE / 2)).toBe("body:part");
    expect(s.pickEntity(SIZE / 2 + 6, SIZE / 2, 2)).toBeNull();
    s.dispose();
  });

  it("never picks the grid or the axes", () => {
    const s = make();
    s.scene.render();
    for (let x = 4; x < SIZE; x += 12) expect(s.pickEntity(x, SIZE / 2, 0)).toBeNull();
    s.dispose();
  });

  it("outlines the selected entity's meshes and clears them", () => {
    const s = sceneWithBox(1);
    const part = s.scene.getMeshByName("part");
    expect(part?.renderOutline).toBeFalsy();
    s.highlight("body:part");
    expect(part?.renderOutline).toBe(true);
    expect(part?.outlineWidth).toBeGreaterThan(0);
    expect([...s.selection]).toEqual(["body:part"]);
    s.highlight(null);
    expect(part?.renderOutline).toBe(false);
    s.dispose();
  });
});

describe("nearestTarget", () => {
  const targets = [
    { ref: "far", x: 40, y: 40, depth: 5 },
    { ref: "near", x: 12, y: 10, depth: 3 },
    { ref: "behind", x: 10, y: 10, depth: -1 },
  ];

  it("takes the nearest projected centre within the radius, never one behind the camera", () => {
    expect(nearestTarget(targets, 10, 10, PICK_RADIUS_PX)).toBe("near");
    expect(nearestTarget(targets, 100, 100, PICK_RADIUS_PX)).toBeNull();
  });

  it("prefers the closer to the camera among equally near ones", () => {
    const t = [
      { ref: "a", x: 10, y: 10, depth: 4 },
      { ref: "b", x: 10, y: 10, depth: 2 },
    ];
    expect(nearestTarget(t, 10, 10, PICK_RADIUS_PX)).toBe("b");
  });

  it("uses the planned thresholds", () => {
    expect(TAP_SLOP_PX).toBe(10);
    expect(PICK_RADIUS_PX).toBe(24);
  });
});
