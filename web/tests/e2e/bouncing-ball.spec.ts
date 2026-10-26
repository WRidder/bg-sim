import { expect, test, type Page } from "@playwright/test";

/**
 * X2.1 acceptance: the `bouncing-ball` sample.
 *
 * 1. create a copy of the sample through `POST /api/projects {name, example}`;
 * 2. open the model, assert the `Ball1` project-library node and the canvas;
 * 3. press Run and wait for `done`;
 * 4. plot one signal from the manifest and assert one legend item with a finite
 *    cursor/legend value.
 *
 * The numerical acceptance is `examples/run_checks.py` against the real Julia
 * worker (impact times and the 0.64 m peak), so this spec uses the fake worker
 * from the Playwright `webServer`. The fake answers every run from its fixed
 * `Synthetic/*` fixture, so `Ball1/h` is not guaranteed in the signal browser;
 * the plot check therefore adds whichever signal the finished run lists first
 * and only proves that the sample opens, runs and renders in the UI. (Against
 * the real worker that first signal is `Ball1/h`, so the same spec also works in
 * the real-worker pass.) The copied project is deleted afterwards.
 */

test.describe.configure({ timeout: 60_000 });

let project = "";

test.beforeEach(async ({ request }) => {
  project = `x21-bouncing-ball-${Date.now()}-${test.info().workerIndex}`;
  const created = await request.post("/api/projects", {
    data: { name: project, example: "bouncing-ball" },
  });
  expect(created.status(), await created.text()).toBe(201);
});

test.afterEach(async ({ request }) => {
  if (project.length > 0) {
    await request.delete(`/api/projects/${project}`);
    project = "";
  }
});

function node(page: Page, name: string) {
  return page.locator(`[data-testid="diagram-node"][data-node-name="${name}"]`);
}

test("opens the sample, runs it and plots the manifest signal", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.goto(
    `/?project=${encodeURIComponent(project)}&model=bouncing-ball`,
  );
  await expect(page.getByTestId("canvas-surface")).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByTestId("run-button")).toBeEnabled();
  await expect(node(page, "Ball1")).toBeVisible();
  await expect(page.getByTestId("diagram-node")).toHaveCount(1);

  await page.getByTestId("run-button").click();
  const runStatus = page.getByTestId("run-status");
  await expect(runStatus).toHaveAttribute("data-status", "done", {
    timeout: 30_000,
  });
  await expect(runStatus).toContainText(/done in/i);

  // The fake manifest is synthetic, the real one has Ball1/h: take the first
  // signal the finished run offers instead of hard-coding an id.
  await page.getByRole("tab", { name: "Signals" }).click();
  await expect(page.getByTestId("signal-browser")).toBeVisible();
  const signal = page.getByTestId("signal-item").first();
  await expect(signal).toBeVisible();
  const signalId = await signal.getAttribute("data-signal-id");
  expect(signalId).not.toBeNull();
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

  // The cursor readout must be a real number, not a placeholder.
  const over = chart.locator(".u-over");
  await expect(over).toBeVisible();
  const area = await over.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    return { x: rect.left, y: rect.top, width: rect.width, height: rect.height };
  });
  if (!(area.width > 0) || !(area.height > 0)) {
    throw new Error("the plot has no measurable area");
  }
  await page.mouse.move(
    Math.round(area.x + area.width * 0.5),
    Math.round(area.y + area.height * 0.5),
  );

  const legendItem = page.locator(
    `[data-testid="legend-item"][data-signal-id="${signalId ?? ""}"]`,
  );
  await expect(legendItem).toHaveCount(1);
  const readout = legendItem.locator(".plot-legend__value");
  await expect(readout).toBeVisible();
  const value = Number.parseFloat(await readout.innerText());
  expect(Number.isFinite(value)).toBe(true);
});
