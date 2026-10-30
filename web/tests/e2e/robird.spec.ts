import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

/**
 * X5.15 acceptance: the `robird` example, a flapping-wing robotic falcon flying a Lissajous figure of eight
 * (`BGSIM_E2E_PORT=8816` for the real-worker pass; the backend also binds the next port).
 *
 * 1. create a copy of the example through `POST /api/projects {name, example}`;
 * 2. open the model and assert the fuselage, a wing joint, the flapping drive and the controller blocks;
 * 3. press Run, wait for `done` (60 s of flight with a 100 Hz flight controller takes about a minute);
 * 4. plot the position (`Truth/x`), the altitude (`Truth/z`) and the cross-track error (`Guide/e_ct`), read
 *    the legend at 12 s (the +x tip of the figure), 30 s and 45 s: x, z and the tracking error;
 * 5. open the 3D view: the twelve bindings (fuselage pose, wing flap, torsion, bend and torsion of the outer
 *    segment, three tail flaps) validate without a problem, the wing joints apply the flap angle of the run at
 *    two times (`data-applied`), and the canvas shows the bird in a different place at the two times.
 *
 * The fake worker answers every run from its fixed `Synthetic/*` fixture, so this spec uses the real
 * worker: it starts one on a free port when the suite was not already started with `BGSIM_E2E_REAL=1`
 * (as the real-worker pass does), and deletes the copied project and the temporary projects root in
 * `afterAll`.
 */

