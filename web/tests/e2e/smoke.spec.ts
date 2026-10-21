import { expect, test } from "@playwright/test";

/**
 * M0.5 smoke test: the backend serves the built app, the shell renders, and
 * the worker health indicator reaches `ready`.
 *
 * The backend is started by `playwright.config.ts` with BGSIM_FAKE_WORKER=1
 * (`npm run e2e` builds web/dist first). Whether the status also says
 * "fake worker" depends on how the backend marks the fake in its `versions`
 * payload; the app derives it from that payload, so it is not asserted here.
 */
test("the app loads and the worker becomes ready", async ({ page }) => {
  await page.goto("/");

  await expect(page).toHaveTitle("bg-sim");
  await expect(page.getByTestId("top-bar")).toBeVisible();

  const workerStatus = page.getByTestId("worker-status");
  await expect(workerStatus).toBeVisible();
  await expect(workerStatus).toHaveAttribute("data-state", "ready", { timeout: 60_000 });
  await expect(workerStatus).toContainText(/ready/i);
  if (process.env.BGSIM_E2E_REAL !== "1") {
    await expect(workerStatus).toContainText(/fake worker/i);
  }

  await expect(page.getByRole("tab", { name: "Plots" })).toBeVisible();
});
