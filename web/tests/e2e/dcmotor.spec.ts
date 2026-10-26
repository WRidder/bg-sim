import {
  expect,
  test,
  type APIRequestContext,
  type Page,
} from "@playwright/test";

/**
 * X1.1 acceptance against the real worker (`BGSIM_E2E_REAL=1`):
 *
 * 1. create the `dc-motor` example project through the API;
 * 2. open its iconic model, press Run and wait for `done`;
 * 3. plot `Motor1/shaft.f` from the Signals tab;
 * 4. move the plot cursor to t = 0.2 s and read the legend: the shaft speed is
 *    239.8 ± 0.1 rad/s (plan 9.1; the same bound as `expected.json`).
 *
 * The project is deleted afterwards. Playwright's `webServer` starts
 * `uv run bgsim`; with `BGSIM_E2E_REAL=1` the config leaves the fake worker
 * off. The worker can still be warming when the HTTP server answers, so the
 * test waits for `/api/health` to report `worker: "ready"` before opening the
 * model.
 */

test.describe.configure({ timeout: 120_000 });

let project = "";

test.beforeEach(async ({ request }) => {
  project = `x11-dcmotor-${Date.now()}-${test.info().workerIndex}`;
  const created = await request.post("/api/projects", {
    data: { name: project, example: "dc-motor" },
  });
  expect(created.status(), await created.text()).toBe(201);
});

test.afterEach(async ({ request }) => {
  if (project.length > 0) {
    await request.delete(`/api/projects/${project}`);
    project = "";
  }
});

async function waitForWorker(request: APIRequestContext): Promise<void> {
  await expect
    .poll(
      async () => {
        const response = await request.get("/api/health");
        if (!response.ok()) {
          return `http ${response.status()}`;
        }
        const health = (await response.json()) as {
          worker: string;
          versions: { julia: string | null };
        };
        // `fake` is the fixture-driven worker's ping answer; the real worker
        // reports the Julia version. This spec is meaningless without it.
        if (health.worker === "ready" && health.versions.julia === "fake") {
          return "fake worker";
        }
        return health.worker;
      },
      {
        message: "the real Julia worker becomes ready",
        timeout: 90_000,
        intervals: [200, 500, 1_000, 2_000],
      },
    )
    .toBe("ready");
}

async function openIconic(page: Page): Promise<void> {
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.goto(`/?project=${encodeURIComponent(project)}&model=iconic`);
  await expect(page.getByTestId("library-item-DCMotor")).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByTestId("run-button")).toBeEnabled();
}

test("plots the shaft speed and reads 239.8 rad/s at t = 0.2 s", async ({
  page,
  request,
}) => {
  await waitForWorker(request);
  await openIconic(page);

  await page.getByTestId("run-button").click();
  const runStatus = page.getByTestId("run-status");
  await expect(runStatus).toHaveAttribute("data-status", "done", {
    timeout: 90_000,
  });
  await expect(runStatus).toContainText(/done in/i);

  // The manifest of the finished run fills the Signals tab.
  await page.getByRole("tab", { name: "Signals" }).click();
  await expect(page.getByTestId("signal-browser")).toBeVisible();
  const signal = page.locator(
    '[data-testid="signal-item"][data-signal-id="Motor1/shaft.f"]',
  );
  await expect(signal).toHaveCount(1);
  await signal.dblclick();

  await page.getByRole("tab", { name: "Plots" }).click();
  const chart = page.getByTestId("plot-chart");
  await expect(chart).toBeVisible();
  await expect(chart).toHaveAttribute("data-series-count", "1");
  await expect(page.getByTestId("legend-item")).toHaveCount(1);
  await expect
    .poll(
      async () => Number((await chart.getAttribute("data-points")) ?? "0"),
      { message: "the run data is loaded into the plot", timeout: 30_000 },
    )
    .toBeGreaterThan(0);

  // The chart's x scale is the run window (0..1 s); 20 % of the uPlot plot area
  // is the 0.2 s position on the 5000-point output grid.
  await expect
    .poll(async () => {
      const min = await chart.getAttribute("data-x-min");
      const max = await chart.getAttribute("data-x-max");
      return min !== null && max !== null && Number(max) > Number(min);
    })
    .toBe(true);
  const xMin = Number(await chart.getAttribute("data-x-min"));
  const xMax = Number(await chart.getAttribute("data-x-max"));
  const over = chart.locator(".u-over");
  await expect(over).toBeVisible();
  // `boundingBox()` rounds the plot origin; read the live rect so the target
  // pixel is computed from the real plot area.
  const area = await over.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    return {
      x: rect.left,
      y: rect.top,
      width: rect.width,
      height: rect.height,
    };
  });
  if (!(area.width > 0) || !(area.height > 0)) {
    throw new Error("the plot has no measurable area");
  }
  // A real mouse addresses whole CSS pixels, so land on the pixel nearest the
  // 0.2 s position (the 5000-point grid is finer than one pixel here). The
  // legend then shows the sample at t = 0.2 s.
  const targetX = Math.round(
    area.x + ((0.2 - xMin) / (xMax - xMin)) * area.width,
  );
  const targetY = Math.round(area.y + area.height * 0.5);
  await page.mouse.move(targetX, targetY);

  const legendTime = page.getByTestId("legend-time");
  await expect(legendTime).toHaveText("t = 0.2 s");

  const legendItem = page.locator(
    '[data-testid="legend-item"][data-signal-id="Motor1/shaft.f"]',
  );
  await expect(legendItem).toHaveCount(1);
  const readout = legendItem.locator(".plot-legend__value");
  // The rotation domain's angular velocity unit is 1/s in the manifest (rad is
  // dimensionless in plan 5.3); the plan quotes the same quantity as rad/s.
  await expect(readout).toContainText("1/s");
  const value = Number.parseFloat(await readout.innerText());
  expect(Number.isFinite(value)).toBe(true);
  expect(Math.abs(value - 239.8)).toBeLessThanOrEqual(0.1);
});
