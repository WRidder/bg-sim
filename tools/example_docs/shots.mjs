// Screenshots for the example docs (X5.10): the model canvas and the 3D view.
// Usage (from web/): node ../tools/example_docs/shots.mjs <jobs.json>
// jobs.json: {baseUrl, jobs: [{project, model, name, kind: "diagram" | "scene", t?, out}]}
// Not part of any test suite; build.py starts the backend and passes its URL.
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(path.join(here, "../../web/package.json"));
const { chromium } = require("@playwright/test");

const { baseUrl, jobs } = JSON.parse(readFileSync(process.argv[2], "utf8"));

const byModel = new Map();
for (const job of jobs) {
  const key = `${job.project}\u0000${job.model}`;
  if (!byModel.has(key)) byModel.set(key, []);
  byModel.get(key).push(job);
}

async function open(browser, project, model, viewport) {
  const context = await browser.newContext({ viewport, deviceScaleFactor: 1 });
  const page = await context.newPage();
  await page.goto(`${baseUrl}/?project=${encodeURIComponent(project)}&model=${encodeURIComponent(model)}`);
  await page.getByTestId("canvas-surface").waitFor({ timeout: 60_000 });
  await page.getByTestId("run-button").waitFor({ state: "visible" });
  return { context, page };
}

const browser = await chromium.launch();
try {
  for (const group of byModel.values()) {
    const { project, model } = group[0];

    // The canvas: a wide window so that the fitted diagram is about 1200 px wide.
    const diagrams = group.filter((j) => j.kind === "diagram");
    if (diagrams.length > 0) {
      const { context, page } = await open(browser, project, model, { width: 1800, height: 900 });
      for (const job of diagrams) {
        await page.getByTestId("fit-view").click();
        await page.waitForTimeout(800);
        await page.getByTestId("canvas-surface").screenshot({ path: job.out });
        console.log(`diagram ${project}/${model} -> ${job.out}`);
      }
      await context.close();
    }

    // The 3D view: run the model in the UI, then step the playback time and screenshot the viewer.
    const scenes = group.filter((j) => j.kind === "scene");
    if (scenes.length > 0) {
      const { context, page } = await open(browser, project, model, { width: 1440, height: 1800 });
      await page.getByTestId("run-button").click();
      await page.getByTestId("run-status").and(page.locator('[data-status="done"]')).waitFor({ timeout: 1_800_000 });
      await page.getByRole("tab", { name: "3D View" }).click();
      await page.getByTestId("scene-view").and(page.locator('[data-state="loaded"]')).waitFor({ timeout: 60_000 });
      await page.getByTestId("playback-bar").and(page.locator('[data-mode="playback"]')).waitFor({ timeout: 60_000 });
      for (const job of scenes) {
        await page.getByTestId("playback-time").fill(String(job.t ?? 0));
        await page.waitForTimeout(400);
        await page.getByTestId("viewer-fit").click();
        await page.waitForTimeout(800);
        await page.getByTestId("viewer-canvas").screenshot({ path: job.out });
        console.log(`scene ${project}/${model} t=${job.t ?? 0} -> ${job.out}`);
      }
      await context.close();
    }
  }
} finally {
  await browser.close();
}
