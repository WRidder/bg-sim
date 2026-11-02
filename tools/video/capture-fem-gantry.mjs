#!/usr/bin/env node
// The FEM gantry video (1280x720, 30 fps): the H-gantry of examples/fem-gantry, its FEM crossbeam coloured by
// von Mises stress, a plain point-to-point move against the same move input-shaped (ZVD). Each run is played at
// 1x (real time), then the stop once more slowed down. Deterministic capture as capture-fem.mjs: the model is
// run on the page, then for frame k the playback time is set and the 3D view screenshotted; ffmpeg encodes.
//
// usage (backend with the real worker on BGSIM_VIDEO_URL, see README.md; never port 8765):
//   node tools/video/capture-fem-gantry.mjs <out.mp4> [--theme dark|light] [--shots <dir>] [--keep-frames]
// --shots also writes paused 3D screenshots (plain and shaped, at the end of the move out) and the dashboard.
import { mkdirSync, rmSync } from "node:fs";
import { spawnSync } from "node:child_process";
import os from "node:os";
import path from "node:path";
import { launchBrowser, createProject, sleep, BASE } from "./lib.mjs";

const arg = (name) => (process.argv.includes(name) ? process.argv[process.argv.indexOf(name) + 1] : undefined);
const out = path.resolve(process.argv[2] ?? "fem-gantry.mp4");
const theme = arg("--theme") ?? "dark";
const shots = arg("--shots") ? path.resolve(arg("--shots")) : null;
const keepFrames = process.argv.includes("--keep-frames");
const frames = path.join(os.tmpdir(), `bgsim-gantry-video-${Date.now().toString(36)}`);
mkdirSync(frames, { recursive: true });
if (shots) mkdirSync(shots, { recursive: true });

const EXAMPLE = "fem-gantry";
const MODEL = "fem-gantry";
const FPS = 30;
const SIZE = { width: 1280, height: 720 };
const EXAGGERATION = "100";
// the stop of the move out (the slow-motion window) and the paused screenshot time
// (the plain move out ends at 0.70 s, the ZVD-shaped one 25 ms later)
const STOP = [0.66, 0.80];
const SHOT_T = { 0: 0.712, 2: 0.738 };

// [shaping, title, sub, segments: [from, to, speed, caption]]
const RUNS = [
  [0, "Plain jerk-limited move", "0.5 m at 10 m/s², 1 m/s. Beam coloured by von Mises stress (0 to 2 MPa), deformation x100.", [
    [0.0, 1.8, 1.0, "Real time (1x): out and back"],
    [STOP[0], STOP[1], 0.1, "The stop, slowed down 10x: the tool rings at 47 Hz"],
  ]],
  [2, "The same move, ZVD input-shaped", "Three impulses tuned to the tool's 47 Hz ringing (from the scipy modal model); the move takes one period (25 ms) longer.", [
    [0.0, 1.8, 1.0, "Real time (1x): out and back"],
    [STOP[0], STOP[1], 0.1, "The stop, slowed down 10x: the 47 Hz ringing is gone"],
  ]],
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
      el.style.cssText = "position:absolute;left:24px;bottom:64px;z-index:99999;max-width:900px;padding:10px 16px;" +
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
  await page.mouse.move(cx, cy);
  await page.mouse.wheel(0, -200); await sleep(150);
  await page.mouse.move(cb.x + cb.width - 5, cb.y + 60);
  await page.addStyleTag({ content: '[data-testid^="viewer-preset"], [data-testid="viewer-fit"], [data-testid="viewer-ortho"], [data-testid="viewer-fullscreen"], [data-testid="detach-viewer"] { visibility: hidden !important; }' });
}

async function setShaping(project, shaping) {
  const r = await fetch(`${BASE}/api/projects/${project}/models/${MODEL}`);
  const doc = await r.json();
  for (const g of doc.parameters) if (g.name === "shaping") g.value = String(Number(shaping).toFixed(1));
  const w = await fetch(`${BASE}/api/projects/${project}/models/${MODEL}`, {
    method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify(doc),
  });
  if (!w.ok) throw new Error(`put model: ${w.status} ${await w.text()}`);
}

const browser = await launchBrowser();
const project = await createProject(EXAMPLE, "gantryvid");
try {
  let k = 0;
  for (const [shaping, title, sub, segments] of RUNS) {
    await setShaping(project, shaping);
    const ctx = await browser.newContext({ viewport: SIZE, deviceScaleFactor: 1, colorScheme: theme });
    const page = await ctx.newPage();
    await page.addInitScript(layout, theme);
    await page.goto(`${BASE}/?project=${encodeURIComponent(project)}&model=${encodeURIComponent(MODEL)}`);
    await page.getByTestId("run-button").waitFor({ state: "visible", timeout: 60000 });
    await page.waitForFunction(() => !document.querySelector('[data-testid="run-button"]')?.disabled, null, { timeout: 60000 });
    if (shots && shaping === 0) {
      await page.getByRole("tab", { name: "Dashboard" }).click().catch(() => {});
    }
    await page.getByRole("tab", { name: "3D View" }).click();
    await page.getByTestId("run-button").click();
    await page.waitForFunction(() => document.querySelector('[data-testid="run-status"]')?.getAttribute("data-status") === "done",
      null, { timeout: 3600000, polling: 1000 });
    await page.waitForFunction(() => document.querySelector('[data-testid="scene-view"]')?.getAttribute("data-state") === "loaded", null, { timeout: 90000 });
    await page.waitForFunction(() => document.querySelector('[data-testid="playback-bar"]')?.getAttribute("data-mode") === "playback", null, { timeout: 120000 });
    await sleep(1000);
    if (shots && shaping === 0) {
      await page.getByRole("tab", { name: "Dashboard" }).click().catch(() => {});
      await sleep(1500);
      await page.screenshot({ path: path.join(shots, "gantry-dashboard.png") });
      await page.getByRole("tab", { name: "3D View" }).click();
      await sleep(1000);
    }
    await page.addStyleTag({ content: '[data-testid="scene-stage"] { position: fixed !important; inset: 0 !important; z-index: 9000 !important; width: 100vw !important; height: 100vh !important; background: var(--color-bg); }' });
    await sleep(1500);
    await page.getByTestId("deformation-exaggeration").selectOption(EXAGGERATION);
    await camera(page);
    await sleep(800);
    // a title hold of one second
    await caption(page, title, sub);
    for (let i = 0; i < FPS; i++) {
      await page.screenshot({ path: path.join(frames, `f${String(k).padStart(5, "0")}.png`) });
      k++;
    }
    for (const [from, to, speed, cap] of segments) {
      await caption(page, `${title}: ${cap}`, sub);
      const n = Math.round(((to - from) / speed) * FPS);
      for (let i = 0; i < n; i++) {
        await setTime(page, from + (i * speed) / FPS);
        await page.screenshot({ path: path.join(frames, `f${String(k).padStart(5, "0")}.png`) });
        k++;
      }
    }
    if (shots) {
      await page.evaluate(() => document.getElementById("vid-caption")?.remove());
      await setTime(page, SHOT_T[shaping]);
      await sleep(500);
      await page.getByTestId("viewer-canvas").screenshot({ path: path.join(shots, `gantry-3d-${shaping === 0 ? "plain" : "zvd"}.png`) });
    }
    await ctx.close();
  }
  console.log(`${k} frames (${(k / FPS).toFixed(1)} s) in ${frames}`);
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
