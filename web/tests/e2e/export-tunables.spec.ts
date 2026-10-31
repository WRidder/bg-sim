import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

/**
 * W-EX1 / J-EX8 on the fake worker: the tunables editor of the Export dialog. dc-motor's
 * speed-control with the motor's R and J as globals (Rm, Jr) and L driven by Rm:
 *
 * 1. nothing is tunable by default; "Expose all globals (2)" adds Rm and Jr, not the driven Lm;
 * 2. the motor's R (computed from a global) cannot be picked; Step1/final can;
 * 3. an open range is noted (W210), a range that leaves out the value blocks the export;
 * 4. the export's report lists the fixed parameters with their ranges and the cost line.
 *
 * Screenshots go to BGSIM_SCREENSHOT_DIR when it is set.
 */

test.describe.configure({ timeout: 90_000 });

const shots = process.env.BGSIM_SCREENSHOT_DIR ?? "";
let project = "";

test.beforeEach(async ({ page, request }) => {
  project = `w-tunables-${Date.now()}-${test.info().workerIndex}`;
  expect((await request.post("/api/projects", { data: { name: project, example: "dc-motor" } })).status()).toBe(201);
  const model = (await (await request.get(`/api/projects/${project}/models/speed-control`)).json()) as {
    parameters?: unknown[];
    diagram: { nodes: { name: string; params?: Record<string, string> }[] };
  };
  model.parameters = [
    { name: "Rm", value: "2.0", unit: "Ohm", description: "winding resistance" },
    { name: "Lm", value: "2.5e-4*Rm", unit: "H", description: "winding inductance" },
    { name: "Jr", value: "1e-5", unit: "kg*m^2", description: "rotor inertia" },
  ];
  const motor = model.diagram.nodes.find((n) => n.name === "Motor1");
  motor!.params = { ...motor!.params, R: "Rm", L: "Lm", J: "Jr" };
  expect((await request.put(`/api/projects/${project}/models/speed-control`, { data: model })).status()).toBe(200);
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.emulateMedia({ reducedMotion: "reduce" });
});

test.afterEach(async ({ request }) => {
  if (project.length > 0) {
    await request.delete(`/api/projects/${project}`);
    project = "";
  }
});

test("picks tunables, exposes the globals and reports what stays settable", async ({ page }) => {
  await page.goto(`/?project=${project}&model=speed-control`);
  await expect(page.getByTestId("diagram-node").first()).toBeVisible({ timeout: 30_000 });
  await page.getByTestId("open-export").click();
  const dialog = page.getByTestId("export-dialog");
  await expect(dialog).toBeVisible();

  const section = page.getByTestId("export-tunables");
  await expect(section).toContainText("None: every parameter is folded");
  await expect(page.getByTestId("export-tunable-table")).toHaveCount(0);
  await expect(page.getByTestId("export-expose-globals")).toHaveText("Expose all globals (2)");
  await page.getByTestId("export-expose-globals").click();
  await expect(page.getByTestId("export-tunable-row-global:Rm")).toBeVisible();
  await expect(page.getByTestId("export-tunable-row-global:Jr")).toBeVisible();
  await expect(page.getByTestId("export-tunable-row-global:Lm")).toHaveCount(0);
  await expect(page.getByTestId("export-tunable-open")).toContainText("2 tunables have an open range");

  // The motor's R is an equation over a global: expose the global instead.
  const pick = page.getByTestId("export-tunable-pick");
  await pick.fill("Motor1/R");
  await expect(page.getByTestId("export-tunable-pick-problem")).toContainText("expose the global instead");
  await expect(page.getByTestId("export-tunable-add")).toBeDisabled();
  await pick.fill("Step1/final");
  await page.getByTestId("export-tunable-add").click();
  await expect(page.getByTestId("export-tunable-row-Step1/final")).toBeVisible();

  await page.getByTestId("export-tunable-min-global:Rm").fill("1");
  await page.getByTestId("export-tunable-max-global:Rm").fill("4");
  await page.getByTestId("export-tunable-min-global:Jr").fill("5e-6");
  await page.getByTestId("export-tunable-max-global:Jr").fill("4e-5");
  await page.getByTestId("export-tunable-min-Step1/final").fill("150");
  await page.getByTestId("export-tunable-max-Step1/final").fill("200");
  await expect(page.getByTestId("export-tunable-row-Step1/final")).toContainText("the range must contain the model's value 100");
  await expect(page.getByTestId("export-start")).toBeDisabled();
  await page.getByTestId("export-tunable-min-Step1/final").fill("50");
  await expect(page.getByTestId("export-tunable-open")).toHaveCount(0);
  await expect(page.getByTestId("export-start")).toBeEnabled();
  if (shots) {
    await section.screenshot({ path: `${shots}/jex8-tunables-editor.png` });
  }

  // The editor is axe-clean (serious and critical rules).
  const axe = await new AxeBuilder({ page }).include('[data-testid="export-tunables"]').analyze();
  expect(
    axe.violations
      .filter((v) => v.impact === "serious" || v.impact === "critical")
      .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`),
  ).toEqual([]);

  const [post] = await Promise.all([
    page.waitForRequest((r) => r.method() === "POST" && r.url().includes("/export")),
    page.getByTestId("export-start").click(),
  ]);
  const body = post.postDataJSON() as { settings: { tunables: unknown[] } };
  expect(body.settings.tunables).toEqual([
    { id: "global:Rm", min: 1, max: 4 },
    { id: "global:Jr", min: 5e-6, max: 4e-5 },
    { id: "Step1/final", min: 50, max: 200 },
  ]);
  await expect(page.getByTestId("export-report")).toBeVisible({ timeout: 30_000 });
  const report = page.getByTestId("export-report-tunables");
  await expect(report.getByTestId("export-report-parameter-Rm")).toContainText("global");
  await expect(report.getByTestId("export-report-parameter-Rm")).toContainText("1 … 4");
  await expect(report.getByTestId("export-report-parameter-Step1/final")).toContainText("fixed");
  await expect(page.getByTestId("export-report-tunable-cost")).toContainText("with everything folded");
  if (shots) {
    await report.screenshot({ path: `${shots}/jex8-tunables-report.png` });
    await dialog.screenshot({ path: `${shots}/jex8-dialog.png` });
  }
});
