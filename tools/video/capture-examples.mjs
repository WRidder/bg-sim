#!/usr/bin/env node
// Video 2 capture: for each example, the diagram, N stills of the 3D view and N plot stills with the
// plot cursor stepping through the run. Output: media/video/frames/examples/<example>/{diagram,v-0..,p-0..}.png
// usage: node capture-examples.mjs [--only a,b] [--skip a,b] [--steps 6]
import { existsSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { launchBrowser, createProject, newPage, openModel, runAndWait, outDir, gallery, repoRoot, sleep } from "./lib.mjs";

const arg = (n) => { const i = process.argv.indexOf(n); return i > 0 ? process.argv[i + 1] : null; };
const only = arg("--only")?.split(",") ?? null;
const skip = arg("--skip")?.split(",") ?? [];
const STEPS = Number(arg("--steps") ?? 6);
const overrides = JSON.parse(readFileSync(new URL("./examples.json", import.meta.url), "utf8"));

const listed = readdirSync(path.join(repoRoot, "examples"), { withFileTypes: true })
  .filter((e) => e.isDirectory() && existsSync(path.join(repoRoot, "examples", e.name, "bgsim.project.json")))
  .map((e) => e.name).sort();

const HIDE = '[role="tooltip"], [role="status"], [role="alert"], .toast, .react-flow__attribution, .react-flow__panel, .react-flow__minimap, .react-flow__controls, [data-testid="canvas-legend"], [data-testid="hover-readout"] { display: none !important; }';

function model(example) {
  return overrides[example]?.model ?? gallery[example]?.models?.[0];
}
function signalsFor(example, m) {
  if (overrides[example]?.signals) return overrides[example].signals;
  const f = path.join(repoRoot, "examples", example, "expected.json");
  if (!existsSync(f)) return [];
  const checks = JSON.parse(readFileSync(f, "utf8")).models?.[m]?.checks ?? [];
  return [...new Set(checks.map((c) => c.signal).filter((s) => typeof s === "string"))].slice(0, 3);
}

async function diagramShot(browser, project, m, dir) {
  const page = await newPage(browser, { viewport: { width: 1800, height: 1000 } });
  await openModel(page, project, m);
  await page.waitForFunction(() => document.querySelectorAll('[data-testid="diagram-node"]').length > 0, null, { timeout: 60000 });
  await page.evaluate(() => document.fonts.ready);
  await page.getByTestId("fit-view").click();
  await sleep(1500);
  await page.addStyleTag({ content: HIDE });
  await page.mouse.move(2, 2);
  await page.locator(".react-flow").screenshot({ path: dir + "/diagram.png", animations: "disabled" });
  await page.context().close();
}

async function capture(browser, example) {
  const m = model(example);
  const dir = outDir("examples", example);
  const project = await createProject(overrides[example]?.example ?? example);
  const info = { example, model: m, times: [], signals: [] };
  try {
    await diagramShot(browser, project, m, dir);
    const page = await newPage(browser, { viewport: { width: 960, height: 1500 } });
    await page.addInitScript(() => { try { localStorage.setItem("bgsim.layout.rows", JSON.stringify({ main: 30, dock: 70 })); } catch {} });
    await openModel(page, project, m);
    if (overrides[example]?.tend) {
      await page.getByTestId("setting-tend").fill(String(overrides[example].tend));
    }
    const t0 = Date.now();
    await runAndWait(page, 900000);
    info.runSeconds = (Date.now() - t0) / 1000;
    // plot signals
    await page.getByRole("tab", { name: "Signals" }).click();
    await page.getByTestId("signal-browser").waitFor();
    const items = page.locator('[data-testid="signal-item"]');
    await items.first().waitFor({ timeout: 30000 });
    let want = signalsFor(example, m);
    const have = new Set(await items.evaluateAll((els) => els.map((e) => e.getAttribute("data-signal-id"))));
    want = want.filter((s) => have.has(s));
    if (want.length === 0) want = [[...have][0]];
    for (const s of want) {
      await page.locator(`[data-testid="signal-item"][data-signal-id="${s}"]`).dblclick();
      info.signals.push(s);
      await sleep(300);
    }
    // 3D
    await page.getByRole("tab", { name: "3D View" }).click();
    await page.getByTestId("scene-view").waitFor({ timeout: 60000 });
    await page.waitForFunction(() => document.querySelector('[data-testid="scene-view"]')?.getAttribute("data-state") === "loaded", null, { timeout: 90000 });
    await page.waitForFunction(() => document.querySelector('[data-testid="playback-bar"]')?.getAttribute("data-mode") === "playback", null, { timeout: 90000 });
    const tree = page.getByTestId("scene-tree-toggle");
    if (await tree.count()) { const exp = await tree.getAttribute("aria-expanded"); if (exp !== "false") await tree.click().catch(() => {}); }
    await sleep(600);
    const slider = page.getByTestId("playback-time");
    const end = Number(await slider.getAttribute("max"));
    const stepA = Number((await slider.getAttribute("step")) ?? "0") || 0.001;
    const sv = (x) => String(Number((Math.round(x / stepA) * stepA).toFixed(3)));
    info.end = end;
    const fr = [...Array(STEPS)].map((_, i) => (STEPS === 1 ? 1 : 0.02 + (0.96 * i) / (STEPS - 1)));
    const fitAt = overrides[example]?.fitAt ?? 0.5;
    await slider.fill(sv(end * fitAt));
    await page.getByTestId("viewer-fit").click();
    await sleep(700);
    const canvas = page.getByTestId("viewer-canvas");
    await page.addStyleTag({ content: '[data-testid^="viewer-preset"], [data-testid="viewer-fit"], [data-testid="viewer-ortho"], [data-testid="detach-viewer"] { visibility: hidden !important; }' });
    const cb = await canvas.boundingBox();
    await page.mouse.move(cb.x + cb.width / 2, cb.y + cb.height / 2);
    for (let z = 0; z < (overrides[example]?.zoom ?? 0); z++) { await page.mouse.wheel(0, -300); await sleep(120); }
    if (overrides[example]?.view) await page.getByTestId("viewer-preset-" + overrides[example].view).dispatchEvent("click");
    await sleep(500);
    for (let i = 0; i < fr.length; i++) {
      await slider.fill(sv(end * fr[i]));
      await sleep(500);
      const tt = Number(await page.getByTestId("playback-bar").getAttribute("data-time"));
      info.times.push(tt);
      await canvas.screenshot({ path: `${dir}/v-${i}.png` });
    }
    // plots with the cursor
    await page.getByRole("tab", { name: "Plots" }).click();
    await page.setViewportSize({ width: 1141, height: 900 });
    await sleep(1200);
    const over = page.locator('[data-testid="plot-chart"] .u-over').first();
    await over.waitFor({ timeout: 30000 });
    const charts = page.getByTestId("plot-charts");
    for (let i = 0; i < fr.length; i++) {
      const box = await over.boundingBox();
      await page.mouse.move(box.x + box.width * fr[i], box.y + box.height * 0.5, { steps: 3 });
      await sleep(400);
      const panels = await page.getByTestId("plot-chart-panel").evaluateAll((els) => els.map((e) => { const r = e.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; }));
      const x0 = Math.min(...panels.map((p) => p[0])), y0 = Math.min(...panels.map((p) => p[1])), x1 = Math.max(...panels.map((p) => p[2])), y1 = Math.max(...panels.map((p) => p[3]));
      await page.screenshot({ path: `${dir}/p-${i}.png`, clip: { x: x0, y: y0, width: x1 - x0, height: y1 - y0 } });
    }
    await page.context().close();
  } finally {
    await fetch(`${process.env.BGSIM_VIDEO_URL ?? "http://127.0.0.1:8810"}/api/projects/${project}`, { method: "DELETE" }).catch(() => {});
  }
  writeFileSync(`${dir}/info.json`, JSON.stringify(info, null, 1));
  return info;
}

const browser = await launchBrowser();
for (const [k, v] of Object.entries(overrides)) if (v.example && !listed.includes(k)) listed.push(k);
const todo = listed.filter((e) => (!only || only.includes(e)) && !skip.includes(e));
for (const ex of todo) {
  const t = Date.now();
  try {
    const info = await capture(browser, ex);
    console.log("OK", ex, `${((Date.now() - t) / 1000).toFixed(0)}s`, `run ${info.runSeconds?.toFixed(1)}s`, info.signals.join(","));
  } catch (e) {
    console.log("FAIL", ex, String(e).split("\n")[0]);
  }
}
await browser.close();
