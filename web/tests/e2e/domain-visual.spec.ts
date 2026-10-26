import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/**
 * W2.3 acceptance against the real worker:
 *
 * 1. copy the `rlc-dual` example, enter `Bondgraph` and assert one causal
 *    stroke on each of its four bonds (`bc1` to, `bc2` from, `bc3` to,
 *    `bc4` from), each physically near the correct end; screenshot the canvas;
 * 2. run the model, set the global inspect time from a plot cursor and hover
 *    `bc4`: the read-out shows e, f and P = e·f at that time;
 * 3. create a small `mm -> m` model through the API: `×0.001` appears on the
 *    scaled signal (`c1`) and nothing appears on the 1.0 signal (`c2`).
 *
 * The spec starts its own backend on a free port unless the real-worker pass
 * already serves 8765, exactly like `rlc-dual.spec.ts`.
 */

test.describe.configure({ timeout: 240_000, mode: "serial" });

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");

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

test.beforeAll(async ({ request: _request }, testInfo) => {
  testInfo.setTimeout(240_000);
  if (process.env.BGSIM_E2E_REAL === "1") {
    serverUrl = "http://127.0.0.1:8765";
    await waitForWorker(serverUrl, null);
    return;
  }

  const port = await freePort();
  serverUrl = `http://127.0.0.1:${port}`;
  projectsRoot = mkdtempSync(path.join(os.tmpdir(), "bgsim-domain-visual-"));
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
      spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
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

async function createProject(
  request: APIRequestContext,
  example: string | null,
): Promise<void> {
  project = `w23-domain-${Date.now()}-${test.info().workerIndex}`;
  const payload = example === null ? { name: project } : { name: project, example };
  const created = await request.post(`${serverUrl}/api/projects`, { data: payload });
  expect(created.status(), await created.text()).toBe(201);
}

function node(page: Page, name: string) {
  return page.locator(`[data-testid="diagram-node"][data-node-name="${name}"]`);
}

async function enterBondgraph(page: Page): Promise<void> {
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.goto(`${serverUrl}/?project=${encodeURIComponent(project)}&model=rlc-dual`);
  await expect(page.getByTestId("canvas-surface")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("run-button")).toBeEnabled();
  const bondgraph = node(page, "Bondgraph");
  await expect(bondgraph).toBeVisible();
  await bondgraph.click();
  await expect(bondgraph).toHaveClass(/is-selected/);
  await bondgraph.dblclick({ position: { x: 8, y: 8 } });
  await expect(page.getByTestId("subsystem-breadcrumbs")).toBeVisible();
  await expect(page.getByTestId("breadcrumb-1")).toHaveAttribute(
    "data-breadcrumb-name",
    "Bondgraph",
  );
  await expect(page.getByTestId("diagram-node")).toHaveCount(5);
  await expect(page.locator('[data-testid^="edge-"]')).toHaveCount(4);
}

test("draws a causal stroke on each bond end and screenshots the canvas", async ({
  page,
  request,
}) => {
  await createProject(request, "rlc-dual");
  await enterBondgraph(page);

  const expected: Record<string, "from" | "to"> = {
    bc1: "to",
    bc2: "from",
    bc3: "to",
    bc4: "from",
  };
  for (const [id, strokeAt] of Object.entries(expected)) {
    await expect(page.getByTestId(`causal-stroke-${id}`), id).toHaveAttribute(
      "data-stroke-at",
      strokeAt,
      { timeout: 30_000 },
    );
  }
  await expect(page.locator('[data-testid^="causal-stroke-"]')).toHaveCount(4);

  // Each bar sits at the end the worker named: nearer that endpoint than the
  // other one, and perpendicular to the bond.
  const geometry = await page.evaluate((expectedIds) => {
    return expectedIds.map((id) => {
      const path = document.querySelector<SVGPathElement>(
        `[data-testid="edge-${id}"] .react-flow__edge-path`,
      );
      const stroke = document.querySelector<SVGLineElement>(
        `[data-testid="causal-stroke-${id}"]`,
      );
      if (path === null || stroke === null) {
        return null;
      }
      const total = path.getTotalLength();
      const from = path.getPointAtLength(0);
      const to = path.getPointAtLength(total);
      const x1 = Number(stroke.getAttribute("x1"));
      const y1 = Number(stroke.getAttribute("y1"));
      const x2 = Number(stroke.getAttribute("x2"));
      const y2 = Number(stroke.getAttribute("y2"));
      const middle = { x: (x1 + x2) / 2, y: (y1 + y2) / 2 };
      const distance = (a: { x: number; y: number }, b: { x: number; y: number }) =>
        Math.hypot(a.x - b.x, a.y - b.y);
      // The bar is perpendicular to the bond direction.
      const bond = { x: to.x - from.x, y: to.y - from.y };
      const bar = { x: x2 - x1, y: y2 - y1 };
      const cosine =
        (bond.x * bar.x + bond.y * bar.y) /
        (Math.hypot(bond.x, bond.y) * Math.hypot(bar.x, bar.y));
      return {
        id,
        strokeAt: stroke.getAttribute("data-stroke-at"),
        fromDistance: distance(middle, from),
        toDistance: distance(middle, to),
        perpendicular: Math.abs(cosine) < 0.05,
      };
    });
  }, Object.keys(expected));
  for (const entry of geometry) {
    expect(entry, entry?.id).not.toBeNull();
    if (entry === null) {
      continue;
    }
    expect(entry.perpendicular, `${entry.id} is perpendicular`).toBe(true);
    if (entry.strokeAt === "to") {
      expect(entry.toDistance, `${entry.id} is at to`).toBeLessThan(entry.fromDistance);
    } else {
      expect(entry.fromDistance, `${entry.id} is at from`).toBeLessThan(entry.toDistance);
    }
  }

  // Keep the pointer off the canvas so no hover tooltip is captured.
  await page.mouse.move(4, 4);
  const canvas = page.getByTestId("canvas-surface");
  await expect(canvas).toHaveScreenshot("rlc-dual-strokes.png", {
    maxDiffPixels: 400,
    animations: "disabled",
    caret: "hide",
  });
});

async function edgePoint(page: Page, id: string): Promise<{ x: number; y: number } | null> {
  return page.evaluate((edgeId) => {
    const path = document.querySelector<SVGPathElement>(
      `[data-testid="edge-${edgeId}"] .react-flow__edge-path`,
    );
    if (path === null) {
      return null;
    }
    const matrix = path.getScreenCTM();
    if (matrix === null) {
      return null;
    }
    const middle = path.getPointAtLength(path.getTotalLength() / 2);
    const screen = middle.matrixTransform(matrix);
    return { x: screen.x, y: screen.y };
  }, id);
}

test("hover shows e, f and P at the global inspect time", async ({ page, request }) => {
  await createProject(request, "rlc-dual");
  await enterBondgraph(page);

  // Before a run there is nothing to read: the hint says so.
  const before = await edgePoint(page, "bc4");
  expect(before).not.toBeNull();
  await page.mouse.move(Math.round(before!.x), Math.round(before!.y));
  const hint = page.getByTestId("hover-readout");
  await expect(hint).toBeVisible();
  await expect(hint).toHaveAttribute("data-state", "hint");
  await expect(hint).toContainText("Run the model");
  await page.mouse.move(4, 4);
  await expect(hint).toBeHidden();

  await page.getByTestId("run-button").click();
  const runStatus = page.getByTestId("run-status");
  await expect(runStatus).toHaveAttribute("data-status", "done", { timeout: 120_000 });

  await page.getByRole("tab", { name: "Signals" }).click();
  const signal = page.locator(
    '[data-testid="signal-item"][data-signal-id="Bondgraph/C1/p.e"]',
  );
  await expect(signal).toHaveCount(1);
  await signal.dblclick();
  await page.getByRole("tab", { name: "Plots" }).click();
  const chart = page.getByTestId("plot-chart");
  await expect(chart).toBeVisible();
  const over = chart.locator(".u-over");
  await expect(over).toBeVisible();
  const area = await over.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    return { x: rect.left, y: rect.top, width: rect.width, height: rect.height };
  });
  expect(area.width).toBeGreaterThan(0);
  await page.mouse.move(
    Math.round(area.x + area.width * 0.5),
    Math.round(area.y + area.height * 0.5),
  );
  const inspect = page.getByTestId("plot-inspect-time");
  await expect(inspect).not.toContainText("—");
  const inspectText = (await inspect.textContent()) ?? "";
  const inspectValue = (inspectText.split("=")[1] ?? "").trim();
  const inspectTime = Number.parseFloat(inspectValue.replace(/[^\d.eE+-]/g, ""));
  expect(Number.isFinite(inspectTime)).toBe(true);

  // Midpoint of bc4's painted path, so the pointer really lands on the bond.
  const point = await edgePoint(page, "bc4");
  expect(point).not.toBeNull();
  await page.mouse.move(Math.round(point!.x), Math.round(point!.y));

  const readout = page.getByTestId("hover-readout");
  await expect(readout).toBeVisible({ timeout: 15_000 });
  await expect(readout).toHaveAttribute("data-state", "ready");
  await expect(readout).toContainText("C1/p");
  await expect(readout).toContainText("e");
  await expect(readout).toContainText("f");
  await expect(readout).toContainText("P = e·f");
  const effort = readout.getByTestId("hover-row-e");
  const flow = readout.getByTestId("hover-row-f");
  const power = readout.getByTestId("hover-row-P");
  await expect(effort).toContainText("effort");
  await expect(flow).toContainText("flow");
  await expect(power).toContainText("effort*flow");
  await expect(effort).not.toContainText("—");
  await expect(flow).not.toContainText("—");
  await expect(power).not.toContainText("—");
  // The read-out is at the global inspect time, not its own cursor.
  await expect(readout).toContainText("t =");
  await expect(readout).toContainText(inspectValue);
});

