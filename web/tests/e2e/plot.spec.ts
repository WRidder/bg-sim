import { expect, test, type Page } from "@playwright/test";

/**
 * W1.4 acceptance against the fake worker:
 *
 * 1. Ctrl+Enter starts a run and the status reaches `done`;
 * 2. three signals are added from the Signals tab and render in one uPlot
 *    panel (two unit groups: V and dimensionless);
 * 3. dragging a time range on the plot re-requests `/api/runs/{id}/data` with
 *    the new `t0`/`t1` and `px = canvas width × devicePixelRatio`, while the
 *    show-all request used `px=0`.
 *
 * Every `/data` request is intercepted with `page.route` and its query string
 * recorded, so the zoom assertion is about the actual network call rather than
 * a visual guess. Each test uses its own project and deletes it afterwards.
 */

let project = "";

test.beforeEach(async ({ page }) => {
  project = `w1-plot-${Date.now()}-${test.info().workerIndex}`;
  await page.setViewportSize({ width: 1600, height: 1000 });
});

test.afterEach(async ({ request }) => {
  if (project.length > 0) {
    await request.delete(`/api/projects/${project}`);
  }
});

async function openModel(page: Page): Promise<void> {
  await page.goto(
    `/?project=${encodeURIComponent(project)}&model=PlotRun`,
  );
  await expect(page.getByTestId("library-item-DCMotor")).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByTestId("run-button")).toBeEnabled();
}

function zoomRequests(requests: URL[]): URL[] {
  return requests.filter((url) => {
    const t0 = url.searchParams.get("t0");
    const t1 = url.searchParams.get("t1");
    const px = Number(url.searchParams.get("px") ?? "0");
    return t0 !== null && t1 !== null && px > 0;
  });
}

test("runs, plots three signals and re-requests data on zoom", async ({
  page,
}) => {
  const dataRequests: URL[] = [];
  await page.route(/\/api\/runs\/[^/]+\/data/, async (route) => {
    dataRequests.push(new URL(route.request().url()));
    await route.continue();
  });

  await openModel(page);

  await page.keyboard.press("Control+Enter");
  const runStatus = page.getByTestId("run-status");
  await expect(runStatus).toHaveAttribute("data-status", "done", {
    timeout: 30_000,
  });
  await expect(runStatus).toContainText(/done in/i);

  // The Signals tab lists the manifest of the finished run.
  await page.getByRole("tab", { name: "Signals" }).click();
  await expect(page.getByTestId("signal-browser")).toBeVisible();
  for (const id of [
    "Synthetic/sine",
    "Synthetic/step",
    "Synthetic/counter",
  ]) {
    await page.locator(`[data-signal-id="${id}"]`).dblclick();
  }

  await page.getByRole("tab", { name: "Plots" }).click();
  const chart = page.locator('[data-testid="plot-chart"]');
  await expect(chart).toBeVisible();
  await expect(chart).toHaveAttribute("data-series-count", "3");
  await expect(page.locator('[data-testid="legend-item"]')).toHaveCount(3);

  // The first data fetches are the "show all" requests: raw, px=0, no window.
  // Signals were added one at a time, so take the request that carries all
  // three plotted ids rather than the first sine-only answer.
  await expect
    .poll(
      () =>
        dataRequests.filter(
          (url) =>
            url.searchParams.get("px") === "0" &&
            url.searchParams.get("ids")?.split(",").length === 3,
        ).length,
      { timeout: 15_000 },
    )
    .toBeGreaterThan(0);
  const raw = dataRequests.find(
    (url) =>
      url.searchParams.get("px") === "0" &&
      url.searchParams.get("ids")?.split(",").length === 3,
  );
  expect(raw?.searchParams.get("t0")).toBeNull();
  expect(raw?.searchParams.get("t1")).toBeNull();
  expect(raw?.searchParams.get("ids")?.split(",")).toEqual([
    "Synthetic/sine",
    "Synthetic/step",
    "Synthetic/counter",
  ]);

  // Drag roughly 25% to 70% of the plot area to zoom.
  const over = page.locator('[data-testid="plot-chart"] .u-over');
  await expect(over).toBeVisible();
  const box = await over.boundingBox();
  if (box === null) {
    throw new Error("the plot has no measurable area");
  }
  const y = box.y + box.height * 0.4;
  await page.mouse.move(box.x + box.width * 0.25, y);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.45, y, { steps: 5 });
  await page.mouse.move(box.x + box.width * 0.7, y, { steps: 10 });
  await page.mouse.up();

  await expect
    .poll(() => zoomRequests(dataRequests).length, { timeout: 15_000 })
    .toBeGreaterThan(0);

  const zoom = zoomRequests(dataRequests).at(-1);
  if (zoom === undefined) {
    throw new Error("no zoomed data request was recorded");
  }
  const t0 = Number(zoom.searchParams.get("t0"));
  const t1 = Number(zoom.searchParams.get("t1"));
  const px = Number(zoom.searchParams.get("px"));
  expect(Number.isFinite(t0)).toBe(true);
  expect(Number.isFinite(t1)).toBe(true);
  expect(t1).toBeGreaterThan(t0);
  expect(t0).toBeGreaterThanOrEqual(0);
  expect(t1).toBeLessThanOrEqual(1.000_001);
  expect(px).toBeGreaterThan(0);
  expect(zoom.searchParams.get("ids")?.split(",")).toHaveLength(3);

  // The canvas width is the chart host (not the dock), and px is its device
  // pixel width as plan 7.5 specifies.
  const canvasWidth = await chart.evaluate(
    (element) => (element as HTMLElement).clientWidth,
  );
  const devicePixelRatio = await page.evaluate(
    () => window.devicePixelRatio || 1,
  );
  expect(px).toBe(Math.round(canvasWidth * devicePixelRatio));

  // Double-click resets the view; the Reset zoom button becomes disabled.
  await page.mouse.dblclick(box.x + box.width * 0.5, y);
  await expect(page.getByTestId("plot-reset-zoom")).toBeDisabled();
  await expect(page.locator('[data-testid="legend-item"]')).toHaveCount(3);
});

test("Stop cancels a running simulation", async ({ page }) => {
  await openModel(page);

  await page.keyboard.press("Control+Enter");
  const runStatus = page.getByTestId("run-status");
  await expect(runStatus).toHaveAttribute("data-status", "running", {
    timeout: 10_000,
  });

  const stop = page.getByRole("button", { name: "Stop simulation" });
  await expect(stop).toBeEnabled();
  await stop.click();

  await expect(runStatus).toHaveAttribute("data-status", "cancelled", {
    timeout: 15_000,
  });
  await expect(stop).toBeDisabled();
});

test("shows the empty-state guidance before the first run", async ({ page }) => {
  await openModel(page);
  await expect(page.getByText("No run data")).toBeVisible();
  await expect(page.getByText(/Signals/).first()).toBeVisible();
  const stop = page.getByRole("button", { name: "Stop simulation" });
  await expect(stop).toBeDisabled();
});
