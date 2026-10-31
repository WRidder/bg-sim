import { mkdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import AxeBuilder from "@axe-core/playwright";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/**
 * The Dashboard tab (plan/DASHBOARD_PLAN.md) against the fake worker:
 *
 * 1. in edit mode a Value, a Slider and a Schedule card are added and bound through their
 *    settings; the run request then carries the slider's `parameterOverrides` and the table's
 *    `parameterSchedule`, the manifest records them, the value card shows a number and the
 *    inspector shows the "dashboard:" badge on the overridden parameter;
 * 2. a full dashboard (gauge, value, plot, bar, indicator, slider, knob, schedule) renders after a
 *    run and is axe-clean in use and edit mode, in both themes. With BGSIM_DASHBOARD_SHOTS set to
 *    a folder, it also writes the screenshots dashboard-<mode>-<theme>.png there.
 *
 * Run with `$env:BGSIM_E2E_PORT="8779"; npx playwright test tests/e2e/dashboard.spec.ts`.
 */

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "../../..");
const shots = process.env.BGSIM_DASHBOARD_SHOTS ?? "";

let project = "";

test.beforeEach(async ({ page }) => {
  project = `dashboard-${Date.now()}-${test.info().workerIndex}`;
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

async function openDashboard(page: Page): Promise<void> {
  await page.goto(`/?project=${project}&model=Rlc`);
  await expect(page.getByTestId("run-button")).toBeEnabled({ timeout: 30_000 });
  await page.getByRole("tab", { name: "Dashboard" }).click();
  await expect(page.getByTestId("dashboard")).toBeVisible();
}

async function closeSettings(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Close the settings" }).click();
  await expect(page.getByTestId("dash-settings")).toBeHidden();
}

async function seriousViolations(page: Page): Promise<string[]> {
  const result = await new AxeBuilder({ page }).include('[data-testid="dashboard"]').analyze();
  return result.violations
    .filter((violation) => violation.impact === "serious" || violation.impact === "critical")
    .map(
      (violation) =>
        `${violation.id}: ${violation.help} — ` +
        violation.nodes
          .slice(0, 3)
          .map((node) => node.target.join(" "))
          .join(", "),
    );
}

test("value, slider and schedule cards: the run carries the overrides and the schedule", async ({
  page,
  request,
}) => {
  test.setTimeout(120_000);
  await store(request, rlc());
  await openDashboard(page);
  await expect(page.getByText("No cards yet")).toBeVisible();

  await page.getByTestId("dash-edit-toggle").click();

  // A Value card bound to a signal id (no run yet, so it is typed).
  await page.getByTestId("dash-add-card").click();
  await page.getByTestId("dash-add-value").click();
  const settings = page.getByTestId("dash-settings");
  await expect(settings).toBeVisible();
  await settings.getByLabel("Search signals").fill("Synthetic/sine");
  await settings.getByLabel("Search signals").press("Enter");
  await closeSettings(page);

  // A Slider bound to R1/R, with a range.
  await page.getByTestId("dash-add-card").click();
  await page.getByTestId("dash-add-slider").click();
  await settings.getByLabel("Search parameters").fill("R1/");
  await settings.getByRole("option", { name: /R1\/R/ }).click();
  await settings.getByLabel("Min", { exact: true }).fill("0");
  await settings.getByLabel("Min", { exact: true }).press("Enter");
  await settings.getByLabel("Max", { exact: true }).fill("50");
  await settings.getByLabel("Max", { exact: true }).press("Enter");
  await settings.getByLabel("Step", { exact: true }).fill("0.5");
  await settings.getByLabel("Step", { exact: true }).press("Enter");
  await closeSettings(page);
  const slider = page.getByTestId("dash-slider-card-2");
  await slider.focus();
  for (let i = 0; i < 5; i += 1) await slider.press("ArrowRight");
  await expect(slider).toHaveValue("12.5");

  // A Schedule table: V1/V steps from 1 to 2 at t = 0.005 s.
  await page.getByTestId("dash-add-card").click();
  await page.getByTestId("dash-add-schedule").click();
  await closeSettings(page);
  await page.getByTestId("dash-schedule-card-3-add-column").selectOption("V1/V");
  await page.getByTestId("dash-schedule-card-3-add-row").click();
  await page.getByTestId("dash-schedule-card-3-add-row").click();
  const t1 = page.getByTestId("dash-schedule-card-3-t-1");
  await t1.fill("0.005");
  await t1.press("Enter");
  const v1 = page.getByTestId("dash-schedule-card-3-v-1-0");
  await v1.fill("2");
  await v1.press("Enter");
  await expect(page.getByTestId("dash-summary")).toHaveText(/1 parameter override, 2 scheduled changes/);

  await page.getByTestId("dash-edit-toggle").click();
  expect(await seriousViolations(page)).toEqual([]);

  const post = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" && /\/api\/projects\/[^/]+\/runs$/.test(response.url()),
  );
  await page.getByTestId("run-button").click();
  const response = await post;
  const body = response.request().postDataJSON() as Record<string, unknown>;
  const { runId } = (await response.json()) as { runId: string };
  expect(body.parameterOverrides).toEqual([{ target: "R1/R", value: 12.5 }]);
  expect(body.parameterSchedule).toEqual([
    { t: 0, target: "V1/V", value: 1 },
    { t: 0.005, target: "V1/V", value: 2 },
  ]);

  const runStatus = page.getByTestId("run-status");
  await expect(runStatus).toHaveAttribute("data-status", "done", { timeout: 30_000 });
  await expect(page.getByTestId("dash-value-card-1")).toHaveText(/^-?\d/, { timeout: 10_000 });

  // The manifest says what the run used.
  const manifest = (await (await request.get(`/api/runs/${runId}`)).json()) as Record<string, unknown>;
  expect(manifest.parameterOverrides).toEqual([{ target: "R1/R", value: 12.5 }]);
  expect(manifest.parameterSchedule).toEqual(body.parameterSchedule);

  // The inspector marks the overridden parameter; the model value is unchanged.
  await page.getByRole("tab", { name: "Diagram" }).click();
  await page.getByTestId("diagram-node").filter({ hasText: "R1" }).first().click();
  await expect(page.getByTestId("dashboard-override-R1/R")).toHaveText("dashboard: 12.5");
});

const FULL_DASHBOARD = {
  cards: [
    { id: "gauge", kind: "gauge", size: "2x2", title: "Sine", signals: ["Synthetic/sine"], options: { min: -1, max: 1, decimals: 2, zones: [{ from: 0.6, to: 1, tone: "warn" }, { from: -1, to: -0.6, tone: "info" }] } },
    { id: "value", kind: "value", size: "1x1", title: "Step", signals: ["Synthetic/step"], options: { decimals: 2, sparkline: true } },
    { id: "bar", kind: "bar", size: "1x2", title: "Counter", signals: ["Synthetic/counter"], options: { min: 0, max: 10 } },
    { id: "plot", kind: "plot", size: "4x2", title: "Sine and step", signals: ["Synthetic/sine", "Synthetic/step"] },
    { id: "led", kind: "indicator", size: "1x1", title: "Flag", signals: ["Synthetic/flag"], options: { threshold: 0.5 } },
    { id: "slider", kind: "slider", size: "2x1", title: "Resistance", parameter: "R1/R", value: 12.5, options: { min: 0, max: 50, step: 0.5 } },
    { id: "knob", kind: "knob", size: "1x1", title: "Inductance", parameter: "L1/L", value: 0.02, options: { min: 0.001, max: 0.1, step: 0.001, decimals: 3 } },
    { id: "sched", kind: "schedule", size: "2x2", title: "Supply", schedule: { parameters: ["V1/V"], rows: [{ t: 0, values: [1] }, { t: 0.004, values: [2] }, { t: 0.008, values: [0.5] }] } },
    { id: "note", kind: "text", size: "2x1", options: { text: "**Series RLC** — slide *R* and re-run.", markdown: true } },
  ],
};

for (const theme of ["dark", "light"] as const) {
  test(`a full dashboard renders after a run and is axe-clean (${theme})`, async ({ page, request }) => {
    test.setTimeout(120_000);
    const model = rlc();
    model.dashboard = FULL_DASHBOARD;
    await store(request, model);
    await page.addInitScript((value) => {
      localStorage.setItem("bgsim.theme", value);
      // Room for the whole dashboard: a short bottom dock and no side panels in the way.
      localStorage.setItem("bgsim.layout.rows", JSON.stringify({ main: 86, dock: 14 }));
    }, theme);
    await page.setViewportSize({ width: 1600, height: 1250 });
    await openDashboard(page);

    await page.getByTestId("run-button").click();
    await expect(page.getByTestId("run-status")).toHaveAttribute("data-status", "done", { timeout: 30_000 });
    await expect(page.getByTestId("dash-value-value")).toHaveText(/^-?\d/, { timeout: 10_000 });
    await expect(page.getByTestId("dash-plot-plot").locator("canvas").first()).toBeVisible();
    await expect(page.getByRole("meter", { name: /Synthetic\/sine/ })).toBeVisible();
    await expect(page.getByRole("slider", { name: "Inductance" })).toHaveAttribute("aria-valuenow", "0.02");

    // Scrubbing: the knob of time is the shared cursor; the gauge follows it.
    const plot = page.getByTestId("dash-plot-plot").locator(".u-over").first();
    const box = await plot.boundingBox();
    if (box !== null) {
      await page.mouse.move(box.x + box.width * 0.25, box.y + box.height / 2);
    }
    await expect(page.getByRole("meter", { name: /Synthetic\/sine at t = / })).toBeVisible();

    expect(await seriousViolations(page)).toEqual([]);
    if (shots.length > 0) {
      mkdirSync(shots, { recursive: true });
      await page.getByTestId("dashboard").screenshot({ path: path.join(shots, `dashboard-use-${theme}.png`) });
    }

    await page.getByTestId("dash-edit-toggle").click();
    await expect(page.getByTestId("dashboard")).toHaveAttribute("data-mode", "edit");
    expect(await seriousViolations(page)).toEqual([]);
    if (shots.length > 0) {
      await page.getByTestId("dashboard").screenshot({ path: path.join(shots, `dashboard-edit-${theme}.png`) });
      await page.getByTestId("dash-add-card").click();
      await page.getByTestId("dashboard").screenshot({ path: path.join(shots, `dashboard-add-${theme}.png`) });
      await page.keyboard.press("Escape");
    }

    await page.getByTestId("dash-card-settings-gauge").click();
    await expect(page.getByTestId("dash-settings")).toBeVisible();
    const settingsAxe = await new AxeBuilder({ page }).include('[data-testid="dash-settings"]').analyze();
    expect(
      settingsAxe.violations
        .filter((violation) => violation.impact === "serious" || violation.impact === "critical")
        .map((violation) => violation.id),
    ).toEqual([]);
    if (shots.length > 0) {
      await page.screenshot({ path: path.join(shots, `dashboard-settings-${theme}.png`) });
    }
  });
}
