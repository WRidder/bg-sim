import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type Locator, type Page } from "@playwright/test";

/**
 * X-MB2 acceptance (plan 9.10, Gate B) against the real worker, the balancer half:
 *
 * 1. import the `reaction-wheel-2d` sample through the Open dialog (the sample
 *    flow copies `examples/<name>` into the projects root and opens its first
 *    model, `balancer`);
 * 2. assert the planar multibond canvas: every `Power{Planar}` bond is a
 *    two-stroke bundle (`data-multibond-strokes="2"`, two stroke paths, one causal
 *    bar) while the two `Rotation` drive bonds stay single-stroke;
 * 3. take the stable `reaction-wheel-2d.png` canvas screenshot;
 * 4. press Run, wait for `done`;
 * 5. plot the body angle and the wheel speed and read them from the legend: the
 *    body stays inside the 0.02 rad band and the wheel has spun up to about
 *    46 rad/s by the end of the run.
 */

test.describe.configure({ timeout: 300_000 });

const repoRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../..",
);

/** The gravity-on balancer's wheel speed at the end of the run (rad/s). */
const WHEEL_END = 46.213366;
/** The run's end and the stated balance band. */
const T_END = 3.0;
const THETA_BAND = 0.02;

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
  projectsRoot = mkdtempSync(path.join(os.tmpdir(), "bgsim-reaction-wheel-"));
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

/** Fit the diagram and wait until the viewport transform stops changing. */
async function fitAndSettle(page: Page): Promise<void> {
  const fit = page.getByTestId("fit-view");
  await expect(fit).toBeVisible();
  await fit.click();
  const viewport = page.locator(".react-flow__viewport");
  let previous = "";
  await expect
    .poll(
      async () => {
        const current = await viewport.evaluate(
          (element) => element.getAttribute("style") ?? "",
        );
        const stable = current.length > 0 && current === previous;
        previous = current;
        return stable;
      },
      { intervals: [100, 100, 100, 100, 100, 100, 100, 100], timeout: 8_000 },
    )
    .toBe(true);
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

test("imports the planar reaction-wheel balancer, shows two strokes, runs it and reads the wheel", async ({
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

  await page.getByTestId("open-project").click();
  await expect(page.getByTestId("open-dialog")).toBeVisible();
  const sample = page.getByTestId("sample-option-reaction-wheel-2d");
  await expect(sample).toBeVisible();
  await sample.click();
  await expect(page).toHaveURL(/project=reaction-wheel-2d/);
  await expect(page).toHaveURL(/model=balancer/);
  project = new URL(page.url()).searchParams.get("project") ?? "";
  expect(project).toMatch(/^reaction-wheel-2d(-\d+)?$/);

  await expect(page.getByTestId("canvas-surface")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("run-button")).toBeEnabled();
  for (const name of [
    "Ground",
    "Pivot",
    "LinkB",
    "BodyJ",
    "Body",
    "WheelJ",
    "Wheel",
    "PivotSe",
    "Motor",
    "Ref",
    "PoseJ1",
    "PoseB",
    "PoseW",
    "Ctrl",
  ]) {
    await expect(node(page, name)).toBeVisible();
  }

  // Planar: two strokes on every power bond, one causal bar per bundle.
  const planarBonds = ["c01", "c02", "c03", "c04", "c05", "c06"];
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
  // The two Rotation drive bonds are scalar bonds: one stroke, no bundle attributes.
  for (const id of ["c10", "c11"]) {
    const drive = page.getByTestId(`edge-${id}`);
    await expect(drive).toBeVisible();
    expect(await drive.getAttribute("data-multibond-strokes")).toBeNull();
    await expect(drive.locator(".editor-edge__multibond-stroke")).toHaveCount(0);
  }

  // Stable screenshot of the flat graph with the two-stroke bundles.
  await fitAndSettle(page);
  const canvas = page.getByTestId("canvas-surface");
  await expect(canvas).toHaveScreenshot("reaction-wheel-2d.png", {
    maxDiffPixels: 400,
    animations: "disabled",
    caret: "hide",
  });

  await page.getByTestId("run-button").click();
  const runStatus = page.getByTestId("run-status");
  await expect(runStatus).toHaveAttribute("data-status", "done", {
    timeout: 240_000,
  });
  await expect(runStatus).toContainText(/done in/i);

  await page.getByRole("tab", { name: "Signals" }).click();
  await expect(page.getByTestId("signal-browser")).toBeVisible();
  for (const signal of ["Pivot/qout", "WheelJ/qdout"]) {
    const item = page.locator(
      `[data-testid="signal-item"][data-signal-id="${signal}"]`,
    );
    await expect(item).toHaveCount(1);
    await item.dblclick();
  }

  await page.getByRole("tab", { name: "Plots" }).click();
  const chart = page.getByTestId("plot-chart");
  await expect(chart).toBeVisible();
  await expect(chart).toHaveAttribute("data-series-count", "2");
  await expect(page.getByTestId("legend-item")).toHaveCount(2);
  await expect
    .poll(
      async () => Number((await chart.getAttribute("data-points")) ?? "0"),
      { message: "the run data is loaded into the plot", timeout: 60_000 },
    )
    .toBeGreaterThan(0);

  // The end of the run: the body is upright and the wheel carries the momentum.
  await hoverAt(page, chart, T_END);
  await expect
    .poll(async () => Math.abs((await legendSeconds(page)) - T_END))
    .toBeLessThan(0.02);
  expect(Math.abs(await legendNumber(page, "Pivot/qout"))).toBeLessThan(THETA_BAND);
  expect(Math.abs((await legendNumber(page, "WheelJ/qdout")) - WHEEL_END)).toBeLessThan(0.5);
});
