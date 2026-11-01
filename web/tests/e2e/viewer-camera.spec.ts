import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

/**
 * The 3D view's camera at every scale (fake worker; no run is needed, the scenes show at rest):
 *
 * 1. the `cars` example's race track (about 1.7 km across): after Fit, every wheel notch over the car brings the
 *    camera a fixed fraction closer to it, until it is a few metres away; a drag that starts on the car orbits
 *    around the car (it stays under the cursor, a pivot dot shows); a tap still selects;
 * 2. a small scene (`van-der-pol`, the belt rig) zooms the same way, in and back out.
 *
 * `data-camera` on the viewer is the camera after each frame (`ViewerScene.cameraState`). With
 * `BGSIM_CAMERA_SHOTS=<dir>` the spec saves screenshots there.
 *
 * Run with `$env:BGSIM_E2E_PORT="8775"; npx playwright test tests/e2e/viewer-camera.spec.ts`.
 */

test.describe.configure({ timeout: 180_000 });

const shots = process.env.BGSIM_CAMERA_SHOTS ?? "";
let project = "";

interface CameraState {
  eye: [number, number, number];
  target: [number, number, number];
  radius: number;
  pivot: boolean;
  view: number[];
  fov: number;
}

async function camera(page: Page): Promise<CameraState> {
  const raw = await page.getByTestId("viewer").getAttribute("data-camera");
  return JSON.parse(raw ?? "null") as CameraState;
}

const distance = (a: readonly number[], b: readonly number[]) => Math.hypot((a[0] ?? 0) - (b[0] ?? 0), (a[1] ?? 0) - (b[1] ?? 0), (a[2] ?? 0) - (b[2] ?? 0));

/** Where a scene point (Y up) is drawn on the page, from the camera's view matrix (perspective). */
async function onPage(page: Page, cam: CameraState, p: readonly [number, number, number]): Promise<{ x: number; y: number }> {
  const box = await page.getByTestId("viewer-canvas").boundingBox();
  if (box === null) throw new Error("the 3D view is not visible");
  const m = cam.view;
  const at = (i: number) => m[i] ?? 0;
  const vx = p[0] * at(0) + p[1] * at(4) + p[2] * at(8) + at(12);
  const vy = p[0] * at(1) + p[1] * at(5) + p[2] * at(9) + at(13);
  const vz = p[0] * at(2) + p[1] * at(6) + p[2] * at(10) + at(14);
  const t = Math.tan(cam.fov / 2);
  const nx = vx / (-vz * t * (box.width / box.height));
  const ny = vy / (-vz * t);
  return { x: box.x + ((nx + 1) / 2) * box.width, y: box.y + ((1 - ny) / 2) * box.height };
}

async function shot(page: Page, name: string): Promise<void> {
  if (shots.length === 0) return;
  // the shaders of a newly shown mesh compile asynchronously; the view redraws once they are ready
  await page.waitForTimeout(1_500);
  await page.getByTestId("scene-view").screenshot({ path: path.join(shots, `${name}.png`) });
}

/** Turns the wheel one notch at the mouse and waits for the frame that shows it. */
async function notch(page: Page, deltaY: number): Promise<CameraState> {
  const before = JSON.stringify(await camera(page));
  await page.mouse.wheel(0, deltaY);
  await expect.poll(async () => JSON.stringify(await camera(page)), { message: "a wheel notch moves the camera" }).not.toBe(before);
  return camera(page);
}

async function openScene(page: Page, example: string, model: string): Promise<void> {
  project = `camera-${example}-${Date.now()}-${test.info().workerIndex}`;
  const created = await page.request.post("/api/projects", { data: { name: project, example } });
  expect(created.status(), await created.text()).toBe(201);
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.goto(`/?project=${encodeURIComponent(project)}&model=${encodeURIComponent(model)}`);
  await page.getByRole("tab", { name: "3D View" }).click();
  await expect(page.getByTestId("scene-view")).toHaveAttribute("data-state", "loaded", { timeout: 60_000 });
  await expect(page.getByTestId("viewer")).toHaveAttribute("data-state", "idle", { timeout: 60_000 });
}

