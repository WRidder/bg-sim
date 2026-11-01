#!/usr/bin/env node
// The vdp-belt video: the dashboard and the 3D view of the belt-driven Van der Pol oscillator (a block
// on a spring riding a belt, friction that falls with slip), for three runs set on the dashboard:
// mu = 0.5 from a small start, mu = 1.0, and mu = 0.5 from a start outside the limit cycle.
//
// Same scheme as capture-bridge-pier.mjs: every run happens off camera (auto re-run switched off), then
// the playback slider of the detached viewer is stepped in real time (t_k = k / FPS) and the dashboard
// (main window) and the 3D canvas (pop-out) are screenshotted. compose: ffmpeg hstack, caption bar with
// the simulation time, H.264.
//
// usage: node tools/video/capture-vdp-belt.mjs <out-dir> [--fps 30] [--max-frames n] [--zoom 6]
//          [--zoom-at 0.5,0.5] [--wheel 120] [--orbit 0,0] [--stills] [--compose-only]
//   BGSIM_VIDEO_URL=http://127.0.0.1:<port> (a private backend, see README.md)
//   --stills: only the framing stills (camera and dashboard), no frames
import { mkdirSync, readFileSync, writeFileSync, rmSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { launchBrowser, createProject, newPage, openModel, runAndWait, sleep, BASE } from "./lib.mjs";

const out = path.resolve(process.argv[2] ?? "vdp-belt-video");
const arg = (n) => { const i = process.argv.indexOf(n); return i > 0 ? process.argv[i + 1] : null; };
const pair = (s, d) => (s ?? d).split(",").map(Number);
const FPS = Number(arg("--fps") ?? 30);
const maxFrames = Number(arg("--max-frames") ?? 0);
const ZOOM = Number(arg("--zoom") ?? 3);          // wheel steps in, at --zoom-at (fractions of the canvas)
const [ZX, ZY] = pair(arg("--zoom-at"), "0.5,0.5");
const [OX, OY] = pair(arg("--orbit"), "0,0");     // orbit drag in px before the zoom
const WHEEL = Number(arg("--wheel") ?? 120);      // wheel delta per zoom step
const STILLS = process.argv.includes("--stills");
const MODEL = "vdp-belt";
const W = 1920, H = 1080, LEFT = 1000;            // dashboard 1000 px wide, 3D 920 px
mkdirSync(out, { recursive: true });

const segments = [
  { id: "grow", seconds: 12, mu: 0.5, x0: 0.2,
    caption: "mu = 0.5: friction that falls with slip feeds the swing, which grows onto the Van der Pol limit cycle" },
  { id: "mu1", seconds: 9, mu: 1.0, x0: 0.2,
    caption: "mu = 1.0: a steeper falling slope, a faster rise and a lopsided cycle; the slip nearly reaches stick" },
  { id: "shrink", seconds: 9, mu: 0.5, x0: 2.5,
    caption: "mu = 0.5, start outside the cycle (x0 = 2.5): the swing shrinks onto the same limit cycle" },
];

const raf = (pg) => pg.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
const sv = (x) => String(Number((Math.round(x / 0.001) * 0.001).toFixed(3)));

const marks = process.argv.includes("--compose-only")
  ? JSON.parse(readFileSync(path.join(out, "marks.json"), "utf8")).marks
  : await capture();
if (marks) compose(marks);

async function capture() {
const browser = await launchBrowser();
const project = await createProject("van-der-pol", "belt");
try {
  const page = await newPage(browser, { viewport: { width: LEFT, height: H } });
  await page.addInitScript(() => { try { localStorage.setItem("bgsim.layout.rows", JSON.stringify({ main: 100, dock: 0 })); } catch {} });
  await openModel(page, project, MODEL);
  await page.getByRole("tab", { name: "Dashboard" }).click();
  await page.getByTestId("dashboard").waitFor();
  const auto = page.getByTestId("dash-auto-rerun");
  if (await auto.isChecked()) await auto.uncheck();
  // the 3D viewer in its own window
  await page.getByRole("tab", { name: "3D View" }).click().catch(() => {});
  await page.getByTestId("scene-view").waitFor({ timeout: 90000 }).catch(() => {});
  const popP = page.waitForEvent("popup");
  await page.getByTestId("detach-viewer").click();
  const pop = await popP;
  await pop.setViewportSize({ width: W - LEFT, height: H });
  await pop.getByTestId("viewer-canvas").waitFor();
  await sleep(2500);
  const tree = pop.getByTestId("scene-tree-toggle");
  if (await tree.count()) { const exp = await tree.getAttribute("aria-expanded"); if (exp !== "false") await tree.click().catch(() => {}); }
  await pop.addStyleTag({ content: '[data-testid^="viewer-preset"], [data-testid="viewer-fit"], [data-testid="viewer-ortho"], [data-testid="dock-viewer-button"] { visibility: hidden !important; }' });
  await page.getByRole("tab", { name: "Dashboard" }).click();
  // the dashboard alone in the left column (library, inspector, dock and their splitters hidden)
  await page.addStyleTag({ content: '#library, #inspector, #dock, [aria-controls="library"], [aria-controls="center"], ' +
    '[aria-controls="main"] { display: none !important; } #center, #main { flex: 1 1 auto !important; }' });
  await sleep(500);
  const canvas = pop.getByTestId("viewer-canvas");

  const frames = path.join(out, "frames");
  if (!STILLS) {
    rmSync(frames, { recursive: true, force: true });
    mkdirSync(path.join(frames, "d"), { recursive: true });
    mkdirSync(path.join(frames, "v"), { recursive: true });
  }
  const marks = [];
  let k = 0;
  let camera = false;
  for (const seg of segments) {
    await page.getByTestId("dash-slider-d2").fill(String(seg.mu));
    await page.getByTestId("dash-slider-d3").fill(String(seg.x0));
    await sleep(400);
    await runAndWait(page, 900000);                 // off camera
    await pop.waitForFunction(() => document.querySelector('[data-testid="playback-bar"]')?.getAttribute("data-mode") === "playback", null, { timeout: 90000 });
    const slider = pop.getByTestId("playback-time");
    const T = Number(await slider.getAttribute("max"));
    if (!camera) {                                  // frame the rig once
      await slider.fill(sv(seg.seconds * 0.5));
      await pop.getByTestId("viewer-fit").dispatchEvent("click");
      await sleep(700);
      const cb = await canvas.boundingBox();
      const cx = cb.x + cb.width / 2, cy = cb.y + cb.height / 2;
      if (OX || OY) {
        await pop.mouse.move(cx, cy);
        await pop.mouse.down(); await pop.mouse.move(cx + OX, cy + OY, { steps: 12 }); await pop.mouse.up();
        await sleep(300);
      }
      await canvas.screenshot({ path: path.join(out, "camera-fit.png") });
      await pop.mouse.move(cb.x + cb.width * ZX, cb.y + cb.height * ZY);
      for (let z = 0; z < ZOOM; z++) { await pop.mouse.wheel(0, -WHEEL); await sleep(120); }
      await pop.mouse.move(cb.x + cb.width - 2, cb.y + 2);
      await sleep(600);
      await canvas.screenshot({ path: path.join(out, "camera.png") });
      camera = true;
    }
    const N0 = Math.round(Math.min(seg.seconds, T) * FPS);
    const N = STILLS ? 0 : maxFrames ? Math.min(N0, maxFrames) : N0;
    marks.push({ id: seg.id, from: k, frames: N, T, caption: seg.caption });
    for (let i = 0; i < N; i++, k++) {
      await slider.fill(sv(i / FPS));
      await Promise.all([raf(pop), raf(page)]);
      await Promise.all([
        canvas.screenshot({ type: "jpeg", quality: 92, path: path.join(frames, "v", `${String(k).padStart(5, "0")}.jpg`) }),
        page.screenshot({ type: "jpeg", quality: 92, path: path.join(frames, "d", `${String(k).padStart(5, "0")}.jpg`) }),
      ]);
    }
    await slider.fill(sv(Math.min(T, seg.seconds)));
    await Promise.all([raf(pop), raf(page)]);
    await canvas.screenshot({ path: path.join(out, `${seg.id}-3d-end.png`) });
    await page.screenshot({ path: path.join(out, `${seg.id}-dashboard-end.png`) });
    console.log("segment", seg.id, `T=${T} frames=${N}`);
  }
  if (STILLS) return null;
  writeFileSync(path.join(out, "marks.json"), JSON.stringify({ fps: FPS, marks }, null, 2));
  await page.context().close();
  return marks;
} finally {
  await fetch(`${BASE}/api/projects/${project}`, { method: "DELETE" }).catch(() => {});
  await browser.close();
}
}

// compose: dashboard | 3D, a caption bar with the simulation time (real time from t = 0 in every
// segment, so t is the segment's own clock), constant FPS
function compose(marks) {
  const frames = path.join(out, "frames");
  const font = "C\\:/Windows/Fonts/segoeui.ttf";
  const esc = (t) => t.replace(/\\/g, "\\\\").replace(/:/g, "\\:").replace(/'/g, "\u2019").replace(/,/g, "\\,");
  const clock = "t = %{eif\\:trunc(t)\\:d}.%{eif\\:mod(trunc(t*100)\\,100)\\:d\\:2} s";
  const parts = [];
  for (const m of marks) {
    const seg = path.join(out, `seg-${m.id}.mp4`);
    const R = W - LEFT;
    const vf = `[0:v]scale=${LEFT}:${H}[d];[1:v]scale=${R}:${H}:force_original_aspect_ratio=decrease,` +
      `pad=${R}:${H}:(ow-iw)/2:(oh-ih)/2:color=0x16181d[v];[d][v]hstack=inputs=2,` +
      `drawbox=x=0:y=ih-64:w=iw:h=64:color=black@0.72:t=fill,` +
      `drawtext=fontfile='${font}':text='${esc(m.caption)}':fontcolor=white:fontsize=26:x=24:y=h-45,` +
      `drawtext=fontfile='${font}':text='${clock}':fontcolor=0xffc04d:fontsize=26:x=w-tw-24:y=h-45`;
    const r = spawnSync("ffmpeg", ["-y", "-loglevel", "error", "-framerate", String(FPS), "-start_number", String(m.from), "-i", path.join(frames, "d", "%05d.jpg"),
      "-framerate", String(FPS), "-start_number", String(m.from), "-i", path.join(frames, "v", "%05d.jpg"),
      "-frames:v", String(m.frames), "-filter_complex", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "22", "-preset", "slow", "-r", String(FPS), seg],
      { stdio: "inherit" });
    if (r.status !== 0) throw new Error(`ffmpeg failed for ${m.id}`);
    parts.push(seg);
  }
  const list = path.join(out, "parts.txt");
  writeFileSync(list, parts.map((p) => `file '${p.replace(/\\/g, "/")}'`).join("\n") + "\n");
  const r = spawnSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", list, "-c", "copy", path.join(out, "vdp-belt.mp4")], { stdio: "inherit" });
  if (r.status !== 0) throw new Error("ffmpeg concat failed");
  console.log("wrote", path.join(out, "vdp-belt.mp4"));
}
