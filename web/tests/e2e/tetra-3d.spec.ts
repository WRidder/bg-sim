import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

/**
 * X5.6 acceptance: the `tetra-3d` example.
 *
 * 1. create a copy of the example through `POST /api/projects {name, example}`;
 * 2. open the model and assert the body, the vertex contacts, the four motors and the firmware;
 * 3. press Run, wait for `done`;
 * 4. plot the angle to the vertex balance direction (`Sense/ang_vert`) and read its legend at t = 3.7 s: the
 *    tetrahedron must be balanced on the vertex inside a 0.5 deg band, then play the run in 3D.
 *
 * The fake worker answers every run from its fixed `Synthetic/*` fixture, so this spec uses
 * the real worker: it starts one on a free port when the suite was not already started with
 * `BGSIM_E2E_REAL=1` (as the real-worker pass does), and deletes the copied project and the
 * temporary projects root in `afterAll`.
 */

test.describe.configure({ timeout: 1_200_000 });

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
    serverUrl = `http://127.0.0.1:${process.env.BGSIM_E2E_PORT ?? "8765"}`;
    await waitForWorker(serverUrl, null);
    return;
  }

  const port = await freePort();
  serverUrl = `http://127.0.0.1:${port}`;
  projectsRoot = mkdtempSync(path.join(os.tmpdir(), "bgsim-tetra-3d-"));
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
  project = `x56-tetra-3d-${Date.now()}-${test.info().workerIndex}`;
  const created = await request.post(`${serverUrl}/api/projects`, {
    data: { name: project, example: "tetra-3d" },
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

test("opens the tetrahedron, runs face -> edge -> vertex and plays it in 3D", async ({
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

  await page.setViewportSize({ width: 1600, height: 1500 });
  await page.goto(
    `${serverUrl}/?project=${encodeURIComponent(project)}&model=sequence-contact`,
  );
  await expect(page.getByTestId("canvas-surface")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("run-button")).toBeEnabled();

  // The tetrahedron, one contact per vertex, the four wheel motors and the firmware.
  for (const name of ["Tetra", "C1", "C4", "Drv1", "Drv4", "Seq", "Alloc"]) {
    await expect(node(page, name)).toBeVisible();
  }

  await page.getByTestId("run-button").click();
  const runStatus = page.getByTestId("run-status");
  await expect(runStatus).toHaveAttribute("data-status", "done", {
    timeout: 900_000,
  });
  await expect(runStatus).toContainText(/done in/i);

  await page.getByRole("tab", { name: "Signals" }).click();
  await expect(page.getByTestId("signal-browser")).toBeVisible();
  await plotSignal(page, "Sense/ang_vert");

  await page.getByRole("tab", { name: "Plots" }).click();
  const chart = page.getByTestId("plot-chart");
  await expect(chart).toBeVisible();
  await expect(chart).toHaveAttribute("data-series-count", "1");
  await expect(
    page.locator('[data-testid="legend-item"][data-signal-id="Sense/ang_vert"]'),
  ).toHaveCount(1);
  await expect
    .poll(
      async () => Number((await chart.getAttribute("data-points")) ?? "0"),
      { message: "the run's signals are loaded", timeout: 30_000 },
    )
    .toBeGreaterThan(0);

  // The cursor is the global inspect time. The run covers 3.8 s, so 97 % of the chart is
  // about t = 3.7 s: the body balances on the vertex and the angle between the world
  // vertical and the vertex balance direction is below 0.5 deg (0.0087 rad).
  const over = page.locator('[data-testid="plot-chart"] .u-over');
  await expect(over).toBeVisible();
  const box = await over.boundingBox();
  if (box === null) {
    throw new Error("the plot has no measurable area");
  }
  await page.mouse.move(box.x + box.width * 0.97, box.y + box.height * 0.45);

  const legendTime = page.getByTestId("legend-time");
  await expect.poll(async () => legendTime.textContent()).toMatch(/t = 3\.[5-8]/);

  const angle = await legendNumber(page, "Sense/ang_vert");
  expect(Math.abs(angle)).toBeLessThan(0.0087266463);

  // The same run plays in 3D: the body follows the pose binding (it is a GLB mesh) and the four wheel
  // joints the integrated wheel angles, and the bindings validate without a diagnostic.
  await page.getByRole("tab", { name: "3D View" }).click();
  const sceneView = page.getByTestId("scene-view");
  await expect(sceneView).toHaveAttribute("data-state", "loaded", { timeout: 30_000 });
  const bar = page.getByTestId("playback-bar");
  await expect(bar).toHaveAttribute("data-mode", "playback", { timeout: 30_000 });

  const tree = page.getByTestId("scene-tree");
  for (const name of ["tetra", "wheel_1_link", "wheel_2_link", "wheel_3_link", "wheel_4_link"]) {
    await expect(tree).toContainText(name);
  }

  await page.getByTestId("bindings-toggle").click();
  await expect(page.getByTestId("bindings-editor")).toBeVisible();
  for (const row of [0, 1, 2, 3, 4]) {
    await expect(page.getByTestId(`binding-row-${row}`)).not.toHaveAttribute(
      "data-invalid",
      "true",
    );
    await expect(page.getByTestId(`binding-problem-${row}`)).toHaveCount(0);
  }
  await page.getByTestId("bindings-toggle").click();

  // Wheel angles of the run (WJoint<k>/q, rad relative to the body), applied to the joints wheel_1..4:
  // the wheels 2 and 3 spin up in opposite directions for the edge, all four for the vertex.
  const appliedTo = async (target: string): Promise<number | undefined> => {
    const raw = await bar.getAttribute("data-applied");
    return (JSON.parse(raw ?? "{}") as Record<string, number>)[target];
  };
  for (const [time, angles] of [
    [1.0, [0.6237, -40.2232, 41.4707, 0.6237]],
    [3.0, [237.5269, -249.1836, 189.4744, -155.3329]],
  ] as const) {
    await page.getByTestId("playback-time").fill(String(time));
    for (const [index, angle] of angles.entries()) {
      await expect
        .poll(
          async () => Math.abs(((await appliedTo(`joint:wheel_${index + 1}`)) ?? Number.NaN) - angle),
          { message: `wheel_${index + 1} at t = ${time} s` },
        )
        .toBeLessThan(2);
    }
  }

  // Start (resting on the base face), edge balance (t = 1.6 s) and vertex balance (t = 3.4 s).
  for (const [time, file] of [
    [0, "tetra-3d-3d.png"],
    [1.6, "tetra-3d-3d-edge.png"],
    [3.4, "tetra-3d-3d-vertex.png"],
  ] as const) {
    await page.getByTestId("playback-time").fill(String(time));
    await expect
      .poll(async () => Number(await bar.getAttribute("data-time")))
      .toBeCloseTo(time, 1);
    await page.getByTestId("viewer-fit").click();
    await page.waitForTimeout(500);
    await page.getByTestId("viewer-canvas").screenshot({ path: `test-results/${file}` });
  }

  await page.getByTestId("playback-rewind").click();
  await expect.poll(async () => Number(await bar.getAttribute("data-time"))).toBe(0);
  await page.getByTestId("playback-speed").selectOption("0.25");
  await page.getByTestId("playback-toggle").click();
  await expect(bar).toHaveAttribute("data-playing", "true");
  await expect
    .poll(async () => Number(await bar.getAttribute("data-time")))
    .toBeGreaterThan(0.05);
  await page.getByTestId("playback-toggle").click();
});
