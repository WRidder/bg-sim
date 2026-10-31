import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

/**
 * Background tasks (the top bar's tasks indicator) on the fake worker: an FMU export goes on
 * when its dialog closes, shows up in the indicator, re-opens its dialog from there ("Show
 * details"), survives a page reload and is cancelled from the popover; a finished export
 * offers a toast that brings its report back.
 *
 * The fake export runner holds a job in `running` per the POST's X-BGSim-Fake-Export-S
 * header (fake worker only), which the test adds with a route.
 */

test.describe.configure({ timeout: 90_000 });

let project = "";

test.beforeEach(async ({ page, request }) => {
  project = `w-tasks-${Date.now()}-${test.info().workerIndex}`;
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

/** Every export POST of this page runs its fake phases `seconds` long. */
async function slowExports(page: Page, seconds: number): Promise<void> {
  await page.route("**/api/projects/*/models/**/export", async (route) => {
    await route.continue({
      headers: { ...route.request().headers(), "x-bgsim-fake-export-s": String(seconds) },
    });
  });
}

test("an export goes on after its dialog closes, survives a reload and is cancelled", async ({ page }) => {
  await slowExports(page, 3);
  await openModel(page);
  const indicator = page.getByTestId("tasks-indicator");
  await expect(indicator).toHaveAttribute("data-state", "idle");

  await page.getByTestId("open-export").click();
  await page.getByTestId("export-start").click();
  await expect(page.getByTestId("export-progress")).toBeVisible();
  await page.getByTestId("export-dialog-close").click();
  await expect(page.getByTestId("export-dialog")).toBeHidden();

  // The job runs on: the indicator spins with a count.
  await expect(indicator).toHaveAttribute("data-state", "running");
  await expect(page.getByTestId("tasks-count")).toHaveText("1");
  await indicator.click();
  const item = page.getByTestId("task-item");
  await expect(item).toHaveCount(1);
  await expect(item).toHaveAttribute("data-status", "running");
  await expect(item).toContainText("FMU export · hydraulic-servo");

  const axe = await new AxeBuilder({ page }).include('[data-testid="tasks-panel"]').analyze();
  expect(
    axe.violations
      .filter((v) => v.impact === "serious" || v.impact === "critical")
      .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`),
  ).toEqual([]);

  // Show details: the dialog comes back on the same job, with its live progress.
  await item.getByTestId("task-details").click();
  await expect(page.getByTestId("tasks-panel")).toBeHidden();
  await expect(page.getByTestId("export-dialog")).toBeVisible();
  await expect(page.getByTestId("export-progress")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("export-dialog")).toBeHidden();

  // A reload lists the project's jobs: the running export is back in the indicator.
  await page.reload();
  await expect(page.getByTestId("diagram-node").first()).toBeVisible({ timeout: 30_000 });
  await expect(indicator).toHaveAttribute("data-state", "running");

  await indicator.click();
  await expect(page.getByTestId("task-item")).toHaveAttribute("data-status", "running");
  await page.getByTestId("task-cancel").click();
  await expect(page.getByTestId("task-item")).toHaveAttribute("data-status", "cancelled");
  await expect(page.getByTestId("task-phase")).toHaveText("Cancelled");

  // Escape closes the popover and focus returns to the indicator.
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("tasks-panel")).toBeHidden();
  await expect(indicator).toBeFocused();
  await expect(indicator).toHaveAttribute("data-state", "idle");

  // Clear finished empties the list, also after another reload.
  await indicator.click();
  await page.getByTestId("tasks-clear").click();
  await expect(page.getByTestId("tasks-empty")).toBeVisible();
  await page.reload();
  await expect(page.getByTestId("diagram-node").first()).toBeVisible({ timeout: 30_000 });
  await indicator.click();
  await expect(page.getByTestId("tasks-empty")).toBeVisible();
});

test("the plot's CSV export runs as a task and saves the file", async ({ page }) => {
  await page.goto(`/?project=${encodeURIComponent(project)}&model=PlotRun`);
  await expect(page.getByTestId("run-button")).toBeEnabled({ timeout: 30_000 });
  await page.keyboard.press("Control+Enter");
  await expect(page.getByTestId("run-status")).toHaveAttribute("data-status", "done", { timeout: 30_000 });
  await page.getByRole("tab", { name: "Signals" }).click();
  await page.locator('[data-signal-id="Synthetic/sine"]').dblclick();
  await page.getByRole("tab", { name: "Plots" }).click();
  await expect(page.locator('[data-testid="legend-item"]')).toHaveCount(1);

  const [file] = await Promise.all([page.waitForEvent("download"), page.getByTestId("export-csv").click()]);
  expect(file.suggestedFilename()).toMatch(/\.csv$/);
  await page.getByTestId("tasks-indicator").click();
  const item = page.getByTestId("task-item");
  await expect(item).toHaveAttribute("data-status", "done");
  await expect(item).toContainText("CSV export · PlotRun (1 signal)");
  await expect(item.getByTestId("task-phase")).toContainText(/Saved .*\.csv/);
});

test("a finished export announces itself and its toast brings the report back", async ({ page }) => {
  await slowExports(page, 0.4);
  await openModel(page);
  await page.getByTestId("open-export").click();
  await page.getByTestId("export-start").click();
  await expect(page.getByTestId("export-progress")).toBeVisible();
  await page.getByTestId("export-dialog-close").click();

  const toast = page.getByTestId("task-toast");
  await expect(toast).toContainText("FMU export · hydraulic-servo finished", { timeout: 30_000 });
  await expect(page.getByTestId("tasks-live")).toHaveText("FMU export · hydraulic-servo finished");
  await expect(page.getByTestId("tasks-indicator")).toHaveAttribute("data-state", "attention");

  await page.getByTestId("task-toast-show").click();
  await expect(page.getByTestId("export-report")).toBeVisible();
  await expect(page.getByTestId("export-download")).toContainText("hydraulic_servo.fmu");
  await expect(page.getByTestId("tasks-indicator")).toHaveAttribute("data-state", "idle");
  await page.keyboard.press("Escape");

  // The popover offers the FMU's download too.
  await page.getByTestId("tasks-indicator").click();
  await expect(page.getByTestId("task-download")).toHaveAttribute("download", "hydraulic_servo.fmu");
});