test.describe.configure({ timeout: 900_000 });

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
  projectsRoot = mkdtempSync(path.join(os.tmpdir(), "bgsim-robird-"));
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
  project = `x515-robird-${Date.now()}-${test.info().workerIndex}`;
  const created = await request.post(`${serverUrl}/api/projects`, {
    data: { name: project, example: "robird" },
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

test("opens the robird, flies the figure of eight and reads the path, the altitude and the 3D bindings", async ({
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
    `${serverUrl}/?project=${encodeURIComponent(project)}&model=robird`,
  );
  await expect(page.getByTestId("canvas-surface")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("run-button")).toBeEnabled();

  // The floating fuselage, a wing joint with its aerodynamic block, the flapping drive and crank, and the
  // flight-control chain: guidance and flight controller.
  for (const name of ["Body", "JL1", "AeroL1", "Drv", "Crank", "Guide", "Fctl"]) {
    await expect(node(page, name)).toBeVisible();
  }

  await page.getByTestId("run-button").click();
  const runStatus = page.getByTestId("run-status");
  await expect(runStatus).toHaveAttribute("data-status", "done", {
    timeout: 600_000,
  });
  await expect(runStatus).toContainText(/done in/i);

  await page.getByRole("tab", { name: "Signals" }).click();
  await expect(page.getByTestId("signal-browser")).toBeVisible();
  await plotSignal(page, "Truth/x");
  await plotSignal(page, "Truth/z");
  await plotSignal(page, "Guide/e_ct");

  await page.getByRole("tab", { name: "Plots" }).click();
  const chart = page.getByTestId("plot-chart");
  await expect(chart).toBeVisible();
  await expect(chart).toHaveAttribute("data-series-count", "3");
  await expect(page.getByTestId("legend-item")).toHaveCount(3);
  await expect
    .poll(
      async () => Number((await chart.getAttribute("data-points")) ?? "0"),
      { message: "the run's signals are loaded", timeout: 60_000 },
    )
    .toBeGreaterThan(0);

  // The cursor is the global inspect time. The run covers 60 s, so 20 % of the chart is t = 12 s.
  const over = page.locator('[data-testid="plot-chart"] .u-over');
  await expect(over).toBeVisible();
  const box = await over.boundingBox();
  if (box === null) {
    throw new Error("the plot has no measurable area");
  }
  const legendTime = page.getByTestId("legend-time");
  const readAt = async (fraction: number, pattern: RegExp) => {
    await page.mouse.move(box.x + box.width * fraction, box.y + box.height * 0.45);
    await expect.poll(async () => legendTime.textContent()).toMatch(pattern);
    return {
      x: await legendNumber(page, "Truth/x"),
      z: await legendNumber(page, "Truth/z"),
      e: await legendNumber(page, "Guide/e_ct"),
    };
  };

  // t = 12 s: the bird is at the +x tip of the figure (x = A = 110 m), 26.5 m high, on the path
  const tip = await readAt(0.2, /t = (11\.[5-9]\d*|12(\.[0-5]\d*)?) s/);
  expect(tip.x).toBeGreaterThan(104);
  expect(tip.x).toBeLessThan(113);
  expect(tip.z).toBeGreaterThan(24.5);
  expect(tip.z).toBeLessThan(28.5);
  expect(Math.abs(tip.e)).toBeLessThan(1.5);
  // t = 30 s: across the second lobe at x = -51 m, 24.4 m high
  const mid = await readAt(0.5, /t = (29\.[5-9]\d*|30(\.[0-5]\d*)?) s/);
  expect(mid.x).toBeGreaterThan(-62);
  expect(mid.x).toBeLessThan(-40);
  expect(mid.z).toBeGreaterThan(22.5);
  expect(mid.z).toBeLessThan(26.5);
  expect(Math.abs(mid.e)).toBeLessThan(1.5);
  // t = 45 s: x = -46.5 m
  const late = await readAt(0.75, /t = (44\.[5-9]\d*|45(\.[0-5]\d*)?) s/);
  expect(late.x).toBeGreaterThan(-58);
  expect(late.x).toBeLessThan(-35);
  expect(Math.abs(late.e)).toBeLessThan(1.5);

  // The same run plays in 3D: the fuselage link follows the pose binding, the wing and tail joints the
  // flap, torsion and bend angles, and the bindings validate without a diagnostic.
  await page.getByRole("tab", { name: "3D View" }).click();
  await expect(page.getByTestId("scene-view")).toHaveAttribute("data-state", "loaded", {
    timeout: 30_000,
  });
  const bar = page.getByTestId("playback-bar");
  await expect(bar).toHaveAttribute("data-mode", "playback", { timeout: 60_000 });

  // the figure is 220 m wide: frame the whole scene (the first fit may precede the content)
  await page.getByTestId("viewer-preset-top").click();
  const tree = page.getByTestId("scene-tree");
  for (const name of ["fuselage", "wing_in_L", "wing_out_R", "elevon_L", "rudder"]) {
    await expect(tree).toContainText(name);
  }

  await page.getByTestId("bindings-toggle").click();
  await expect(page.getByTestId("bindings-editor")).toBeVisible();
  for (const row of [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]) {
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
    await page.waitForTimeout(800);
    await page.screenshot({ path: `test-results/robird-3d-${time}.png` });
    return page.getByTestId("viewer-canvas").screenshot();
  };
  const shots: Buffer[] = [];
  // flap angle of the left wing (JL1/qout, rad): near the top of the stroke at 12 s (0.54), near the bottom at 30 s (-0.47)
  for (const [time, flap] of [
    [12.0, 0.54],
    [30.0, -0.47],
  ] as const) {
    shots.push(await frames(time));
    await expect
      .poll(
        async () => Math.abs(((await appliedTo("joint:flap_L")) ?? Number.NaN) - flap),
        { message: `flap_L at t = ${time} s` },
      )
      .toBeLessThan(0.15);
    await expect
      .poll(
        async () => Math.abs(((await appliedTo("joint:flap_R")) ?? Number.NaN) - flap),
        { message: `flap_R at t = ${time} s` },
      )
      .toBeLessThan(0.15);
  }
  // at 12 s the bird is at (110, 7, 26.5), at 30 s at (-51, 34, 24.4): the pose binding moves it, so the two canvases differ
  expect(shots[0].equals(shots[1]), "the canvas shows the bird in another place").toBe(false);
  await page.screenshot({ path: "test-results/robird-3d.png" });

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
