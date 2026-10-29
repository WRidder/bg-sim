import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

/**
 * X2.5 acceptance: the `hydraulic-servo` sample (plan 9.6).
 *
 * 1. create a copy of the sample through `POST /api/projects {name, example}`;
 * 2. open the model and assert the hydraulic plant (the pressure source, the tank, the
 *    4/3 valve subsystem, the cylinder, the rod 1-junction with the mass and damper, the
 *    position sensor and the 1 ms PID);
 * 3. press Run, wait for `done`;
 * 4. plot the rod position and the two chamber pressures through the `PSensA/y` /
 *    `PSensB/y` taps and read the three legends at t = 1 s: the rod is on the 0.1 m
 *    reference and both pressures are below the 100.5 bar supply bound.
 *
 * Like the other real-plant specs this needs Julia (the fake worker answers every run from
 * its fixed `Synthetic/*` fixture). It starts a backend and the real worker on a free port
 * unless the suite was already started with `BGSIM_E2E_REAL=1`, and deletes the copied
 * project and the temporary projects root in `afterAll`. The expected run reports only the
 * structural W202 of the valve's series port sensors.
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
    serverUrl = `http://127.0.0.1:${process.env.BGSIM_E2E_PORT ?? "8765"}`;
    await waitForWorker(serverUrl, null);
    return;
  }

  const port = await freePort();
  serverUrl = `http://127.0.0.1:${port}`;
  projectsRoot = mkdtempSync(path.join(os.tmpdir(), "bgsim-hydraulic-servo-"));
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
  project = `x25-hydraulic-servo-${Date.now()}-${test.info().workerIndex}`;
  const created = await request.post(`${serverUrl}/api/projects`, {
    data: { name: project, example: "hydraulic-servo" },
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

test("opens the hydraulic servo, runs it and reads the rod and both chamber pressures at 1 s", async ({
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
    `${serverUrl}/?project=${encodeURIComponent(project)}&model=hydraulic-servo`,
  );
  await expect(page.getByTestId("canvas-surface")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("run-button")).toBeEnabled();

  // The hydraulic plant: supply, tank, the valve subsystem, the cylinder, the rod
  // 1-junction with its inertia and damper, the position sensor and the PID.
  for (const name of ["PS", "TK", "Valve", "Cyl", "Jrod", "IM", "RD", "XS", "PID1"]) {
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
  await plotSignal(page, "XS/y");
  await plotSignal(page, "PSensA/y");
  await plotSignal(page, "PSensB/y");

  await page.getByRole("tab", { name: "Plots" }).click();
  const chart = page.getByTestId("plot-chart");
  await expect(chart).toBeVisible();
  await expect(chart).toHaveAttribute("data-series-count", "3");
  await expect(page.getByTestId("legend-item")).toHaveCount(3);
  await expect
    .poll(
      async () => Number((await chart.getAttribute("data-points")) ?? "0"),
      { message: "the run's signals are loaded", timeout: 30_000 },
    )
    .toBeGreaterThan(0);

  // The run covers 1.5 s and the reference step lands at 0.1 s: at t = 1 s the rod is on
  // the 0.1 m reference and both chambers are below the 100.5 bar supply bound.
  await cursorAt(page, 1.0);
  await expect
    .poll(async () => page.getByTestId("legend-time").textContent(), {
      timeout: 10_000,
    })
    .toMatch(/t = (0\.9|1|1\.0)/);

  const position = await legendNumber(page, "XS/y");
  const pressureA = await legendNumber(page, "PSensA/y");
  const pressureB = await legendNumber(page, "PSensB/y");
  expect(Math.abs(position - 0.1)).toBeLessThan(0.01);
  expect(pressureA).toBeGreaterThan(0);
  expect(pressureA).toBeLessThanOrEqual(100.5e5);
  expect(pressureB).toBeGreaterThan(0);
  expect(pressureB).toBeLessThanOrEqual(100.5e5);
});
