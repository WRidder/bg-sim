import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

/**
 * X2.6 acceptance: the `industrial-servo` sample (plan 9.6b).
 *
 * 1. create a copy of the sample through `POST /api/projects {name, example}`;
 * 2. open the `baseline` variant, assert the dq bond-graph nodes and the three firmware
 *    blocks, press Run and wait for `done`;
 * 3. plot the phase current (`Iphase/y`) and the motor speed (`WmSens/p.f`) and read the
 *    legends at about t = 1.15 s: the drive holds position under the 2 N m load, so the
 *    speed is ~0 and the q current is ~4.17 A;
 * 4. switch to the `full` variant through the Open dialog (the project exposes its five
 *    variants as models/tabs), run it, plot the same two signals and check the combined
 *    switching + two-mass + 24-bit encoder run again.
 *
 * The fake worker answers every run from its fixed `Synthetic/*` fixture, so it cannot
 * serve the signals this sample is about. The spec starts one real worker on a free port
 * unless the suite was started with `BGSIM_E2E_REAL=1` (the real-worker pass on 8765), and
 * deletes the copied project and the temporary projects root in `afterAll`. The run reports
 * only W205 (the dimensionless Generic bond island), which is expected.
 */

test.describe.configure({ timeout: 600_000 });

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
  const deadline = Date.now() + 180_000;
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
  // A cold Julia worker (MTK precompilation plus the first compile) needs more than 30 s.
  test.setTimeout(600_000);
  if (process.env.BGSIM_E2E_REAL === "1") {
    serverUrl = `http://127.0.0.1:${process.env.BGSIM_E2E_PORT ?? "8765"}`;
    await waitForWorker(serverUrl, null);
    return;
  }

  const port = await freePort();
  serverUrl = `http://127.0.0.1:${port}`;
  projectsRoot = mkdtempSync(path.join(os.tmpdir(), "bgsim-industrial-servo-"));
  const environment: NodeJS.ProcessEnv = {
    ...process.env,
    BGSIM_PORT_HTTP: String(port),
    BGSIM_PROJECTS_ROOT: projectsRoot,
    BGSIM_REPO: repoRoot,
  };
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
  project = `x26-industrial-servo-${Date.now()}-${test.info().workerIndex}`;
  const created = await request.post(`${serverUrl}/api/projects`, {
    data: { name: project, example: "industrial-servo" },
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
  const value = page.locator(`[data-testid="legend-item"][data-signal-id="${signalId}"] .plot-legend__value`);
  const text = (await value.textContent()) ?? "";
  const match = /[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?/.exec(text);
  expect(match, `the legend of ${signalId} shows a number, got ${JSON.stringify(text)}`).not.toBeNull();
  return Number(match?.[0]);
}

async function runAndPlot(page: Page, model: string): Promise<void> {
  await expect(page.getByTestId("canvas-surface")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByTestId("run-button")).toBeEnabled({ timeout: 60_000 });
  await page.getByTestId("run-button").click();
  const runStatus = page.getByTestId("run-status");
  await expect(runStatus).toHaveAttribute("data-status", "done", {
    timeout: 300_000,
  });
  await expect(runStatus).toContainText(/done in/i);

  await page.getByRole("tab", { name: "Signals" }).click();
  await expect(page.getByTestId("signal-browser")).toBeVisible();
  await plotSignal(page, "Iphase/y");
  await plotSignal(page, "WmSens/p.f");

  await page.getByRole("tab", { name: "Plots" }).click();
  const chart = page.getByTestId("plot-chart");
  await expect(chart).toBeVisible();
  await expect(chart).toHaveAttribute("data-series-count", "2");
  await expect(page.getByTestId("legend-item")).toHaveCount(2);
  await expect(
    page.locator('[data-testid="legend-item"][data-signal-id="Iphase/y"]'),
  ).toHaveCount(1);
  await expect(
    page.locator('[data-testid="legend-item"][data-signal-id="WmSens/p.f"]'),
  ).toHaveCount(1);
  await expect
    .poll(
      async () => Number((await chart.getAttribute("data-points")) ?? "0"),
      { message: `the ${model} run's signals are loaded`, timeout: 60_000 },
    )
    .toBeGreaterThan(0);
}

async function readSteadyLegends(page: Page): Promise<{ speed: number; current: number }> {
  // The run covers 1.2 s; 95 % of the chart is about t = 1.14 s, after the 0.9 s load
  // step. The position loop holds the shaft, so the speed is ~0 and i_q ~4.2 A.
  const over = page.locator('[data-testid="plot-chart"] .u-over');
  await expect(over).toBeVisible();
  const box = await over.boundingBox();
  if (box === null) {
    throw new Error("the plot has no measurable area");
  }
  await page.mouse.move(box.x + box.width * 0.95, box.y + box.height * 0.45);
  const legendTime = page.getByTestId("legend-time");
  await expect.poll(async () => legendTime.textContent()).toMatch(/t = 1\.[0-2]/);
  return {
    speed: await legendNumber(page, "WmSens/p.f"),
    current: await legendNumber(page, "Iphase/y"),
  };
}

test("opens the industrial servo, runs baseline and full, and reads current and speed", async ({
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
    `${serverUrl}/?project=${encodeURIComponent(project)}&model=baseline`,
  );

  // The dq bond-graph plant and the three sampled loops.
  for (const name of ["Vd", "DJ", "Rd", "Id", "MGY", "Vq", "QJ", "Iq", "Bemf", "GY", "MJ", "Jm", "CurLoop", "SpeedLoop", "PosLoop", "Theta"]) {
    await expect(node(page, name)).toBeVisible();
  }

  await runAndPlot(page, "baseline");
  const baseline = await readSteadyLegends(page);
  expect(Math.abs(baseline.speed)).toBeLessThan(0.5);
  expect(Math.abs(baseline.current - 4.17)).toBeLessThan(0.8);

  // Switch to the combined variant through the model selector and run it.
  await page.getByTestId("open-project").click();
  await page.getByTestId("model-option-full").click();
  await expect(page.getByTestId("canvas-surface")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByTestId("top-bar")).toContainText(/full/i);
  for (const name of ["Notch", "Enc", "SpeedEst", "PWM", "WlSens"]) {
    await expect(node(page, name)).toBeVisible();
  }

  await runAndPlot(page, "full");
  const full = await readSteadyLegends(page);
  expect(Math.abs(full.speed)).toBeLessThan(0.5);
  expect(Math.abs(full.current - 4.2)).toBeLessThan(1.0);
});
