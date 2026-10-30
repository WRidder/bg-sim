import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

/**
 * X5.12 acceptance: the `pendulum-double-cart` and `pendulum-triple-cart` examples.
 *
 * For each example:
 * 1. create a copy through `POST /api/projects {name, example}`;
 * 2. open the model and assert the rail, the motor drive train and the firmware blocks;
 * 3. press Run, wait for `done`;
 * 4. plot a link angle (`Ctrl/th1`) and read its legend before the disturbance (balanced inside
 *    0.2 deg), right after the pulse (deflected by more than 5.7 deg) and at the end (recovered);
 * 5. open the 3D view, check the bindings validate and read the cart and link joints at two
 *    times (the swing-up and the end of the run) from the playback bar.
 *
 * The fake worker answers every run from its fixed `Synthetic/*` fixture, so this spec uses the
 * real worker: it starts one on a free port when the suite was not already started with
 * `BGSIM_E2E_REAL=1` (as the real-worker pass does, port 8788 for this WP), and deletes the
 * copied project and the temporary projects root in `afterAll`.
 */

test.describe.configure({ timeout: 480_000 });

const repoRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../..",
);

interface Case {
  example: string;
  nodes: string[];
  /** Run length (s), the pulse time (s) and the link count. */
  tEnd: number;
  tPulse: number;
  /** Seconds after the pulse at which link 1 is still far from upright. */
  tPeek: number;
  links: number;
  /** Joint targets read in 3D: [time, {target: value}] (rad, m) from the real run (60 Hz playback). */
  playback: Array<[number, Record<string, number>]>;
}

const cases: Case[] = [
  {
    example: "pendulum-double-cart",
    nodes: ["Rail", "Cart", "Joint1", "Joint2", "Body1", "Body2", "Motor", "Gear", "Pulley", "Belt", "Traj", "Ctrl", "Push"],
    tEnd: 12,
    tPulse: 7,
    tPeek: 0.1,
    links: 2,
    playback: [
      [2.0, { "joint:rail": 0.2548, "joint:hinge1": -1.5814, "joint:hinge2": 0.8008 }],
      [12.0, { "joint:rail": 0.0, "joint:hinge1": 1.5708, "joint:hinge2": 0.0 }],
    ],
  },
  {
    example: "pendulum-triple-cart",
    nodes: ["Rail", "Cart", "Joint1", "Joint2", "Joint3", "Body1", "Body2", "Body3", "Motor", "Gear", "Pulley", "Belt", "Traj", "Ctrl", "Push"],
    tEnd: 14.5,
    tPulse: 8,
    tPeek: 0.25,
    links: 3,
    playback: [
      [2.5, { "joint:rail": 0.0288, "joint:hinge1": -0.1826, "joint:hinge2": 0.5702, "joint:hinge3": -1.8969 }],
      [14.5, { "joint:rail": 0.0, "joint:hinge1": 1.5708, "joint:hinge2": 0.0, "joint:hinge3": 0.0 }],
    ],
  },
];

let server: ChildProcess | null = null;
let spawnError: Error | null = null;
let serverUrl = "";
let projectsRoot = "";

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
  projectsRoot = mkdtempSync(path.join(os.tmpdir(), "bgsim-pendulum-cart-"));
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

