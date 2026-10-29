import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/**
 * W5.3 acceptance (plan 7.6): a model with a scene and a binding of a joint `position` to a signal
 * the fake worker produces (`Synthetic/counter`, floor(t / 0.1) over 0..1 s, gain 0.1 rad per step).
 * After a run, moving the plot cursor moves the joint in the 3D View, playing and scrubbing in the
 * 3D View moves the plot cursor, and the binding table validates (E303) and edits the model.
 *
 * Test hooks (read only): `[data-testid=playback-bar]` carries `data-mode`, `data-playing`,
 * `data-time` (head, s) and `data-applied` (JSON, target -> value the viewer last set after gain
 * and offset); `[data-testid=plot-inspect-time]` is the plot cursor.
 *
 * Run with `$env:BGSIM_E2E_PORT="8776"; npx playwright test tests/e2e/bindings-playback.spec.ts`.
 */

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "../../..");
const sceneFixture = readFileSync(path.join(here, "..", "fixtures", "scenes", "chain.sdf"), "utf8");

let project = "";

test.beforeEach(async ({ page }) => {
  project = `w53-${Date.now()}-${test.info().workerIndex}`;
  await page.setViewportSize({ width: 1600, height: 1000 });
});

test.afterEach(async ({ request }) => {
  if (project.length > 0) await request.delete(`/api/projects/${project}`);
});

async function store(request: APIRequestContext, bindings: unknown[]): Promise<void> {
  expect((await request.post("/api/projects", { data: { name: project } })).status()).toBe(201);
  const model = JSON.parse(
    readFileSync(path.join(repoRoot, "contracts", "fixtures", "model", "valid", "model.rlc.iconic.json"), "utf8"),
  ) as Record<string, unknown>;
  model["scene"] = { file: "scenes/chain.sdf" };
  model["bindings"] = bindings;
  expect((await request.put(`/api/projects/${project}/models/Arm`, { data: model })).status()).toBe(200);
  const put = await request.put(`/api/projects/${project}/scenes/chain.sdf`, {
    data: sceneFixture,
    headers: { "content-type": "application/xml" },
  });
  expect(put.status()).toBe(200);
}

const COUNTER_BINDING = { target: "joint:j1", property: "position", signal: "Synthetic/counter", gain: 0.1 };

async function openAndRun(page: Page): Promise<void> {
  await page.goto(`/?project=${project}&model=Arm`);
  await expect(page.getByTestId("run-button")).toBeEnabled({ timeout: 30_000 });
  await page.keyboard.press("Control+Enter");
  await expect(page.getByTestId("run-status")).toHaveAttribute("data-status", "done", { timeout: 30_000 });
}

async function plotCounter(page: Page): Promise<void> {
  await page.getByRole("tab", { name: "Signals" }).click();
  await page.locator('[data-signal-id="Synthetic/counter"]').dblclick();
  await page.getByRole("tab", { name: "Plots" }).click();
  await expect(page.locator('[data-testid="plot-chart"] .u-over').first()).toBeVisible();
}

/** Hover the plot at a fraction of its width; returns the inspect time in seconds. */
async function hoverPlot(page: Page, fraction: number): Promise<number> {
  const over = page.locator('[data-testid="plot-chart"] .u-over').first();
  const box = await over.boundingBox();
  if (box === null) throw new Error("the plot has no measurable area");
  await page.mouse.move(box.x + box.width * fraction, box.y + box.height * 0.5, { steps: 4 });
  await expect.poll(async () => inspectTime(page)).toBeGreaterThan(0);
  return inspectTime(page);
}

/** The plot cursor (global inspect time) in seconds, NaN while it has none. */
async function inspectTime(page: Page): Promise<number> {
  const text = (await page.getByTestId("plot-inspect-time").textContent()) ?? "";
  return Number.parseFloat(/=\s*([0-9.eE+-]+)/.exec(text)?.[1] ?? "");
}

async function openViewer(page: Page): Promise<void> {
  await page.getByRole("tab", { name: "3D View" }).click();
  await expect(page.getByTestId("scene-view")).toHaveAttribute("data-state", "loaded", { timeout: 30_000 });
  await expect(page.getByTestId("playback-bar")).toHaveAttribute("data-mode", "playback", { timeout: 30_000 });
}

async function applied(page: Page, target = "joint:j1"): Promise<number | undefined> {
  const raw = await page.getByTestId("playback-bar").getAttribute("data-applied");
  return (JSON.parse(raw ?? "{}") as Record<string, number>)[target];
}

async function barTime(page: Page): Promise<number> {
  return Number(await page.getByTestId("playback-bar").getAttribute("data-time"));
}

