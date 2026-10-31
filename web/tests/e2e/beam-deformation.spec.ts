import { mkdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import AxeBuilder from "@axe-core/playwright";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/**
 * Elastic beams in the 3D View: deformation bindings bend and twist a box and a cylinder from modal
 * coordinates. The FlexibleBeam blocks are not needed: the fake worker's `Synthetic/counter`
 * (floor(t / 0.1), no unit) stands in for every modal coordinate, scaled by the binding gains. The box
 * bends in y and twists (striped), the cylinder bends in z over two free-free modes and is coloured by
 * its bending strain. The exaggeration chip sits in the view, is stored per model and is shared with
 * the detached window and full screen.
 *
 * Screenshots land in test-results/ (and in $BGSIM_SHOT_DIR when set).
 * Run with `$env:BGSIM_E2E_PORT="8781"; npx playwright test tests/e2e/beam-deformation.spec.ts`.
 */

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "../../..");
const sceneFixture = readFileSync(path.join(here, "..", "fixtures", "scenes", "beam.sdf"), "utf8");
const shotDirs = ["test-results", ...(process.env["BGSIM_SHOT_DIR"] ? [process.env["BGSIM_SHOT_DIR"]] : [])];

const C = "Synthetic/counter";
const BINDINGS = [
  { target: "visual:beam_box", property: "deformation", family: "bending-y", basis: "clamped-free", beam: { axis: "+x" }, signal: [C], gain: 1.5e-4 },
  { target: "visual:beam_box", property: "deformation", family: "torsion", basis: "clamped-free", beam: { axis: "+x" }, signal: [C], gain: 2e-3 },
  {
    target: "visual:rod",
    property: "deformation",
    family: "bending-z",
    basis: "free-free",
    beam: { axis: "+z" },
    signal: [C, C],
    gain: 5e-5,
    strain: { colormap: "heat", range: [0, 0.0015] },
  },
];

let project = "";

test.beforeEach(async ({ page }) => {
  project = `beam-${Date.now()}-${test.info().workerIndex}`;
  await page.setViewportSize({ width: 1600, height: 1000 });
});

test.afterEach(async ({ request }) => {
  if (project.length > 0) await request.delete(`/api/projects/${project}`);
});

async function store(request: APIRequestContext): Promise<void> {
  expect((await request.post("/api/projects", { data: { name: project } })).status()).toBe(201);
  const model = JSON.parse(
    readFileSync(path.join(repoRoot, "contracts", "fixtures", "model", "valid", "model.rlc.iconic.json"), "utf8"),
  ) as Record<string, unknown>;
  model["scene"] = { file: "scenes/beam.sdf" };
  model["bindings"] = BINDINGS;
  expect((await request.put(`/api/projects/${project}/models/Beam`, { data: model })).status()).toBe(200);
  const put = await request.put(`/api/projects/${project}/scenes/beam.sdf`, { data: sceneFixture, headers: { "content-type": "application/xml" } });
  expect(put.status()).toBe(200);
}

async function openAndRun(page: Page): Promise<void> {
  await page.goto(`/?project=${project}&model=Beam`);
  await expect(page.getByTestId("run-button")).toBeEnabled({ timeout: 30_000 });
  await page.keyboard.press("Control+Enter");
  await expect(page.getByTestId("run-status")).toHaveAttribute("data-status", "done", { timeout: 30_000 });
}

async function applied(page: Page, key: string): Promise<number | undefined> {
  const raw = await page.getByTestId("playback-bar").getAttribute("data-applied");
  return (JSON.parse(raw ?? "{}") as Record<string, number>)[key];
}

/** The view after it has drawn the current state (on-demand rendering: wait for an idle frame). */
async function settle(page: Page): Promise<void> {
  await expect(page.getByTestId("viewer")).toHaveAttribute("data-state", "idle", { timeout: 10_000 });
  await page.waitForTimeout(150);
}

/** A screenshot of the page (the full-screen view), also saved under `name`. */
async function shoot(page: Page, name: string): Promise<Buffer> {
  const shot = await page.screenshot();
  for (const dir of shotDirs) {
    mkdirSync(dir, { recursive: true });
    await page.screenshot({ path: path.join(dir, name) });
  }
  return shot;
}

