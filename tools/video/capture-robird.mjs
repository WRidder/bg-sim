#!/usr/bin/env node
// (robird variant: one segment of the robird model, parametrised: node capture-robird.mjs --seg lap|close [--max-frames n])
// Video 2, 60 fps: after the run, drive the detached 3D viewer's playback slider frame by frame
// (t_k = k * s / 60); the viewer drives the plot cursor of the main window. Both windows are screenshotted per frame.
// Output (resumable, cached per example): media/video/frames/sim60/<example>/{v,p}/%05d.jpg + meta.json (+ done.json)
// usage: node capture-sim60.mjs [--only a,b] [--skip a,b] [--max-frames n] [--force]
import { existsSync, readFileSync, writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";
import { launchBrowser, createProject, newPage, openModel, runAndWait, framesDir, repoRoot, gallery, sleep, BASE } from "./lib.mjs";

const arg = (n) => { const i = process.argv.indexOf(n); return i > 0 ? process.argv[i + 1] : null; };
const only = arg("--only")?.split(",") ?? null;
const skip = arg("--skip")?.split(",") ?? [];
const maxFrames = Number(arg("--max-frames") ?? 0);
const force = process.argv.includes("--force");
const FPS = 60;
const seg = arg("--seg") ?? "lap";
const SEG = {
  lap: { t0: 0, t1: 60, speed: 3.5, view: "top", zoom: 0, panels: [["Truth/x", "Truth/y"], ["Guide/e_ct"]], zoomPlot: null },
  close: { t0: 0.5, t1: 1.25, speed: 0.25, view: "front", zoom: 0, chase: { r: Number(arg("--r") ?? 26), elev: Number(arg("--elev") ?? 0.55), az: Number(arg("--az") ?? 0.9) }, panels: [["JL1/qout"], ["Drv/isense/y"]], zoomPlot: [0.004, 0.03] },
  iso: { t0: 8.5, t1: 18.5, speed: 1, view: "front", zoom: 0, chase: { r: Number(arg("--r") ?? 38), elev: Number(arg("--elev") ?? 0.6), az: Number(arg("--az") ?? 0.9) }, panels: [["Fctl/phi", "JL1/qout"], ["Guide/e_ct"]], zoomPlot: [8 / 60, 19 / 60] },
}[seg];

async function capture(browser, id) {
  const outRoot = path.join(framesDir, "robird60", seg);
  if (!force && existsSync(outRoot + "/done.json")) { console.log("cached", id); return; }
  mkdirSync(outRoot + "/v", { recursive: true });
  mkdirSync(outRoot + "/p", { recursive: true });
    const ov = { model: "robird", view: SEG.view, zoom: SEG.zoom };
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
    for (let pi = 0; pi < SEG.panels.length; pi++) {
      if (pi > 0) {
        await page.getByRole("tab", { name: "Plots" }).click();
        await page.getByTestId("add-plot-panel").click();
        await page.getByRole("tab", { name: "Signals" }).click();
      }
      for (const sg of SEG.panels[pi]) {
        await page.locator(`[data-testid="signal-item"][data-signal-id="${sg}"]`).dblclick();
        await sleep(300);
      }
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
    await slider.fill(sv((SEG.t0 + SEG.t1) / 2));
    await pop.getByTestId("viewer-fit").click();
    await sleep(700);
    const canvas = pop.getByTestId("viewer-canvas");
    await pop.addStyleTag({ content: '[data-testid^="viewer-preset"], [data-testid="viewer-fit"], [data-testid="viewer-ortho"], [data-testid="dock-viewer-button"] { visibility: hidden !important; }' });
    const cb = await canvas.boundingBox();
    await pop.mouse.move(cb.x + cb.width / 2, cb.y + cb.height / 2);
    if (ov.view) await pop.getByTestId("viewer-preset-" + ov.view).dispatchEvent("click");
    await sleep(600);
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
    if (SEG.zoomPlot) {
      const over = page.locator('[data-testid="plot-chart"] .u-over');
      for (let i = 0; i < 1; i++) {
        const b = await over.nth(i).boundingBox();
        const y = b.y + b.height * 0.45;
        await page.mouse.move(b.x + b.width * SEG.zoomPlot[0], y); await page.mouse.down();
        await page.mouse.move(b.x + b.width * SEG.zoomPlot[1], y, { steps: 10 }); await page.mouse.up();
        await sleep(900);
      }
    }
    if (process.argv.includes("--scan")) {
      await slider.fill(sv(SEG.t0 + 0.3));
      for (let z = 0; z <= 44; z += 4) { await canvas.screenshot({ path: `${outRoot}/scan-${String(z).padStart(2, "0")}.jpg` }); for (let q = 0; q < 4; q++) { await pop.mouse.wheel(0, -300); await sleep(120); } await sleep(400); }
      process.exit(0);
    }
    // scene access (React fiber of the viewer canvas): hide the waypoint spheres, chase camera
    const hasScene = await pop.evaluate(() => {
      const c = document.querySelector('[data-testid="viewer-canvas"]');
      const fk = Object.keys(c).find((k) => k.startsWith("__reactFiber"));
      for (let f = c[fk], d = 0; f && d < 60; d++, f = f.return) {
        for (let h = f.memoizedState; h; h = h.next) {
          const v = h.memoizedState;
          if (v && typeof v === "object" && v.current && v.current.camera && v.current.scene) { window.__vs = v.current; return true; }
        }
      }
      return false;
    });
    if (hasScene) {
      await pop.evaluate(() => {
        for (const m of window.__vs.scene.meshes) if (/^visual:(path_|start)/.test(m.name)) m.setEnabled(false);
        window.__vs.invalidate?.();
      });
    }
    const SMOOTH = (arr, w) => arr.map((_, i) => { let s = 0, n = 0; for (let j = Math.max(0, i - w); j <= Math.min(arr.length - 1, i + w); j++) { s += arr[j]; n++; } return s / n; });
    let chase = null;
    if (SEG.chase && hasScene) {
      const sN = Math.round(((SEG.t1 - SEG.t0) / SEG.speed) * FPS);
      const px = [], py = [], pz = [];
      for (let k = 0; k < Math.min(sN, maxFrames || 1e9); k++) {
        await slider.fill(sv(Math.min(T, SEG.t0 + (k * SEG.speed) / FPS)));
        await pop.evaluate(() => new Promise((r) => requestAnimationFrame(r)));
        const p = await pop.evaluate(() => { const m = window.__vs.scene.getMeshByName("visual:torso"); m.computeWorldMatrix(true); const q = m.getAbsolutePosition(); return [q.x, q.y, q.z]; });
        px.push(p[0]); py.push(p[1]); pz.push(p[2]);
      }
      const w = SEG.chase.smooth ?? 6;
      const sx = SMOOTH(px, w), sy = SMOOTH(py, w), sz = SMOOTH(pz, w);
      const al = [];
      let prev = null;
      for (let k = 0; k < sx.length; k++) {
        const a = Math.max(0, k - 20), b = Math.min(sx.length - 1, k + 20);
        let fx = sx[b] - sx[a], fz = sz[b] - sz[a];
        const n = Math.hypot(fx, fz);
        if (n < 1e-6 && prev) { al.push(prev); continue; }
        const hdg = Math.atan2(fz, fx);
        const cam = hdg + Math.PI + (SEG.chase.az ?? 0.9);   // behind the bird, rotated to one side
        let v = cam;
        if (prev !== null) { while (v - prev > Math.PI) v -= 2 * Math.PI; while (v - prev < -Math.PI) v += 2 * Math.PI; }
        prev = v; al.push(v);
      }
      chase = { sx, sy, sz, al: SMOOTH(al, 10) };
    }
    // playback segment
    const s = SEG.speed;
    const L = (SEG.t1 - SEG.t0) / s;
    let N = Math.round(L * FPS);
    if (maxFrames) N = Math.min(N, maxFrames);
    const raf = (pg) => pg.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
    const t0 = Date.now();
    if (chase) { await slider.fill(sv(SEG.t0)); for (let q = 0; q < 3; q++) await pop.evaluate(() => new Promise((r) => requestAnimationFrame(r))); }
    for (let k = 0; k < N; k++) {
      const vf = `${outRoot}/v/${String(k).padStart(5, "0")}.jpg`;
      if (!force && existsSync(vf)) continue;
      const t = Math.min(T, SEG.t0 + (k * s) / FPS);
      await slider.fill(sv(t));
      if (chase) {
        await raf(pop);
        await pop.evaluate((c) => { const cam = window.__vs.camera; const tg = cam.target.clone(); tg.x = c.x; tg.y = c.y; tg.z = c.z; cam.upperRadiusLimit = 1e6; cam.setTarget(tg, false, false, true); cam.alpha = c.al; cam.beta = c.beta; cam.radius = c.r; window.__vs.invalidate(); }, { x: chase.sx[k], y: chase.sy[k], z: chase.sz[k], al: chase.al[k], beta: Math.PI / 2 - (SEG.chase.elev ?? 0.6), r: SEG.chase.r });
      }
      await Promise.all([raf(pop), raf(page)]);
      if (chase) await raf(pop);
      await Promise.all([
        canvas.screenshot({ type: "jpeg", quality: 92, path: vf }),
        page.screenshot({ type: "jpeg", quality: 92, path: `${outRoot}/p/${String(k).padStart(5, "0")}.jpg`, clip }),
      ]);
    }
    writeFileSync(outRoot + "/meta.json", JSON.stringify({ id, seg, t0: SEG.t0, T, s, N, L, fps: FPS, clip, captureSeconds: (Date.now() - t0) / 1000 }));
    writeFileSync(outRoot + "/done.json", "{}");
    console.log("OK", id, `T=${T} s=${s.toFixed(3)} frames=${N} in ${((Date.now() - t0) / 1000).toFixed(0)}s`);
    await page.context().close();
  } finally {
    await fetch(`${BASE}/api/projects/${project}`, { method: "DELETE" }).catch(() => {});
  }
}

const browser = await launchBrowser();
try { await capture(browser, "robird"); } catch (e) { console.log("FAIL", String(e).split(String.fromCharCode(10)).slice(0, 3).join(" | ")); }
await browser.close();
