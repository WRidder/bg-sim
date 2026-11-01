#!/usr/bin/env node
// The bridge-pier video: the dashboard and the 3D view of the two-span truss bridge on a pier, for
// two runs: the overloaded lorry buckles the slender diagonal and the redundant truss holds, then
// weaker members (dashboard slider) let the pier column buckle and the bridge collapses.
//
// Deterministic: every run happens off camera (the dashboard's auto re-run is switched off and the
// run is started and awaited before any frame); then the playback slider of the detached viewer is
// set to t_k = k * s / FPS for frame k (fixed dt), and the dashboard (main window, cursor-following
// cards) and the 3D canvas (pop-out) are screenshotted. compose: ffmpeg hstack, caption bar, H.264.
//
// usage: node tools/video/capture-bridge-pier.mjs <out-dir> [--fps 25] [--max-frames n] [--zoom 9] [--compose-only]
//   BGSIM_VIDEO_URL=http://127.0.0.1:<port> (a private backend, see README.md)
import { mkdirSync, readFileSync, writeFileSync, rmSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { launchBrowser, createProject, newPage, openModel, runAndWait, sleep, BASE } from "./lib.mjs";

const out = path.resolve(process.argv[2] ?? "bridge-pier-video");
const arg = (n) => { const i = process.argv.indexOf(n); return i > 0 ? process.argv[i + 1] : null; };
const FPS = Number(arg("--fps") ?? 25);
const maxFrames = Number(arg("--max-frames") ?? 0);
const ZOOM = Number(arg("--zoom") ?? 9);         // wheel steps in after the fit
const MODEL = "bridge-pier";
const W = 1920, H = 1080, LEFT = 1000;          // dashboard 1000 px wide, 3D 920 px
mkdirSync(out, { recursive: true });

const segments = [
  { id: "hold", seconds: 13, caption: "40 t lorry at 15 m/s: the slender diagonal next to the pier buckles, its X-partner takes the shear, the bridge holds",
    strength: null },
  { id: "collapse", seconds: 9, caption: "Member strength 0.5: the shed load breaks the post and chord next to it, the pier column buckles, the bridge collapses",
    strength: 0.5 },
];

const raf = (pg) => pg.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));

// --compose-only: compose the video again from the frames and marks.json of an earlier capture
const marks = process.argv.includes("--compose-only")
  ? JSON.parse(readFileSync(path.join(out, "marks.json"), "utf8")).marks
  : await capture();
compose(marks);

