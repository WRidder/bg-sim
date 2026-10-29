import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type Locator, type Page } from "@playwright/test";

/**
 * X5.3 acceptance: the RRR equation-block arm of the `robot-arm-3d` sample (plan 9.8).
 *
 * 1. create a copy of the sample through `POST /api/projects {name, example}` and open its
 *    `rrr` model (the six-axis multibond arm `arm` of X-MB3 is the sample's first model and is
 *    covered by `robot-arm-3d.spec.ts`);
 * 2. assert the drive chain of each joint (`Motor` -> `Gear`) and the arm, controller and
 *    reference nodes;
 * 3. press Run, wait for `done` (the run reports the expected W201: the motor rotors are
 *    derivative-causal behind the rigid gears);
 * 4. plot the three joint angles `Arm/q1..q3` and read the legends at 1.6 s (after the first
 *    minimum-jerk move) and at the end of the run (after the second move): the arm sits on the
 *    reference angles.
 *
 * It then opens the 3D View tab and checks the arm plays (bindings, seek, playback). Like the other example specs this one
 * needs Julia (the fake worker answers every run from its `Synthetic/*` fixture). It starts a
 * backend and the real worker on a free port unless the suite was already started with
 * `BGSIM_E2E_REAL=1`, and deletes the copied project and the temporary projects root in
 * `afterAll`.
 */

test.describe.configure({ timeout: 360_000 });

const repoRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../..",
);

/** The end of the 5 s run: the plot right edge is 1-2 px short of it. */
const T_END = 5.0;
/** Joint targets (rad) of the two minimum-jerk moves (design/design.py). */
const AFTER_MOVE_A = { q1: 1.2, q2: 1.0, q3: -0.4 };
const AFTER_MOVE_B = { q1: -0.6, q2: 0.3, q3: -1.3 };

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
        const health = (await response.json()) as {
          worker?: string;
          versions?: { julia?: string | null };
        };
        last = `worker state ${JSON.stringify(health.worker)}`;
        if (health.worker === "ready") {
          if (health.versions?.julia === "fake") {
            throw new Error("this spec needs the real Julia worker, not the fake one");
          }
          return;
        }
      } else {
        last = `GET /api/health -> ${response.status}`;
      }
    } catch (error) {
      if (error instanceof Error && error.message.includes("real Julia worker")) {
        throw error;
      }
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
  projectsRoot = mkdtempSync(path.join(os.tmpdir(), "bgsim-robot-arm-3r-"));
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

test.afterEach(async ({ request }) => {
  if (project.length > 0) {
    await request.delete(`${serverUrl}/api/projects/${project}`);
    project = "";
  }
});

function node(page: Page, name: string) {
  return page.locator(`[data-testid="diagram-node"][data-node-name="${name}"]`);
}

/** The live plot area, in CSS pixels. */
async function plotArea(chart: Locator) {
  const over = chart.locator(".u-over");
  await expect(over).toBeVisible();
  return over.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    return { x: rect.left, y: rect.top, width: rect.width, height: rect.height };
  });
}

async function hoverAt(page: Page, chart: Locator, time: number) {
  const xMin = Number(await chart.getAttribute("data-x-min"));
  const xMax = Number(await chart.getAttribute("data-x-max"));
  expect(Number.isFinite(xMin) && Number.isFinite(xMax) && xMax > xMin).toBe(true);
  const area = await plotArea(chart);
  const left = Math.ceil(area.x) + 1;
  const right = Math.floor(area.x + area.width) - 1;
  const target = Math.round(area.x + ((time - xMin) / (xMax - xMin)) * area.width);
  const x = Math.min(right, Math.max(left, target));
  await page.mouse.move(x, Math.round(area.y + area.height * 0.5));
}

