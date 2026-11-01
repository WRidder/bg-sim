#!/usr/bin/env node
// The FEM bracket video (1280x720, 30 fps): a FEM flexible body (ModalBody3D, reduced from a finite element
// model by julia/BGSimFEM) carrying a payload on an indexing turntable, drawn from its GLB mesh with one morph
// target per mode. Deterministic capture: the model is run once on the page, then for frame k the playback
// time is set to t0 + k * speed / fps, two animation frames are awaited and the 3D view is screenshotted;
// ffmpeg encodes the frames at a fixed rate. Captions are injected into the page.
//
// usage (backend with the real worker on BGSIM_VIDEO_URL, see README.md):
//   node tools/video/capture-fem.mjs <out.mp4> [--theme dark|light] [--shots <dir>] [--keep-frames]
// --shots also writes paused 3D screenshots (bracket-3d.png and a close-up) for the model docs.
import { mkdirSync, rmSync } from "node:fs";
import { spawnSync } from "node:child_process";
import os from "node:os";
import path from "node:path";
import { launchBrowser, createProject, sleep, BASE } from "./lib.mjs";

const arg = (name) => (process.argv.includes(name) ? process.argv[process.argv.indexOf(name) + 1] : undefined);
const out = path.resolve(process.argv[2] ?? "fem.mp4");
const theme = arg("--theme") ?? "dark";
const shots = arg("--shots") ? path.resolve(arg("--shots")) : null;
const keepFrames = process.argv.includes("--keep-frames");
const frames = path.join(os.tmpdir(), `bgsim-fem-video-${Date.now().toString(36)}`);
mkdirSync(frames, { recursive: true });
if (shots) mkdirSync(shots, { recursive: true });

const EXAMPLE = "fem-bracket";
const MODEL = "fem-bracket";
const FPS = 30;
const SIZE = { width: 1280, height: 720 };

// The script: [from, to, speed (simulated s per video s), caption, sub-caption]. About 23 s of video.
const PLAN = [
  [0.0, 0.2, 0.2, "A FEM flexible body on a turntable", "Aluminium L-bracket reduced from 39 348 FE DOFs to 10 coordinates (Craig-Bampton). Deformation drawn x100."],
  [0.2, 0.75, 0.1, "Index +90 degrees: the upright bends in its thin direction", "Jerk-limited move, 8 rad/s. The payload (0.5 kg) lags behind."],
  [0.75, 1.6, 0.15, "After the move the payload rings at about 18 Hz", "Clamped with the payload: full FE model 18.5719 Hz, reduced model 18.5719 Hz."],
  [1.6, 2.15, 0.1, "And back to 0 degrees", "Gravity, geometric stiffening and the servo spring are all in the model."],
  [2.15, 3.0, 0.15, "Ring-down", "Modal damping 1 %; real Julia simulation, mesh deformed by the morph targets of the GLB."],
];

const layout = (th) => {
  try {
    localStorage.setItem("bgsim.layout.rows", JSON.stringify({ main: 8, dock: 92 }));
    localStorage.setItem("bgsim.layout.columns", JSON.stringify({ library: 4, center: 92, inspector: 4 }));
    localStorage.setItem("bgsim.theme", th);
  } catch {}
};

async function caption(page, title, sub = "") {
  await page.evaluate(([t, s]) => {
    const host = document.querySelector('[data-testid="scene-stage"]') ?? document.body;
    let el = document.getElementById("vid-caption");
    if (!el || el.parentElement !== host) {
      el?.remove();
      el = document.createElement("div");
      el.id = "vid-caption";
      el.style.cssText = "position:absolute;left:24px;bottom:64px;z-index:99999;max-width:820px;padding:10px 16px;" +
        "border-radius:8px;background:rgba(15,17,22,0.86);color:#fff;font:600 19px/1.3 'Segoe UI',sans-serif;" +
        "border-left:4px solid #f5a623;box-shadow:0 4px 18px rgba(0,0,0,0.35);pointer-events:none";
      if (getComputedStyle(host).position === "static") host.style.position = "relative";
      host.appendChild(el);
    }
    el.innerHTML = "";
    const a = document.createElement("div");
    a.textContent = t;
    el.appendChild(a);
    if (s) {
      const b = document.createElement("div");
      b.textContent = s;
      b.style.cssText = "font-weight:400;font-size:15px;color:#d8dbe2;margin-top:3px";
      el.appendChild(b);
    }
  }, [title, sub]);
}

const frame2 = (page) => page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => r()))));

