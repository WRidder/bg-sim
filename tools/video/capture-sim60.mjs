#!/usr/bin/env node
// Video 2, 60 fps: after the run, drive the detached 3D viewer's playback slider frame by frame
// (t_k = k * s / 60); the viewer drives the plot cursor of the main window. Both windows are screenshotted per frame.
// Output (resumable, cached per example): media/video/frames/sim60/<example>/{v,p}/%05d.jpg + meta.json (+ done.json)
// usage: node capture-sim60.mjs [--only a,b] [--skip a,b] [--max-frames n] [--force]
import { existsSync, readFileSync, writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";
import { chromium, createProject, newPage, openModel, runAndWait, framesDir, repoRoot, gallery, sleep, BASE } from "./lib.mjs";

const arg = (n) => { const i = process.argv.indexOf(n); return i > 0 ? process.argv[i + 1] : null; };
const only = arg("--only")?.split(",") ?? null;
const skip = arg("--skip")?.split(",") ?? [];
const maxFrames = Number(arg("--max-frames") ?? 0);
const force = process.argv.includes("--force");
const cards = JSON.parse(readFileSync(new URL("./cards.json", import.meta.url), "utf8"));
const overrides = JSON.parse(readFileSync(new URL("./examples.json", import.meta.url), "utf8"));
const FPS = 60;

async function capture(browser, id) {
  const outRoot = path.join(framesDir, "sim60", id);
  if (!force && existsSync(outRoot + "/done.json")) { console.log("cached", id); return; }
  mkdirSync(outRoot + "/v", { recursive: true });
  mkdirSync(outRoot + "/p", { recursive: true });
  const old = JSON.parse(readFileSync(path.join(framesDir, "examples", id, "info.json"), "utf8"));
  const ov = overrides[id] ?? {};
  const model = ov.model ?? gallery[id]?.models?.[0];
  const project = await createProject(ov.example ?? id, id.slice(0, 12));
  try {
    const page = await newPage(browser, { viewport: { width: 1141, height: 900 } });
    await page.addInitScript(() => { try { localStorage.setItem("bgsim.layout.rows", JSON.stringify({ main: 30, dock: 70 })); } catch {} });
    await openModel(page, project, model);
    if (ov.tend) await page.getByTestId("setting-tend").fill(String(ov.tend));
    await runAndWait(page, 900000);
    await page.getByRole("tab", { name: "Signals" }).click();
    const items = page.locator('[data-testid="signal-item"]');
    await items.first().waitFor({ timeout: 30000 });
    for (const s of old.signals) {
      await page.locator(`[data-testid="signal-item"][data-signal-id="${s}"]`).dblclick();
      await sleep(250);
    }
    await page.getByRole("tab", { name: "3D View" }).click();
    await page.waitForFunction(() => document.querySelector('[data-testid="scene-view"]')?.getAttribute("data-state") === "loaded", null, { timeout: 90000 });
    await page.waitForFunction(() => document.querySelector('[data-testid="playback-bar"]')?.getAttribute("data-mode") === "playback", null, { timeout: 90000 });
    const popP = page.waitForEvent("popup");
    await page.getByTestId("detach-viewer").click();
    const pop = await popP;
    await pop.setViewportSize({ width: 1100, height: 1000 });
    await pop.getByTestId("viewer-canvas").waitFor();
    await sleep(2500);
    const tree = pop.getByTestId("scene-tree-toggle");
    if (await tree.count()) { const exp = await tree.getAttribute("aria-expanded"); if (exp !== "false") await tree.click().catch(() => {}); }
    await sleep(600);
    const slider = pop.getByTestId("playback-time");
    const T = Number(await slider.getAttribute("max"));
    const stepA = 0.001;
    const sv = (x) => String(Number((Math.round(x / stepA) * stepA).toFixed(3)));
    await slider.fill(sv(T * (ov.fitAt ?? 0.5)));
    await pop.getByTestId("viewer-fit").click();
    await sleep(700);
    const canvas = pop.getByTestId("viewer-canvas");
    await pop.addStyleTag({ content: '[data-testid^="viewer-preset"], [data-testid="viewer-fit"], [data-testid="viewer-ortho"], [data-testid="dock-viewer-button"] { visibility: hidden !important; }' });
    const cb = await canvas.boundingBox();
    await pop.mouse.move(cb.x + cb.width / 2, cb.y + cb.height / 2);
    if (ov.view) { await pop.getByTestId("viewer-preset-" + ov.view).dispatchEvent("click"); await sleep(500); }
    { let rest = ov.orbitX ?? 0; const cx = cb.x + cb.width / 2, cy = cb.y + cb.height / 2;
      while (Math.abs(rest) > 1) { const d = Math.sign(rest) * Math.min(Math.abs(rest), 400); await pop.mouse.move(cx - d / 2, cy); await pop.mouse.down(); await pop.mouse.move(cx + d / 2, cy, { steps: 12 }); await pop.mouse.up(); rest -= d; await sleep(200); }
      if (ov.orbitY) { await pop.mouse.move(cx, cy - ov.orbitY / 2); await pop.mouse.down(); await pop.mouse.move(cx, cy + ov.orbitY / 2, { steps: 10 }); await pop.mouse.up(); }
    }
    await sleep(400);
    if (process.argv.includes("--scan")) {
      await slider.fill(sv(ov.scanT ?? T * 0.55));
      for (let z = 0; z <= (ov.scanMax ?? 40); z += 5) { await canvas.screenshot({ path: `${outRoot}/scan-${String(z).padStart(2, "0")}.jpg` }); for (let q = 0; q < 5; q++) { await pop.mouse.wheel(0, -300); await sleep(120); } await sleep(400); }
      process.exit(0);
    }
    for (let z = 0; z < (ov.zoom ?? 0); z++) { await pop.mouse.wheel(0, -300); await sleep(120); }
    await sleep(600);
    // plots in the main window
    await page.getByRole("tab", { name: "Plots" }).click();
    await sleep(1200);
    await page.getByTestId("plot-chart-panel").first().waitFor({ timeout: 30000 });
    const panels = await page.getByTestId("plot-chart-panel").evaluateAll((els) => els.map((e) => { const r = e.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; }));
    const clip = { x: Math.min(...panels.map((p) => p[0])), y: Math.min(...panels.map((p) => p[1])), width: 0, height: 0 };
    clip.width = Math.max(...panels.map((p) => p[2])) - clip.x;
    clip.height = Math.max(...panels.map((p) => p[3])) - clip.y;
    // playback: about 6 to 10 s of video per example
    const L = Math.min(10, Math.max(6, T));
    const s = T / L;
    let N = Math.round(L * FPS);
    if (maxFrames) N = Math.min(N, maxFrames);
    const raf = (pg) => pg.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
    const t0 = Date.now();
    for (let k = 0; k < N; k++) {
      const vf = `${outRoot}/v/${String(k).padStart(5, "0")}.jpg`;
      if (!force && existsSync(vf)) continue;
      const t = Math.min(T, (k * s) / FPS);
      await slider.fill(sv(t));
      await Promise.all([raf(pop), raf(page)]);
      await Promise.all([
        canvas.screenshot({ type: "jpeg", quality: 92, path: vf }),
        page.screenshot({ type: "jpeg", quality: 92, path: `${outRoot}/p/${String(k).padStart(5, "0")}.jpg`, clip }),
      ]);
    }
    writeFileSync(outRoot + "/meta.json", JSON.stringify({ id, T, s, N, L, fps: FPS, clip, captureSeconds: (Date.now() - t0) / 1000 }));
    writeFileSync(outRoot + "/done.json", "{}");
    console.log("OK", id, `T=${T} s=${s.toFixed(3)} frames=${N} in ${((Date.now() - t0) / 1000).toFixed(0)}s`);
    await page.context().close();
  } finally {
    await fetch(`${BASE}/api/projects/${project}`, { method: "DELETE" }).catch(() => {});
  }
}

const browser = await chromium.launch();
for (const c of cards) {
  if ((only && !only.includes(c.id)) || skip.includes(c.id)) continue;
  try { await capture(browser, c.id); } catch (e) { console.log("FAIL", c.id, String(e).split("\n")[0]); }
}
await browser.close();
