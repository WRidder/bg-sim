import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/**
 * W4.3 acceptance (plan 7.9, "At a pause") against the fake worker's debug runs
 * (`backend/src/bgsim_server/fake_debug.py`). The model is the RLC fixture with a scene and a binding of a
 * joint to `Synthetic/counter` (as `bindings-playback.spec.ts`), so the 3D playback bar exists.
 *
 * 1. A watch `Synthetic/sine > 0.5` pauses at t = 0.084: the plot ends at the pause time with the marker
 *    (`data-pause-time`, `data-pause-x` on the chart), the inspect time is the pause time, and the 3D
 *    playback bar shows the pause marker and ends at the pause time. Continue removes the marker.
 * 2. At the pause a parameter edit in live mode (banner) is listed under Edits and the model document is
 *    unchanged (REST document before and after, the field after the resume).
 * 3. After the run ended, "Rewind to here" at an earlier cursor time follows a branch run: paused with reason
 *    time, whose manifest has `parentRun` and `branchAt`.
 *
 * Run with `$env:BGSIM_E2E_PORT="8793"; npx playwright test tests/e2e/debug-pause.spec.ts`.
 */

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "../../..");
const sceneFixture = readFileSync(path.join(here, "..", "fixtures", "scenes", "chain.sdf"), "utf8");

let project = "";

test.beforeEach(async ({ page, request }) => {
  project = `w43-${Date.now()}-${test.info().workerIndex}`;
  await page.setViewportSize({ width: 1700, height: 1000 });
  expect((await request.post("/api/projects", { data: { name: project } })).status()).toBe(201);
  const model = JSON.parse(
    readFileSync(path.join(repoRoot, "contracts", "fixtures", "model", "valid", "model.rlc.iconic.json"), "utf8"),
  ) as Record<string, unknown>;
  model["scene"] = { file: "scenes/chain.sdf" };
  model["bindings"] = [{ target: "joint:j1", property: "position", signal: "Synthetic/counter", gain: 0.1 }];
  expect((await request.put(`/api/projects/${project}/models/Arm`, { data: model })).status()).toBe(200);
  const scene = await request.put(`/api/projects/${project}/scenes/chain.sdf`, {
    data: sceneFixture,
    headers: { "content-type": "application/xml" },
  });
  expect(scene.status()).toBe(200);
});

test.afterEach(async ({ request }) => {
  if (project.length > 0) {
    await request.delete(`/api/projects/${project}`);
    project = "";
  }
});

/** Open the model, run it once so the signals exist, plot the sine and set a watch `sine > 0.5`. */
async function prepare(page: Page): Promise<void> {
  await page.goto(`/?project=${project}&model=Arm`);
  await expect(page.getByTestId("run-button")).toBeEnabled({ timeout: 30_000 });
  await page.keyboard.press("Control+Enter");
  await expect(page.getByTestId("run-status")).toHaveAttribute("data-status", "done", { timeout: 30_000 });

  await page.getByRole("tab", { name: "Signals" }).click();
  const row = page.locator('[data-testid="signal-item"][data-signal-id="Synthetic/sine"]');
  await row.dblclick();
  await row.click({ button: "right" });
  await page.getByTestId("signal-menu").getByTestId("break-when").click();
  await page.getByTestId("break-when-comparison").selectOption(">");
  await page.getByTestId("break-when-value").fill("0.5");
  await page.getByTestId("break-when-add").click();
  await expect(page.getByTestId("break-when-dialog")).toHaveCount(0);
  await page.getByRole("tab", { name: "Plots" }).click();
  await expect(page.locator('[data-testid="plot-chart"] .u-over').first()).toBeVisible();
}

async function debugToPause(page: Page): Promise<void> {
  await page.getByTestId("debug-button").click();
  const status = page.getByTestId("run-status");
  await expect(status).toHaveAttribute("data-status", "paused", { timeout: 20_000 });
  await expect(status).toContainText("Paused at t = 0.0840 s");
}

