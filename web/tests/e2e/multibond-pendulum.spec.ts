import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type Locator, type Page } from "@playwright/test";

/**
 * X-MB1 acceptance (plan 9.3 Gate A) against the real worker:
 *
 * 1. import the `multibond-pendulum-2d` sample through the Open dialog (the sample
 *    flow copies `examples/<name>` into the projects root and opens its first model);
 * 2. assert the planar multibond canvas: every `Power{Planar}` bond is a two-stroke
 *    bundle (`data-multibond-strokes="2"`, two stroke paths, one causal bar) while
 *    the `Rotation` drive bond stays a single stroke;
 * 3. press Run, wait for `done`;
 * 4. plot `Joint/q`, read it at t ≈ 0 (q0 = 0.01 rad) and at the quarter-period
 *    up-crossing (q ≈ 0), and assert the plot legend;
 * 5. take the stable `multibond-pendulum.png` canvas screenshot.
 *
 * Like `quarter-car.spec.ts` this spec needs Julia (the fake worker answers every
 * run from its `Synthetic/*` fixture). It starts a backend and the real worker on a
 * free port unless the suite was already started with `BGSIM_E2E_REAL=1`, and
 * deletes the imported project and the temporary projects root in `afterAll`.
 */

test.describe.configure({ timeout: 240_000 });

const repoRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../..",
);

/** The amplitude-corrected physical period from the J-MB4 pendulum, in seconds. */
const PERIOD = 1.4187960322337063;
/** The first upward zero crossing of q = q0*cos(2*pi*t/T): three quarters of a period. */
const QUARTER_CROSSING = (3 * PERIOD) / 4;

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
  projectsRoot = mkdtempSync(path.join(os.tmpdir(), "bgsim-multibond-pendulum-"));
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
  // A real mouse addresses whole CSS pixels: land on the pixel nearest `time`, and
  // stay one pixel inside the plot area so the t = 0 target is not on the boundary.
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

test("imports the 2D multibond pendulum, shows two strokes, runs it and reads the angle", async ({
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
  await page.goto(`${serverUrl}/`);
  await expect(page.getByTestId("open-project")).toBeVisible({ timeout: 30_000 });

  // Import a copy of the sample through the Open dialog (never edit the sample tree).
  await page.getByTestId("open-project").click();
  await expect(page.getByTestId("open-dialog")).toBeVisible();
  const sample = page.getByTestId("sample-option-multibond-pendulum-2d");
  await expect(sample).toBeVisible();
  await sample.click();
  await expect(page).toHaveURL(/project=multibond-pendulum-2d/);
  await expect(page).toHaveURL(/model=pendulum/);
  project = new URL(page.url()).searchParams.get("project") ?? "";
  expect(project).toMatch(/^multibond-pendulum-2d(-\d+)?$/);

  await expect(page.getByTestId("canvas-surface")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("run-button")).toBeEnabled();
  for (const name of [
    "Ground",
    "Pivot",
    "Joint",
    "Link",
    "J1",
    "Body",
    "Gravity",
    "Coriolis",
    "De",
    "Df",
    "Compose",
  ]) {
    await expect(node(page, name)).toBeVisible();
  }

  // Planar: two strokes on the pivot/link/body bonds, one causal bar per bundle.
  const planarBonds = ["c01", "c02", "c03", "c04", "c05", "c06", "c07", "c08", "c09"];
  for (const id of planarBonds) {
    const edge = page.getByTestId(`edge-${id}`);
    await expect(edge).toBeVisible();
    await expect(edge).toHaveAttribute("data-multibond-strokes", "2");
    await expect(edge.locator(".editor-edge__multibond-stroke")).toHaveCount(2);
    await expect(page.getByTestId(`causal-stroke-${id}`)).toHaveCount(1);
  }
  await expect(page.getByTestId("edge-c01")).toHaveAttribute(
    "aria-label",
    "Planar multibond, 3 components, 2 strokes",
  );
  // The Rotation drive bond is a scalar bond: one stroke, no bundle attributes.
  const drive = page.getByTestId("edge-c10");
  await expect(drive).toBeVisible();
  expect(await drive.getAttribute("data-multibond-strokes")).toBeNull();
  await expect(drive.locator(".editor-edge__multibond-stroke")).toHaveCount(0);

  // Stable screenshot of the flat graph with the two-stroke bundles.
  const canvas = page.getByTestId("canvas-surface");
  await expect(canvas).toHaveScreenshot("multibond-pendulum.png", {
    maxDiffPixels: 400,
    animations: "disabled",
    caret: "hide",
  });

  await page.getByTestId("run-button").click();
  const runStatus = page.getByTestId("run-status");
  await expect(runStatus).toHaveAttribute("data-status", "done", {
    timeout: 180_000,
  });
  await expect(runStatus).toContainText(/done in/i);

  await page.getByRole("tab", { name: "Signals" }).click();
  await expect(page.getByTestId("signal-browser")).toBeVisible();
  const signal = page.locator(
    '[data-testid="signal-item"][data-signal-id="Joint/q"]',
  );
  await expect(signal).toHaveCount(1);
  await signal.dblclick();

  await page.getByRole("tab", { name: "Plots" }).click();
  const chart = page.getByTestId("plot-chart");
  await expect(chart).toBeVisible();
  await expect(chart).toHaveAttribute("data-series-count", "1");
  await expect(page.getByTestId("legend-item")).toHaveCount(1);
  await expect(
    page.locator('[data-testid="legend-item"][data-signal-id="Joint/q"]'),
  ).toHaveCount(1);
  await expect
    .poll(
      async () => Number((await chart.getAttribute("data-points")) ?? "0"),
      { message: "the run data is loaded into the plot", timeout: 30_000 },
    )
    .toBeGreaterThan(0);

  // t ≈ 0: the joint starts at q0 = 0.01 rad.
  await hoverAt(page, chart, 0.0);
  await expect.poll(async () => legendSeconds(page)).toBeLessThan(0.02);
  expect(Math.abs((await legendNumber(page, "Joint/q")) - 0.01)).toBeLessThan(5e-4);

  // The first upward zero crossing is exactly three quarters of the period after t = 0.
  await hoverAt(page, chart, QUARTER_CROSSING);
  await expect
    .poll(async () => Math.abs((await legendSeconds(page)) - QUARTER_CROSSING))
    .toBeLessThan(0.01);
  expect(Math.abs(await legendNumber(page, "Joint/q"))).toBeLessThan(1e-3);
});
