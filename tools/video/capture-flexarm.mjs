#!/usr/bin/env node
// The flexible-arm triple rotary pendulum video (about 35 s, 1280x720): Playwright records the real app with the
// real Julia worker. The rigid arm swings up and balances; the same firmware on a flexible steel-strip arm shakes
// the arm's first bending mode until the amplifier saturates and the swing-up is lost; the firmware designed with
// a low-pass in the loop balances on the flexible arm. Captions are injected into the page.
//
// usage (backend with the real worker on BGSIM_VIDEO_URL, see README.md):
//   node tools/video/capture-flexarm.mjs <out.mp4|out.webm> [--theme dark|light] [--shots <dir>]
// The recording is a .webm; with ffmpeg on PATH the kept segments are cut out and encoded to H.264 .mp4 at the
// recording's own 25 fps. Model loads and runs are cut. --shots also writes paused 3D screenshots (flex-3d.png,
// flex-lowpass-3d.png) for the model docs.
import { mkdirSync, readdirSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import os from "node:os";
import path from "node:path";
import { launchBrowser, createProject, sleep, BASE } from "./lib.mjs";

const arg = (name) => (process.argv.includes(name) ? process.argv[process.argv.indexOf(name) + 1] : undefined);
const out = path.resolve(process.argv[2] ?? "flexarm.mp4");
const theme = arg("--theme") ?? "dark";
const shots = arg("--shots") ? path.resolve(arg("--shots")) : null;
const work = path.join(os.tmpdir(), `bgsim-flexarm-video-${Date.now().toString(36)}`);
mkdirSync(work, { recursive: true });
if (shots) mkdirSync(shots, { recursive: true });

const RIGID = "pendulum-triple-rotary";
const FLEX = "pendulum-triple-rotary-flex";
const LOWPASS = "pendulum-triple-rotary-flex-lowpass";

const layout = (th) => {
  try {
    localStorage.setItem("bgsim.layout.rows", JSON.stringify({ main: 8, dock: 92 }));
    localStorage.setItem("bgsim.layout.columns", JSON.stringify({ library: 4, center: 92, inspector: 4 }));
    localStorage.setItem("bgsim.theme", th);
  } catch {}
};

async function caption(page, title, sub = "") {
  await page.evaluate(([t, s]) => {
    // inside the full-screen stage: only its subtree is drawn while it is full screen
    const host = document.querySelector('[data-testid="scene-stage"]') ?? document.body;
    let el = document.getElementById("vid-caption");
    if (!el || el.parentElement !== host) {
      el?.remove();
      el = document.createElement("div");
      el.id = "vid-caption";
      el.style.cssText = "position:absolute;left:24px;bottom:64px;z-index:99999;max-width:760px;padding:10px 16px;" +
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

const timeNow = (page) => page.evaluate(() => Number(document.querySelector('[data-testid="playback-time"]')?.value));

async function play(page, from, to, speed) {
  const slider = page.getByTestId("playback-time");
  await page.getByTestId("playback-speed").selectOption(String(speed));
  if (from !== null) {
    await slider.fill(String(from));
    await sleep(300);
  }
  await page.getByTestId("playback-toggle").click();
  await page.waitForFunction((t) => Number(document.querySelector('[data-testid="playback-time"]')?.value) >= t, to,
    { timeout: 180000, polling: 20 });
  await page.getByTestId("playback-toggle").click();
}

// Kept stretches of the recording, in seconds from the page start; everything else is cut.
const segments = [];
let t0 = 0;
let segStart = null;
const MARGIN = 0.3;
const keep = () => { segStart = (Date.now() - t0) / 1000 + MARGIN; };
const cut = () => {
  if (segStart !== null) segments.push([segStart, (Date.now() - t0) / 1000 - MARGIN]);
  segStart = null;
};

// Off camera: open the model (same page), run it, show the 3D view with the camera and exaggeration set.
async function load(page, project, model, factor, at) {
  cut();
  await page.goto(`${BASE}/?project=${encodeURIComponent(project)}&model=${encodeURIComponent(model)}`);
  await page.getByTestId("run-button").waitFor({ state: "visible", timeout: 60000 });
  await page.waitForFunction(() => !document.querySelector('[data-testid="run-button"]')?.disabled, null, { timeout: 60000 });
  await page.getByRole("tab", { name: "3D View" }).click();
  await page.getByTestId("run-button").click();
  await page.waitForFunction(() => document.querySelector('[data-testid="run-status"]')?.getAttribute("data-status") === "done",
    null, { timeout: 900000, polling: 250 });
  await page.waitForFunction(() => document.querySelector('[data-testid="scene-view"]')?.getAttribute("data-state") === "loaded", null, { timeout: 90000 });
  await page.waitForFunction(() => document.querySelector('[data-testid="playback-bar"]')?.getAttribute("data-mode") === "playback", null, { timeout: 120000 });
  await sleep(1000);
  // the 3D stage (view and playback bar) over the whole page. Not the full-screen button: headless
  // Chromium shrinks a full-screen page to its 800x600 default screen, and the recording shows that.
  await page.addStyleTag({ content: '[data-testid="scene-stage"] { position: fixed !important; inset: 0 !important; z-index: 9000 !important; width: 100vw !important; height: 100vh !important; background: var(--color-bg); }' });
  await sleep(1500);
  if (factor) await page.getByTestId("deformation-exaggeration").selectOption(String(factor));
  await camera(page);
  await page.getByTestId("playback-time").fill(String(at));
  await sleep(800);
}

// The same camera for every model: framed on the hanging chain, orbited up, the hub panned to the
// centre and zoomed out so the chain fits both hanging and upright.
async function camera(page) {
  await page.getByTestId("playback-time").fill("0.5");
  await sleep(500);
  await page.getByTestId("viewer-preset-iso").dispatchEvent("click");
  await sleep(300);
  await page.getByTestId("viewer-fit").dispatchEvent("click");
  await sleep(300);
  const cb = await page.getByTestId("viewer-canvas").boundingBox();
  const cx = cb.x + cb.width / 2, cy = cb.y + cb.height / 2;
  await page.mouse.move(cx - 60, cy); await page.mouse.down(); await page.mouse.move(cx + 60, cy + 50, { steps: 10 }); await page.mouse.up();
  await sleep(200);
  await page.mouse.move(cx, cy); await page.mouse.down({ button: "right" }); await page.mouse.move(cx, cy + 210, { steps: 10 }); await page.mouse.up({ button: "right" });
  await sleep(200);
  await page.mouse.move(cx, cy);
  await page.mouse.wheel(0, 300); await sleep(150);
  await page.mouse.wheel(0, 300); await sleep(150);
  await page.mouse.move(cb.x + cb.width - 5, cb.y + 60);
  await page.addStyleTag({ content: '[data-testid^="viewer-preset"], [data-testid="viewer-fit"], [data-testid="viewer-ortho"], [data-testid="viewer-fullscreen"], [data-testid="detach-viewer"] { visibility: hidden !important; }' });
}

// Paused stills of the arm for the docs: a close-up from the video camera (`<file>.png`) and a view from
// above (`<file>-top.png`), where the horizontal bending shows best. Runs after cut(): not in the video.
async function shot(page, file, t) {
  if (!shots) return;
  await page.evaluate(() => document.getElementById("vid-caption")?.remove());
  await page.getByTestId("playback-time").fill(String(t));
  const cb = await page.getByTestId("viewer-canvas").boundingBox();
  await page.mouse.move(cb.x + cb.width / 2, cb.y + cb.height / 2);
  for (let z = 0; z < 2; z++) { await page.mouse.wheel(0, -300); await sleep(150); }
  await sleep(800);
  await page.getByTestId("viewer-canvas").screenshot({ path: path.join(shots, `${file}.png`) });
  await page.getByTestId("viewer-preset-top").dispatchEvent("click");
  await sleep(300);
  await page.getByTestId("viewer-fit").dispatchEvent("click");
  await sleep(300);
  await page.mouse.wheel(0, -300);
  await sleep(800);
  await page.getByTestId("viewer-canvas").screenshot({ path: path.join(shots, `${file}-top.png`) });
}

const browser = await launchBrowser();
const project = await createProject(RIGID, "flexvid");
try {
  // every model is run on the page itself (one to two and a half minutes each); the waits are cut
  const ctx = await browser.newContext({
    viewport: { width: 1280, height: 720 }, colorScheme: theme,
    recordVideo: { dir: work, size: { width: 1280, height: 720 } },
  });
  const page = await ctx.newPage();
  t0 = Date.now();
  await page.addInitScript(layout, theme);

  // 1. the rigid arm
  await load(page, project, RIGID, null, 1.0);
  await caption(page, "Triple rotary pendulum, rigid arm: swing-up and balance",
    "1 kHz LQR firmware tracking a collocation swing-up; real Julia simulation of the bond graph.");
  keep();
  await sleep(1200);
  await play(page, 1.0, 4.6, 1);
  await sleep(800);

  // 2. the flexible arm, same firmware
  await load(page, project, FLEX, 10, 1.0);
  await caption(page, "Same firmware, flexible arm: a 3 x 50 mm steel strip (FlexibleBeam3D)",
    "First bending mode about 75 Hz with the hub on the motor. Deformation drawn x10.");
  keep();
  await sleep(1500);
  await play(page, 1.0, 2.55, 1);
  await caption(page, "Near the top the gains grow: the loop shakes the arm's bending mode (shown at 0.1x)",
    "The link encoders read the bending as link motion, and the loop has no roll-off.");
  await play(page, null, 3.25, 0.1);
  await caption(page, "The amplifier saturates at 15 V: the swing-up is lost", "The chain is never caught.");
  await play(page, null, 6.0, 1);
  await sleep(600);
  cut();
  await shot(page, "flex-3d", 4.055);

  // 3. the fix
  await load(page, project, LOWPASS, 100, 1.0);
  await caption(page, "The fix: the same LQR weights, designed with a 12 Hz low-pass in the loop",
    "The loop rolls off below the arm mode. Deformation drawn x100: the swing-up bends the strip by about 1.6 mm.");
  keep();
  await sleep(1500);
  await play(page, 1.0, 4.3, 0.5);
  await caption(page, "Caught at 5.0 s; a 0.1 N push on the tip link at 8.5 s", "It recovers in about 2 s (rigid arm: 1.35 s).");
  await play(page, 8.3, 10.0, 1);
  await sleep(1000);
  cut();
  await shot(page, "flex-lowpass-3d", 2.953);
  await ctx.close();

  const webm = readdirSync(work).find((f) => f.endsWith(".webm"));
  const src = path.join(work, webm);
  writeFileSync(path.join(work, "marks.json"), JSON.stringify({ segments }));
  const total = segments.reduce((s, [a, b]) => s + b - a, 0);
  const ff = spawnSync("ffmpeg", ["-version"]);
  if (ff.status === 0 && out.endsWith(".mp4")) {
    const parts = segments.map(([a, b], i) => `[0:v]trim=start=${a.toFixed(3)}:end=${b.toFixed(3)},setpts=PTS-STARTPTS[s${i}]`);
    const filter = `${parts.join(";")};${segments.map((_, i) => `[s${i}]`).join("")}concat=n=${segments.length}:v=1:a=0[v]`;
    const r = spawnSync("ffmpeg", ["-y", "-i", src, "-filter_complex", filter, "-map", "[v]",
      "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "slow", "-r", "25", "-an", out], { stdio: "inherit" });
    if (r.status !== 0) throw new Error("ffmpeg failed");
  } else {
    renameSync(src, out.replace(/\.mp4$/, ".webm"));
  }
  console.log("video", out, `(${total.toFixed(1)} s in ${segments.length} segments)`, JSON.stringify(segments));
} catch (e) {
  console.error("FAILED", e);
  process.exitCode = 1;
} finally {
  await fetch(`${BASE}/api/projects/${project}`, { method: "DELETE" }).catch(() => {});
  await browser.close();
  try { rmSync(work, { recursive: true, force: true }); } catch {}
}
