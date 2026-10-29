import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

/**
 * X2.4 acceptance: the `drivetrain-kalman` sample.
 *
 * 1. create a copy of the sample through `POST /api/projects {name, example}`;
 * 2. open the main model and assert the bond-graph plant (the motor junction, the three rod
 *    segments and the 10:1 gear) plus the LQG firmware node;
 * 3. press Run, wait for `done`;
 * 4. plot the load speed (`IW2/p.f`) and the control voltage (`V/p.e`) and read both legends
 *    at about t = 1.5 s: the speed must sit near the 10 rad/s reference after the load step
 *    and the voltage inside the +-24 V clamp.
 *
 * Like the inverted-pendulum spec this needs the real worker (the fake worker answers every
 * run from its fixed `Synthetic/*` fixture). It starts one on a free port unless the suite
 * was already started with `BGSIM_E2E_REAL=1`, and deletes the copied project and the
 * temporary projects root in `afterAll`. The run reports W201 (the ideal gear makes IW1 a
 * dependent store) and W205 (the dimensionless Generic bond island); both are expected.
 */

test.describe.configure({ timeout: 240_000 });

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
  test.setTimeout(300_000);
  if (process.env.BGSIM_E2E_REAL === "1") {
    serverUrl = `http://127.0.0.1:${process.env.BGSIM_E2E_PORT ?? "8765"}`;
    await waitForWorker(serverUrl, null);
    return;
  }

  const port = await freePort();
  serverUrl = `http://127.0.0.1:${port}`;
  projectsRoot = mkdtempSync(path.join(os.tmpdir(), "bgsim-drivetrain-kalman-"));
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
  project = `x24-drivetrain-kalman-${Date.now()}-${test.info().workerIndex}`;
  const created = await request.post(`${serverUrl}/api/projects`, {
    data: { name: project, example: "drivetrain-kalman" },
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

test("opens the bond-graph drivetrain, runs it and reads the load speed and voltage", async ({
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
    `${serverUrl}/?project=${encodeURIComponent(project)}&model=drivetrain-kalman`,
  );
  await expect(page.getByTestId("canvas-surface")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("run-button")).toBeEnabled();

  // The motor bond graph, the three rod segments and the sampled firmware.
  for (const name of ["Elec", "MotorJ", "GY", "TFa", "TFb", "WheelJ1", "S1", "Rod1", "S2", "Rod2", "WheelJ2", "LQG"]) {
    await expect(node(page, name)).toBeVisible();
  }
  // A Generic bond port on a sensor uses the bond itself as its marker.
  await expect(node(page, "Current").locator(".port-glyph--power")).toBeHidden();

  await page.getByTestId("run-button").click();
  const runStatus = page.getByTestId("run-status");
  await expect(runStatus).toHaveAttribute("data-status", "done", {
    timeout: 180_000,
  });
  await expect(runStatus).toContainText(/done in/i);

  await page.getByRole("tab", { name: "Signals" }).click();
  await expect(page.getByTestId("signal-browser")).toBeVisible();
  await plotSignal(page, "IW2/p.f");
  await plotSignal(page, "V/p.e");

  await page.getByRole("tab", { name: "Plots" }).click();
  const chart = page.getByTestId("plot-chart");
  await expect(chart).toBeVisible();
  await expect(chart).toHaveAttribute("data-series-count", "2");
  await expect(page.getByTestId("legend-item")).toHaveCount(2);
  await expect(
    page.locator('[data-testid="legend-item"][data-signal-id="IW2/p.f"]'),
  ).toHaveCount(1);
  await expect(
    page.locator('[data-testid="legend-item"][data-signal-id="V/p.e"]'),
  ).toHaveCount(1);
  await expect
    .poll(
      async () => Number((await chart.getAttribute("data-points")) ?? "0"),
      { message: "the run's signals are loaded", timeout: 30_000 },
    )
    .toBeGreaterThan(0);

  // The run covers 2 s, so 75 % of the chart is about t = 1.5 s: after the 1 s load step the
  // load speed has settled back to the 10 rad/s reference and the voltage is ~9.7 V.
  const over = page.locator('[data-testid="plot-chart"] .u-over');
  await expect(over).toBeVisible();
  const box = await over.boundingBox();
  if (box === null) {
    throw new Error("the plot has no measurable area");
  }
  await page.mouse.move(box.x + box.width * 0.75, box.y + box.height * 0.45);

  const legendTime = page.getByTestId("legend-time");
  await expect.poll(async () => legendTime.textContent()).toMatch(/t = (1\.[3-7]|2\.[0-1])/);

  const speed = await legendNumber(page, "IW2/p.f");
  const voltage = await legendNumber(page, "V/p.e");
  expect(Math.abs(speed - 10)).toBeLessThan(0.5);
  expect(Math.abs(voltage)).toBeLessThanOrEqual(24);
});
