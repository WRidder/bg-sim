import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

/**
 * X5.13 acceptance: `pendulum-double-rotary` (the triple is not finished, see the WP report;
 * add its case to `CASES` when it exists).
 *
 * For the example:
 *
 * 1. create a copy through `POST /api/projects {name, example}`;
 * 2. open the model and assert the arm joint, the servo, the links and the firmware;
 * 3. press Run, wait for `done`;
 * 4. plot the tip link angle (`Angles/phi<N>`): before the disturbance (a second before it) the
 *    chain stands upright inside 1 deg, and at the end of the run it has recovered inside 1 deg;
 * 5. open 3D: the scene loads, the bindings of every joint validate, and the first link joint
 *    follows `J2/qout` at two times (hanging at pi, upright at 0).
 *
 * The fake worker answers every run from a fixed fixture, so this spec uses the real worker: it
 * starts one on a free port when the suite was not already started with `BGSIM_E2E_REAL=1` (as
 * the real-worker pass does; port 8800 for this WP), and removes the copied projects and the
 * temporary projects root afterwards.
 */

test.describe.configure({ timeout: 600_000 });

const repoRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../..",
);

interface Case {
  example: string;
  links: number;
  /** Disturbance time and end of the run [s], from the example's design.json. */
  tDist: number;
  tEnd: number;
  nodes: string[];
}

const CASES: Case[] = [
  {
    example: "pendulum-double-rotary",
    links: 2,
    tDist: 8.5,
    tEnd: 12,
    nodes: ["Ctrl", "Motor", "Gear", "J1", "J2", "J3", "Arm", "Rod1", "Rod2", "Dist"],
  },
];

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
  test.setTimeout(300_000);
  if (process.env.BGSIM_E2E_REAL === "1") {
    serverUrl = `http://127.0.0.1:${process.env.BGSIM_E2E_PORT ?? "8800"}`;
    await waitForWorker(serverUrl, null);
    return;
  }

  const port = await freePort();
  serverUrl = `http://127.0.0.1:${port}`;
  projectsRoot = mkdtempSync(path.join(os.tmpdir(), "bgsim-pendulum-rotary-"));
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

for (const scenario of CASES) {
  test(`${scenario.example}: swing-up, balance, disturbance and recovery`, async ({
    page,
    request,
  }) => {
    project = `x513-${scenario.example}-${Date.now()}-${test.info().workerIndex}`;
    const created = await request.post(`${serverUrl}/api/projects`, {
      data: { name: project, example: scenario.example },
    });
    expect(created.status(), await created.text()).toBe(201);

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
      `${serverUrl}/?project=${encodeURIComponent(project)}&model=${scenario.example}`,
    );
    await expect(page.getByTestId("canvas-surface")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("run-button")).toBeEnabled();

    for (const name of scenario.nodes) {
      await expect(node(page, name)).toHaveCount(1);
    }

    await page.getByTestId("run-button").click();
    const runStatus = page.getByTestId("run-status");
    await expect(runStatus).toHaveAttribute("data-status", "done", {
      timeout: 480_000,
    });
    await expect(runStatus).toContainText(/done in/i);

    const tip = `Angles/phi${scenario.links}`;
    await page.getByRole("tab", { name: "Signals" }).click();
    await expect(page.getByTestId("signal-browser")).toBeVisible();
    await plotSignal(page, tip);

    await page.getByRole("tab", { name: "Plots" }).click();
    const chart = page.getByTestId("plot-chart");
    await expect(chart).toBeVisible();
    await expect(chart).toHaveAttribute("data-series-count", "1");
    await expect
      .poll(
        async () => Number((await chart.getAttribute("data-points")) ?? "0"),
        { message: "the run's signals are loaded", timeout: 30_000 },
      )
      .toBeGreaterThan(0);

    const over = page.locator('[data-testid="plot-chart"] .u-over');
    await expect(over).toBeVisible();
    const box = await over.boundingBox();
    if (box === null) {
      throw new Error("the plot has no measurable area");
    }
    const legendTime = page.getByTestId("legend-time");
    const timeAt = async (fraction: number): Promise<number> => {
      await page.mouse.move(box.x + box.width * fraction, box.y + box.height * 0.45);
      let seconds = Number.NaN;
      await expect
        .poll(async () => {
          const text = (await legendTime.textContent()) ?? "";
          const match = /t = ([-+]?\d+(?:\.\d+)?)/.exec(text);
          seconds = match === null ? Number.NaN : Number(match[1]);
          return Math.abs(seconds - fraction * scenario.tEnd);
        })
        .toBeLessThan(0.4);
      return seconds;
    };

    // One second before the disturbance: every link stands upright (the tip link is the
    // sum of all relative joint angles), inside 1 deg = 0.01745 rad.
    const before = await timeAt((scenario.tDist - 1.0) / scenario.tEnd);
    expect(before).toBeLessThan(scenario.tDist);
    expect(Math.abs(await legendNumber(page, tip))).toBeLessThan(0.01745);
    // At the end of the run it has recovered.
    await timeAt(0.995);
    expect(Math.abs(await legendNumber(page, tip))).toBeLessThan(0.01745);

    // The same run in 3D: arm joint and one joint per link, valid bindings.
    await page.getByRole("tab", { name: "3D View" }).click();
    await expect(page.getByTestId("scene-view")).toHaveAttribute("data-state", "loaded", {
      timeout: 30_000,
    });
    const bar = page.getByTestId("playback-bar");
    await expect(bar).toHaveAttribute("data-mode", "playback", { timeout: 30_000 });
    const tree = page.getByTestId("scene-tree");
    await expect(tree).toContainText("arm");
    await expect(tree).toContainText(`link${scenario.links}`);

    await page.getByTestId("bindings-toggle").click();
    await expect(page.getByTestId("bindings-editor")).toBeVisible();
    for (let row = 0; row <= scenario.links; row += 1) {
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
    // Hanging at t = 0.5 s (link 1 at pi), upright at t = tDist - 1 s (J2/qout near 0).
    for (const [time, angle, tolerance] of [
      [0.5, Math.PI, 0.02],
      [scenario.tDist - 1.0, 0.0, 0.05],
    ] as const) {
      await page.getByTestId("playback-time").fill(String(time));
      await expect
        .poll(async () => Math.abs(((await appliedTo("joint:link1")) ?? Number.NaN) - angle), {
          message: `the first link joint at t = ${time} s`,
        })
        .toBeLessThan(tolerance);
    }

    await page.getByTestId("playback-time").fill("3");
    await page.getByTestId("viewer-fit").click();
    await page.screenshot({ path: `test-results/${scenario.example}-3d.png` });
  });
}
