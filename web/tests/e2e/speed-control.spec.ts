import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

/**
 * X2.5 acceptance: the `speed-control` model of the `dc-motor` sample (plan 9.1, M2).
 *
 * 1. create the `dc-motor` example project through `POST /api/projects`;
 * 2. open its `speed-control` model: the iconic DC motor closed by a 1 ms discrete PI on
 *    the SpeedSensor;
 * 3. press Run, wait for `done`;
 * 4. plot the measured speed and the voltage command and read two cursor positions:
 *    at t = 0.0105 s the command is at the +24 V clamp, and at t = 0.1 s the speed is
 *    100 +- 1 rad/s while the command has dropped to the ~5 V steady value.
 *
 * The spec starts its own backend and the real Julia worker on a free port unless the suite
 * was already started with `BGSIM_E2E_REAL=1`; it deletes the copied project and the
 * temporary projects root afterwards. The run reports no diagnostics.
 */

test.describe.configure({ timeout: 300_000 });

const repoRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../..",
);

let server: ChildProcess | null = null;
let spawnError: Error | null = null;
let serverUrl = "";
let projectsRoot = "";
let project = "";

function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const socket = net.createServer();
    socket.unref();
    socket.on("error", reject);
    socket.listen(0, "127.0.0.1", () => {
      const address = socket.address();
      const port = typeof address === "object" && address !== null ? address.port : 0;
      socket.close(() => resolve(port));
    });
  });
}

async function waitForWorker(url: string, child: ChildProcess | null): Promise<void> {
  const deadline = Date.now() + 240_000;
  let last = "no answer";
  while (Date.now() < deadline) {
    if (spawnError !== null) {
      throw new Error(`the backend did not start: ${spawnError.message}`);
    }
    if (child !== null && child.exitCode !== null) {
      throw new Error(`the backend exited with code ${child.exitCode}`);
    }
    try {
      const response = await fetch(`${url}/api/health`, {
        signal: AbortSignal.timeout(3_000),
      });
      if (response.ok) {
        const health = (await response.json()) as { worker?: string };
        last = `worker state ${JSON.stringify(health.worker)}`;
        if (health.worker === "ready") {
          return;
        }
      } else {
        last = `GET /api/health -> ${response.status}`;
      }
    } catch (error) {
      last = error instanceof Error ? error.message : String(error);
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`the real worker did not become ready (${last})`);
}

test.beforeAll(async () => {
  test.setTimeout(360_000);
  if (process.env.BGSIM_E2E_REAL === "1") {
    serverUrl = "http://127.0.0.1:8765";
    await waitForWorker(serverUrl, null);
    return;
  }

  const port = await freePort();
  serverUrl = `http://127.0.0.1:${port}`;
  projectsRoot = mkdtempSync(path.join(os.tmpdir(), "bgsim-speed-control-"));
  const environment: NodeJS.ProcessEnv = {
    ...process.env,
    BGSIM_PORT_HTTP: String(port),
    BGSIM_PROJECTS_ROOT: projectsRoot,
    BGSIM_REPO: repoRoot,
  };
  // This spec always wants Julia, even when the fake-worker suite started us.
  delete environment.BGSIM_FAKE_WORKER;

  server = spawn(process.platform === "win32" ? "uv.exe" : "uv", ["run", "bgsim"], {
    cwd: repoRoot,
    env: environment,
    stdio: "ignore",
  });
  server.on("error", (error) => {
    spawnError = error;
  });
  await waitForWorker(serverUrl, server);
});

test.afterAll(async () => {
  if (server !== null) {
    const child = server;
    server = null;
    if (process.platform === "win32" && child.pid !== undefined) {
      spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], {
        stdio: "ignore",
      });
    } else {
      child.kill("SIGTERM");
    }
  }
  if (projectsRoot.length > 0) {
    rmSync(projectsRoot, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
    projectsRoot = "";
  }
});

test.beforeEach(async ({ request }) => {
  project = `x25-speed-control-${Date.now()}-${test.info().workerIndex}`;
  const created = await request.post(`${serverUrl}/api/projects`, {
    data: { name: project, example: "dc-motor" },
  });
  expect(created.status(), await created.text()).toBe(201);
});

test.afterEach(async ({ request }) => {
  if (project.length > 0) {
    await request.delete(`${serverUrl}/api/projects/${project}`);
    project = "";
  }
});

function node(page: Page, name: string) {
  return page.locator(`[data-testid="diagram-node"][data-node-name="${name}"]`);
}

