/**
 * The two plotting budgets of plan 7.5 (W2.4):
 *
 *  1. 20 signals × 1e6 points: after the zoom/pan data arrives, the uPlot
 *     re-render must be under 50 ms.
 *  2. 60 fps while live-streaming 10 signals over the run socket.
 *
 * The run is mocked at the HTTP/WebSocket boundary: the POST, the manifest and
 * the decimated `/data` answer come from `page.route`, and the live tails come
 * from `page.routeWebSocket` at the contract's 20 messages/s. The 1e6-point
 * show-all frame is built inside the page: a 168 MB `route.fulfill` body
 * exceeds the CDP message limit and crashes the browser, so the init script
 * replaces only the `px=0` `/data` response with the same binary layout. Every
 * measured render is the real UPlotChart render; `data-render-ms` is the time
 * from `chart.setData` to the uPlot draw microtask (UPlotChart.tsx).
 *
 * Run with `npx playwright test tests/perf` from `web/`.
 */

import { expect, test, type Page } from "@playwright/test";

test.describe.configure({ timeout: 180_000 });

const POINTS = 1_000_000;
const SIGNALS = 20;
const LIVE_SIGNALS = 10;
const BUDGET_MS = 50;
const TARGET_FPS = 60;

let project = "";

test.beforeEach(async ({ page }) => {
  project = `w24-perf-${Date.now()}-${test.info().workerIndex}`;
  await page.setViewportSize({ width: 1600, height: 1000 });
});

test.afterEach(async ({ request }) => {
  if (project.length > 0) {
    await request.delete(`/api/projects/${project}`);
  }
});

function signalList(count: number): {
  id: string;
  unit: string | null;
  kind: "state";
  path: string;
  type: "Real";
}[] {
  return Array.from({ length: count }, (_, index) => ({
    id: `Perf/s${index}`,
    unit: "V",
    kind: "state" as const,
    path: "Perf",
    type: "Real" as const,
  }));
}

function manifest(
  count: number,
  options: { id?: string; status: "running" | "done"; n: number; t1: number },
): Record<string, unknown> {
  return {
    id: options.id ?? "perf-run",
    model: "PerfModel",
    modelHash: "0".repeat(64),
    created: "2026-10-22T00:00:00Z",
    status: options.status,
    settings: {
      t_start: 0,
      t_end: options.t1,
      solver: "auto",
      reltol: 1e-6,
      abstol: 1e-8,
      max_step: null,
      output: { mode: "points", points: POINTS },
      event_limit: 10000,
    },
    stats: {
      compile_s: 0.1,
      sim_s: 1,
      steps: options.n,
      events: 0,
      states: count,
      equations: count,
    },
    signals: signalList(count),
    time: { n: options.n, t0: 0, t1: options.t1 },
    diagnostics: [],
    layout: "columnar-f64-v1",
  };
}

/** One `/data` frame: u32 n_signals | u32 n_points | time | columns. */
function frame(
  ids: readonly string[],
  points: number,
  t0: number,
  t1: number,
): Buffer {
  const buffer = Buffer.alloc(8 + (ids.length + 1) * points * 8);
  buffer.writeUInt32LE(ids.length, 0);
  buffer.writeUInt32LE(points, 4);
  for (let index = 0; index < points; index += 1) {
    const t = points === 1 ? t0 : t0 + ((t1 - t0) * index) / (points - 1);
    buffer.writeDoubleLE(t, 8 + index * 8);
  }
  ids.forEach((_id, signal) => {
    for (let index = 0; index < points; index += 1) {
      const value = Math.sin((index / Math.max(points - 1, 1)) * 8 + signal);
      buffer.writeDoubleLE(
        value,
        8 + ((signal + 1) * points + index) * 8,
      );
    }
  });
  return buffer;
}

/**
 * Make the browser answer a raw `/data?px=0` request with the plan's
 * 20-signal × 1e6-point frame. Bypassing Playwright's route body is the only
 * way to keep a 168 MB frame inside the browser process.
 */