const UNITS_MODEL = {
  format: "bgsim.model",
  language: "0.1.0",
  name: "units",
  diagram: {
    nodes: [
      {
        id: "n1",
        name: "MmOut",
        block: {
          inline: {
            source:
              '@block MmOut begin\n    @outputs y::Real = 0.0, [unit = "mm"]\n    @equations y ~ 5.0\nend\n',
          },
        },
        position: { x: 80, y: 80 },
        rotation: 0,
        flipX: false,
        params: {},
        constants: {},
        starts: {},
        ui: { showLabel: true, color: null },
      },
      {
        id: "n2",
        name: "MSink",
        block: {
          inline: {
            source:
              '@block MSink begin\n    @inputs u::Real, [unit = "m"]\n    @outputs y::Real = 0.0, [unit = "m"]\n    @equations y ~ u\nend\n',
          },
        },
        position: { x: 420, y: 80 },
        rotation: 0,
        flipX: false,
        params: {},
        constants: {},
        starts: {},
        ui: { showLabel: true, color: null },
      },
      {
        id: "n3",
        name: "MOut",
        block: {
          inline: {
            source:
              '@block MOut begin\n    @outputs y::Real = 0.0, [unit = "m"]\n    @equations y ~ 5.0\nend\n',
          },
        },
        position: { x: 80, y: 260 },
        rotation: 0,
        flipX: false,
        params: {},
        constants: {},
        starts: {},
        ui: { showLabel: true, color: null },
      },
      {
        id: "n4",
        name: "MSink2",
        block: {
          inline: {
            source:
              '@block MSink begin\n    @inputs u::Real, [unit = "m"]\n    @outputs y::Real = 0.0, [unit = "m"]\n    @equations y ~ u\nend\n',
          },
        },
        position: { x: 420, y: 260 },
        rotation: 0,
        flipX: false,
        params: {},
        constants: {},
        starts: {},
        ui: { showLabel: true, color: null },
      },
    ],
    connections: [
      {
        id: "c1",
        kind: "signal",
        from: { node: "n1", port: "y" },
        to: { node: "n2", port: "u" },
        route: [],
        label: null,
      },
      {
        id: "c2",
        kind: "signal",
        from: { node: "n3", port: "y" },
        to: { node: "n4", port: "u" },
        route: [],
        label: null,
      },
    ],
    subsystemPorts: [],
    annotations: [],
  },
  settings: {
    t_start: 0,
    t_end: 0.5,
    solver: "auto",
    reltol: 1e-6,
    abstol: 1e-8,
    max_step: null,
    output: { mode: "points", points: 2 },
    event_limit: 10000,
  },
  plots: [],
  scene: null,
  bindings: [],
};

test("shows ×0.001 on the scaled signal and nothing on 1.0", async ({ page, request }) => {
  await createProject(request, null);
  const written = await request.put(
    `${serverUrl}/api/projects/${project}/models/units`,
    { data: UNITS_MODEL },
  );
  expect(written.status(), await written.text()).toBe(200);

  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.goto(`${serverUrl}/?project=${encodeURIComponent(project)}&model=units`);
  await expect(page.getByTestId("canvas-surface")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator('[data-testid^="edge-"]')).toHaveCount(2);
  const badge = page.getByTestId("unit-badge-c1");
  await expect(badge).toHaveText("×0.001", { timeout: 30_000 });
  await expect(page.locator('[data-testid="unit-badge-c2"]')).toHaveCount(0);

  const legend = page.getByTestId("canvas-legend");
  await expect(legend).toBeVisible();
  await expect(legend.getByTestId("legend-causal")).toBeVisible();
  await expect(legend.getByTestId("legend-unit")).toBeVisible();
  await expect(legend.getByTestId("legend-domain-Generic")).toBeVisible();
});