async function setTime(page, t) {
  // set the slider through the native setter (React listens for input events); the full-screen
  // stage covers the playback bar, so Playwright's fill() would wait for it to be visible
  await page.evaluate((v) => {
    const el = document.querySelector('[data-testid="playback-time"]');
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(el, String(v));
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }, t);
  await frame2(page);
}

async function camera(page) {
  await setTime(page, 0.0);
  await page.getByTestId("viewer-preset-iso").dispatchEvent("click");
  await sleep(300);
  await page.getByTestId("viewer-fit").dispatchEvent("click");
  await sleep(300);
  const cb = await page.getByTestId("viewer-canvas").boundingBox();
  const cx = cb.x + cb.width / 2, cy = cb.y + cb.height / 2;
  // orbit a little so the upright's thin direction (the bending) faces the camera, then zoom in
  await page.mouse.move(cx, cy); await page.mouse.down(); await page.mouse.move(cx + 40, cy + 20, { steps: 10 }); await page.mouse.up();
  await sleep(200);
  await page.mouse.move(cx, cy);
  await page.mouse.wheel(0, -300); await sleep(150);
  await page.mouse.move(cb.x + cb.width - 5, cb.y + 60);
  await page.addStyleTag({ content: '[data-testid^="viewer-preset"], [data-testid="viewer-fit"], [data-testid="viewer-ortho"], [data-testid="viewer-fullscreen"], [data-testid="detach-viewer"] { visibility: hidden !important; }' });
}

const browser = await launchBrowser();
const project = await createProject(EXAMPLE, "femvid");
try {
  const ctx = await browser.newContext({ viewport: SIZE, deviceScaleFactor: 1, colorScheme: theme });
  const page = await ctx.newPage();
  await page.addInitScript(layout, theme);
  await page.goto(`${BASE}/?project=${encodeURIComponent(project)}&model=${encodeURIComponent(MODEL)}`);
  await page.getByTestId("run-button").waitFor({ state: "visible", timeout: 60000 });
  await page.waitForFunction(() => !document.querySelector('[data-testid="run-button"]')?.disabled, null, { timeout: 60000 });
  await page.getByRole("tab", { name: "3D View" }).click();
  await page.getByTestId("run-button").click();
  await page.waitForFunction(() => document.querySelector('[data-testid="run-status"]')?.getAttribute("data-status") === "done",
    null, { timeout: 1800000, polling: 500 });
  await page.waitForFunction(() => document.querySelector('[data-testid="scene-view"]')?.getAttribute("data-state") === "loaded", null, { timeout: 90000 });
  await page.waitForFunction(() => document.querySelector('[data-testid="playback-bar"]')?.getAttribute("data-mode") === "playback", null, { timeout: 120000 });
  await sleep(1000);
  await page.addStyleTag({ content: '[data-testid="scene-stage"] { position: fixed !important; inset: 0 !important; z-index: 9000 !important; width: 100vw !important; height: 100vh !important; background: var(--color-bg); }' });
  await sleep(1500);
  await page.getByTestId("deformation-exaggeration").selectOption("100");
  await camera(page);
  await sleep(800);

  let k = 0;
  for (const [from, to, speed, title, sub] of PLAN) {
    await caption(page, title, sub);
    const n = Math.round(((to - from) / speed) * FPS);
    for (let i = 0; i < n; i++) {
      await setTime(page, from + (i * speed) / FPS);
      await page.screenshot({ path: path.join(frames, `f${String(k).padStart(5, "0")}.png`) });
      k++;
    }
  }
  console.log(`${k} frames (${(k / FPS).toFixed(1)} s) in ${frames}`);
  if (shots) {
    await page.evaluate(() => document.getElementById("vid-caption")?.remove());
    await setTime(page, 0.45);
    await sleep(500);
    await page.getByTestId("viewer-canvas").screenshot({ path: path.join(shots, "bracket-3d.png") });
  }
  await ctx.close();
  const r = spawnSync("ffmpeg", ["-y", "-framerate", String(FPS), "-i", path.join(frames, "f%05d.png"),
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "slow", "-r", String(FPS), "-an", out], { stdio: "inherit" });
  if (r.status !== 0) throw new Error("ffmpeg failed");
  console.log("video", out);
} catch (e) {
  console.error("FAILED", e);
  process.exitCode = 1;
} finally {
  await fetch(`${BASE}/api/projects/${project}`, { method: "DELETE" }).catch(() => {});
  await browser.close();
  if (!keepFrames) {
    try { rmSync(frames, { recursive: true, force: true }); } catch {}
  }
}
