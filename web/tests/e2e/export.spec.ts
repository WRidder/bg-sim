import { readFileSync } from "node:fs";

import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

/**
 * W-EX1 on the fake worker (BGSIM_FAKE_WORKER=1, the fake export runner: no Julia, no
 * compiler, the real interface and refusal rules): export hydraulic-servo as a whole model
 * and its Valve subsystem from the canvas context menu, read the report and download both
 * FMUs.
 */

test.describe.configure({ timeout: 90_000 });

let project = "";

test.beforeEach(async ({ page, request }) => {
  project = `w-export-${Date.now()}-${test.info().workerIndex}`;
  const created = await request.post("/api/projects", {
    data: { name: project, example: "hydraulic-servo" },
  });
  expect(created.status(), await created.text()).toBe(201);
  await page.setViewportSize({ width: 1600, height: 1000 });
});

test.afterEach(async ({ request }) => {
  if (project.length > 0) {
    await request.delete(`/api/projects/${project}`);
    project = "";
  }
});

async function openModel(page: Page): Promise<void> {
  await page.goto(`/?project=${project}&model=hydraulic-servo`);
  await expect(page.getByTestId("diagram-node").first()).toBeVisible({ timeout: 30_000 });
}

async function download(page: Page, expected: string): Promise<Buffer> {
  const [file] = await Promise.all([
    page.waitForEvent("download"),
    page.getByTestId("export-download").click(),
  ]);
  expect(file.suggestedFilename()).toBe(expected);
  const saved = test.info().outputPath(expected);
  await file.saveAs(saved);
  const bytes = readFileSync(saved);
  expect(bytes.subarray(0, 2).toString()).toBe("PK"); // a zip archive
  return bytes;
}

test("exports the whole model and downloads the FMU", async ({ page }) => {
  await openModel(page);
  await page.getByTestId("open-export").click();
  const dialog = page.getByTestId("export-dialog");
  await expect(dialog).toBeVisible();
  await expect(page.getByTestId("export-scope-model")).toBeChecked();
  // hydraulic-servo has no Export markers: the W209 hint says the FMU would publish nothing.
  await expect(page.getByTestId("export-w209")).toBeVisible();
  await expect(page.getByTestId("export-method")).toHaveValue("auto");
  await expect(page.getByTestId("export-dt")).toHaveValue("");

  await page.getByTestId("export-start").click();
  await expect(page.getByTestId("export-progress")).toBeVisible();
  await expect(page.getByTestId("export-report")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("export-report-method")).toHaveText("RK4");
  await expect(page.getByTestId("export-candidates")).toContainText("Rodas4P");
  await expect(page.getByTestId("export-diagnostic-W209")).toBeVisible();
  await expect(page.getByTestId("export-build")).toContainText("Source-only FMU");
  await download(page, "hydraulic_servo.fmu");

  // The dialog with its report is axe-clean (serious and critical rules).
  const axe = await new AxeBuilder({ page }).include('[data-testid="export-dialog"]').analyze();
  expect(
    axe.violations
      .filter((v) => v.impact === "serious" || v.impact === "critical")
      .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`),
  ).toEqual([]);

  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
});

test("exports a subsystem from its context menu", async ({ page }) => {
  await openModel(page);
  await page.locator('[data-testid="diagram-node"][data-node-name="Valve"]').click({ button: "right" });
  await page.getByTestId("export-subsystem").click();

  await expect(page.getByTestId("export-dialog")).toBeVisible();
  await expect(page.getByTestId("export-scope-subsystem")).toBeChecked();
  await expect(page.getByTestId("export-scope-select")).toHaveValue("Valve");
  await expect(page.getByTestId("export-w209")).toBeHidden();
  for (const port of ["P", "T", "A", "B"]) {
    await expect(page.getByTestId(`export-power-${port}`)).toHaveValue("effort");
  }
  await page.getByTestId("export-power-A").selectOption("flow");
  await expect(page.getByTestId("export-inputs")).toContainText("A_f");
  await expect(page.getByTestId("export-outputs")).toContainText("A_e");

  await page.getByTestId("export-advanced").locator("summary").click();
  await page.getByTestId("export-linear-solver").selectOption("dense");
  await page.getByTestId("export-start").click();
  await expect(page.getByTestId("export-report")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("export-report")).toContainText("5 inputs, 4 outputs");
  await expect(page.getByTestId("export-diagnostic-W209")).toHaveCount(0);
  await download(page, "hydraulic_servo_Valve.fmu");
});
