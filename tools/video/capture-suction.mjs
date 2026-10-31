#!/usr/bin/env node
// The suction-gripper showcase video (about 37 s, 1280x720): Playwright records the real app with the real
// Julia worker. A safe S-curve move, the aggressive trapezoid that peels the cups off, the same move time as
// an S-curve that holds, and a porous parcel on an undersized generator. The dashboard (cup utilisation,
// cup vacuum, held indicator) runs above the 3D view; captions are injected into the page.
//
// usage (backend with the real worker on BGSIM_VIDEO_URL, see README.md):
//   node tools/video/capture-suction.mjs <out.mp4|out.webm> [--theme dark|light]
// The recording is a .webm; with ffmpeg on PATH the kept segments are cut out and encoded to H.264 .mp4.
// The re-runs between the scenes are not kept: while a run streams in, the 3D view jumps and flashes.
import { mkdirSync, readdirSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import os from "node:os";
import path from "node:path";
import { launchBrowser, createProject, openModel, runAndWait, sleep, BASE } from "./lib.mjs";

const out = path.resolve(process.argv[2] ?? "suction.mp4");
const theme = process.argv.includes("--theme") ? process.argv[process.argv.indexOf("--theme") + 1] : "dark";
const work = path.join(os.tmpdir(), `bgsim-suction-video-${Date.now().toString(36)}`);
mkdirSync(work, { recursive: true });

const layout = (th) => {
  try {
    localStorage.setItem("bgsim.layout.rows", JSON.stringify({ main: 40, dock: 60 }));
    localStorage.setItem("bgsim.layout.columns", JSON.stringify({ library: 4, center: 92, inspector: 4 }));
    localStorage.setItem("bgsim.theme", th);
  } catch {}
};

async function caption(page, title, sub = "") {
  await page.evaluate(([t, s]) => {
    let el = document.getElementById("vid-caption");
    if (!el) {
      el = document.createElement("div");
      el.id = "vid-caption";
      el.style.cssText = "position:fixed;left:84px;bottom:52px;z-index:99999;max-width:640px;padding:10px 16px;" +
        "border-radius:8px;background:rgba(15,17,22,0.86);color:#fff;font:600 19px/1.3 'Segoe UI',sans-serif;" +
        "border-left:4px solid #f5a623;box-shadow:0 4px 18px rgba(0,0,0,0.35);transition:opacity .3s";
      document.body.appendChild(el);
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

async function setSlider(page, id, value) {
  await page.getByTestId(`dash-slider-${id}`).fill(String(value));
  await sleep(350);
}

async function play(page, from, to, speed = "0.25") {
  const slider = page.getByTestId("playback-time");
  await page.getByTestId("playback-speed").selectOption(speed);
  await slider.fill(String(from));
  await sleep(300);
  await page.getByTestId("playback-toggle").click();
  await page.waitForFunction((t) => Number(document.querySelector('[data-testid="playback-time"]')?.value) >= t, to,
    { timeout: 120000, polling: 50 });
  await page.getByTestId("playback-toggle").click();
}

// Kept stretches of the recording, in seconds from the page start; everything else is cut.
const segments = [];
let t0 = 0;
let segStart = null;
const MARGIN = 0.3;  // s trimmed at each cut, so no frame of a re-run slips in
const keep = () => { segStart = (Date.now() - t0) / 1000 + MARGIN; };
const cut = () => {
  if (segStart !== null) segments.push([segStart, (Date.now() - t0) / 1000 - MARGIN]);
  segStart = null;
};

// Off camera: set the sliders, run, park the playback at `from` and let the view settle.
async function rerun(page, sliders, from) {
  cut();
  for (const [id, value] of sliders) await setSlider(page, id, value);
  await runNow(page);
  await page.getByTestId("playback-time").fill(String(from));
  await sleep(800);
}

async function runNow(page) {
  await page.getByTestId("dash-card-umax").evaluate((el) => el.scrollIntoView({ block: "start" }));  // the plots back in view
  await page.getByTestId("run-button").click();
  await page.waitForFunction(() => document.querySelector('[data-testid="run-status"]')?.getAttribute("data-status") === "done",
    null, { timeout: 600000, polling: 200 });
  await page.waitForFunction(() => {
    const bar = document.querySelector('[data-testid="playback-bar"]');
    return bar === null || bar.getAttribute("data-mode") === "playback";
  }, null, { timeout: 90000 });
  await sleep(600);
}

const browser = await launchBrowser();
const project = await createProject("suction-gripper", "sgvid");
try {
  // warm-up (not recorded): compile the plant once, so the recorded runs take about a second
  {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 } });
    const page = await ctx.newPage();
    await openModel(page, project, "transfer");
    await runAndWait(page, 900000);
    await ctx.close();
  }
  const ctx = await browser.newContext({
    viewport: { width: 1280, height: 720 }, colorScheme: theme,
    recordVideo: { dir: work, size: { width: 1280, height: 720 } },
  });
  const page = await ctx.newPage();
  t0 = Date.now();  // the recording starts with the page, not the context
  await page.addInitScript(layout, theme);
  await openModel(page, project, "transfer");
  await page.getByRole("tab", { name: "Dashboard" }).click();
  await runNow(page);
  await page.getByRole("tab", { name: "3D View" }).click();
  await page.waitForFunction(() => document.querySelector('[data-testid="scene-view"]')?.getAttribute("data-state") === "loaded", null, { timeout: 90000 });
  await page.waitForFunction(() => document.querySelector('[data-testid="playback-bar"]')?.getAttribute("data-mode") === "playback", null, { timeout: 90000 });
  await sleep(1200);
  const tree = page.getByTestId("scene-tree-toggle");
  if (await tree.count()) { const exp = await tree.getAttribute("aria-expanded"); if (exp !== "false") await tree.click().catch(() => {}); }
  await page.getByTestId("playback-time").fill("0.6");
  await page.getByTestId("viewer-fit").click();
  await sleep(400);
  await page.getByTestId("viewer-preset-side").dispatchEvent("click");
  await sleep(400);
  const cb = await page.getByTestId("viewer-canvas").boundingBox();
  const cx = cb.x + cb.width / 2, cy = cb.y + cb.height / 2;
  await page.mouse.move(cx - 30, cy); await page.mouse.down(); await page.mouse.move(cx + 30, cy, { steps: 10 }); await page.mouse.up();
  await page.mouse.move(cx + cb.width * 0.1, cy + cb.height * 0.12);
  for (let z = 0; z < 8; z++) { await page.mouse.wheel(0, -300); await sleep(100); }
  await page.addStyleTag({ content: '[data-testid^="viewer-preset"], [data-testid="viewer-fit"], [data-testid="viewer-ortho"] { visibility: hidden !important; }' });
  await sleep(500);
  // 1. the safe move
  await caption(page, "Six-cup vacuum gripper, 10 kg carton, real Julia simulation",
    "Safe move: S-curve, 1 m in 1.75 s. Every cup keeps U ≤ 0.5 (safety factor 2). Cups: blue = low load, red = U ≥ 1.");
  keep();
  await sleep(900);
  await play(page, 0.6, 2.9, "0.5");
  await sleep(400);

  // 2. aggressive trapezoid
  await rerun(page, [["kind", 1], ["tmove", 0.7]], 1.0);
  await caption(page, "Faster: trapezoid profile, 0.7 s (9.2 m/s², infinite jerk)", "Set on the dashboard, run again (about 1 s).");
  keep();
  await sleep(1200);
  await play(page, 1.0, 1.5, "0.5");
  await caption(page, "The acceleration steps ring the bellows", "At the deceleration the cups peel, lose their seal one after the other, and the parcel drops.");
  await play(page, 1.5, 2.05);
  await sleep(1000);

  // 3. same time, S-curve
  await rerun(page, [["kind", 2]], 0.9);
  await caption(page, "Same 0.7 s as an S-curve: 13.1 m/s² peak, but finite jerk", "No cup loses its seal; the parcel arrives.");
  keep();
  await sleep(1200);
  await play(page, 0.9, 2.1, "0.5");
  await sleep(600);

  // 4. air flow: porous parcel, undersized generator
  await rerun(page, [["perm", 2e-6], ["qmax", 6e-4], ["tmove", 1.2]], 1.0);
  await caption(page, "Air flow matters: porous parcel on a 36 l/min generator",
    "Air leaks through the material; the generator only holds 21.5 kPa. A 1.2 s S-curve tears the parcel off.");
  keep();
  await sleep(1500);
  await play(page, 1.0, 1.6, "0.5");
  await play(page, 1.6, 2.25);
  await sleep(1200);
  cut();
  await ctx.close();

  const webm = readdirSync(work).find((f) => f.endsWith(".webm"));
  const src = path.join(work, webm);
  writeFileSync(path.join(work, "marks.json"), JSON.stringify({ segments }));
  const total = segments.reduce((s, [a, b]) => s + b - a, 0);
  const ff = spawnSync("ffmpeg", ["-version"]);
  if (ff.status === 0 && out.endsWith(".mp4")) {
    // Trim each kept segment and concatenate; keep the recording's own 25 fps (no resampling judder).
    const parts = segments.map(([a, b], i) => `[0:v]trim=start=${a.toFixed(3)}:end=${b.toFixed(3)},setpts=PTS-STARTPTS[s${i}]`);
    const filter = `${parts.join(";")};${segments.map((_, i) => `[s${i}]`).join("")}concat=n=${segments.length}:v=1:a=0[v]`;
    const r = spawnSync("ffmpeg", ["-y", "-i", src, "-filter_complex", filter, "-map", "[v]",
      "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "slow", "-r", "25", "-an", out], { stdio: "inherit" });
    if (r.status !== 0) throw new Error("ffmpeg failed");
  } else {
    renameSync(src, out.replace(/\.mp4$/, ".webm"));
  }
  console.log("video", out, `(${total.toFixed(1)} s in ${segments.length} segments)`);
} catch (e) {
  console.error("FAILED", e);
  process.exitCode = 1;
} finally {
  await fetch(`${BASE}/api/projects/${project}`, { method: "DELETE" }).catch(() => {});
  await browser.close();
  try { rmSync(work, { recursive: true, force: true }); } catch {}
}
