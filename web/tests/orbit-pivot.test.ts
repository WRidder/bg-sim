import { afterEach, describe, expect, it } from "vitest";
import { NullEngine } from "@babylonjs/core/Engines/nullEngine";
import { Matrix, Vector3 } from "@babylonjs/core/Maths/math.vector";
import { CreateBox } from "@babylonjs/core/Meshes/Builders/boxBuilder";
import {
  clipPlanes,
  MAX_NOTCHES_PER_EVENT,
  MIN_ZOOM_DISTANCE_M,
  NEAR_MIN_M,
  orthoZoomEye,
  pivotRig,
  rayPlane,
  wheelNotches,
  zoomEye,
  zoomFactor,
  zoomScale,
  ZOOM_RATIO_PER_NOTCH,
} from "../src/viewer/orbitPivot";
import { fadeAlpha, PIVOT_FADE_MS, PivotFade, driveFade } from "../src/viewer/pivotFade";
import { tagEntity, ViewerScene } from "../src/viewer/viewerScene";

describe("wheelNotches", () => {
  it("counts a mouse notch as one, in pixels, lines or pages, wheel up zooming in", () => {
    expect(wheelNotches(-100, 0)).toBeCloseTo(1, 12);
    expect(wheelNotches(100, 0)).toBeCloseTo(-1, 12);
    expect(wheelNotches(-3, 1)).toBeCloseTo(1, 12);
    expect(wheelNotches(1, 2)).toBeCloseTo(-1, 12);
    // a trackpad scroll sends fractions
    expect(wheelNotches(-10, 0)).toBeCloseTo(0.1, 12);
  });

  it("clamps a burst to a few notches", () => {
    expect(wheelNotches(-3000, 0)).toBe(MAX_NOTCHES_PER_EVENT);
    expect(wheelNotches(3000, 0)).toBe(-MAX_NOTCHES_PER_EVENT);
  });

  it("maps a trackpad pinch (Ctrl+wheel, deltaY = -100 ln scale) to the distance change of the pinch", () => {
    for (const scale of [1.05, 0.9, 1.3]) {
      const n = wheelNotches(-100 * Math.log(scale), 0, true);
      expect(zoomFactor(n)).toBeCloseTo(1 / scale, 9);
    }
  });
});

describe("zoomFactor", () => {
  it("is exponential: every notch scales the distance alike, in and out", () => {
    expect(zoomFactor(1)).toBeCloseTo(ZOOM_RATIO_PER_NOTCH, 12);
    expect(zoomFactor(-1)).toBeCloseTo(1 / ZOOM_RATIO_PER_NOTCH, 12);
    expect(zoomFactor(0)).toBe(1);
    expect(zoomFactor(2.5) * zoomFactor(-2.5)).toBeCloseTo(1, 12);
    expect(zoomFactor(1) * zoomFactor(2)).toBeCloseTo(zoomFactor(3), 12);
  });

  it("takes as many notches from 2 km to 5 m as from 2 m to 5 mm (scale-free)", () => {
    const notches = (from: number, to: number) => Math.log(to / from) / Math.log(ZOOM_RATIO_PER_NOTCH);
    expect(notches(2000, 5)).toBeCloseTo(notches(2, 0.005), 9);
    expect(notches(2000, 5)).toBeLessThan(30);
  });
});

describe("zoomEye", () => {
  const point = new Vector3(10, 0, 0);
  it("moves the eye toward the point by the factor, on the line through both", () => {
    const eye = new Vector3(10, 0, 100);
    const next = zoomEye(eye, point, 0.8, MIN_ZOOM_DISTANCE_M, 1e6);
    expect(next?.z).toBeCloseTo(80, 9);
    expect(next?.x).toBeCloseTo(10, 9);
    const off = zoomEye(new Vector3(0, 0, 0), point, 0.5, MIN_ZOOM_DISTANCE_M, 1e6);
    expect(off?.x).toBeCloseTo(5, 9);
  });

  it("stops at the closest distance and at the farthest, and never moves closer on a zoom out", () => {
    const close = zoomEye(new Vector3(10, 0, 0.0011), point, 0.5, MIN_ZOOM_DISTANCE_M, 1e6);
    expect(close?.z).toBeCloseTo(MIN_ZOOM_DISTANCE_M, 12);
    expect(zoomEye(new Vector3(10, 0, MIN_ZOOM_DISTANCE_M), point, 0.5, MIN_ZOOM_DISTANCE_M, 1e6)).toBeNull();
    const far = zoomEye(new Vector3(10, 0, 90), point, 1.25, MIN_ZOOM_DISTANCE_M, 100);
    expect(far?.z).toBeCloseTo(100, 9);
    // already beyond the farthest distance (the point is far away): a zoom out leaves the eye
    expect(zoomEye(new Vector3(10, 0, 500), point, 1.25, MIN_ZOOM_DISTANCE_M, 100)).toBeNull();
  });
});