test.afterEach(async ({ request }) => {
  if (project.length > 0) await request.delete(`/api/projects/${project}`);
  project = "";
});

test("zooms toward the car on the race track until it is close, and orbits around it", async ({ page }) => {
  await openScene(page, "cars", "racecar-sim");
  let cam = await camera(page);
  // The car rests at the model origin (z up, metres); in the scene frame (y up) its body is about 0.5 m up.
  const car: [number, number, number] = [0, 0.5, 0];
  const far = distance(cam.eye, car);
  expect(far, "Fit frames the whole 1.7 km track").toBeGreaterThan(800);
  await shot(page, "track-1-fit");

  const start = await onPage(page, cam, car);
  await page.mouse.move(start.x, start.y);
  let d = far;
  for (let i = 0; i < 40 && d > 12; i += 1) {
    cam = await notch(page, -100);
    const next = distance(cam.eye, car);
    // every notch closes in by about the same fraction, at 1 km as at 20 m
    expect(next / d, `notch ${i + 1} at ${d.toFixed(1)} m`).toBeLessThan(0.9);
    d = next;
    // the point zoomed to (the new orbit pivot) stays under the cursor
    const at = await onPage(page, cam, cam.target);
    expect(Math.hypot(at.x - start.x, at.y - start.y), `the zoom point under the cursor after notch ${i + 1}`).toBeLessThan(2);
  }
  expect(d, "about 30 notches bring the car within 12 m").toBeLessThan(12);
  expect(distance(cam.target, car), "the zoom point is on the car").toBeLessThan(3);
  await expect(page.getByTestId("viewer")).toHaveAttribute("data-state", "idle");
  await shot(page, "track-2-zoomed-to-car");

  // A drag that starts on the car orbits around it: the orbit target is on the car and the car stays put.
  await page.mouse.move(start.x, start.y);
  await page.mouse.down();
  await page.mouse.move(start.x + 60, start.y + 10, { steps: 6 });
  await page.mouse.move(start.x + 160, start.y + 20, { steps: 10 });
  await expect.poll(async () => (await camera(page)).pivot, { message: "the pivot dot shows during the drag" }).toBe(true);
  cam = await camera(page);
  expect(distance(cam.target, car), "the orbit pivot is on the car").toBeLessThan(3);
  const pivotAt = await onPage(page, cam, [cam.target[0], cam.target[1], cam.target[2]]);
  expect(Math.hypot(pivotAt.x - start.x, pivotAt.y - start.y), "the pivot stays under the press point while orbiting").toBeLessThan(6);
  await shot(page, "track-3-orbit-around-car");
  await page.mouse.up();
  await expect.poll(async () => (await camera(page)).pivot, { message: "the pivot dot fades out after the release", timeout: 5_000 }).toBe(false);

  // A tap still selects what it hits.
  const now = await camera(page);
  const tap = await onPage(page, now, [now.target[0], now.target[1], now.target[2]]);
  await page.mouse.click(tap.x, tap.y);
  await expect(page.locator('[data-testid^="scene-tree-row-"][aria-pressed="true"]')).not.toHaveCount(0);

  // Fit brings the whole track back.
  await page.getByTestId("viewer-fit").click();
  await expect.poll(async () => distance((await camera(page)).eye, car)).toBeGreaterThan(800);
});

test("zooms a small scene the same way, in and back out", async ({ page }) => {
  await openScene(page, "van-der-pol", "vdp-belt");
  const box = await page.getByTestId("viewer-canvas").boundingBox();
  if (box === null) throw new Error("the 3D view is not visible");
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  const first = await camera(page);
  const r0 = distance(first.eye, first.target);
  await shot(page, "vdp-1-fit");
  let cam = first;
  for (let i = 0; i < 8; i += 1) cam = await notch(page, -100);
  const near = distance(cam.eye, first.target);
  expect(near).toBeLessThan(r0 * 0.5);
  await shot(page, "vdp-2-zoomed");
  for (let i = 0; i < 8; i += 1) cam = await notch(page, 100);
  expect(distance(cam.eye, first.target)).toBeGreaterThan(r0 * 0.8);
});
