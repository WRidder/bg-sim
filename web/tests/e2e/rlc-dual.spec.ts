import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  expect,
  test,
  type Page,
} from "@playwright/test";

/**
 * X2.2 acceptance: the `rlc-dual` sample.
 *
 * 1. create a copy of the sample through `POST /api/projects {name, example}`;
 * 2. open the model, assert the two subsystem nodes, enter `Iconic` by
 *    double-click and leave through the breadcrumbs;
 * 3. press Run, wait for `done`, plot `Iconic/C1/p.e` and
 *    `Bondgraph/C1/p.e` and assert two legend items.
 *
 * The fake worker answers every run from its fixed `Synthetic/*` fixture, so it
 * cannot serve the two subsystem signals the plan 9.3 check is about. This spec
 * therefore uses the real worker: it starts one on a free port when the suite
 * was not already started with `BGSIM_E2E_REAL=1` (as the real-worker pass
 * does), and deletes the copied project and the temporary projects root in
 * `afterAll`. The worker reports W205 for the pure bond-graph island; that is
 * expected (plan 5.6) and does not affect the two capacitor voltages.
 */

test.describe.configure({ timeout: 180_000 });

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
  const deadline = Date.now() + 120_000;
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
  if (process.env.BGSIM_E2E_REAL === "1") {
    // The real-worker Playwright pass already serves this URL.
    serverUrl = "http://127.0.0.1:8765";
    await waitForWorker(serverUrl, null);
    return;
  }

  const port = await freePort();
  serverUrl = `http://127.0.0.1:${port}`;
  projectsRoot = mkdtempSync(path.join(os.tmpdir(), "bgsim-rlc-dual-"));
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
  project = `x22-rlc-dual-${Date.now()}-${test.info().workerIndex}`;
  const created = await request.post(`${serverUrl}/api/projects`, {
    data: { name: project, example: "rlc-dual" },
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

test("opens Iconic and Bondgraph and plots both capacitor voltages", async ({
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
    `${serverUrl}/?project=${encodeURIComponent(project)}&model=rlc-dual`,
  );
  await expect(page.getByTestId("canvas-surface")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("run-button")).toBeEnabled();
  await expect(node(page, "Iconic")).toBeVisible();
  await expect(node(page, "Bondgraph")).toBeVisible();
  await expect(page.getByTestId("diagram-node")).toHaveCount(2);

  // Enter the iconic subsystem: six children and one crumb.
  await node(page, "Iconic").click();
  await expect(node(page, "Iconic")).toHaveClass(/is-selected/);
  await node(page, "Iconic").dblclick({ position: { x: 8, y: 8 } });
  await expect(page.getByTestId("subsystem-breadcrumbs")).toBeVisible();
  await expect(page.getByTestId("breadcrumb-1")).toHaveAttribute(
    "data-breadcrumb-name",
    "Iconic",
  );
  await expect(page.getByTestId("diagram-node")).toHaveCount(6);
  // Leave via the root breadcrumb (the prompt's "use the breadcrumbs to leave").
  await page.getByTestId("breadcrumb-0").click();
  await expect(page.getByTestId("diagram-node")).toHaveCount(2);

  await page.getByTestId("run-button").click();
  const runStatus = page.getByTestId("run-status");
  await expect(runStatus).toHaveAttribute("data-status", "done", {
    timeout: 120_000,
  });
  await expect(runStatus).toContainText(/done in/i);

  await page.getByRole("tab", { name: "Signals" }).click();
  await expect(page.getByTestId("signal-browser")).toBeVisible();
  await plotSignal(page, "Iconic/C1/p.e");
  await plotSignal(page, "Bondgraph/C1/p.e");

  await page.getByRole("tab", { name: "Plots" }).click();
  const chart = page.getByTestId("plot-chart");
  await expect(chart).toBeVisible();
  await expect(chart).toHaveAttribute("data-series-count", "2");
  await expect(page.getByTestId("legend-item")).toHaveCount(2);
  await expect(
    page.locator('[data-testid="legend-item"][data-signal-id="Iconic/C1/p.e"]'),
  ).toHaveCount(1);
  await expect(
    page.locator(
      '[data-testid="legend-item"][data-signal-id="Bondgraph/C1/p.e"]',
    ),
  ).toHaveCount(1);
  await expect
    .poll(
      async () => Number((await chart.getAttribute("data-points")) ?? "0"),
      { message: "the capacitor voltages are loaded", timeout: 30_000 },
    )
    .toBeGreaterThan(0);
});