async function plotSignal(page: Page, signalId: string): Promise<void> {
  const item = page.locator(
    `[data-testid="signal-item"][data-signal-id="${signalId}"]`,
  );
  await expect(item).toHaveCount(1);
  await item.dblclick();
}

/** The number a legend value renders, without the unit suffix. */
async function legendNumber(page: Page, signalId: string): Promise<number> {
  const value = page.locator(
    `[data-testid="legend-item"][data-signal-id="${signalId}"] .plot-legend__value`,
  );
  const text = (await value.textContent()) ?? "";
  const match = /[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?/.exec(text);
  expect(
    match,
    `the legend of ${signalId} shows a number, got ${JSON.stringify(text)}`,
  ).not.toBeNull();
  return Number(match?.[0]);
}

/** Move the plot cursor to the data time `t` (the x scale is the run window). */
async function cursorAt(page: Page, t: number): Promise<void> {
  const chart = page.getByTestId("plot-chart");
  const over = chart.locator(".u-over");
  await expect(over).toBeVisible();
  const xMin = Number(await chart.getAttribute("data-x-min"));
  const xMax = Number(await chart.getAttribute("data-x-max"));
  expect(Number.isFinite(xMin) && Number.isFinite(xMax)).toBe(true);
  const area = await over.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    return { x: rect.left, y: rect.top, width: rect.width, height: rect.height };
  });
  if (!(area.width > 0) || !(area.height > 0)) {
    throw new Error("the plot has no measurable area");
  }
  const targetX = Math.round(
    area.x + ((t - xMin) / (xMax - xMin)) * area.width,
  );
  await page.mouse.move(targetX, Math.round(area.y + area.height * 0.5));
  await expect(page.getByTestId("legend-time")).not.toHaveText("—");
}

test("opens speed-control, runs it and reads the 24 V clamp and the 100 rad/s plateau", async ({
  page,
  request,
}) => {
  await expect
    .poll(
      async () => {
        const response = await request.get(`${serverUrl}/api/health`);
        if (!response.ok()) {
          return `http ${response.status()}`;
        }
        return ((await response.json()) as { worker: string }).worker;
      },
      { message: "the worker becomes ready", timeout: 60_000 },
    )
    .toBe("ready");

  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.goto(
    `${serverUrl}/?project=${encodeURIComponent(project)}&model=speed-control`,
  );
  await expect(page.getByTestId("canvas-surface")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("run-button")).toBeEnabled();

  // The iconic motor plus the sampled loop: reference, error, PID, source, motor, sensor.
  for (const name of ["Step1", "Err", "PID1", "V1", "Motor1", "WmSens"]) {
    await expect(node(page, name)).toBeVisible();
  }

  await page.getByTestId("run-button").click();
  const runStatus = page.getByTestId("run-status");
  await expect(runStatus).toHaveAttribute("data-status", "done", {
    timeout: 240_000,
  });
  await expect(runStatus).toContainText(/done in/i);

  await page.getByRole("tab", { name: "Signals" }).click();
  await expect(page.getByTestId("signal-browser")).toBeVisible();
  await plotSignal(page, "WmSens/y");
  await plotSignal(page, "PID1/y");

  await page.getByRole("tab", { name: "Plots" }).click();
  const chart = page.getByTestId("plot-chart");
  await expect(chart).toBeVisible();
  await expect(chart).toHaveAttribute("data-series-count", "2");
  await expect(page.getByTestId("legend-item")).toHaveCount(2);
  await expect
    .poll(
      async () => Number((await chart.getAttribute("data-points")) ?? "0"),
      { message: "the run's signals are loaded", timeout: 30_000 },
    )
    .toBeGreaterThan(0);

  // t = 0.0105 s: the step at 0.01 s has been sampled and the PI commands the +24 V clamp.
  await cursorAt(page, 0.0105);
  const clamped = await legendNumber(page, "PID1/y");
  expect(clamped).toBeGreaterThan(23.9);
  expect(clamped).toBeLessThanOrEqual(24.0);

  // t = 0.1 s: the speed has reached 100 +- 1 rad/s and the command is back at ~5 V.
  await cursorAt(page, 0.1);
  await expect
    .poll(async () => page.getByTestId("legend-time").textContent(), {
      timeout: 10_000,
    })
    .toMatch(/t = (0\.09|0\.1|0\.10)/);
  const speed = await legendNumber(page, "WmSens/y");
  const voltage = await legendNumber(page, "PID1/y");
  expect(Math.abs(speed - 100)).toBeLessThanOrEqual(1);
  expect(voltage).toBeGreaterThan(0);
  expect(voltage).toBeLessThanOrEqual(24);
});
