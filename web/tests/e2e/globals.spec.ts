import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

/**
 * Global parameters (spec "Global parameters"), fake worker:
 *
 * 1. with nothing selected the inspector is the model's Equations manager;
 *    add `m = 2` and `k = 4*m` and see k evaluate to 8;
 * 2. set R1's R to `k`: the field gets the Σ marker and "= 8 Ohm";
 * 3. rename k -> stiffness in the table: R1.R follows;
 * 4. a cycle shows an error on both rows; fixing it clears them;
 * 5. the model runs (fake worker) and the manager is axe-clean in both themes.
 *
 * Screenshots go to BGSIM_SCREENSHOT_DIR when it is set.
 */

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "../../..");
const shots = process.env.BGSIM_SCREENSHOT_DIR ?? "";
// BGSIM_E2E_REAL=1 runs against the Julia worker, which warms up and compiles first.
const real = process.env.BGSIM_E2E_REAL === "1";

let project = "";

test.beforeEach(async ({ page, request }) => {
  project = `globals-e2e-${Date.now()}-${test.info().workerIndex}`;
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  expect((await request.post("/api/projects", { data: { name: project } })).status()).toBe(201);
  const model = JSON.parse(
    readFileSync(path.join(repoRoot, "contracts", "fixtures", "model", "valid", "model.rlc.iconic.json"), "utf8"),
  ) as Record<string, unknown>;
  expect((await request.put(`/api/projects/${project}/models/Globals`, { data: model })).status()).toBe(200);
});

test.afterEach(async ({ request }) => {
  if (project.length > 0) {
    await request.delete(`/api/projects/${project}`);
  }
});

async function openModel(page: Page, theme: "dark" | "light" = "dark"): Promise<void> {
  await page.addInitScript((value) => localStorage.setItem("bgsim.theme", value), theme);
  if (real) {
    // The catalog answers 503 until the Julia worker has warmed up; the app does not retry by itself.
    await expect
      .poll(async () => (await page.request.get(`/api/catalog?project=${encodeURIComponent(project)}`)).status(), {
        timeout: 900_000,
        intervals: [5_000],
      })
      .toBe(200);
  }
  await page.goto(`/?project=${encodeURIComponent(project)}&model=Globals`);
  await expect(page.getByTestId("canvas-surface")).toBeVisible({ timeout: real ? 120_000 : 30_000 });
  await expect(page.getByTestId("inspector-model")).toBeVisible();
}

async function commit(page: Page, testId: string, text: string): Promise<void> {
  const field = page.getByTestId(testId);
  await field.fill(text);
  await field.press("Enter");
}

async function readDocument(page: Page): Promise<{
  parameters?: { name: string; value: string }[];
  diagram: { nodes: { name: string; params?: Record<string, string> }[] };
}> {
  const text = await page.getByTestId("document-json").textContent();
  return JSON.parse(text ?? "null");
}

async function addGlobal(page: Page, name: string, value: string): Promise<void> {
  await page.getByTestId("global-add").click();
  const fresh = page.getByTestId(/^global-name-p\d+$/).last();
  await expect(fresh).toBeFocused();
  await fresh.fill(name);
  await fresh.press("Enter");
  await commit(page, `global-value-${name}`, value);
}

async function selectR1(page: Page): Promise<void> {
  await page.locator('[data-testid="diagram-node"][data-node-name="R1"]').click();
  await expect(page.getByTestId("inspector-node")).toBeVisible();
}

async function deselect(page: Page): Promise<void> {
  await page.getByTestId("canvas-surface").click({ position: { x: 30, y: 30 } });
  await expect(page.getByTestId("inspector-model")).toBeVisible();
}

