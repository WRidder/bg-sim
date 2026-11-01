import { mkdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import AxeBuilder from "@axe-core/playwright";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/**
 * XY plots (one signal against another): a dock panel switches its x axis from time to a signal
 * and back, a saved model plot with `x` opens as an XY panel, and a dashboard plot card draws
 * against its `x` and sets it in the card editor. Fake worker (the synthetic run: a 1 Hz sine,
 * a step, a counter and a flag, 1001 rows).
 *
 * Run with `$env:BGSIM_E2E_PORT="8791"; npx playwright test tests/e2e/plot-xy.spec.ts`. With
 * BGSIM_SCREENSHOT_DIR set it also writes xy-panel.png and xy-dashboard.png there.
 */

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "../../..");
const shots = process.env.BGSIM_SCREENSHOT_DIR ?? "";

let project = "";

test.beforeEach(async ({ page }) => {
  project = `plot-xy-${Date.now()}-${test.info().workerIndex}`;
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.emulateMedia({ reducedMotion: "reduce" });
});

test.afterEach(async ({ request }) => {
  if (project.length > 0) await request.delete(`/api/projects/${project}`);
});

function rlc(): Record<string, unknown> {
  return JSON.parse(
    readFileSync(path.join(repoRoot, "contracts", "fixtures", "model", "valid", "model.rlc.iconic.json"), "utf8"),
  ) as Record<string, unknown>;
}

async function store(request: APIRequestContext, model: Record<string, unknown>): Promise<void> {
  expect((await request.post("/api/projects", { data: { name: project } })).status()).toBe(201);
  expect((await request.put(`/api/projects/${project}/models/Rlc`, { data: model })).status()).toBe(200);
}

async function openAndRun(page: Page): Promise<void> {
  await page.goto(`/?project=${project}&model=Rlc`);
  await expect(page.getByTestId("run-button")).toBeEnabled({ timeout: 30_000 });
  await page.getByTestId("run-button").click();
  await expect(page.getByTestId("run-status")).toHaveAttribute("data-status", "done", { timeout: 30_000 });
}

async function addFromBrowser(page: Page, id: string): Promise<void> {
  await page.getByRole("tab", { name: "Signals" }).click();
  await expect(page.getByTestId("signal-browser")).toBeVisible();
  await page.locator(`[data-signal-id="${id}"]`).dblclick();
}