async function installRawFrame(page: Page, signals: number): Promise<void> {
  await page.addInitScript(
    ({ points, count }) => {
      const original = window.fetch.bind(window);
      window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
        const url =
          typeof input === "string"
            ? input
            : input instanceof URL
              ? input.href
              : input.url;
        if (!url.includes("/data?") || !/[?&]px=0(?:&|$)/.test(url)) {
          return original(input, init);
        }
        const params = new URL(url, window.location.href).searchParams;
        const ids = (params.get("ids") ?? "").split(",").filter(Boolean);
        const nSignals = ids.length > 0 ? ids.length : count;
        const timeStart = Number(params.get("t0") ?? "0");
        const timeEnd = Number(params.get("t1") ?? "10");
        const buffer = new ArrayBuffer(8 + (nSignals + 1) * points * 8);
        const view = new DataView(buffer);
        view.setUint32(0, nSignals, true);
        view.setUint32(4, points, true);
        const floats = new Float64Array(buffer, 8);
        for (let index = 0; index < points; index += 1) {
          floats[index] =
            timeStart + ((timeEnd - timeStart) * index) / Math.max(points - 1, 1);
        }
        for (let signal = 0; signal < nSignals; signal += 1) {
          const offset = (signal + 1) * points;
          for (let index = 0; index < points; index += 1) {
            floats[offset + index] = Math.sin(index * 0.001 + signal);
          }
        }
        return new Response(buffer, {
          status: 200,
          headers: { "content-type": "application/octet-stream" },
        });
      };
    },
    { points: POINTS, count: signals },
  );
}

async function openModel(page: Page, model: string): Promise<void> {
  await page.goto(`/?project=${encodeURIComponent(project)}&model=${model}`);
  await expect(page.getByTestId("library-item-DCMotor")).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByTestId("run-button")).toBeEnabled();
}

async function plotAll(page: Page): Promise<void> {
  await page.getByRole("tab", { name: "Signals" }).click();
  await expect(page.getByTestId("signal-browser")).toBeVisible();
  await page.getByTestId("plot-all-signals").click();
  await page.getByRole("tab", { name: "Plots" }).click();
  await expect(page.getByTestId("plot-chart")).toBeVisible();
}

function chart(page: Page) {
  return page.locator('[data-testid="plot-chart"]').first();
}

