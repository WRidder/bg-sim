import { expect, test, type Page } from "@playwright/test";

/**
 * W2.4 acceptance (plan 7.5): multiple panels share one cursor as the global
 * inspect time, a pinned run overlays as dashed same-colour lines, the canvas
 * context menu plots a port's effort/flow/power and an instance's outputs, and
 * a live run follows its tail until `run.done` stops it.
 *
 * The first two tests use the real fake worker (the same path as plot.spec).
 * The menu and live tests mock the run endpoints so their signal names and
 * timing are exact; the catalog, project and canvas stay real.
 */

let project = "";

test.beforeEach(async ({ page }) => {
  project = `w24-${Date.now()}-${test.info().workerIndex}`;
  await page.setViewportSize({ width: 1600, height: 1000 });
});

test.afterEach(async ({ request }) => {
  if (project.length > 0) {
    await request.delete(`/api/projects/${project}`);
  }
});

async function openModel(page: Page, model = "PlotV2"): Promise<void> {
  await page.goto(`/?project=${encodeURIComponent(project)}&model=${model}`);
  await expect(page.getByTestId("library-item-DCMotor")).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByTestId("run-button")).toBeEnabled();
}

async function runToDone(page: Page): Promise<void> {
  await page.getByTestId("run-button").click();
  await expect(page.getByTestId("run-status")).toHaveAttribute(
    "data-status",
    "done",
    { timeout: 30_000 },
  );
}

async function addFromBrowser(page: Page, id: string): Promise<void> {
  await page.getByRole("tab", { name: "Signals" }).click();
  await expect(page.getByTestId("signal-browser")).toBeVisible();
  await page.locator(`[data-signal-id="${id}"]`).dblclick();
}

async function addPanel(page: Page): Promise<void> {
  await page.getByRole("tab", { name: "Plots" }).click();
  await page.getByTestId("add-plot-panel").click();
}

async function dragRange(
  page: Page,
  chartIndex: number,
  from: number,
  to: number,
): Promise<void> {
  const over = page.locator('[data-testid="plot-chart"] .u-over').nth(chartIndex);
  const box = await over.boundingBox();
  if (box === null) {
    throw new Error("the plot has no measurable area");
  }
  const y = box.y + box.height * 0.45;
  await page.mouse.move(box.x + box.width * from, y);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * to, y, { steps: 12 });
  await page.mouse.up();
}

test("panels share the global inspect cursor", async ({ page }) => {
  await openModel(page);
  await runToDone(page);

  await addFromBrowser(page, "Synthetic/sine");
  await addFromBrowser(page, "Synthetic/step");
  await addPanel(page);
  await addFromBrowser(page, "Synthetic/counter");
  await page.getByRole("tab", { name: "Plots" }).click();

  await expect(page.getByTestId("plot-chart-panel")).toHaveCount(2);
  await expect(page.getByTestId("plot-chart")).toHaveCount(2);

  const over = page.locator('[data-testid="plot-chart"] .u-over').first();
  const box = await over.boundingBox();
  if (box === null) {
    throw new Error("the first plot has no measurable area");
  }
  await page.mouse.move(box.x + box.width * 0.55, box.y + box.height * 0.45);

  const inspect = page.getByTestId("plot-inspect-time");
  await expect.poll(async () => inspect.textContent()).toMatch(/\d/);

  const first = page.getByTestId("legend-time").first();
  await expect.poll(async () => first.textContent()).toMatch(/t = [\d.]+ s/);
  const timeText = (await first.textContent()) ?? "";
  // cursor.sync moves the second panel's cursor to the same time; its legend
  // must read the same value.
  await expect(page.getByTestId("legend-time").nth(1)).toHaveText(timeText);
  expect(await inspect.textContent()).toContain(
    timeText.replace("t = ", "").replace(" s", ""),
  );
});