describe("zoomScale and orthoZoomEye", () => {
  it("scales within the limits, monotonic in the zoom direction", () => {
    expect(zoomScale(10, 0.8, 1, 100)).toBeCloseTo(8, 12);
    expect(zoomScale(1.1, 0.5, 1, 100)).toBe(1);
    expect(zoomScale(1, 0.5, 1, 100)).toBeNull();
    expect(zoomScale(200, 1.25, 1, 100)).toBeNull();
    expect(zoomScale(0, 0.5, 1, 100)).toBeNull();
  });

  it("slides the orthographic eye sideways toward the point, its depth unchanged", () => {
    const eye = new Vector3(0, 0, 10);
    const forward = new Vector3(0, 0, -1);
    const next = orthoZoomEye(eye, forward, new Vector3(4, -2, -50), 0.75);
    expect(next.x).toBeCloseTo(1, 12);
    expect(next.y).toBeCloseTo(-0.5, 12);
    expect(next.z).toBeCloseTo(10, 12);
  });
});

describe("pivotRig", () => {
  const up = new Vector3(0, 1, 0);
  /** The orbit camera's view: look-at from `position` to `target`, shifted by the screen offset. */
  function orbitView(position: Vector3, target: Vector3, offset: readonly [number, number]): Matrix {
    const m = Matrix.LookAtRH(position, target, up);
    m.addAtIndex(12, offset[0]);
    m.addAtIndex(13, offset[1]);
    return m;
  }

  it("keeps the view exactly while the target moves to an off-axis point", () => {
    const eye = new Vector3(3, 2, 5);
    const forward = new Vector3(-0.5, -0.3, -1).normalize();
    const view = Matrix.LookAtRH(eye, eye.add(forward), up);
    const point = new Vector3(-1, 0.4, -2.5);
    const p = pivotRig(eye, forward, point, view);
    expect(p.target.equalsWithEpsilon(point, 1e-12)).toBe(true);
    expect(p.radius).toBeCloseTo(Vector3.Dot(point.subtract(eye), forward), 12);
    const after = orbitView(p.position, p.target, p.offset);
    // Babylon matrices are float32: 6 digits
    for (let i = 0; i < 16; i += 1) expect(after.m[i]).toBeCloseTo(view.m[i] ?? 0, 6);
  });

  it("orbits around the pivot: it stays at its screen place while the camera turns about it", () => {
    const eye = new Vector3(0, 0, 10);
    const forward = new Vector3(0, 0, -1);
    const point = new Vector3(2, 1, 0);
    const p = pivotRig(eye, forward, point, Matrix.LookAtRH(eye, eye.add(forward), up));
    // turn the orbit position about the target by 0.4 rad around the vertical
    const rel = p.position.subtract(p.target);
    const turned = p.target.add(Vector3.TransformCoordinates(rel, Matrix.RotationY(0.4)));
    const v = orbitView(turned, p.target, p.offset);
    const inView = Vector3.TransformCoordinates(point, v);
    expect(inView.x).toBeCloseTo(p.offset[0], 9);
    expect(inView.y).toBeCloseTo(p.offset[1], 9);
  });
});

describe("rayPlane", () => {
  it("meets the plane in front of the ray, never behind or along it", () => {
    const hit = rayPlane(new Vector3(0, 5, 0), new Vector3(0, -1, 1).normalize(), Vector3.Zero(), new Vector3(0, 1, 0));
    expect(hit?.z).toBeCloseTo(5, 9);
    expect(rayPlane(new Vector3(0, 5, 0), new Vector3(0, 1, 0), Vector3.Zero(), new Vector3(0, 1, 0))).toBeNull();
    expect(rayPlane(new Vector3(0, 5, 0), new Vector3(1, 0, 0), Vector3.Zero(), new Vector3(0, 1, 0))).toBeNull();
  });
});