async function dragRange(
  page: Page,
  from: number,
  to: number,
): Promise<void> {
  const over = page.locator('[data-testid="plot-chart"] .u-over').first();
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

async function renderSnapshot(
  page: Page,
): Promise<{ seq: number; ms: number; points: number; at: number; xMax: number }> {
  return await chart(page).evaluate((element) => {
    const host = element as HTMLElement;
    return {
      seq: Number(host.dataset.renderSeq ?? "0"),
      ms: Number(host.dataset.renderMs ?? "0"),
      points: Number(host.dataset.points ?? "0"),
      at: Number(host.dataset.renderAt ?? "0"),
      xMax: Number(host.dataset.xMax ?? "0"),
    };
  });
}

/** Response-end to uPlot draw for the latest zoomed `/data` answer. */
async function responseToRender(page: Page): Promise<number | null> {
  return await page.evaluate(() => {
    const host = document.querySelector<HTMLElement>(
      '[data-testid="plot-chart"]',
    );
    const renderAt = Number(host?.dataset.renderAt ?? "0");
    if (!Number.isFinite(renderAt) || renderAt <= 0) {
      return null;
    }
    const entries = performance
      .getEntriesByType("resource")
      .filter((entry): entry is PerformanceResourceTiming =>
        entry instanceof PerformanceResourceTiming,
      )
      .filter((entry) => {
        if (!entry.name.includes("/data?")) {
          return false;
        }
        const px = Number(new URL(entry.name).searchParams.get("px") ?? "0");
        return px > 0;
      });
    const last = entries.at(-1);
    if (last === undefined) {
      return null;
    }
    return Math.max(0, renderAt - last.responseEnd);
  });
}

test("20 signals x 1e6 points: zoom and pan re-render under 50 ms", async ({
  page,
}) => {
  await installRawFrame(page, SIGNALS);

  await page.route("**/api/projects/*/runs", async (route) => {
    if (route.request().method() !== "POST") {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ runId: "perf-run" }),
    });
  });
  await page.route(
    (url) => url.pathname.startsWith("/api/runs/perf-run"),
    async (route) => {
      const url = new URL(route.request().url());
      if (!url.pathname.endsWith("/data")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(
            manifest(SIGNALS, { status: "done", n: POINTS, t1: 10 }),
          ),
        });
        return;
      }
      const ids = (url.searchParams.get("ids") ?? "")
        .split(",")
        .filter(Boolean);
      const px = Number(url.searchParams.get("px") ?? "0");
      const t0 = Number(url.searchParams.get("t0") ?? "0");
      const t1 = Number(url.searchParams.get("t1") ?? "10");
      const points = Math.min(Math.max(2 * px, 200), 4800);
      await route.fulfill({
        status: 200,
        contentType: "application/octet-stream",
        body: frame(ids, points, t0, t1),
      });
    },
  );

  await openModel(page, "PerfZoom");
  await page.getByTestId("run-button").click();
  await expect(page.getByTestId("plot-run-status")).toHaveAttribute(
    "data-status",
    "done",
    { timeout: 30_000 },
  );

  await plotAll(page);
  await expect(chart(page)).toHaveAttribute("data-series-count", String(SIGNALS));

  // The show-all answer is the 20 x 1e6 frame. Wait for the app to finish
  // parsing and drawing it; the render time is reported, not asserted: the
  // plan's 50 ms budget is for the decimated zoom/pan answer.
  await expect
    .poll(async () => (await renderSnapshot(page)).points, { timeout: 120_000 })
    .toBe(POINTS);
  const raw = await renderSnapshot(page);
  console.warn(
    `[perf] raw 20 x 1e6 draw: ${raw.ms.toFixed(1)} ms (points=${raw.points})`,
  );

  const results: number[] = [];
  const endToEnd: number[] = [];
  for (let step = 0; step < 2; step += 1) {
    const before = await renderSnapshot(page);
    if (step === 0) {
      await dragRange(page, 0.2, 0.65);
    } else {
      // Pan inside the zoomed window; uPlot still reports a new x scale.
      await dragRange(page, 0.45, 0.8);
    }
    await expect
      .poll(async () => (await renderSnapshot(page)).seq, { timeout: 30_000 })
      .toBeGreaterThan(before.seq);
    const after = await renderSnapshot(page);
    expect(after.points).toBeGreaterThan(0);
    expect(after.points).toBeLessThan(POINTS);
    const afterData = await responseToRender(page);
    results.push(after.ms);
    if (afterData !== null) {
      endToEnd.push(afterData);
    }
    console.warn(
      `[perf] ${step === 0 ? "zoom" : "pan"} re-render: ` +
        `${after.ms.toFixed(1)} ms draw, ` +
        `${afterData === null ? "n/a" : `${afterData.toFixed(1)} ms`} after the ` +
        `response arrived (${after.points} points)`,
    );
  }

  expect(Math.max(...results)).toBeLessThan(BUDGET_MS);
  if (endToEnd.length > 0) {
    // The plan's budget is the uPlot re-render. The response-to-draw number is
    // reported too; the first one includes collecting the 168 MB raw frame, so
    // it is a sanity bound rather than the 50 ms budget.
    expect(Math.max(...endToEnd)).toBeLessThan(500);
  }
});