function legendNumber(page: Page, signalId: string) {
  return page
    .locator(`[data-testid="legend-item"][data-signal-id="${signalId}"] .plot-legend__value`)
    .innerText()
    .then((text) => {
      const match = /[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?/.exec(text);
      expect(match, `the legend of ${signalId} shows a number, got ${JSON.stringify(text)}`)
        .not.toBeNull();
      return Number(match?.[0]);
    });
}

async function legendSeconds(page: Page): Promise<number> {
  const text = (await page.getByTestId("legend-time").innerText()) ?? "";
  const match = /t = ([-+]?\d+(?:\.\d+)?)/.exec(text);
  expect(match, `the legend shows a cursor time, got ${JSON.stringify(text)}`).not.toBeNull();
  return Number(match?.[1]);
}

test.beforeEach(async ({ request }) => {
  project = `x53-robot-arm-3r-${Date.now()}-${test.info().workerIndex}`;
  const created = await request.post(`${serverUrl}/api/projects`, {
    data: { name: project, example: "robot-arm-3d" },
  });
  expect(created.status(), await created.text()).toBe(201);
});

test("opens the RRR equation-block arm, runs it and plots the joint angles", async ({
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
  await page.goto(`${serverUrl}/?project=${encodeURIComponent(project)}&model=rrr`);
  await expect(page.getByTestId("canvas-surface")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("run-button")).toBeEnabled();

  for (const name of [
    "Arm",
    "Ctrl",
    "Ref1",
    "Ref2",
    "Ref3",
    "Motor1",
    "Motor2",
    "Motor3",
    "Gear1",
    "Gear2",
    "Gear3",
  ]) {
    await expect(node(page, name)).toBeVisible();
  }

  await page.getByTestId("run-button").click();
  const runStatus = page.getByTestId("run-status");
  await expect(runStatus).toHaveAttribute("data-status", "done", { timeout: 300_000 });
  await expect(runStatus).toContainText(/done in/i);

  await page.getByRole("tab", { name: "Signals" }).click();
  await expect(page.getByTestId("signal-browser")).toBeVisible();
  for (const signal of ["Arm/q1", "Arm/q2", "Arm/q3"]) {
    const item = page.locator(`[data-testid="signal-item"][data-signal-id="${signal}"]`);
    await expect(item).toHaveCount(1);
    await item.dblclick();
  }

  await page.getByRole("tab", { name: "Plots" }).click();
  const chart = page.getByTestId("plot-chart");
  await expect(chart).toBeVisible();
  await expect(chart).toHaveAttribute("data-series-count", "3");
  await expect(page.getByTestId("legend-item")).toHaveCount(3);
  await expect
    .poll(async () => Number((await chart.getAttribute("data-points")) ?? "0"), {
      message: "the run data is loaded into the plot",
      timeout: 60_000,
    })
    .toBeGreaterThan(0);

  // After the first move (it ends at 1.2 s) the arm sits on the first target.
  await hoverAt(page, chart, 1.6);
  await expect.poll(async () => Math.abs((await legendSeconds(page)) - 1.6)).toBeLessThan(0.02);
  expect(Math.abs((await legendNumber(page, "Arm/q1")) - AFTER_MOVE_A.q1)).toBeLessThan(5e-3);
  expect(Math.abs((await legendNumber(page, "Arm/q2")) - AFTER_MOVE_A.q2)).toBeLessThan(5e-3);
  expect(Math.abs((await legendNumber(page, "Arm/q3")) - AFTER_MOVE_A.q3)).toBeLessThan(5e-3);

  // The end of the run: the second move (3.0 s) has settled on its target.
  await hoverAt(page, chart, T_END);
  await expect.poll(async () => Math.abs((await legendSeconds(page)) - T_END)).toBeLessThan(0.02);
  expect(Math.abs((await legendNumber(page, "Arm/q1")) - AFTER_MOVE_B.q1)).toBeLessThan(5e-3);
  expect(Math.abs((await legendNumber(page, "Arm/q2")) - AFTER_MOVE_B.q2)).toBeLessThan(5e-3);
  expect(Math.abs((await legendNumber(page, "Arm/q3")) - AFTER_MOVE_B.q3)).toBeLessThan(5e-3);

  // The same run plays in 3D: joint1..3 follow Arm/q1..q3 and the bindings validate cleanly.
  // The dock can still be settling after the run; retry the tab click until the view mounts.
  await expect(async () => {
    await page.getByRole("tab", { name: "3D View" }).click();
    await expect(page.getByTestId("scene-view")).toBeVisible({ timeout: 4_000 });
  }).toPass({ timeout: 30_000 });
  await expect(page.getByTestId("scene-view")).toHaveAttribute("data-state", "loaded", {
    timeout: 30_000,
  });
  const bar = page.getByTestId("playback-bar");
  await expect(bar).toHaveAttribute("data-mode", "playback", { timeout: 30_000 });

  const tree = page.getByTestId("scene-tree");
  for (const link of ["base", "turret", "upper_arm", "forearm"]) {
    await expect(tree).toContainText(link);
  }

  await page.getByTestId("bindings-toggle").click();
  await expect(page.getByTestId("bindings-editor")).toBeVisible();
  for (const row of [0, 1, 2]) {
    await expect(page.getByTestId(`binding-row-${row}`)).not.toHaveAttribute(
      "data-invalid",
      "true",
    );
    await expect(page.getByTestId(`binding-problem-${row}`)).toHaveCount(0);
  }
  await page.getByTestId("bindings-toggle").click();

  const appliedTo = async (target: string): Promise<number> => {
    const raw = await bar.getAttribute("data-applied");
    return (JSON.parse(raw ?? "{}") as Record<string, number>)[target] ?? Number.NaN;
  };
  // Values of the independent numpy replica (design/design.py), checked to 1e-9 against the
  // Julia run in expected.json; 60 Hz decimation plus interpolation gives 1e-3 here.
  const samples: [number, [number, number, number]][] = [
    [0.7, [0.59699418, 0.79219330, -0.65748946]],
    [1.6, [1.20005503, 0.99995984, -0.40013646]],
    [2.4, [0.30950162, 0.64571457, -0.83993106]],
  ];
  for (const [time, q] of samples) {
    await page.getByTestId("playback-time").fill(String(time));
    for (const [index, target] of ["joint:joint1", "joint:joint2", "joint:joint3"].entries()) {
      await expect
        .poll(async () => Math.abs((await appliedTo(target)) - q[index]!), {
          message: `${target} at t = ${time} s`,
        })
        .toBeLessThan(1e-3);
    }
    if (time === 0.7) {
      await page.screenshot({ path: "test-results/robot-arm-3r-3d.png" });
    }
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