test("globals drive a block parameter, rename through, report cycles and run", async ({ page }) => {
  if (real) test.setTimeout(2_400_000);
  await openModel(page);
  await expect(page.getByTestId("globals-empty")).toBeVisible();

  await addGlobal(page, "m", "2");
  await addGlobal(page, "k", "4*m");
  await expect(page.getByTestId("global-result-k")).toHaveText("8");
  expect((await readDocument(page)).parameters).toEqual([
    { name: "m", value: "2" },
    { name: "k", value: "4*m" },
  ]);

  // A block parameter driven by a global: Σ and the evaluated value with its unit.
  await selectR1(page);
  const r = page.getByTestId("inspector-param-R");
  await r.fill("k");
  await r.press("Enter");
  await expect(page.getByTestId("inspector-param-R-sigma")).toBeVisible();
  await expect(page.getByTestId("inspector-param-R-value")).toHaveText("= 8 Ohm");
  if (shots.length > 0) {
    await page.getByTestId("inspector-panel").screenshot({ path: path.join(shots, "globals-field-dark.png") });
  }

  // Rename k -> stiffness in the table; R1.R follows.
  await deselect(page);
  await page.getByTestId("global-uses-k").click();
  await expect(page.getByTestId("global-users-k")).toContainText("R1.R");
  await commit(page, "global-name-k", "stiffness");
  await expect(page.getByTestId("global-result-stiffness")).toHaveText("8");
  const renamed = await readDocument(page);
  expect(renamed.diagram.nodes.find((node) => node.name === "R1")?.params?.R).toBe("stiffness");

  // The Equations view lists R1.R.
  await page.getByTestId("equations-tab-equations").click();
  await expect(page.getByTestId("equation-value-R1.R")).toHaveText("8");
  await page.getByTestId("equations-tab-globals").click();

  // A cycle is reported on both rows; fixing it clears the errors.
  await commit(page, "global-value-m", "stiffness / 4");
  await expect(page.getByTestId("global-error-m")).toHaveText("Cycle: m → stiffness → m.");
  await expect(page.getByTestId("global-error-stiffness")).toContainText("Cycle");
  if (shots.length > 0) {
    await page.getByTestId("inspector-panel").screenshot({ path: path.join(shots, "globals-cycle-dark.png") });
  }
  await commit(page, "global-value-m", "2");
  await expect(page.getByTestId("global-error-m")).toHaveCount(0);
  await expect(page.getByTestId("global-result-stiffness")).toHaveText("8");
  if (shots.length > 0) {
    await page.getByTestId("inspector-panel").screenshot({ path: path.join(shots, "globals-manager-dark.png") });
  }

  // Click-through from "used by" selects R1.
  await page.getByTestId("global-uses-stiffness").click();
  await page.getByTestId("global-user-stiffness-R1.R").click();
  await expect(page.getByTestId("inspector-param-R")).toHaveValue("stiffness");

  // Run (fake worker by default; BGSIM_E2E_REAL=1 runs the Julia worker, which folds the globals).
  await expect(page.getByTestId("run-button")).toBeEnabled({ timeout: real ? 600_000 : 5_000 });
  await page.keyboard.press("Control+Enter");
  await expect(page.getByTestId("run-status")).toHaveAttribute("data-status", "done", {
    timeout: real ? 600_000 : 30_000,
  });
});

for (const theme of ["light", "dark"] as const) {
  test(`the Equations manager and its dialog are axe-clean (${theme})`, async ({ page }) => {
    await openModel(page, theme);
    await addGlobal(page, "m", "2");
    await addGlobal(page, "k", "4*m");
    await page.getByTestId("global-uses-k").click();
    const check = async (): Promise<void> => {
      const result = await new AxeBuilder({ page }).include('[data-testid="inspector-panel"]').analyze();
      const serious = result.violations.filter(
        (violation) => violation.impact === "serious" || violation.impact === "critical",
      );
      expect(serious.map((violation) => `${violation.id}: ${violation.nodes.map((node) => node.target.join(" ")).join(", ")}`)).toEqual([]);
    };
    await check();
    if (shots.length > 0) {
      await page.getByTestId("inspector-panel").screenshot({ path: path.join(shots, `globals-manager-${theme}.png`) });
    }
    await page.getByTestId("equations-open-dialog").click();
    await expect(page.getByTestId("equations-dialog")).toBeVisible();
    await commit(page, "dialog-global-unit-m", "kg");
    await commit(page, "dialog-global-comment-m", "Base mass");
    const dialogResult = await new AxeBuilder({ page }).include('[data-testid="equations-dialog"]').analyze();
    expect(
      dialogResult.violations.filter((violation) => violation.impact === "serious" || violation.impact === "critical").map((violation) => violation.id),
    ).toEqual([]);
    if (shots.length > 0) {
      await page.getByTestId("equations-dialog").screenshot({ path: path.join(shots, `globals-dialog-${theme}.png`) });
    }
    await page.getByTestId("equations-dialog-close").click();

    await selectR1(page);
    await commit(page, "inspector-param-R", "= 1.25*k");
    await expect(page.getByTestId("inspector-param-R-value")).toHaveText("= 10 Ohm");
    if (shots.length > 0) {
      await page.getByTestId("inspector-panel").screenshot({ path: path.join(shots, `globals-field-${theme}.png`) });
    }
  });
}