async function documentJson(request: APIRequestContext): Promise<string> {
  const response = await request.get(`/api/projects/${project}/models/Arm`);
  expect(response.status()).toBe(200);
  return JSON.stringify(await response.json());
}

test("at a pause the plot ends at the pause time with the marker, and so does the 3D playback", async ({
  page,
}) => {
  await prepare(page);
  await debugToPause(page);

  const chart = page.locator('[data-testid="plot-chart"]').first();
  await expect(chart).toHaveAttribute("data-pause-time", /^0\.084/);
  await expect.poll(async () => Number(await chart.getAttribute("data-x-max"))).toBeCloseTo(0.084, 4);
  await expect(chart).toHaveAttribute("data-pause-x", /^\d/);
  await expect(page.getByTestId("plot-pause-badge")).toContainText("paused at t = 0.084 s");
  await expect(page.getByTestId("live-badge")).toHaveCount(0);
  // the plotted series end exactly at the pause row: 85 samples of the 1 ms grid (0 .. 0.084)
  await expect.poll(async () => Number(await chart.getAttribute("data-points"))).toBe(85);

  // the inspect time jumped to the pause time
  await expect(page.getByTestId("plot-inspect-time")).toContainText("0.084 s");

  // the 3D playback bar: pause marker and time, the head ends at the pause time
  await page.getByRole("tab", { name: "3D View" }).click();
  await expect(page.getByTestId("scene-view")).toHaveAttribute("data-state", "loaded", { timeout: 30_000 });
  const bar = page.getByTestId("playback-bar");
  await expect(bar).toHaveAttribute("data-pause-time", "0.084");
  await expect(page.getByTestId("playback-pause-marker")).toBeVisible();
  await expect(page.getByTestId("playback-paused")).toContainText("Paused at 0.084 s");
  await expect.poll(async () => Number(await bar.getAttribute("data-time"))).toBeCloseTo(0.084, 1);
  await expect(page.getByTestId("playback-readout")).toContainText("/ 0.084 s");

  // continue: the marker goes away everywhere and the run finishes
  await page.getByTestId("debug-continue").click();
  await expect(page.getByTestId("run-status")).toHaveAttribute("data-status", "done", { timeout: 30_000 });
  await expect(bar).toHaveAttribute("data-pause-time", "");
  await expect(page.getByTestId("playback-pause-marker")).toHaveCount(0);
  await page.getByRole("tab", { name: "Plots" }).click();
  await expect(chart).not.toHaveAttribute("data-pause-time", /.*/);
  await expect(page.getByTestId("plot-pause-badge")).toHaveCount(0);
});

test("a live parameter edit at the pause is listed under Edits and leaves the model alone", async ({
  page,
  request,
}) => {
  await prepare(page);
  const before = await documentJson(request);
  await debugToPause(page);

  await page.locator('[data-testid="diagram-node"][data-node-name="R1"]').click();
  await expect(page.getByTestId("inspector-node")).toBeVisible();
  const banner = page.getByTestId("inspector-live-banner");
  await expect(banner).toContainText("Live:");
  await expect(banner).toContainText("changes apply to the paused run");

  const r = page.getByTestId("inspector-param-R");
  await expect(r).toHaveAttribute("data-live", "true");
  await r.fill("Rbase * 2");
  await expect(page.getByTestId("inspector-param-R-error")).toContainText("Live edits take a number");

  await r.fill("25");
  await r.press("Enter");
  await expect(page.getByTestId("inspector-param-R-live-value")).toContainText("25");

  await page.getByRole("tab", { name: "Debug" }).click();
  const rows = page.getByTestId("edit-row");
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toHaveAttribute("data-kind", "parameter");
  await expect(rows.first()).toContainText("R1/R = 25");
  await expect(rows.first()).toContainText("at t = 0.0840 s");

  // the model document is unchanged (server copy and the open document), and nothing is left to undo
  await page.waitForTimeout(1500);
  expect(await documentJson(request)).toBe(before);
  const open = JSON.parse((await page.getByTestId("document-json").textContent()) ?? "null") as {
    diagram: { nodes: { name: string; params?: Record<string, string> }[] };
  };
  expect(open.diagram.nodes.find((node) => node.name === "R1")?.params?.R).toBe("10.0");

  // after the resume the inspector is the normal one and shows the model value
  await page.getByTestId("debug-continue").click();
  await expect(page.getByTestId("run-status")).toHaveAttribute("data-status", "done", { timeout: 30_000 });
  await expect(page.getByTestId("inspector-live-banner")).toHaveCount(0);
  await expect(page.getByTestId("inspector-param-R")).toHaveValue("10.0");
  await expect(page.getByTestId("inspector-param-R")).not.toHaveAttribute("data-live", "true");
});

