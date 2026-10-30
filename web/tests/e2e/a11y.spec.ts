import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import AxeBuilder from "@axe-core/playwright";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/**
 * W5.4 acceptance (plan 7.8): no axe violation at serious level or above on the main screens, in
 * the light and the dark theme. No rule is disabled. Fake worker; the model is the RLC fixture with
 * the `chain.sdf` scene, a finished run and a plotted signal.
 *
 * Run with `$env:BGSIM_E2E_PORT="8778"; npx playwright test tests/e2e/a11y.spec.ts`.
 */

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "../../..");

let project = "";

test.beforeEach(async ({ page }) => {
  project = `w54-a11y-${Date.now()}-${test.info().workerIndex}`;
  await page.setViewportSize({ width: 1600, height: 1000 });
  // Axe measures colours as rendered: a button caught in its 120 ms enable transition
  // reports an intermediate background (FIX-M4-1, intermittent `.button--primary`
  // contrast). The app honours prefers-reduced-motion, so the check sees the final state.
  await page.emulateMedia({ reducedMotion: "reduce" });
});

test.afterEach(async ({ request }) => {
  if (project.length > 0) await request.delete(`/api/projects/${project}`);
});

async function store(request: APIRequestContext): Promise<void> {
  expect((await request.post("/api/projects", { data: { name: project } })).status()).toBe(201);
  const model = JSON.parse(
    readFileSync(path.join(repoRoot, "contracts", "fixtures", "model", "valid", "model.rlc.iconic.json"), "utf8"),
  ) as Record<string, unknown>;
  model["scene"] = { file: "scenes/chain.sdf" };
  expect((await request.put(`/api/projects/${project}/models/Arm`, { data: model })).status()).toBe(200);
  const put = await request.put(`/api/projects/${project}/scenes/chain.sdf`, {
    data: readFileSync(path.join(here, "..", "fixtures", "scenes", "chain.sdf"), "utf8"),
    headers: { "content-type": "application/xml" },
  });
  expect(put.status()).toBe(200);
}

/** Serious and critical violations, formatted so a failure names the rule and the nodes. */
async function violations(page: Page): Promise<string[]> {
  const result = await new AxeBuilder({ page }).analyze();
  return result.violations
    .filter((violation) => violation.impact === "serious" || violation.impact === "critical")
    .map(
      (violation) =>
        `${violation.id} (${violation.impact}): ${violation.help}\n` +
        violation.nodes
          .slice(0, 4)
          .map((node) => `    ${node.target.join(" ")}  ${node.failureSummary?.split("\n")[1] ?? ""}`)
          .join("\n"),
    );
}

async function expectClean(page: Page, screen: string): Promise<void> {
  expect.soft(await violations(page), `axe violations on ${screen}`).toEqual([]);
}

for (const theme of ["light", "dark"] as const) {
  test(`start page, editor, plots, code, diagnostics, 3D view and dialogs are axe-clean (${theme})`, async ({
    page,
    request,
  }) => {
    test.setTimeout(180_000);
    await store(request);
    await page.addInitScript((value) => localStorage.setItem("bgsim.theme", value), theme);

    // Start page with the example gallery.
    await page.goto("/");
    await expect(page.getByTestId("start-page")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("start-page")).toHaveAttribute("data-state", "ready");
    await expectClean(page, "start page");

    // Open dialog from the start page.
    await page.keyboard.press("Control+o");
    await expect(page.getByTestId("open-dialog")).toBeVisible();
    await expect(page.getByTestId("open-project-list")).toBeVisible();
    await expectClean(page, "open dialog");
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("open-dialog")).toBeHidden();

    // Shortcuts overlay.
    await page.keyboard.press("?");
    await expect(page.getByTestId("shortcuts-overlay")).toBeVisible();
    await expectClean(page, "shortcuts overlay");
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("shortcuts-overlay")).toBeHidden();

    // Editor with a diagram.
    await page.goto(`/?project=${project}&model=Arm`);
    await expect(page.getByTestId("run-button")).toBeEnabled({ timeout: 30_000 });
    await expect(page.getByTestId("diagram-node").first()).toBeVisible();
    await expectClean(page, "editor");

    // Inspector with a selected node.
    await page.getByTestId("diagram-node").first().click();
    await expect(page.getByTestId("inspector-panel")).toBeVisible();
    await expectClean(page, "inspector");

    // Block help for the selected node.
    await page.getByTestId("block-help-button").click();
    await expect(page.getByTestId("block-help")).toBeVisible();
    await expectClean(page, "block help");
    await page.keyboard.press("Escape");

    // Plots with a run.
    await page.keyboard.press("Control+Enter");
    await expect(page.getByTestId("run-status")).toHaveAttribute("data-status", "done", { timeout: 30_000 });
    await page.getByRole("tab", { name: "Signals" }).click();
    await expect(page.getByTestId("signal-browser")).toBeVisible();
    await expectClean(page, "signals");
    await page.locator('[data-signal-id="Synthetic/sine"]').dblclick();
    await page.getByRole("tab", { name: "Plots" }).click();
    await expect(page.locator('[data-testid="plot-chart"] .u-over').first()).toBeVisible();
    await expectClean(page, "plots");

    // Automatic plot and log tabs.
    await page.getByRole("tab", { name: "Auto Plot" }).click();
    await expectClean(page, "auto plot");
    await page.getByRole("tab", { name: "Log" }).click();
    await expectClean(page, "log");

    // Code tab: first the empty state, then a block's source in the editor.
    await page.getByRole("tab", { name: "Code" }).click();
    await expect(page.getByTestId("code-tab")).toBeVisible();
    await expectClean(page, "code tab");
    await page.getByTestId("code-empty-new-equation").click();
    await expect(page.getByTestId("code-editor")).toBeVisible();
    await expectClean(page, "code editor");
    await page.getByRole("tab", { name: "Diagram" }).click();

    // Diagnostics.
    await page.getByRole("tab", { name: /Diagnostics/ }).click();
    await expectClean(page, "diagnostics");

    // 3D view with a scene.
    await page.getByRole("tab", { name: "3D View" }).click();
    await expect(page.getByTestId("scene-view")).toHaveAttribute("data-state", "loaded", { timeout: 30_000 });
    await expect(page.getByTestId("playback-bar")).toBeVisible({ timeout: 30_000 });
    await expectClean(page, "3D view");
    await page.getByTestId("bindings-toggle").click();
    await expect(page.getByTestId("bindings-editor")).toBeVisible();
    await expectClean(page, "3D view with the bindings editor");

    // Open dialog over the editor.
    await page.getByTestId("open-project").click();
    await expect(page.getByTestId("open-project-list")).toBeVisible();
    await expectClean(page, "open dialog over the editor");
  });
}