test("10 live signals stream at 60 fps", async ({ page }) => {
  const live = {
    tails: 0,
    rows: 0,
    timer: null as ReturnType<typeof setInterval> | null,
  };
  const tailPoints = 20;
  const intervalMs = 50;
  const totalPoints = 2001;

  await page.route("**/api/projects/*/runs", async (route) => {
    if (route.request().method() !== "POST") {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ runId: "perf-live" }),
    });
  });

  let finished = false;
  await page.route(
    (url) => url.pathname.startsWith("/api/runs/perf-live"),
    async (route) => {
      const url = new URL(route.request().url());
      if (!url.pathname.endsWith("/data")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(
            manifest(LIVE_SIGNALS, {
              id: "perf-live",
              status: finished ? "done" : "running",
              n: finished ? totalPoints : 0,
              t1: 4,
            }),
          ),
        });
        return;
      }
      const ids = (url.searchParams.get("ids") ?? "")
        .split(",")
        .filter(Boolean);
      await route.fulfill({
        status: 200,
        contentType: "application/octet-stream",
        body: frame(ids, totalPoints, 0, 4),
      });
    },
  );

  // The backend sends at most 20 tails per second (P2.1); this fake follows the
  // same contract so the measurement is the render cost, not a faster stream.
  await page.routeWebSocket(
    (url) => url.pathname === "/ws/runs/perf-live",
    (ws) => {
      let time = 0;
      let sent = 0;
      ws.onMessage((message) => {
        let subscribe: string[] | null;
        try {
          const parsed = JSON.parse(String(message)) as { subscribe?: string[] };
          subscribe = Array.isArray(parsed.subscribe) ? parsed.subscribe : [];
        } catch {
          return;
        }
        if (subscribe === null || subscribe.length === 0 || live.timer !== null) {
          return;
        }
        const ids = [...subscribe];
        const sendTail = (): void => {
          if (sent >= 100) {
            if (live.timer !== null) {
              clearInterval(live.timer);
              live.timer = null;
            }
            ws.send(
              JSON.stringify({
                method: "run.done",
                params: {
                  runId: "perf-live",
                  status: "done",
                  stats: {
                    compile_s: 0.1,
                    sim_s: 5,
                    steps: live.rows,
                    events: 0,
                    states: LIVE_SIGNALS,
                    equations: LIVE_SIGNALS,
                  },
                  diagnostics: [],
                },
              }),
            );
            finished = true;
            try {
              ws.close();
            } catch {
              /* the page may already have closed the socket */
            }
            return;
          }
          sent += 1;
          live.tails = sent;
          const first = live.rows;
          live.rows += tailPoints;
          time += 0.01 * tailPoints;
          const times = Array.from(
            { length: tailPoints },
            (_, index) => time - 0.01 * (tailPoints - 1 - index),
          );
          const values = ids.map((_id, signal) =>
            times.map((_t, index) => Math.sin((first + index) * 0.02 + signal)),
          );
          ws.send(
            JSON.stringify({
              method: "run.progress",
              params: { runId: "perf-live", t: time, rows: live.rows },
            }),
          );
          ws.send(
            JSON.stringify({
              method: "run.tail",
              params: {
                runId: "perf-live",
                ids,
                t0: times[0],
                t1: times[times.length - 1],
                time: times,
                values,
              },
            }),
          );
        };
        live.timer = setInterval(sendTail, intervalMs);
        sendTail();
      });
      ws.onClose(() => {
        if (live.timer !== null) {
          clearInterval(live.timer);
          live.timer = null;
        }
      });
    },
  );

  await openModel(page, "PerfLive");
  await page.getByTestId("run-button").click();
  await expect(page.getByTestId("run-status")).toHaveAttribute(
    "data-status",
    "running",
    { timeout: 15_000 },
  );

  await plotAll(page);
  await expect(page.getByTestId("live-badge")).toBeVisible({
    timeout: 15_000,
  });
  await expect
    .poll(async () => (await renderSnapshot(page)).points, { timeout: 15_000 })
    .toBeGreaterThan(0);
  await expect(chart(page)).toHaveAttribute("data-autoscroll", "true");

  const before = await renderSnapshot(page);
  const tailsBefore = live.tails;
  const fps = await page.evaluate(async () => {
    return await new Promise<number>((resolve) => {
      let frames = 0;
      const start = performance.now();
      const tick = (): void => {
        frames += 1;
        const elapsed = performance.now() - start;
        if (elapsed >= 2000) {
          resolve((frames * 1000) / elapsed);
        } else {
          requestAnimationFrame(tick);
        }
      };
      requestAnimationFrame(tick);
    });
  });
  const after = await renderSnapshot(page);
  const tailsAfter = live.tails;
  const measuredRate = (tailsAfter - tailsBefore) / 2;

  console.warn(
    `[perf] live 10 signals: ${fps.toFixed(1)} fps, ` +
      `${measuredRate.toFixed(1)} tail messages/s, ` +
      `${before.points} -> ${after.points} points`,
  );

  expect(fps).toBeGreaterThanOrEqual(TARGET_FPS - 2);
  expect(measuredRate).toBeGreaterThanOrEqual(15);
  expect(measuredRate).toBeLessThanOrEqual(25);
  expect(after.points).toBeGreaterThan(before.points);
  // Autoscroll: the visible x window follows the appended points.
  expect(after.xMax).toBeGreaterThan(before.xMax);
  await expect(chart(page)).toHaveAttribute("data-autoscroll", "true");

  await expect(page.getByTestId("run-status")).toHaveAttribute(
    "data-status",
    "done",
    { timeout: 30_000 },
  );
  await expect(page.getByTestId("live-badge")).toHaveCount(0);
  expect(live.timer).toBeNull();
});