async function capture() {
const browser = await launchBrowser();
const project = await createProject("bridge", "pier");
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
  // the dashboard alone in the left column: library, inspector and dock hidden (their splitters too),
  // so the cards lay out in three columns and the gauge, indicators and plots are in view
  await page.addStyleTag({ content: '#library, #inspector, #dock, [aria-controls="library"], [aria-controls="center"], ' +
    '[aria-controls="main"] { display: none !important; } #center, #main { flex: 1 1 auto !important; }' });
  await sleep(500);
  const canvas = pop.getByTestId("viewer-canvas");

  // a still of the bridge before any run (the scene puts every bar at its rest place)
  await sleep(1500);
  await canvas.screenshot({ path: path.join(out, "before-run-3d.png") });
  await page.screenshot({ path: path.join(out, "before-run-dashboard.png") });

  let k = 0;
  const frames = path.join(out, "frames");
  rmSync(frames, { recursive: true, force: true });
  mkdirSync(path.join(frames, "d"), { recursive: true });
  mkdirSync(path.join(frames, "v"), { recursive: true });
  const marks = [];
  let camera = false;
  for (const seg of segments) {
    if (seg.strength !== null) {
      const slider = page.getByTestId("dash-slider-d2");
      await slider.fill(String(seg.strength));
      await sleep(400);
    }
    await runAndWait(page, 900000);                 // off camera
    await pop.waitForFunction(() => document.querySelector('[data-testid="playback-bar"]')?.getAttribute("data-mode") === "playback", null, { timeout: 90000 });
    const slider = pop.getByTestId("playback-time");
    const T = Number(await slider.getAttribute("max"));
    const sv = (x) => String(Number((Math.round(x / 0.001) * 0.001).toFixed(3)));
    if (!camera) {                                  // frame the bridge once, at mid-run
      await slider.fill(sv(T * 0.5));
      await pop.getByTestId("viewer-fit").dispatchEvent("click");
      await sleep(700);
      const cb = await canvas.boundingBox();
      const cx = cb.x + cb.width / 2, cy = cb.y + cb.height / 2;
      await pop.mouse.move(cx, cy);
      await pop.mouse.down(); await pop.mouse.move(cx + 160, cy - 40, { steps: 12 }); await pop.mouse.up();
      for (let z = 0; z < ZOOM; z++) { await pop.mouse.wheel(0, -300); await sleep(120); }
      await sleep(600);
      camera = true;
    }
    const N0 = Math.round(seg.seconds * FPS);
    const N = maxFrames ? Math.min(N0, maxFrames) : N0;
    const s = T / (N - 1);
    marks.push({ id: seg.id, from: k, frames: N, T, caption: seg.caption });
    for (let i = 0; i < N; i++, k++) {
      await slider.fill(sv(Math.min(T, i * s)));
      await Promise.all([raf(pop), raf(page)]);
      await Promise.all([
        canvas.screenshot({ type: "jpeg", quality: 92, path: path.join(frames, "v", `${String(k).padStart(5, "0")}.jpg`) }),
        page.screenshot({ type: "jpeg", quality: 92, path: path.join(frames, "d", `${String(k).padStart(5, "0")}.jpg`) }),
      ]);
    }
    await canvas.screenshot({ path: path.join(out, `${seg.id}-3d-end.png`) });
    await page.screenshot({ path: path.join(out, `${seg.id}-dashboard-end.png`) });
    await slider.fill(sv(T * 0.45));
    await Promise.all([raf(pop), raf(page)]);
    await canvas.screenshot({ path: path.join(out, `${seg.id}-3d-mid.png`) });
    console.log("segment", seg.id, `T=${T} frames=${N}`);
  }
  writeFileSync(path.join(out, "marks.json"), JSON.stringify({ fps: FPS, marks }, null, 2));
  await page.context().close();
  return marks;
} finally {
  await fetch(`${BASE}/api/projects/${project}`, { method: "DELETE" }).catch(() => {});
  await browser.close();
}
}

// compose: dashboard | 3D (the canvas scaled and padded to the right column), a caption bar at the
// bottom of each segment, constant FPS
function compose(marks) {
  const frames = path.join(out, "frames");
  const font = "C\\:/Windows/Fonts/segoeui.ttf";
  const esc = (t) => t.replace(/\\/g, "\\\\").replace(/:/g, "\\:").replace(/'/g, "\u2019").replace(/,/g, "\\,");
  const parts = [];
  for (const m of marks) {
    const seg = path.join(out, `seg-${m.id}.mp4`);
    const R = W - LEFT;
    const vf = `[0:v]scale=${LEFT}:${H}[d];[1:v]scale=${R}:${H}:force_original_aspect_ratio=decrease,` +
      `pad=${R}:${H}:(ow-iw)/2:(oh-ih)/2:color=0x16181d[v];[d][v]hstack=inputs=2,` +
      `drawbox=x=0:y=ih-64:w=iw:h=64:color=black@0.72:t=fill,` +
      `drawtext=fontfile='${font}':text='${esc(m.caption)}':fontcolor=white:fontsize=28:x=24:y=h-46`;
    const r = spawnSync("ffmpeg", ["-y", "-loglevel", "error", "-framerate", String(FPS), "-start_number", String(m.from), "-i", path.join(frames, "d", "%05d.jpg"),
      "-framerate", String(FPS), "-start_number", String(m.from), "-i", path.join(frames, "v", "%05d.jpg"),
      "-frames:v", String(m.frames), "-filter_complex", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-r", String(FPS), seg],
      { stdio: "inherit" });
    if (r.status !== 0) throw new Error(`ffmpeg failed for ${m.id}`);
    parts.push(seg);
  }
  const list = path.join(out, "parts.txt");
  writeFileSync(list, parts.map((p) => `file '${p.replace(/\\/g, "/")}'`).join("\n") + "\n");
  const r = spawnSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", list, "-c", "copy", path.join(out, "bridge-pier.mp4")], { stdio: "inherit" });
  if (r.status !== 0) throw new Error("ffmpeg concat failed");
  console.log("wrote", path.join(out, "bridge-pier.mp4"));
}