for (const c of cases) {
  test(`${c.example}: runs the swing-up, the catch and the recovery`, async ({ page, request }) => {
    const project = `x512-${c.example}-${Date.now()}-${test.info().workerIndex}`;
    const created = await request.post(`${serverUrl}/api/projects`, {
      data: { name: project, example: c.example },
    });
    expect(created.status(), await created.text()).toBe(201);
    try {
      await page.setViewportSize({ width: 1600, height: 1000 });
      await page.goto(`${serverUrl}/?project=${encodeURIComponent(project)}&model=${c.example}`);
      await expect(page.getByTestId("canvas-surface")).toBeVisible({ timeout: 30_000 });
      await expect(page.getByTestId("run-button")).toBeEnabled();

      for (const name of c.nodes) {
        await expect(node(page, name)).toBeVisible();
      }

      await page.getByTestId("run-button").click();
      const runStatus = page.getByTestId("run-status");
      await expect(runStatus).toHaveAttribute("data-status", "done", { timeout: 360_000 });
      await expect(runStatus).toContainText(/done in/i);

      await page.getByRole("tab", { name: "Signals" }).click();
      await expect(page.getByTestId("signal-browser")).toBeVisible();
      await plotSignal(page, "Ctrl/th1");

      await page.getByRole("tab", { name: "Plots" }).click();
      const chart = page.getByTestId("plot-chart");
      await expect(chart).toBeVisible();
      await expect(chart).toHaveAttribute("data-series-count", "1");
      await expect
        .poll(async () => Number((await chart.getAttribute("data-points")) ?? "0"), {
          message: "the run's signals are loaded",
          timeout: 30_000,
        })
        .toBeGreaterThan(0);

      const over = page.locator('[data-testid="plot-chart"] .u-over');
      await expect(over).toBeVisible();
      const box = await over.boundingBox();
      if (box === null) {
        throw new Error("the plot has no measurable area");
      }
      const legendTime = page.getByTestId("legend-time");
      const readAt = async (time: number): Promise<number> => {
        await page.mouse.move(box.x + (box.width * time) / c.tEnd, box.y + box.height * 0.45);
        await expect
          .poll(async () => Number(/t = ([\d.]+)/.exec((await legendTime.textContent()) ?? "")?.[1] ?? "NaN"), {
            message: `the cursor reaches t = ${time} s`,
          })
          .toBeGreaterThan(time - 0.35);
        const shown = Number(/t = ([\d.]+)/.exec((await legendTime.textContent()) ?? "")?.[1] ?? "NaN");
        expect(shown).toBeLessThan(time + 0.35);
        return legendNumber(page, "Ctrl/th1");
      };

      // Balanced before the pulse: link 1 within 0.2 deg (0.0035 rad) of upright.
      expect(Math.abs(await readAt(c.tPulse - 0.6))).toBeLessThan(0.0035);
      // Just after the pulse link 1 is deflected by more than 5.7 deg (0.1 rad).
      expect(Math.abs(await readAt(c.tPulse + c.tPeek))).toBeGreaterThan(0.1);
      // Recovered at the end of the run.
      expect(Math.abs(await readAt(c.tEnd - 0.2))).toBeLessThan(0.0035);

      // The same run plays in 3D: the rail and every link follow their joint signals.
      await page.getByRole("tab", { name: "3D View" }).click();
      await expect(page.getByTestId("scene-view")).toHaveAttribute("data-state", "loaded", {
        timeout: 30_000,
      });
      const bar = page.getByTestId("playback-bar");
      await expect(bar).toHaveAttribute("data-mode", "playback", { timeout: 30_000 });

      const tree = page.getByTestId("scene-tree");
      await expect(tree).toContainText("cart");
      for (let i = 1; i <= c.links; i += 1) {
        await expect(tree).toContainText(`link${i}`);
      }

      await page.getByTestId("bindings-toggle").click();
      await expect(page.getByTestId("bindings-editor")).toBeVisible();
      for (let i = 0; i <= c.links; i += 1) {
        await expect(page.getByTestId(`binding-row-${i}`)).not.toHaveAttribute("data-invalid", "true");
        await expect(page.getByTestId(`binding-problem-${i}`)).toHaveCount(0);
      }
      await page.getByTestId("bindings-toggle").click();

      const appliedTo = async (target: string): Promise<number | undefined> => {
        const raw = await bar.getAttribute("data-applied");
        return (JSON.parse(raw ?? "{}") as Record<string, number>)[target];
      };
      for (const [time, joints] of c.playback) {
        await page.getByTestId("playback-time").fill(String(time));
        for (const [target, expected] of Object.entries(joints)) {
          await expect
            .poll(async () => Math.abs(((await appliedTo(target)) ?? Number.NaN) - expected), {
              message: `${target} at t = ${time} s`,
            })
            .toBeLessThan(0.02);
        }
      }
      // Hanging at 0.5 s: link 1 is at -pi/2, and it has left that pose by the first time above.
      await page.getByTestId("playback-time").fill("0.5");
      await expect
        .poll(async () => Math.abs(((await appliedTo("joint:hinge1")) ?? Number.NaN) + Math.PI / 2))
        .toBeLessThan(0.01);

      await page.screenshot({ path: `test-results/${c.example}-3d.png` });

      await page.getByTestId("playback-rewind").click();
      await expect.poll(async () => Number(await bar.getAttribute("data-time"))).toBe(0);
      await page.getByTestId("playback-speed").selectOption("0.25");
      await page.getByTestId("playback-toggle").click();
      await expect(bar).toHaveAttribute("data-playing", "true");
      await expect
        .poll(async () => Number(await bar.getAttribute("data-time")))
        .toBeGreaterThan(0.05);
      await page.getByTestId("playback-toggle").click();
    } finally {
      await request.delete(`${serverUrl}/api/projects/${project}`);
    }
  });
}
