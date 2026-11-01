import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

/**
 * XY plots on a real run: the `van-der-pol` example's tunnel-diode oscillator (about 32 000
 * rows). The saved phase portrait (`p7`, Yc/y against Xc/y, equal aspect) opens from the
 * Plots toolbar as an XY panel that draws every row of the run, and the dashboard's two XY
 * cards (`d15` phase portrait, `d16` diode current against voltage) draw against their x.
 *
 * Needs Julia: it starts a backend and the real worker on a free port unless the suite was
 * started with `BGSIM_E2E_REAL=1`. With BGSIM_SCREENSHOT_DIR set it writes
 * vdp-phase-portrait.png and vdp-dashboard.png there.
 */

test.describe.configure({ timeout: 240_000 });

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const shots = process.env.BGSIM_SCREENSHOT_DIR ?? "";

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
    if (spawnError !== null) throw new Error(`the backend did not start: ${spawnError.message}`);
    if (child !== null && child.exitCode !== null) throw new Error(`the backend exited with code ${child.exitCode}`);
    try {
      const response = await fetch(`${url}/api/health`, { signal: AbortSignal.timeout(3_000) });
      if (response.ok) {
        const health = (await response.json()) as { worker?: string };
        last = `worker state ${JSON.stringify(health.worker)}`;
        if (health.worker === "ready") return;
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
    serverUrl = `http://127.0.0.1:${process.env.BGSIM_E2E_PORT ?? "8765"}`;
    await waitForWorker(serverUrl, null);
    return;
  }
  const port = await freePort();
  serverUrl = `http://127.0.0.1:${port}`;
  projectsRoot = mkdtempSync(path.join(os.tmpdir(), "bgsim-vdp-xy-"));
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

test.afterAll(() => {
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

test.beforeEach(async ({ request }) => {
  project = `vdp-xy-${Date.now()}-${test.info().workerIndex}`;
  const created = await request.post(`${serverUrl}/api/projects`, {
    data: { name: project, example: "van-der-pol" },
  });
  expect(created.status(), await created.text()).toBe(201);
});

test.afterEach(async ({ request }) => {
  if (project.length > 0) {
    await request.delete(`${serverUrl}/api/projects/${project}`);
    project = "";
  }
});

test("the tunnel-diode phase portrait opens as an XY panel and the dashboard draws its XY cards", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.addInitScript(() => {
    // A tall dock for the Plots panel (kept when the test changes it later).
    if (localStorage.getItem("bgsim.layout.rows") === null) {
      localStorage.setItem("bgsim.layout.rows", JSON.stringify({ main: 40, dock: 60 }));
    }
  });
  await page.goto(`${serverUrl}/?project=${encodeURIComponent(project)}&model=vdp-tunnel-diode`);
  await expect(page.getByTestId("run-button")).toBeEnabled({ timeout: 30_000 });
  await page.getByTestId("run-button").click();
  await expect(page.getByTestId("run-status")).toHaveAttribute("data-status", "done", { timeout: 180_000 });

  await page.getByRole("tab", { name: "Plots" }).click();
  await page.getByTestId("saved-plot-select").selectOption("p7");
  const chart = page.getByTestId("plot-chart-panel").last().getByTestId("plot-chart");
  await expect(chart).toHaveAttribute("data-mode", "xy");
  await expect(chart).toHaveAttribute("data-x-signal", "Xc/y");
  await expect(chart).toHaveAttribute("data-equal-aspect", "true");
  // Every row of the run (whole rows, no min/max envelope).
  await expect
    .poll(async () => Number((await chart.getAttribute("data-points")) ?? "0"), { timeout: 30_000 })
    .toBeGreaterThan(30_000);
  const drawn = Number(await chart.getAttribute("data-drawn-points"));
  const renderMs = Number(await chart.getAttribute("data-render-ms"));
  test.info().annotations.push({
    type: "xy-render",
    description: `${await chart.getAttribute("data-points")} rows, ${drawn} drawn points, ${renderMs} ms`,
  });
  expect(drawn).toBeGreaterThan(100);
  expect(renderMs).toBeLessThan(50);
  if (shots.length > 0) {
    mkdirSync(shots, { recursive: true });
    await page.getByTestId("plot-chart-panel").last().screenshot({ path: path.join(shots, "vdp-phase-portrait.png") });
    writeFileSync(path.join(shots, "vdp-xy-render.txt"), `${test.info().annotations.at(-1)?.description ?? ""}
`);
  }

  // A shorter dock: the dashboard gets the room.
  await page.evaluate(() => {
    localStorage.setItem("bgsim.layout.rows", JSON.stringify({ main: 80, dock: 20 }));
  });
  await page.reload();
  await expect(page.getByTestId("run-button")).toBeEnabled({ timeout: 30_000 });
  await page.getByRole("tab", { name: "Dashboard" }).click();
  await page.getByTestId("run-button").click();
  await expect(page.getByTestId("run-status")).toHaveAttribute("data-status", "done", { timeout: 180_000 });
  for (const [card, x] of [
    ["d15", "Xc/y"],
    ["d16", "Vm/y"],
  ] as const) {
    const xy = page.getByTestId(`dash-plot-${card}`).getByTestId("plot-chart");
    await expect(xy).toHaveAttribute("data-mode", "xy");
    await expect(xy).toHaveAttribute("data-x-signal", x);
    await expect
      .poll(async () => Number((await xy.getAttribute("data-points")) ?? "0"), { timeout: 30_000 })
      .toBeGreaterThan(30_000);
  }
  if (shots.length > 0) {
    // The two XY cards side by side (the dashboard scrolls; clip to the cards).
    const first = page.getByTestId("dash-card-d15");
    await first.scrollIntoViewIfNeeded();
    const a = await first.boundingBox();
    const b = await page.getByTestId("dash-card-d16").boundingBox();
    if (a !== null && b !== null) {
      const x = Math.min(a.x, b.x) - 8;
      const y = Math.min(a.y, b.y) - 8;
      await page.screenshot({
        path: path.join(shots, "vdp-dashboard.png"),
        clip: {
          x,
          y,
          width: Math.max(a.x + a.width, b.x + b.width) + 8 - x,
          height: Math.max(a.y + a.height, b.y + b.height) + 8 - y,
        },
      });
    }
  }
});