describe("clipPlanes", () => {
  it("brings the near plane in with the radius and takes in the farthest object", () => {
    const big = clipPlanes(2300, null, 3400);
    const close = clipPlanes(5, null, 3400);
    expect(big.near).toBeGreaterThan(1);
    expect(close.near).toBeLessThan(0.05);
    expect(big.far).toBeGreaterThanOrEqual(3400);
    expect(close.far).toBeGreaterThanOrEqual(3400);
    // a km-scale view keeps far/near well under the 1e6 of a fixed 0.01 m .. 10 km frustum
    expect(big.far / big.near).toBeLessThan(1e4);
  });

  it("stays in front of a nearer object and never comes closer than the minimum", () => {
    expect(clipPlanes(500, 0.4, 600).near).toBeCloseTo(0.2, 12);
    expect(clipPlanes(1e-3, null, 1).near).toBe(NEAR_MIN_M);
  });
});

describe("pivot fade", () => {
  it("fades smoothly from 1 to 0 over the fade time and is then done", () => {
    expect(fadeAlpha(0)).toBe(1);
    expect(fadeAlpha(0.5)).toBeCloseTo(0.5, 12);
    expect(fadeAlpha(1)).toBe(0);
    const f = new PivotFade();
    expect(f.alpha(0)).toBe(1);
    f.start(100);
    f.start(200); // a running fade keeps its start
    expect(f.done(100 + PIVOT_FADE_MS - 1)).toBe(false);
    expect(f.done(100 + PIVOT_FADE_MS)).toBe(true);
    f.reset();
    expect(f.fading).toBe(false);
  });

  it("drives the fade frame by frame until done", () => {
    let now = 0;
    const frames: (() => void)[] = [];
    const seen: [number, boolean][] = [];
    const f = new PivotFade();
    f.start(0);
    driveFade(f, {
      now: () => now,
      raf: (cb) => frames.push(cb),
      cancel: () => undefined,
      apply: (alpha, done) => seen.push([alpha, done]),
    });
    for (let i = 0; i < 40 && frames.length > 0; i += 1) {
      now += 50;
      frames.shift()?.();
    }
    expect(seen.at(-1)).toEqual([0, true]);
    expect(seen.length).toBe(PIVOT_FADE_MS / 50);
  });
});

// The scene behind the viewer, on a NullEngine: a 2 km ground with a 4 m car far from its centre.
const SIZE = 64;
const engines: NullEngine[] = [];
afterEach(() => {
  for (const e of engines.splice(0)) e.dispose();
});

function make(): ViewerScene {
  const engine = new NullEngine({ renderWidth: SIZE, renderHeight: SIZE, textureSize: SIZE, deterministicLockstep: false, lockstepMaxSteps: 1, useHighPrecisionMatrix: true });
  engines.push(engine);
  return new ViewerScene(engine);
}

function trackScene(): { s: ViewerScene; car: Vector3 } {
  const s = make();
  const ground = CreateBox("ground", { width: 2000, height: 1200, depth: 1 }, s.scene);
  ground.parent = s.root;
  ground.position.set(0, 0, -0.5);
  tagEntity(ground, "visual:ground");
  const car = CreateBox("car", { width: 4, height: 2, depth: 1.2 }, s.scene);
  car.parent = s.root;
  car.position.set(600, 300, 0.6);
  tagEntity(car, "visual:body");
  s.fit("iso");
  s.scene.render();
  return { s, car: car.getAbsolutePosition().clone() };
}

/** The canvas point (px) a scene point is drawn at. */
function screenOf(s: ViewerScene, p: Vector3): { x: number; y: number } {
  const engine = s.scene.getEngine();
  const viewport = s.camera.viewport.toGlobal(engine.getRenderWidth(), engine.getRenderHeight());
  const q = Vector3.Project(p, Matrix.Identity(), s.scene.getTransformMatrix(), viewport);
  return { x: q.x, y: q.y };
}

function viewOf(s: ViewerScene): number[] {
  return Array.from(s.camera.getViewMatrix().m);
}