test("the plot cursor drives the joint in 3D, and playing in 3D drives the plot cursor", async ({ page, request }) => {
  await store(request, [COUNTER_BINDING]);
  await openAndRun(page);
  await plotCounter(page);

  const t1 = await hoverPlot(page, 0.55);
  await openViewer(page);
  await expect.poll(() => applied(page)).toBeCloseTo(Math.floor(t1 / 0.1 + 1e-9) * 0.1, 6);
  expect(await barTime(page)).toBeCloseTo(t1, 2);

  await page.getByRole("tab", { name: "Plots" }).click();
  const t2 = await hoverPlot(page, 0.95);
  expect(t2).toBeGreaterThan(t1);
  await page.getByRole("tab", { name: "3D View" }).click();
  await expect.poll(() => applied(page)).toBeCloseTo(Math.floor(t2 / 0.1 + 1e-9) * 0.1, 6);
  expect(Math.floor(t2 / 0.1 + 1e-9) * 0.1).toBeGreaterThan(Math.floor(t1 / 0.1 + 1e-9) * 0.1);

  // scrubbing the 3D time slider moves the joint and the plot cursor
  const slider = page.getByTestId("playback-time");
  await slider.fill("0.25");
  await expect.poll(() => applied(page)).toBeCloseTo(0.2, 6);
  await page.getByRole("tab", { name: "Plots" }).click();
  await expect.poll(async () => inspectTime(page)).toBeCloseTo(0.25, 2);

  // play and pause through the bar
  await page.getByRole("tab", { name: "3D View" }).click();
  const bar = page.getByTestId("playback-bar");
  await page.getByTestId("playback-rewind").click();
  await expect.poll(() => barTime(page)).toBe(0);
  await page.getByTestId("playback-speed").selectOption("0.25");
  await page.getByTestId("playback-toggle").click();
  await expect(bar).toHaveAttribute("data-playing", "true");
  await expect.poll(() => barTime(page)).toBeGreaterThan(0.05);
  await page.getByTestId("playback-toggle").click();
  await expect(bar).toHaveAttribute("data-playing", "false");
  const held = await barTime(page);
  await page.waitForTimeout(300);
  expect(await barTime(page)).toBe(held);
  expect(await applied(page)).toBeCloseTo(Math.floor(held / 0.1 + 1e-9) * 0.1, 6);

  // the plot cursor stopped where the 3D head stopped
  await page.getByRole("tab", { name: "Plots" }).click();
  await expect.poll(async () => inspectTime(page)).toBeCloseTo(held, 2);
});

test("space toggles playback while the 3D view has focus, and the run plays through to the end", async ({ page, request }) => {
  await store(request, [COUNTER_BINDING]);
  await openAndRun(page);
  await openViewer(page);
  const bar = page.getByTestId("playback-bar");
  await page.getByTestId("playback-speed").selectOption("4");
  await page.getByTestId("scene-stage").focus();
  await page.keyboard.press("Space");
  await expect(bar).toHaveAttribute("data-playing", "true");
  await expect(bar).toHaveAttribute("data-playing", "false", { timeout: 10_000 }); // 1 s at 4x
  expect(await barTime(page)).toBeCloseTo(1, 3);
  expect(await applied(page)).toBeCloseTo(1.0, 6);
});

test("the binding table reports E303 and edits the model", async ({ page, request }) => {
  await store(request, [COUNTER_BINDING, { target: "joint:j2", property: "position", signal: "Synthetic/sine" }]);
  await openAndRun(page);
  await openViewer(page);

  await page.getByTestId("bindings-toggle").click();
  await expect(page.getByTestId("bindings-editor")).toBeVisible();
  await expect(page.getByTestId("binding-row-0")).not.toHaveAttribute("data-invalid", "true");
  await expect(page.getByTestId("binding-row-1")).toHaveAttribute("data-invalid", "true");
  await expect(page.getByTestId("binding-problem-1")).toContainText("E303");
  await expect(page.getByTestId("binding-problem-1")).toContainText("Synthetic/sine");

  await page.getByRole("tab", { name: /^Diagnostics/ }).click();
  await expect(page.getByTestId("diagnostics-panel")).toContainText("E303");
  await page.getByRole("tab", { name: "3D View" }).click();

  // gain 0.1 -> 0.2 doubles the angle at the held time
  await page.getByTestId("playback-time").fill("0.55");
  await expect.poll(() => applied(page)).toBeCloseTo(0.5, 6);
  const gain = page.getByTestId("binding-gain-0");
  await gain.fill("0.2");
  await gain.press("Enter");
  await expect.poll(() => applied(page)).toBeCloseTo(1.0, 6);

  // adding a binding through the form
  await page.getByTestId("add-property").selectOption("scale.z");
  await page.getByTestId("add-target").selectOption("visual:l2_visual");
  await page.getByTestId("add-signal-0").selectOption({ label: "Synthetic/step [V]" });
  await page.getByTestId("add-binding").click();
  await expect(page.getByTestId("binding-row-2")).toBeVisible();
  await expect(page.getByTestId("binding-property-2")).toHaveText("scale.z");
  await page.getByTestId("binding-remove-2").click();
  await expect(page.getByTestId("binding-row-2")).toHaveCount(0);
});

test("an unknown target is reported as E301 and does not stop the other bindings", async ({ page, request }) => {
  await store(request, [{ target: "joint:elbow", property: "position", signal: "Synthetic/counter" }, COUNTER_BINDING]);
  await openAndRun(page);
  await openViewer(page);
  await page.getByTestId("playback-time").fill("0.35");
  await expect.poll(() => applied(page)).toBeCloseTo(0.3, 6);
  await page.getByRole("tab", { name: /^Diagnostics/ }).click();
  await expect(page.getByTestId("diagnostics-panel")).toContainText("E301");
  await expect(page.getByTestId("diagnostics-panel")).toContainText("joint:elbow");
});