/** Hover the plot at a fraction of its width; returns the inspect time in seconds. */
async function hoverPlot(page: Page, fraction: number): Promise<number> {
  const over = page.locator('[data-testid="plot-chart"] .u-over').first();
  const box = await over.boundingBox();
  if (box === null) throw new Error("the plot has no measurable area");
  await page.mouse.move(box.x + box.width * fraction, box.y + box.height * 0.5, { steps: 4 });
  await expect.poll(async () => inspectTime(page)).toBeGreaterThan(0);
  return inspectTime(page);
}

async function inspectTime(page: Page): Promise<number> {
  const text = (await page.getByTestId("plot-inspect-time").textContent()) ?? "";
  return Number.parseFloat(/=\s*([0-9.eE+-]+)/.exec(text)?.[1] ?? "");
}

test("Rewind to here opens a branch run, paused at the cursor time", async ({ page, request }) => {
  await prepare(page);
  await debugToPause(page);
  await page.getByTestId("debug-continue").click();
  await expect(page.getByTestId("run-status")).toHaveAttribute("data-status", "done", { timeout: 30_000 });
  const parent = (await page.getByTestId("plot-run-status").getAttribute("title")) ?? "";
  expect(parent).toMatch(/\S/);

  const t = await hoverPlot(page, 0.4);
  expect(t).toBeGreaterThan(0.2);
  expect(t).toBeLessThan(0.6);
  const plotBox = await page.locator('[data-testid="plot-chart"] .u-over').first().boundingBox();
  if (plotBox === null) throw new Error("the plot has no measurable area");
  await page.locator('[data-testid="plot-chart"] .u-over').first().click({ button: "right", position: { x: plotBox.width * 0.4, y: 60 } });
  const item = page.getByTestId("plot-rewind");
  await expect(item).toBeEnabled();
  await item.click();

  // the branch run is followed as a paused debug run (reason time)
  const status = page.getByTestId("run-status");
  await expect(status).toHaveAttribute("data-status", "paused", { timeout: 20_000 });
  await expect(status).toContainText("time breakpoint");
  const branch = (await page.getByTestId("plot-run-status").getAttribute("title")) ?? "";
  expect(branch).not.toBe(parent);
  const manifest = (await (await request.get(`/api/runs/${branch}`)).json()) as {
    parentRun?: string;
    branchAt?: number;
    status: string;
  };
  expect(manifest.parentRun).toBe(parent);
  expect(manifest.branchAt).toBeGreaterThan(0.2);
  expect(Math.abs((manifest.branchAt ?? 0) - t)).toBeLessThan(0.02);
  expect(manifest.status).toBe("paused");
  await expect(page.locator('[data-testid="plot-chart"]').first()).toHaveAttribute("data-pause-time", /^0\./);

  // Continue works on the branch run
  await page.getByTestId("debug-continue").click();
  await expect(status).toHaveAttribute("data-status", "done", { timeout: 30_000 });

  // the run's end time is not before the run's current time: the menu item is disabled
  const over = page.locator('[data-testid="plot-chart"] .u-over').first();
  const box = await over.boundingBox();
  if (box === null) throw new Error("the plot has no measurable area");
  await over.click({ button: "right", position: { x: box.width - 1, y: 60 } });
  await expect(page.getByTestId("plot-rewind")).toBeDisabled();
  await expect(page.getByTestId("plot-rewind")).toHaveAttribute("title", /before the run's current time/);
});