test("targets panels, renames one and detaches the plots into a window", async ({
  page,
}) => {
  await openModel(page);
  await runToDone(page);

  // A second panel, then route each signal through the target dropdown.
  await addPanel(page);
  await page.getByRole("tab", { name: "Signals" }).click();
  const target = page.getByTestId("plot-target-select");
  await target.selectOption({ label: "Panel 1" });
  await page.locator('[data-signal-id="Synthetic/sine"]').dblclick();
  await target.selectOption({ label: "Panel 2" });
  await page.locator('[data-signal-id="Synthetic/step"]').dblclick();
  await page.getByRole("tab", { name: "Plots" }).click();

  await expect(page.getByTestId("plot-chart-panel")).toHaveCount(2);
  const title = page.getByTestId("plot-panel-title-1");
  await title.fill("Speed");
  await title.press("Enter");
  await expect(title).toHaveValue("Speed");

  const popupPromise = page.waitForEvent("popup");
  await page.getByTestId("detach-plot").click();
  const popup = await popupPromise;
  await expect(popup.getByTestId("plot-panel")).toBeVisible();
  await expect(popup.getByTestId("plot-chart-panel")).toHaveCount(2);
  await expect(popup.getByTestId("plot-panel-title-1")).toHaveValue("Speed");

  // The dock keeps the detached state and can bring the plots back.
  await expect(page.getByTestId("plots-detached")).toBeVisible();
  await popup.getByTestId("dock-plot").click();
  await expect.poll(async () => popup.isClosed()).toBe(true);
  await expect(page.getByTestId("plots-detached")).toHaveCount(0);
  await expect(page.getByTestId("plot-panel")).toBeVisible();
});

test("pins a finished run as dashed same-colour overlays", async ({ page }) => {
  await openModel(page);
  await runToDone(page);
  await addFromBrowser(page, "Synthetic/sine");
  await addFromBrowser(page, "Synthetic/step");
  await page.getByRole("tab", { name: "Plots" }).click();

  await page.getByTestId("pin-run").click();
  await expect(page.getByTestId("pinned-run")).toContainText(/Comparing with/);

  await runToDone(page);
  await expect
    .poll(async () => page.getByTestId("legend-item").count(), {
      timeout: 15_000,
    })
    .toBe(4);

  const compare = page.locator('[data-testid="legend-item"][data-compare="true"]');
  await expect(compare).toHaveCount(2);
  const current = page.locator('[data-testid="legend-item"][data-compare="false"]');
  await expect(current).toHaveCount(2);
  for (let index = 0; index < 2; index += 1) {
    const compareSwatch = compare.nth(index).locator(".plot-legend__swatch");
    const currentSwatch = current.nth(index).locator(".plot-legend__swatch");
    await expect(compareSwatch).toHaveClass(/plot-legend__swatch--dashed/);
    expect(await compareSwatch.evaluate((el) => (el as HTMLElement).style.color)).toBe(
      await currentSwatch.evaluate((el) => (el as HTMLElement).style.color),
    );
  }

  // The overlays survive a zoom (the pinned run is fetched for the new window).
  await dragRange(page, 0, 0.25, 0.7);
  await expect(compare).toHaveCount(2);
  await expect(page.getByTestId("pinned-run")).toBeVisible();

  await page.getByTestId("unpin-run").click();
  await expect(page.getByTestId("pinned-run")).toHaveCount(0);
  await expect(compare).toHaveCount(0);
});

function mockFrame(ids: readonly string[], points = 101): Buffer {
  const buffer = Buffer.alloc(8 + (ids.length + 1) * points * 8);
  buffer.writeUInt32LE(ids.length, 0);
  buffer.writeUInt32LE(points, 4);
  for (let index = 0; index < points; index += 1) {
    const t = index / (points - 1);
    buffer.writeDoubleLE(t, 8 + index * 8);
    ids.forEach((_id, signal) => {
      buffer.writeDoubleLE(
        Math.sin(t * 6 + signal),
        8 + ((signal + 1) * points + index) * 8,
      );
    });
  }
  return buffer;
}

function mockManifest(
  id: string,
  signals: { id: string; unit: string | null; kind: string; path: string; type: string }[],
  status: "running" | "done",
  points: number,
): Record<string, unknown> {
  return {
    id,
    model: "PlotV2",
    modelHash: "0".repeat(64),
    created: "2026-10-22T00:00:00Z",
    status,
    settings: {
      t_start: 0,
      t_end: 1,
      solver: "auto",
      reltol: 1e-6,
      abstol: 1e-8,
      max_step: null,
      output: { mode: "points", points },
      event_limit: 10000,
    },
    stats: {
      compile_s: 0.1,
      sim_s: 0.2,
      steps: points,
      events: 0,
      states: signals.length,
      equations: signals.length,
    },
    signals,
    time: { n: status === "done" ? points : 0, t0: 0, t1: 1 },
    diagnostics: [],
    layout: "columnar-f64-v1",
  };
}