test("modal coordinates bend and twist the beams, exaggerated in the view", async ({ page, request }) => {
  await store(request);
  await openAndRun(page);
  await page.getByRole("tab", { name: "3D View" }).click();
  await expect(page.getByTestId("scene-view")).toHaveAttribute("data-state", "loaded", { timeout: 30_000 });
  await expect(page.getByTestId("playback-bar")).toHaveAttribute("data-mode", "playback", { timeout: 30_000 });

  // the chip is in the view, at true scale until asked
  const badge = page.getByTestId("deformation-badge");
  await expect(badge).toHaveAttribute("data-factor", "1");
  await expect(badge).toContainText("true scale");
  // no binding problems: the counter has no unit, the shapes are a box and a cylinder along its axis
  await page.getByTestId("bindings-toggle").click();
  for (const row of [0, 1, 2]) await expect(page.getByTestId(`binding-row-${String(row)}`)).not.toHaveAttribute("data-invalid", "true");
  await page.getByTestId("bindings-toggle").click();

  // a fixed time: counter = 9
  await page.getByTestId("playback-time").fill("0.95");
  await expect.poll(() => applied(page, "visual:beam_box#bending-y")).toBeCloseTo(9 * 1.5e-4, 9);
  await expect.poll(() => applied(page, "visual:beam_box#torsion")).toBeCloseTo(18e-3, 9);
  await expect.poll(() => applied(page, "visual:rod#bending-z")).toBeCloseTo(4.5e-4, 9);
  // full screen, framed: the chip stays in the view
  await page.getByTestId("viewer-fullscreen").click();
  await expect(page.getByTestId("viewer-fullscreen")).toHaveAttribute("aria-pressed", "true");
  await expect(badge).toBeVisible();
  await page.getByTestId("viewer-preset-iso").click();
  await page.getByTestId("viewer-fit").click();
  await settle(page);
  const trueScale = await shoot(page, "beam-deformation-x1.png");

  await page.getByTestId("deformation-exaggeration").selectOption("100");
  await expect(badge).toHaveAttribute("data-exaggerated", "true");
  await expect(badge).toContainText("exaggerated");
  await expect(badge).toHaveAttribute("data-factor", "100");
  await settle(page);
  const exaggerated = await shoot(page, "beam-deformation-x100.png");
  expect(exaggerated.equals(trueScale)).toBe(false);

  // the light theme
  await page.evaluate(() => {
    document.documentElement.dataset["theme"] = "light";
  });
  await settle(page);
  await shoot(page, "beam-deformation-x100-light.png");
  // looking down the beams from their free ends: the twisted box section and the stripes
  await page.getByTestId("viewer-preset-front").click();
  await settle(page);
  await shoot(page, "beam-deformation-x100-front.png");

  await page.getByTestId("viewer-fullscreen").click();
  await expect(page.getByTestId("viewer-fullscreen")).toHaveAttribute("aria-pressed", "false");

  // stored per model: a reload keeps ×100
  await page.reload();
  await page.getByRole("tab", { name: "3D View" }).click();
  await expect(page.getByTestId("scene-view")).toHaveAttribute("data-state", "loaded", { timeout: 30_000 });
  await expect(page.getByTestId("deformation-badge")).toHaveAttribute("data-factor", "100");
});

test("the exaggeration chip and the deformation rows of the binding table are axe-clean", async ({ page, request }) => {
  await store(request);
  await openAndRun(page);
  await page.getByRole("tab", { name: "3D View" }).click();
  await expect(page.getByTestId("scene-view")).toHaveAttribute("data-state", "loaded", { timeout: 30_000 });
  await page.getByTestId("deformation-exaggeration").selectOption("10");
  await page.getByTestId("bindings-toggle").click();
  await page.getByTestId("add-property").selectOption("deformation");
  await page.getByTestId("binding-strain-0").check();
  for (const theme of ["light", "dark"] as const) {
    await page.evaluate((t) => {
      document.documentElement.dataset["theme"] = t;
    }, theme);
    const result = await new AxeBuilder({ page }).include('[data-testid="scene-view"]').analyze();
    const serious = result.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
    expect.soft(serious, `axe violations (${theme})`).toEqual([]);
  }
  for (const dir of shotDirs) {
    mkdirSync(dir, { recursive: true });
    await page.getByTestId("scene-view").screenshot({ path: path.join(dir, "beam-deformation-bindings.png") });
  }
});

test("the detached window shows and sets the same exaggeration", async ({ page, request }) => {
  await store(request);
  await openAndRun(page);
  await page.getByRole("tab", { name: "3D View" }).click();
  await expect(page.getByTestId("scene-view")).toHaveAttribute("data-state", "loaded", { timeout: 30_000 });
  await page.getByTestId("deformation-exaggeration").selectOption("1000");

  const popupPromise = page.waitForEvent("popup");
  await page.getByTestId("detach-viewer").click();
  const popup = await popupPromise;
  await expect(popup.getByTestId("scene-view")).toHaveAttribute("data-state", "loaded", { timeout: 30_000 });
  await expect(popup.getByTestId("playback-bar")).toHaveAttribute("data-mode", "playback", { timeout: 30_000 });
  await expect(popup.getByTestId("deformation-badge")).toHaveAttribute("data-factor", "1000");
  await popup.getByTestId("playback-time").fill("0.95");
  await expect.poll(() => applied(popup, "visual:rod#bending-z")).toBeCloseTo(4.5e-4, 9);
  await popup.getByTestId("deformation-exaggeration").selectOption("10");
  await expect(popup.getByTestId("deformation-badge")).toHaveAttribute("data-factor", "10");
  await expect(popup.getByTestId("viewer")).toHaveAttribute("data-state", "idle", { timeout: 10_000 });
  await popup.waitForTimeout(150);
  for (const dir of shotDirs) {
    mkdirSync(dir, { recursive: true });
    await popup.getByTestId("scene-view").screenshot({ path: path.join(dir, "beam-deformation-popup-x10.png") });
  }

  await popup.close();
  await expect(page.getByTestId("scene-view")).toHaveAttribute("data-state", "loaded", { timeout: 30_000 });
  await expect(page.getByTestId("deformation-badge")).toHaveAttribute("data-factor", "10");
});
