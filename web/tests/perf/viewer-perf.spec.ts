/**
 * The 3D viewer's frame budget (plan 7.6, W5.1): drawing is on demand, so a stationary
 * view renders at most 2 frames per second and a hidden one (hidden page, or another dock
 * tab active) renders none.
 *
 * Frames are counted by the viewer itself (`data-frames` on `[data-testid=viewer]`, the
 * render scheduler's count of drawn frames). Page hiding is emulated by overriding
 * `document.hidden` and firing `visibilitychange`, the signal a real hidden tab sends.
 *
 * Run with `$env:BGSIM_E2E_PORT="8771"; npx playwright test tests/perf/viewer-perf.spec.ts --project perf`.
 */

import { expect, test, type Page } from "@playwright/test";

const WINDOW_MS = 3000;
const MAX_IDLE_FPS = 2;

// A project in the URL opens the editor; without one the app shows the start page (W5.4).
let project = "";

test.beforeEach(() => {
  project = `w51-perf-${Date.now()}-${test.info().workerIndex}`;
});

test.afterEach(async ({ request }) => {
  if (project.length > 0) {
    await request.delete(`/api/projects/${project}`);
  }
});

async function frames(page: Page): Promise<number> {
  return Number(await page.getByTestId("viewer").getAttribute("data-frames"));
}

/** Frames drawn during `ms`, while `during` pokes the page the way a user or the layout would. */
async function framesOver(page: Page, ms: number, during: () => Promise<void> = async () => {}): Promise<number> {
  const before = await frames(page);
  await during();
  await page.waitForTimeout(ms);
  return (await frames(page)) - before;
}

async function openViewer(page: Page): Promise<void> {
  await page.setViewportSize({ width: 1400, height: 900 });
  await page.goto(`/?project=${encodeURIComponent(project)}&model=Perf`);
  await page.getByRole("tab", { name: "3D View" }).click();
  const viewer = page.getByTestId("viewer");
  await expect(viewer).toBeVisible({ timeout: 30_000 });
  await expect(viewer).toHaveAttribute("data-state", "idle", { timeout: 30_000 });
}

/** Resizing the window makes the viewer's ResizeObserver ask for a redraw: the strongest wake-up there is. */
async function nudgeLayout(page: Page, width: number): Promise<void> {
  await page.setViewportSize({ width, height: 900 });
}

function setHidden(page: Page, hidden: boolean): Promise<void> {
  return page.evaluate((value) => {
    Object.defineProperty(document, "hidden", { configurable: true, get: () => value });
    document.dispatchEvent(new Event("visibilitychange"));
  }, hidden);
}

test("a stationary view draws at most 2 frames per second", async ({ page }) => {
  await openViewer(page);
  const drawn = await framesOver(page, WINDOW_MS);
  const fps = (drawn * 1000) / WINDOW_MS;
  console.warn(`[perf] 3D view stationary: ${fps.toFixed(2)} fps (${drawn} frames in ${WINDOW_MS} ms)`);
  expect(fps).toBeLessThanOrEqual(MAX_IDLE_FPS);
});

test("a view that is being orbited draws, then settles to idle", async ({ page }) => {
  await openViewer(page);
  const canvas = page.getByTestId("viewer-canvas");
  const box = await canvas.boundingBox();
  if (box === null) throw new Error("the 3D canvas has no measurable area");
  const before = await frames(page);
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 120, box.y + box.height / 2 + 40, { steps: 10 });
  await page.mouse.up();
  await expect.poll(() => frames(page)).toBeGreaterThan(before + 2);
  await expect(page.getByTestId("viewer")).toHaveAttribute("data-state", "idle", { timeout: 10_000 });
  const settled = await framesOver(page, 1000);
  expect(settled).toBeLessThanOrEqual(MAX_IDLE_FPS);
});

test("a hidden page draws 0 frames, and draws again when shown", async ({ page }) => {
  await openViewer(page);
  await setHidden(page, true);
  // let a frame that was already queued land before counting
  await page.waitForTimeout(300);
  const drawn = await framesOver(page, WINDOW_MS, () => nudgeLayout(page, 1200));
  console.warn(`[perf] 3D view hidden page: ${((drawn * 1000) / WINDOW_MS).toFixed(2)} fps (${drawn} frames in ${WINDOW_MS} ms)`);
  expect(drawn).toBe(0);

  const hiddenAt = await frames(page);
  await setHidden(page, false);
  await expect.poll(() => frames(page)).toBeGreaterThan(hiddenAt);
});

test("another dock tab draws 0 frames, and returning draws again", async ({ page }) => {
  await openViewer(page);
  await page.getByRole("tab", { name: "Plots" }).click();
  await page.waitForTimeout(300);
  const drawn = await framesOver(page, WINDOW_MS, () => nudgeLayout(page, 1200));
  console.warn(`[perf] 3D view other dock tab: ${((drawn * 1000) / WINDOW_MS).toFixed(2)} fps (${drawn} frames in ${WINDOW_MS} ms)`);
  expect(drawn).toBe(0);

  const awayAt = await frames(page);
  await page.getByRole("tab", { name: "3D View" }).click();
  await expect(page.getByTestId("viewer")).toBeVisible();
  await expect.poll(() => frames(page)).toBeGreaterThan(awayAt);
  await expect(page.getByTestId("viewer")).toHaveAttribute("data-state", "idle");
});
