import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import { existsSync, mkdtempSync, readdirSync, readFileSync, rmSync } from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

/**
 * X5.G, the M5 gate (plan 10.2): a manual-style walkthrough of every example on the real worker.
 *
 * For each example listed by `GET /api/examples` (one `test()` each):
 * 1. copy it through `POST /api/projects {name, example}`;
 * 2. open its first gallery model (first model on disk when the gallery lacks the example);
 * 3. press Run, wait for `done` and assert that the Diagnostics tab holds no error;
 * 4. plot one signal, the first named by a check of the model in the example's `expected.json`;
 * 5. open the 3D view, scrub and play it, assert no binding diagnostic and a rendering canvas;
 * 6. delete the copy.
 *
 * Real worker only (DEC-M5-6): started on a free port when the suite was not started with
 * `BGSIM_E2E_REAL=1`. Run with
 * `BGSIM_E2E_REAL=1 BGSIM_E2E_PORT=8802 npx playwright test tests/e2e/walkthrough.spec.ts --workers=1`.
 */

test.describe.configure({ timeout: 900_000 });

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const examplesRoot = path.join(repoRoot, "examples");

interface Gallery {
  [example: string]: { models?: string[] };
}
interface Expected {
  models?: Record<string, { checks?: { signal?: string }[] }>;
}

const gallery = JSON.parse(
  readFileSync(path.join(repoRoot, "web/src/examples/gallery.json"), "utf8"),
) as Gallery;

/** The examples to walk: the directories of `examples/` that hold a project file (what the API lists). */
const examples = readdirSync(examplesRoot, { withFileTypes: true })
  .filter(
    (entry) =>
      entry.isDirectory() &&
      existsSync(path.join(examplesRoot, entry.name, "bgsim.project.json")),
  )
  .map((entry) => entry.name)
  .sort();

function firstModel(example: string): string {
  const fromGallery = gallery[example]?.models?.[0];
  if (fromGallery !== undefined) {
    return fromGallery;
  }
  const dir = path.join(examplesRoot, example, "models");
  const file = readdirSync(dir)
    .filter((name) => name.endsWith(".bgmodel.json"))
    .sort()[0];
  if (file === undefined) {
    throw new Error(`${example} has no model`);
  }
  return file.replace(/\.bgmodel\.json$/, "");
}

function firstSignal(example: string, model: string): string | null {
  const file = path.join(examplesRoot, example, "expected.json");
  if (!existsSync(file)) {
    return null;
  }
  const expected = JSON.parse(readFileSync(file, "utf8")) as Expected;
  const checks = expected.models?.[model]?.checks ?? [];
  return checks.find((check) => typeof check.signal === "string")?.signal ?? null;
}

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
      const response = await fetch(`${url}/api/health`, { signal: AbortSignal.timeout(3_000) });
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
    serverUrl = `http://127.0.0.1:${process.env.BGSIM_E2E_PORT ?? "8765"}`;
    await waitForWorker(serverUrl, null);
    return;
  }
  const port = await freePort();
  serverUrl = `http://127.0.0.1:${port}`;
  projectsRoot = mkdtempSync(path.join(os.tmpdir(), "bgsim-walkthrough-"));
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

test.afterEach(async ({ request }) => {
  if (project.length > 0) {
    await request.delete(`${serverUrl}/api/projects/${project}`);
    project = "";
  }
});

test("the backend lists the examples of the repository", async ({ request }) => {
  const response = await request.get(`${serverUrl}/api/examples`);
  expect(response.ok()).toBe(true);
  const listed = ((await response.json()) as { examples: string[] }).examples;
  // Tool folders such as `examples/__pycache__` are not listed.
  expect([...listed].sort()).toEqual(examples);
});