async function seriousViolations(page: Page, selector: string): Promise<string[]> {
  const result = await new AxeBuilder({ page }).include(selector).analyze();
  return result.violations
    .filter((violation) => violation.impact === "serious" || violation.impact === "critical")
    .map((violation) => `${violation.id}: ${violation.help} — ${violation.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

test("a panel switches its x axis to a signal and back, marks the inspect time and is axe-clean", async ({
  page,
  request,
}) => {
  await store(request, rlc());
  await page.addInitScript(() => {
    // A tall dock: the XY panel (240 px plus its legend) fits without scrolling.
    localStorage.setItem("bgsim.layout.rows", JSON.stringify({ main: 45, dock: 55 }));
  });
  await openAndRun(page);
  await addFromBrowser(page, "Synthetic/sine");
  await addFromBrowser(page, "Synthetic/counter");
  await page.getByRole("tab", { name: "Plots" }).click();

  const chart = page.getByTestId("plot-chart").first();
  await expect(chart).toHaveAttribute("data-series-count", "2");
  await expect(chart).not.toHaveAttribute("data-mode", "xy");

  // The panel header's x control (a native select: keyboard accessible).
  const xAxis = page.getByTestId("plot-panel-x-1");
  await expect(xAxis).toHaveAccessibleName("X axis of Panel 1");
  await xAxis.selectOption("Synthetic/sine");
  await expect(chart).toHaveAttribute("data-mode", "xy");
  await expect(chart).toHaveAttribute("data-x-signal", "Synthetic/sine");
  // The x signal leaves the y list: counter against sine.
  await expect(chart).toHaveAttribute("data-series-count", "1");
  await expect(chart).toHaveAttribute("data-points", "1001");
  await expect.poll(async () => Number(await chart.getAttribute("data-drawn-points"))).toBeGreaterThan(20);
  await expect(page.getByTestId("legend-x")).toHaveAttribute("data-signal-id", "Synthetic/sine");
  await expect(page.getByTestId("legend-item")).toHaveCount(1);
  await expect(page.locator(".plot-chart-panel .u-axis").first()).toBeVisible();

  // No inspect time yet: the marker sits on the newest sample (t = 1 s).
  await expect.poll(async () => chart.getAttribute("data-marker-t")).toBe("1");
  // Hover: the nearest drawn sample becomes the global inspect time, legend and marker follow.
  const over = chart.locator(".u-over");
  const box = await over.boundingBox();
  if (box === null) throw new Error("the XY plot has no measurable area");
  await page.mouse.move(box.x + box.width * 0.85, box.y + box.height * 0.5);
  const inspect = page.getByTestId("plot-inspect-time");
  await expect.poll(async () => inspect.textContent()).toMatch(/inspect t = [\d.]+/);
  const markerT = Number(await chart.getAttribute("data-marker-t"));
  expect(markerT).toBeGreaterThanOrEqual(0);
  expect(markerT).toBeLessThan(1);
  await expect(page.getByTestId("legend-time").first()).toHaveText(/t = [\d.]+ (m)?s/);
  await expect(chart.locator('[data-testid="xy-marker"]')).toBeVisible();

  if (shots.length > 0) {
    mkdirSync(shots, { recursive: true });
    await page.getByTestId("plot-chart-panel").first().screenshot({ path: path.join(shots, "xy-panel.png") });
  }

  // Equal aspect.
  const aspect = page.getByTestId("plot-panel-x-1-aspect");
  await expect(aspect).toHaveAttribute("aria-pressed", "false");
  await aspect.focus();
  await page.keyboard.press("Enter");
  await expect(aspect).toHaveAttribute("aria-pressed", "true");
  await expect(chart).toHaveAttribute("data-equal-aspect", "true");

  expect(await seriousViolations(page, '[data-testid="plot-panel"]')).toEqual([]);

  // Back to time: the x signal returns to the front of the y list.
  await xAxis.selectOption("");
  await expect(chart).not.toHaveAttribute("data-mode", "xy");
  await expect(chart).toHaveAttribute("data-series-count", "2");
  await expect(page.getByTestId("legend-item").first()).toHaveAttribute("data-signal-id", "Synthetic/sine");
});

test("a saved model plot with x opens as an XY panel", async ({ page, request }) => {
  const model = rlc();
  model.plots = [
    { id: "p1", title: "Counter against sine", signals: ["Synthetic/counter"], x: "Synthetic/sine", equalAspect: true },
    { id: "p2", title: "Sine", signals: ["Synthetic/sine"] },
  ];
  await store(request, model);
  await openAndRun(page);
  await page.getByRole("tab", { name: "Plots" }).click();
  const saved = page.getByTestId("saved-plot-select");
  await expect(saved.locator("option")).toHaveCount(3);
  await saved.selectOption("p1");
  const panel = page.getByTestId("plot-chart-panel").last();
  await expect(panel.getByTestId("plot-chart")).toHaveAttribute("data-mode", "xy");
  await expect(panel.getByTestId("plot-chart")).toHaveAttribute("data-x-signal", "Synthetic/sine");
  await expect(panel.getByTestId("plot-chart")).toHaveAttribute("data-equal-aspect", "true");
  await expect(panel.locator(".plot-chart__title")).toHaveValue("Counter against sine");
  await saved.selectOption("p2");
  await expect(page.getByTestId("plot-chart-panel")).toHaveCount(2);
  await expect(page.getByTestId("plot-chart-panel").last().getByTestId("plot-chart")).not.toHaveAttribute(
    "data-mode",
    "xy",
  );
});

test("a dashboard plot card draws against its x and sets it in the card editor", async ({ page, request }) => {
  const model = rlc();
  model.dashboard = {
    cards: [
      { id: "xy", kind: "plot", size: "2x2", title: "Counter against sine", signals: ["Synthetic/counter"], x: "Synthetic/sine" },
      { id: "time", kind: "plot", size: "2x2", title: "Against time", signals: ["Synthetic/sine", "Synthetic/step"] },
    ],
  };
  await store(request, model);
  await page.addInitScript(() => {
    localStorage.setItem("bgsim.layout.rows", JSON.stringify({ main: 80, dock: 20 }));
  });
  await page.goto(`/?project=${project}&model=Rlc`);
  await expect(page.getByTestId("run-button")).toBeEnabled({ timeout: 30_000 });
  await page.getByRole("tab", { name: "Dashboard" }).click();
  await expect(page.getByTestId("dashboard")).toBeVisible();
  await page.getByTestId("run-button").click();
  await expect(page.getByTestId("run-status")).toHaveAttribute("data-status", "done", { timeout: 30_000 });

  const xy = page.getByTestId("dash-plot-xy").getByTestId("plot-chart");
  await expect(xy).toHaveAttribute("data-mode", "xy");
  await expect(xy).toHaveAttribute("data-x-signal", "Synthetic/sine");
  await expect(xy).toHaveAttribute("data-series-count", "1");
  await expect(xy).toHaveAttribute("data-points", "1001");
  await expect(page.getByTestId("dash-plot-time").getByTestId("plot-chart")).not.toHaveAttribute("data-mode", "xy");
  expect(await seriousViolations(page, '[data-testid="dashboard"]')).toEqual([]);
  if (shots.length > 0) {
    mkdirSync(shots, { recursive: true });
    await page.getByTestId("dashboard").screenshot({ path: path.join(shots, "xy-dashboard.png") });
  }

  // The card editor: the second card becomes XY (step against sine), with equal aspect.
  await page.getByTestId("dash-edit-toggle").click();
  await page.getByTestId("dash-card-settings-time").click();
  await expect(page.getByTestId("dash-settings")).toBeVisible();
  const equal = page.getByTestId("dash-settings-equal-aspect");
  await expect(equal).toBeDisabled();
  await page.getByTestId("dash-settings-x").selectOption("Synthetic/sine");
  await expect(equal).toBeEnabled();
  await equal.check();
  const settingsAxe = await seriousViolations(page, '[data-testid="dash-settings"]');
  expect(settingsAxe).toEqual([]);
  await page.getByRole("button", { name: "Close the settings" }).click();
  const second = page.getByTestId("dash-plot-time").getByTestId("plot-chart");
  await expect(second).toHaveAttribute("data-mode", "xy");
  await expect(second).toHaveAttribute("data-series-count", "1");
  await expect(second).toHaveAttribute("data-equal-aspect", "true");
});