test("plots a bond's effort/flow/power and an instance's outputs from the canvas menu", async ({
  page,
}) => {
  const signals = [
    { id: "Se/p.e", unit: "V", kind: "port", path: "Se", type: "Real" },
    { id: "Se/p.f", unit: "A", kind: "port", path: "Se", type: "Real" },
    { id: "Se/p.P", unit: "W", kind: "power", path: "Se", type: "Real" },
    { id: "Se/out", unit: null, kind: "output", path: "Se", type: "Real" },
  ];
  await page.route("**/api/projects/*/runs", async (route) => {
    if (route.request().method() !== "POST") {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ runId: "menu-run" }),
    });
  });
  await page.route(
    (url) => url.pathname.startsWith("/api/runs/menu-run"),
    async (route) => {
      const url = new URL(route.request().url());
      if (!url.pathname.endsWith("/data")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(mockManifest("menu-run", signals, "done", 101)),
        });
        return;
      }
      const ids = (url.searchParams.get("ids") ?? "").split(",").filter(Boolean);
      await route.fulfill({
        status: 200,
        contentType: "application/octet-stream",
        body: mockFrame(ids),
      });
    },
  );

  await openModel(page, "MenuPlot");
  await page.getByTestId("library-item-Se").dragTo(
    page.getByTestId("canvas-surface"),
    { targetPosition: { x: 100, y: 240 } },
  );
  await page.getByTestId("library-item-R").dragTo(
    page.getByTestId("canvas-surface"),
    { targetPosition: { x: 520, y: 240 } },
  );
  await expect(page.getByTestId("diagram-node")).toHaveCount(2);

  const from = page
    .locator('[data-testid="diagram-node"][data-node-name="Se"]')
    .locator('[data-port="p"]')
    .first();
  const to = page
    .locator('[data-testid="diagram-node"][data-node-name="R"]')
    .locator('[data-port="p"]')
    .first();
  const fromBox = await from.boundingBox();
  const toBox = await to.boundingBox();
  if (fromBox === null || toBox === null) {
    throw new Error("the bond ports are not visible");
  }
  await page.mouse.move(fromBox.x + fromBox.width / 2, fromBox.y + fromBox.height / 2);
  await page.mouse.down();
  await page.mouse.move(fromBox.x + 20, fromBox.y + 10, { steps: 3 });
  await page.mouse.move(toBox.x + toBox.width / 2, toBox.y + toBox.height / 2, {
    steps: 12,
  });
  await page.mouse.up();
  await expect(page.locator('[data-testid^="edge-"]')).toHaveCount(1);

  await runToDone(page);

  await page
    .locator('[data-testid^="edge-"]')
    .first()
    .dispatchEvent("contextmenu", {
      bubbles: true,
      button: 2,
      clientX: 600,
      clientY: 400,
    });
  await expect(page.getByTestId("canvas-menu")).toBeVisible();
  await expect(page.getByTestId("plot-effort")).toBeVisible();
  await expect(page.getByTestId("plot-flow")).toBeVisible();
  await expect(page.getByTestId("plot-power")).toBeVisible();
  await page.getByTestId("plot-effort").click();

  await page
    .locator('[data-testid="diagram-node"][data-node-name="Se"]')
    .dispatchEvent("contextmenu", {
      bubbles: true,
      button: 2,
      clientX: 300,
      clientY: 300,
    });
  await expect(page.getByTestId("plot-all-outputs")).toBeVisible();
  await page.getByTestId("plot-all-outputs").click();

  // The canvas action switches to the Plots tab so the new series are visible.
  await expect(page.getByRole("tab", { name: "Plots" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await expect(
    page.locator('[data-testid="legend-item"][data-signal-id="Se/p.e"]'),
  ).toHaveCount(1);
  await expect(
    page.locator('[data-testid="legend-item"][data-signal-id="Se/out"]'),
  ).toHaveCount(1);
  const href = await page.getByTestId("export-csv").getAttribute("href");
  expect(href).toContain("ids=Se%2Fp.e%2CSe%2Fout");
});

test("live tails autoscroll, pause on zoom and stop on run.done", async ({
  page,
}) => {
  const signals = [
    { id: "Live/a", unit: "V", kind: "state", path: "Live", type: "Real" },
    { id: "Live/b", unit: "V", kind: "state", path: "Live", type: "Real" },
    { id: "Live/c", unit: "V", kind: "state", path: "Live", type: "Real" },
  ];
  let finished = false;
  const totalPoints = 201;

  await page.route("**/api/projects/*/runs", async (route) => {
    if (route.request().method() !== "POST") {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ runId: "live-e2e" }),
    });
  });
  await page.route(
    (url) => url.pathname.startsWith("/api/runs/live-e2e"),
    async (route) => {
      const url = new URL(route.request().url());
      if (!url.pathname.endsWith("/data")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(
            mockManifest(
              "live-e2e",
              signals,
              finished ? "done" : "running",
              totalPoints,
            ),
          ),
        });
        return;
      }
      const ids = (url.searchParams.get("ids") ?? "").split(",").filter(Boolean);
      await route.fulfill({
        status: 200,
        contentType: "application/octet-stream",
        body: mockFrame(ids, totalPoints),
      });
    },
  );

  await page.routeWebSocket(
    (url) => url.pathname === "/ws/runs/live-e2e",
    (ws) => {
      let rows = 0;
      let timer: ReturnType<typeof setInterval> | null = null;
      ws.onMessage((message) => {
        const parsed = JSON.parse(String(message)) as { subscribe?: string[] };
        const ids = parsed.subscribe ?? [];
        if (ids.length === 0 || timer !== null) {
          return;
        }
        let sent = 0;
        const tick = (): void => {
          sent += 1;
          if (sent > 40) {
            if (timer !== null) {
              clearInterval(timer);
              timer = null;
            }
            finished = true;
            ws.send(
              JSON.stringify({
                method: "run.done",
                params: {
                  runId: "live-e2e",
                  status: "done",
                  stats: {
                    compile_s: 0.1,
                    sim_s: 2,
                    steps: rows,
                    events: 0,
                    states: ids.length,
                    equations: ids.length,
                  },
                  diagnostics: [],
                },
              }),
            );
            return;
          }
          const times = Array.from({ length: 10 }, (_, index) => {
            rows += index === 0 ? 0 : 1;
            return rows / 1000;
          });
          ws.send(
            JSON.stringify({
              method: "run.progress",
              params: { runId: "live-e2e", t: rows / 1000, rows },
            }),
          );
          ws.send(
            JSON.stringify({
              method: "run.tail",
              params: {
                runId: "live-e2e",
                ids,
                t0: times[0],
                t1: times[times.length - 1],
                time: times,
                values: ids.map((_id, signal) =>
                  times.map((t) => Math.sin(t * 20 + signal)),
                ),
              },
            }),
          );
        };
        timer = setInterval(tick, 50);
        tick();
      });
      ws.onClose(() => {
        if (timer !== null) {
          clearInterval(timer);
          timer = null;
        }
      });
    },
  );

  await openModel(page, "LiveV2");
  await page.getByTestId("run-button").click();
  await expect(page.getByTestId("run-status")).toHaveAttribute(
    "data-status",
    "running",
    { timeout: 15_000 },
  );

  await page.getByRole("tab", { name: "Signals" }).click();
  await expect(page.getByTestId("signal-browser")).toBeVisible();
  await page.getByTestId("plot-all-signals").click();
  await page.getByRole("tab", { name: "Plots" }).click();

  const badge = page.getByTestId("live-badge");
  await expect(badge).toBeVisible({ timeout: 15_000 });
  await expect(badge).toHaveAttribute("data-following", "true");
  await expect
    .poll(async () =>
      Number(
        (await page.getByTestId("plot-chart").getAttribute("data-points")) ?? "0",
      ),
    )
    .toBeGreaterThan(0);

  // A zoom pauses autoscroll and offers Follow live; tails keep arriving.
  await dragRange(page, 0, 0.2, 0.6);
  await expect(badge).toHaveAttribute("data-following", "false");
  await page.getByTestId("follow-live").click();
  await expect(badge).toHaveAttribute("data-following", "true");

  await expect(page.getByTestId("run-status")).toHaveAttribute(
    "data-status",
    "done",
    { timeout: 30_000 },
  );
  await expect(page.getByTestId("live-badge")).toHaveCount(0);
  await expect
    .poll(async () =>
      Number(
        (await page.getByTestId("plot-chart").getAttribute("data-points")) ?? "0",
      ),
    )
    .toBe(totalPoints);
  await expect(page.getByTestId("plot-run-status")).toHaveAttribute(
    "data-status",
    "done",
  );
});