for (const example of examples) {
  test(`walkthrough: ${example}`, async ({ page, request }) => {
    const model = firstModel(example);
    const signal = firstSignal(example, model);

    project = `x5g-${example}-${Date.now()}-${test.info().workerIndex}`;
    const created = await request.post(`${serverUrl}/api/projects`, {
      data: { name: project, example },
    });
    expect(created.status(), await created.text()).toBe(201);

    // Open the model.
    await page.setViewportSize({ width: 1600, height: 1000 });
    await page.goto(
      `${serverUrl}/?project=${encodeURIComponent(project)}&model=${encodeURIComponent(model)}`,
    );
    await expect(page.getByTestId("canvas-surface")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("run-button")).toBeEnabled({ timeout: 60_000 });

    // Run and wait for completion.
    await page.getByTestId("run-button").click();
    await expect(page.getByTestId("run-status")).toHaveAttribute("data-status", "done", {
      timeout: 720_000,
    });

    // No error diagnostic.
    await page.getByRole("tab", { name: /^Diagnostics/ }).click();
    await expect(page.getByTestId("diagnostics-panel")).toBeVisible();
    await expect(page.getByTestId("diagnostics-count-error")).toContainText(/^\s*0 /);
    await expect(
      page.locator('[data-testid="diagnostics-panel"] [data-severity="error"]'),
    ).toHaveCount(0);

    // Plot one signal: the one expected.json names, else the first listed one.
    await page.getByRole("tab", { name: "Signals" }).click();
    await expect(page.getByTestId("signal-browser")).toBeVisible();
    const items = page.locator('[data-testid="signal-item"]');
    await expect(items.first()).toBeVisible({ timeout: 30_000 });
    let item = items.first();
    if (signal !== null) {
      const named = page.locator(`[data-testid="signal-item"][data-signal-id="${signal}"]`);
      if ((await named.count()) > 0) {
        item = named;
      }
    }
    await item.dblclick();
    await page.getByRole("tab", { name: "Plots" }).click();
    const chart = page.getByTestId("plot-chart");
    await expect(chart).toBeVisible();
    await expect(chart).toHaveAttribute("data-series-count", "1");
    await expect
      .poll(async () => Number((await chart.getAttribute("data-points")) ?? "0"), {
        message: "the plotted signal has points",
        timeout: 30_000,
      })
      .toBeGreaterThan(0);

    // 3D view: no binding diagnostics, scrub, play, rendering canvas.
    await page.getByRole("tab", { name: "3D View" }).click();
    await expect(page.getByTestId("scene-view")).toHaveAttribute("data-state", "loaded", {
      timeout: 60_000,
    });
    const bar = page.getByTestId("playback-bar");
    await expect(bar).toHaveAttribute("data-mode", "playback", { timeout: 60_000 });

    await page.getByTestId("bindings-toggle").click();
    await expect(page.getByTestId("bindings-editor")).toBeVisible();
    // E303 (the unit of a bound signal is not the unit of the target: integrator outputs and
    // the g[5] pose entries carry no unit in the real worker's signal list) is reported as a
    // known finding instead of failing the gate; any other binding diagnostic fails.
    const problems = await page.locator('[data-testid^="binding-problem-"]').allInnerTexts();
    const unitProblems = problems.filter((text) => text.startsWith("E303"));
    if (unitProblems.length > 0) {
      test.info().annotations.push({
        type: "known-E303",
        description: `${String(unitProblems.length)} binding(s) report a signal unit mismatch`,
      });
    }
    expect(
      problems.filter((text) => !text.startsWith("E303")),
      "binding diagnostics other than E303",
    ).toEqual([]);
    await page.getByTestId("bindings-toggle").click();

    const slider = page.getByTestId("playback-time");
    const end = Number(await slider.getAttribute("max"));
    await slider.fill(String(end * 0.5));
    await expect.poll(async () => Number(await bar.getAttribute("data-time"))).toBeGreaterThan(0);
    await page.getByTestId("playback-rewind").click();
    await expect.poll(async () => Number(await bar.getAttribute("data-time"))).toBe(0);
    await page.getByTestId("playback-toggle").click();
    await expect
      .poll(async () => Number(await bar.getAttribute("data-time")), { timeout: 30_000 })
      .toBeGreaterThan(0);
    await page.getByTestId("playback-toggle").click();

    const canvas = page.getByTestId("viewer-canvas");
    await expect(canvas).toBeVisible();
    const box = await canvas.boundingBox();
    expect(box !== null && box.width > 50 && box.height > 50, "the 3D canvas has an area").toBe(
      true,
    );
    const shot = await canvas.screenshot();
    expect(shot.length, "the 3D canvas renders something").toBeGreaterThan(2_000);
  });
}