describe("ViewerScene zoom and orbit pivot", () => {
  it("zooms toward the car under the cursor on a 2 km scene until it is close, every notch closing in", () => {
    const { s, car } = trackScene();
    const start = screenOf(s, car);
    let distance = Vector3.Distance(s.eye(), car);
    expect(distance).toBeGreaterThan(1000);
    for (let i = 0; i < 26; i += 1) {
      expect(s.zoomAt(start.x, start.y, 1)).toBe(true);
      s.scene.render();
      const next = Vector3.Distance(s.eye(), car);
      // a near constant fraction per notch, at 2 km as at 10 m
      expect(next / distance).toBeGreaterThan(0.7);
      expect(next / distance).toBeLessThan(0.9);
      distance = next;
      // the car stays under the cursor
      const at = screenOf(s, car);
      expect(Math.hypot(at.x - start.x, at.y - start.y)).toBeLessThan(1.5);
    }
    expect(distance).toBeLessThan(20);
    expect(s.pickEntity(start.x, start.y, 0)).toBe("visual:body");
    // the orbit pivot is on the car now
    expect(Vector3.Distance(s.camera.target, car)).toBeLessThan(2);
    // near plane for a close-up, far plane still takes in the whole ground
    expect(s.camera.minZ).toBeLessThan(0.1);
    expect(s.camera.maxZ).toBeGreaterThan(1000);
    // and back out: as many notches bring the camera back to the start distance
    for (let i = 0; i < 26; i += 1) s.zoomAt(start.x, start.y, -1);
    s.scene.render();
    expect(Vector3.Distance(s.eye(), car)).toBeGreaterThan(1000);
    s.dispose();
  });

  it("zooms toward the plane through the target when nothing is under the cursor", () => {
    const s = make();
    s.fit("front");
    s.scene.render();
    const before = Vector3.Distance(s.eye(), s.camera.target);
    expect(s.zoomAt(SIZE / 2, 2, 1)).toBe(true);
    s.scene.render();
    expect(Vector3.Distance(s.eye(), s.camera.target)).toBeLessThan(before);
    s.dispose();
  });

  it("makes the point under a press the orbit pivot without moving the view, and orbits around it", () => {
    const { s, car } = trackScene();
    const at = screenOf(s, car);
    const view = viewOf(s);
    const pivot = s.pivotAt(at.x, at.y);
    expect(pivot).not.toBeNull();
    s.scene.render();
    viewOf(s).forEach((v, i) => expect(v).toBeCloseTo(view[i] ?? 0, 6));
    expect(Vector3.Distance(s.camera.target, pivot ?? Vector3.Zero())).toBeLessThan(1e-9);
    const pivotScreen = screenOf(s, pivot ?? Vector3.Zero());
    s.camera.alpha += 0.4;
    s.camera.beta -= 0.2;
    s.scene.render();
    const turned = screenOf(s, pivot ?? Vector3.Zero());
    expect(Math.hypot(turned.x - pivotScreen.x, turned.y - pivotScreen.y)).toBeLessThan(0.01);
    s.dispose();
  });

  it("keeps the pivot when a press finds nothing under it, and fit clears the screen offset", () => {
    const s = make();
    s.scene.render();
    const target = s.camera.target.clone();
    expect(s.pivotAt(1, 1)).toBeNull();
    expect(s.camera.target.equals(target)).toBe(true);
    s.showPivot(target);
    expect(s.pivotPoint()).not.toBeNull();
    s.fit();
    expect(s.pivotPoint()).toBeNull();
    expect(s.camera.targetScreenOffset.x).toBe(0);
    s.dispose();
  });

  it("zooms in orthographic projection too, the point under the cursor staying put", () => {
    const { s, car } = trackScene();
    s.setOrthographic(true);
    s.scene.render();
    const start = screenOf(s, car);
    const half = s.camera.orthoTop ?? 0;
    for (let i = 0; i < 5; i += 1) s.zoomAt(start.x, start.y, 1);
    s.scene.render();
    expect(s.camera.orthoTop ?? 0).toBeLessThan(half * 0.5);
    const at = screenOf(s, car);
    expect(Math.hypot(at.x - start.x, at.y - start.y)).toBeLessThan(1.5);
    // a press there pivots without changing the orthographic view
    const view = viewOf(s);
    const top = s.camera.orthoTop;
    expect(s.pivotAt(at.x, at.y)).not.toBeNull();
    s.scene.render();
    expect(s.camera.orthoTop).toBeCloseTo(top ?? 0, 9);
    viewOf(s).forEach((v, i) => expect(v).toBeCloseTo(view[i] ?? 0, 6));
    s.dispose();
  });
});
