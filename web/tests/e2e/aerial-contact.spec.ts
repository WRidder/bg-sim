import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

/**
 * X5.8 acceptance: the `aerial-contact` example (port 8786, `BGSIM_E2E_PORT=8786`).
 *
 * 1. create a copy of the example through `POST /api/projects {name, example}`;
 * 2. open the model and assert the manipulator chain, the contact blocks and the controllers;
 * 3. press Run, wait for `done` (a 34 s run with 250 Hz firmware takes about a minute);
 * 4. plot the total wall force (`WallForce/N`) and read its legend at t = 14 s: the end-effector pushes on the
 *    wall with m g tan(27 deg) = 11.65 N (measured 11.4 N) while it climbs;
 * 5. open the 3D view: the twelve bindings (multirotor and end-effector poses, the arm joint, six rotors and
 *    three wheels) validate without a problem, the arm joint applies the servo angle of the run at two times
 *    (`data-applied`: level at t = 2 s, tipped by the equilibrium angle 27 deg at t = 14 s) and the canvas
 *    shows the scene in a different state at the two times.
 *
 * The fake worker answers every run from its fixed `Synthetic/*` fixture, so this spec uses the real
 * worker: it starts one on a free port when the suite was not already started with `BGSIM_E2E_REAL=1`
 * (as the real-worker pass does), and deletes the copied project and the temporary projects root in
 * `afterAll`.
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
  projectsRoot = mkdtempSync(path.join(os.tmpdir(), "bgsim-aerial-contact-"));
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
  project = `x58-aerial-contact-${Date.now()}-${test.info().workerIndex}`;
  const created = await request.post(`${serverUrl}/api/projects`, {
    data: { name: project, example: "aerial-contact" },
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

test("opens the aerial manipulator, runs the contact scenario and reads the wall force and the 3D bindings", async ({
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
    `${serverUrl}/?project=${encodeURIComponent(project)}&model=aerial-contact`,
  );
  await expect(page.getByTestId("canvas-surface")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("run-button")).toBeEnabled();

  // The multirotor, the manipulator chain (servo, rubber mount, end-effector), the three omni-wheel contacts and
  // the controllers of the phase machine.
  for (const name of [
    "Body",
    "Servo",
    "Rub",
    "EE",
    "Wheel1",
    "Wheel2",
    "Wheel3",
    "Sup",
    "Pos",
    "Eng",
    "Con",
    "Mix",
  ]) {
    await expect(node(page, name)).toBeVisible();
  }

  await page.getByTestId("run-button").click();
  const runStatus = page.getByTestId("run-status");
  await expect(runStatus).toHaveAttribute("data-status", "done", {
    timeout: 420_000,
  });
  await expect(runStatus).toContainText(/done in/i);

  await page.getByRole("tab", { name: "Signals" }).click();
  await expect(page.getByTestId("signal-browser")).toBeVisible();
  await plotSignal(page, "WallForce/N");

  await page.getByRole("tab", { name: "Plots" }).click();
  const chart = page.getByTestId("plot-chart");
  await expect(chart).toBeVisible();
  await expect(chart).toHaveAttribute("data-series-count", "1");
  await expect(page.getByTestId("legend-item")).toHaveCount(1);
  await expect(
    page.locator('[data-testid="legend-item"][data-signal-id="WallForce/N"]'),
  ).toHaveCount(1);
  await expect
    .poll(
      async () => Number((await chart.getAttribute("data-points")) ?? "0"),
      { message: "the signals of the run are loaded", timeout: 60_000 },
    )
    .toBeGreaterThan(0);

  // The cursor is the global inspect time. The run covers 34 s, so 41 % of the chart is about t = 14 s: the
  // contact controller holds theta_sp = 27 deg and the three wheels push on the wall with 11.4 N in total.
  const over = page.locator('[data-testid="plot-chart"] .u-over');
  await expect(over).toBeVisible();
  const box = await over.boundingBox();
  if (box === null) {
    throw new Error("the plot has no measurable area");
  }
  await page.mouse.move(box.x + box.width * 0.4118, box.y + box.height * 0.45);

  const legendTime = page.getByTestId("legend-time");
  await expect.poll(async () => legendTime.textContent()).toMatch(/t = (13\.[5-9]|14\.[0-5])/);

  const force = await legendNumber(page, "WallForce/N");
  expect(force).toBeGreaterThan(10.4);
  expect(force).toBeLessThan(12.4);

  // The same run plays in 3D: the multirotor and the end-effector follow their pose bindings, the arm joint the
  // servo angle, the rotors and the wheels their integrated angles, and the bindings validate without a diagnostic.
  await page.getByRole("tab", { name: "3D View" }).click();
  await expect(page.getByTestId("scene-view")).toHaveAttribute("data-state", "loaded", {
    timeout: 30_000,
  });
  const bar = page.getByTestId("playback-bar");
  await expect(bar).toHaveAttribute("data-mode", "playback", { timeout: 60_000 });

  const tree = page.getByTestId("scene-tree");
  for (const name of ["body", "arm_link", "ee", "rotor_1_link", "rotor_6_link", "wheel_1_link", "wheel_3_link"]) {
    await expect(tree).toContainText(name);
  }

  await page.getByTestId("bindings-toggle").click();
  await expect(page.getByTestId("bindings-editor")).toBeVisible();
  const bindingRows = 12;
  for (let row = 0; row < bindingRows; row += 1) {
    const problems = page.getByTestId(`binding-problem-${row}`);
    const text = (await problems.count()) > 0 ? await problems.innerText() : "";
    expect(text, `binding ${row} reports no problem`).toBe("");
    await expect(page.getByTestId(`binding-row-${row}`)).not.toHaveAttribute(
      "data-invalid",
      "true",
    );
    await expect(page.getByTestId(`binding-problem-${row}`)).toHaveCount(0);
  }
  await page.getByTestId("bindings-toggle").click();

  const appliedTo = async (target: string): Promise<number | undefined> => {
    const raw = await bar.getAttribute("data-applied");
    return (JSON.parse(raw ?? "{}") as Record<string, number>)[target];
  };
  const frames = async (time: number): Promise<Buffer> => {
    await page.getByTestId("playback-time").fill(String(time));
    await page.waitForTimeout(600);
    return page.getByTestId("viewer-canvas").screenshot();
  };
  // Servo angle of the run (Servo/qout, rad, a rotation about +y of the multirotor): the arm is level at 2 s
  // (-0.001 rad) and tipped to the equilibrium mu_c = theta_sp = 27 deg of the contact controller at 14 s
  // (-0.467 rad).
  const shots: Buffer[] = [];
  for (const [time, arm] of [
    [2.0, -0.0011],
    [14.0, -0.4672],
  ] as const) {
    shots.push(await frames(time));
    await expect
      .poll(
        async () =>
          Math.abs(((await appliedTo("joint:arm")) ?? Number.NaN) - arm),
        { message: `the arm joint at t = ${time} s` },
      )
      .toBeLessThan(0.03);
  }
  // The wheel angle integrates the open-loop wheel command: wheel 2 has turned 12.99 rad at 20 s.
  await page.getByTestId("playback-time").fill("20");
  await expect
    .poll(
      async () =>
        Math.abs(((await appliedTo("joint:wheel_2")) ?? Number.NaN) - 12.99),
      { message: "the wheel_2 joint at t = 20 s" },
    )
    .toBeLessThan(0.5);
  // at 2 s the multirotor hovers 0.45 m from the origin with the arm level, at 14 s it is 0.94 m along x with the
  // arm raised 27 deg and the end-effector on the wall: the pose bindings and the arm joint move the scene
  expect(shots[0].equals(shots[1]), "the canvas shows the scene in another state").toBe(false);
  await page.screenshot({ path: "test-results/aerial-contact-3d.png" });

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
