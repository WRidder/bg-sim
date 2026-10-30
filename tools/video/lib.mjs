// Shared helpers for the bg-sim video capture scripts (X5.V).
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { mkdirSync, existsSync, readFileSync } from "node:fs";

const here = path.dirname(fileURLToPath(import.meta.url));
export const repoRoot = path.resolve(here, "../..");
export const framesDir = path.join(repoRoot, "media/video/frames");
const require = createRequire(path.join(repoRoot, "web/package.json"));
export const { chromium } = require("@playwright/test");
export const BASE = process.env.BGSIM_VIDEO_URL ?? "http://127.0.0.1:8810";
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export const gallery = JSON.parse(readFileSync(path.join(repoRoot, "web/src/examples/gallery.json"), "utf8"));

export function outDir(...parts) {
  const d = path.join(framesDir, ...parts);
  mkdirSync(d, { recursive: true });
  return d;
}

export async function createProject(example, tag) {
  const name = `vid-${tag ?? example}-${Date.now().toString(36)}`;
  const r = await fetch(`${BASE}/api/projects`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ name, example }),
  });
  if (r.status !== 201) throw new Error(`create ${example}: ${r.status} ${await r.text()}`);
  return name;
}

export async function newPage(browser, opts = {}) {
  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1, colorScheme: "dark", ...opts });
  const page = await ctx.newPage();
  return page;
}

export async function openModel(page, project, model) {
  await page.goto(`${BASE}/?project=${encodeURIComponent(project)}&model=${encodeURIComponent(model)}`);
  await page.getByTestId("canvas-surface").waitFor({ timeout: 60000 });
  await page.getByTestId("run-button").waitFor({ state: "visible", timeout: 60000 });
  await page.waitForFunction(() => !document.querySelector('[data-testid="run-button"]')?.disabled, null, { timeout: 60000 });
}

export async function runAndWait(page, timeout = 600000) {
  await page.getByTestId("run-button").click();
  await page.waitForFunction(() => document.querySelector('[data-testid="run-status"]')?.getAttribute("data-status") === "done", null, { timeout, polling: 500 });
}
