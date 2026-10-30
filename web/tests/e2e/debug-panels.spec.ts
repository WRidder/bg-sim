import { expect, test, type Page } from "@playwright/test";

/**
 * W4.2 acceptance (plan 7.9) against the fake worker's debug runs
 * (`backend/src/bgsim_server/fake_debug.py`):
 *
 * - run once so the Signals tab lists the signals, then "Break when..." on
 *   `Synthetic/sine` > 0.5 from the signal context menu;
 * - Explain the signal (needs no pause): kind, defining expression, source link;
 * - start debugging: the run pauses on the watch at t = 0.084;
 * - the Debug tab shows the pause, the watched signal's value, the breakpoint
 *   (verified, "1 / 16 watch slots") and evaluates an added watch expression.
 */

let project = "";

test.beforeEach(async ({ page }) => {
  project = `w42-debug-${Date.now()}-${test.info().workerIndex}`;
  await page.setViewportSize({ width: 1700, height: 1000 });
});

test.afterEach(async ({ request }) => {
  if (project.length > 0) {
    await request.delete(`/api/projects/${project}`);
    project = "";
  }
});

async function openModel(page: Page): Promise<void> {
  await page.goto(`/?project=${encodeURIComponent(project)}&model=DebugPanels`);
  await expect(page.getByTestId("library-item-DCMotor")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("run-button")).toBeEnabled();
}

async function signalMenu(page: Page, signalId: string, item: "break-when" | "explain-signal") {
  await page.getByRole("tab", { name: "Signals" }).click();
  const row = page.locator(`[data-testid="signal-item"][data-signal-id="${signalId}"]`);
  await row.click({ button: "right" });
  await expect(page.getByTestId("signal-menu")).toBeVisible();
  await page.getByTestId("signal-menu").getByTestId(item).click();
}

test("breaks when a signal crosses a value, shows variables, evaluates an expression and explains a signal", async ({
  page,
}) => {
  await openModel(page);

  // A normal run lists the signals.
  await page.keyboard.press("Control+Enter");
  await expect(page.getByTestId("run-status")).toHaveAttribute("data-status", "done", {
    timeout: 30_000,
  });

  // Break when Synthetic/sine > 0.5.
  await signalMenu(page, "Synthetic/sine", "break-when");
  const dialog = page.getByTestId("break-when-dialog");
  await expect(dialog).toBeVisible();
  await expect(page.getByTestId("break-when-signal")).toHaveValue("Synthetic/sine");
  await page.getByTestId("break-when-comparison").selectOption(">");
  await page.getByTestId("break-when-value").fill("0.5");
  await expect(page.getByTestId("break-when-preview")).toContainText('s"Synthetic/sine" > 0.5');
  await page.getByTestId("break-when-add").click();
  await expect(dialog).toHaveCount(0);

  // Explain the signal without a pause: kind, expression, source link.
  await signalMenu(page, "Synthetic/sine", "explain-signal");
  const popover = page.getByTestId("explain-popover");
  await expect(popover).toBeVisible();
  await expect(page.getByTestId("explain-kind")).toHaveText("Observed variable");
  await expect(page.getByTestId("explain-expression")).toContainText("sin(2 * pi * t)");
  await expect(page.getByTestId("explain-origin").first()).toBeVisible();
  await expect(page.getByTestId("explain-origin").first()).toContainText("line");
  await page.getByTestId("explain-close").click();
  await expect(popover).toHaveCount(0);

  // Debug: the run pauses on the watch at t = 0.084.
  await page.getByTestId("debug-button").click();
  const status = page.getByTestId("run-status");
  await expect(status).toHaveAttribute("data-status", "paused", { timeout: 20_000 });
  await expect(status).toContainText("Paused at t = 0.0840 s");
  await expect(status).toContainText('watch s"Synthetic/sine" > 0.5');

  // The Debug tab: variables at the pause.
  await page.getByRole("tab", { name: "Debug" }).click();
  await expect(page.getByTestId("debug-panel")).toBeVisible();
  await expect(page.getByTestId("variables-pause")).toContainText("0.0840");
  const watched = page.locator('[data-testid="var-signal"][data-signal-id="Synthetic/sine"]');
  await expect(watched).toBeVisible();
  await expect(watched.getByTestId("var-signal-value")).toHaveText(/^0\.5\d*$/);

  // The breakpoint is verified and uses one of the 16 slots.
  await expect(page.getByTestId("watch-slots")).toHaveText("1 / 16 watch slots");
  const row = page.getByTestId("breakpoint-row").first();
  await expect(row).toHaveAttribute("data-kind", "watch");
  await expect(row).toHaveAttribute("data-verified", "true");
  await expect(row).toContainText('s"Synthetic/sine" > 0.5');

  // A watch expression is evaluated at the pause.
  await page.getByTestId("watch-expression-input").fill('s"Synthetic/sine" * 2');
  await page.getByTestId("watch-expression-add").click();
  await expect(page.getByTestId("watch-expression-value")).toHaveText(/^1\.00\d*$/);

  // Stop the paused run.
  await page.keyboard.press("Shift+F5");
  await expect(status).toHaveAttribute("data-status", "cancelled", { timeout: 20_000 });
});
