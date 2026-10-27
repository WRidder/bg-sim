import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

/**
 * X2.7 acceptance: the `inverted-pendulum-cart` sample.
 *
 * 1. create a copy of the sample through `POST /api/projects {name, example}`;
 * 2. open the model and assert the bond-graph nodes and the LQR block;
 * 3. press Run, wait for `done`;
 * 4. plot the pendulum angle (`ThetaInt/y`) and the controller force (`MSe1/p.e`) and read
 *    both legends at t = 3 s: the angle must be inside the 0.5 deg band and the force
 *    inside the +-20 N limit.
 *
 * The fake worker answers every run from its fixed `Synthetic/*` fixture, so it cannot serve
 * the signals plan 9.6c is about. This spec therefore uses the real worker: it starts one on
 * a free port when the suite was not already started with `BGSIM_E2E_REAL=1` (as the
 * real-worker pass does), and deletes the copied project and the temporary projects root in
 * `afterAll`. The run reports W201 (the point mass has one redundant store) and W205 (the
 * Generic bond island); both are expected and do not stop the run.
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
  // A cold Julia worker (ModelingToolkit precompilation plus the first compile) can take
  // longer than the 30 s default hook budget.
  test.setTimeout(300_000);
  if (process.env.BGSIM_E2E_REAL === "1") {
    // The real-worker Playwright pass already serves this URL.
    serverUrl = "http://127.0.0.1:8765";
    await waitForWorker(serverUrl, null);
    return;
  }

  const port = await freePort();
  serverUrl = `http://127.0.0.1:${port}`;
  projectsRoot = mkdtempSync(path.join(os.tmpdir(), "bgsim-inverted-pendulum-cart-"));
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
  project = `x27-inverted-pendulum-cart-${Date.now()}-${test.info().workerIndex}`;
  const created = await request.post(`${serverUrl}/api/projects`, {
    data: { name: project, example: "inverted-pendulum-cart" },
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

test("opens the bond-graph cart-pole, runs it and reads the angle and force at 3 s", async ({
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
    `${serverUrl}/?project=${encodeURIComponent(project)}&model=inverted-pendulum-cart`,
  );
  await expect(page.getByTestId("canvas-surface")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("run-button")).toBeEnabled();

  // The bond-graph plant plus the LQR firmware.
  for (const name of ["CartJ", "HS", "PendJ", "MTFh", "MTFv", "MSe1", "LQR1"]) {
    await expect(node(page, name)).toBeVisible();
  }

  await page.getByTestId("run-button").click();
  const runStatus = page.getByTestId("run-status");
  await expect(runStatus).toHaveAttribute("data-status", "done", {
    timeout: 180_000,
  });
  await expect(runStatus).toContainText(/done in/i);

  await page.getByRole("tab", { name: "Signals" }).click();
  await expect(page.getByTestId("signal-browser")).toBeVisible();
  await plotSignal(page, "ThetaInt/y");
  await plotSignal(page, "MSe1/p.e");

  await page.getByRole("tab", { name: "Plots" }).click();
  const chart = page.getByTestId("plot-chart");
  await expect(chart).toBeVisible();
  await expect(chart).toHaveAttribute("data-series-count", "2");
  await expect(page.getByTestId("legend-item")).toHaveCount(2);
  await expect(
    page.locator('[data-testid="legend-item"][data-signal-id="ThetaInt/y"]'),
  ).toHaveCount(1);
  await expect(
    page.locator('[data-testid="legend-item"][data-signal-id="MSe1/p.e"]'),
  ).toHaveCount(1);
  await expect
    .poll(
      async () => Number((await chart.getAttribute("data-points")) ?? "0"),
      { message: "the run's signals are loaded", timeout: 30_000 },
    )
    .toBeGreaterThan(0);

  // The cursor is the global inspect time. The run covers 4 s, so 75 % of the chart is
  // about t = 3 s: the angle has settled into the 0.5 deg band and the force is far below
  // its +-20 N limit.
  const over = page.locator('[data-testid="plot-chart"] .u-over');
  await expect(over).toBeVisible();
  const box = await over.boundingBox();
  if (box === null) {
    throw new Error("the plot has no measurable area");
  }
  await page.mouse.move(box.x + box.width * 0.75, box.y + box.height * 0.45);

  const legendTime = page.getByTestId("legend-time");
  await expect.poll(async () => legendTime.textContent()).toMatch(/t = (2\.[4-9]|3\.[0-6])/);

  const angle = await legendNumber(page, "ThetaInt/y");
  const force = await legendNumber(page, "MSe1/p.e");
  expect(Math.abs(angle)).toBeLessThan(0.0087266);
  expect(Math.abs(force)).toBeLessThanOrEqual(20);
});
