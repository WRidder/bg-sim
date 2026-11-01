#!/usr/bin/env node
// The suction-cup video: the dashboard and the 3D view of the single bellows suction cup example, one
// segment per model (hold and release, vertical bounce, horizontal steps, tilt swing, lateral chirp,
// overload, linear vs nonlinear cup), every segment in real time (1x).
//
// Same scheme as capture-vdp-belt.mjs: each model runs off camera (auto re-run off), then the playback
// slider of the detached viewer is stepped in real time (t_k = k / FPS) and the dashboard (main window)
// and the 3D canvas (pop-out) are screenshotted. compose: ffmpeg hstack, a caption bar with the model,
// "1x real time" and the simulation time, H.264.
//
// usage: node tools/video/capture-suction-cup.mjs <out-dir> [--fps 30] [--max-frames n] [--zoom 6]
//          [--zoom-at 0.5,0.42] [--wheel 120] [--orbit 0,0] [--only a,b] [--stills] [--compose-only]
//   BGSIM_VIDEO_URL=http://127.0.0.1:<port> (a private backend, see README.md)
//   --stills: only the framing stills and the segment ends, no frames
import { mkdirSync, readFileSync, writeFileSync, rmSync, statSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { launchBrowser, createProject, newPage, openModel, runAndWait, sleep, BASE } from "./lib.mjs";

const out = path.resolve(process.argv[2] ?? "suction-cup-video");
const arg = (n) => { const i = process.argv.indexOf(n); return i > 0 ? process.argv[i + 1] : null; };
const pair = (s, d) => (s ?? d).split(",").map(Number);
const FPS = Number(arg("--fps") ?? 30);
const maxFrames = Number(arg("--max-frames") ?? 0);
const ZOOM = Number(arg("--zoom") ?? 6);
const ZOOM_SET = arg("--zoom") !== null;          // --zoom overrides the per-segment zoom
const [ZX, ZY] = pair(arg("--zoom-at"), "0.5,0.42");
const [OX, OY] = pair(arg("--orbit"), "0,-40");
const WHEEL = Number(arg("--wheel") ?? 120);
const STILLS = process.argv.includes("--stills");
const ONLY = arg("--only")?.split(",") ?? null;
const W = 1920, H = 1080, LEFT = 1000;            // dashboard 1000 px wide, 3D 920 px
mkdirSync(out, { recursive: true });

const segments = [
  { id: "hold-release", zoom: 6, seconds: 3.49,
    caption: "Hold: the vacuum pulls the bellows shut and lifts the box off the table (lift stroke); lift, hold, place, release" },
  { id: "bounce", zoom: 7, seconds: 8.89,
    caption: "Bounce: a 4 mm step rings the axial mode (10.3 Hz), then a vertical chirp; at resonance the folds bottom" },
  { id: "steps", zoom: 3, seconds: 7.29,
    caption: "Steps: horizontal acceleration pulses of 1.5, 3 and 4.5 m/s^2: shear, sway, tilt and peel load" },
  { id: "swing", zoom: 6, seconds: 7.49,
    caption: "Swing: the tool tilts to 30 deg and back, then swings +-10 deg at 1.5 Hz: shear and moment on the lip" },
  { id: "chirp", zoom: 7, seconds: 13.09,
    caption: "Chirp: lateral 1.5 to 20 Hz, 0.4 mm: the sway (6.6 Hz) and tilt (13 Hz) resonances, transmissibility" },
  { id: "overload", zoom: 3, seconds: 5.0,
    caption: "Overload: a 0.8 kg box on steps up to 9 m/s^2: U reaches 1, the lip peels, the seal is lost, the box falls" },
  { id: "linear-vs-nonlinear", zoom: 5, seconds: 8.89,
    caption: "Nonlinear cup (blue box) next to the linear cup (sand box): the lift stroke and the bottoming of the folds" },
].filter((s) => !ONLY || ONLY.includes(s.id));

const raf = (pg) => pg.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
const sv = (x) => String(Number((Math.round(x / 0.002) * 0.002).toFixed(3)));

const marks = process.argv.includes("--compose-only")
  ? JSON.parse(readFileSync(path.join(out, "marks.json"), "utf8")).marks
  : await capture();
if (marks) compose(marks);

async function capture() {
const browser = await launchBrowser();
const project = await createProject("suction-cup", "cup");
try {
  const page = await newPage(browser, { viewport: { width: LEFT, height: H } });
  await page.addInitScript(() => { try { localStorage.setItem("bgsim.layout.rows", JSON.stringify({ main: 100, dock: 0 })); } catch {} });
  const frames = path.join(out, "frames");
  if (!STILLS) {
    rmSync(frames, { recursive: true, force: true });
    mkdirSync(path.join(frames, "d"), { recursive: true });
    mkdirSync(path.join(frames, "v"), { recursive: true });
  }
  const marks = [];
  let k = 0;
  for (const seg of segments) {
    await openModel(page, project, seg.id);
    await page.getByRole("tab", { name: "Dashboard" }).click();
    await page.getByTestId("dashboard").waitFor();
    const auto = page.getByTestId("dash-auto-rerun");
    if (await auto.isChecked()) await auto.uncheck();
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
    await page.addStyleTag({ content: '#library, #inspector, #dock, [aria-controls="library"], [aria-controls="center"], ' +
      '[aria-controls="main"] { display: none !important; } #center, #main { flex: 1 1 auto !important; }' });
    await sleep(500);
    await page.screenshot({ path: path.join(out, `${seg.id}-dashboard-start.png`) });
    await runAndWait(page, 900000);                 // off camera
    await pop.waitForFunction(() => document.querySelector('[data-testid="playback-bar"]')?.getAttribute("data-mode") === "playback", null, { timeout: 90000 });
    const canvas = pop.getByTestId("viewer-canvas");
    const slider = pop.getByTestId("playback-time");
    const T = Number(await slider.getAttribute("max"));
    // frame the cup: fit at the start (box on the table), orbit, zoom in at the cup
    await slider.fill(sv(0.2));
    await pop.getByTestId("viewer-fit").dispatchEvent("click");
    await sleep(700);
    const cb = await canvas.boundingBox();
    const cx = cb.x + cb.width / 2, cy = cb.y + cb.height / 2;
    if (OX || OY) {
      await pop.mouse.move(cx, cy);
      await pop.mouse.down(); await pop.mouse.move(cx + OX, cy + OY, { steps: 12 }); await pop.mouse.up();
      await sleep(300);
    }
    await pop.mouse.move(cb.x + cb.width * ZX, cb.y + cb.height * ZY);
    for (let z = 0; z < (ZOOM_SET ? ZOOM : seg.zoom ?? ZOOM); z++) { await pop.mouse.wheel(0, -WHEEL); await sleep(120); }
    await pop.mouse.move(cb.x + cb.width - 2, cb.y + 2);
    await sleep(600);
    await canvas.screenshot({ path: path.join(out, `${seg.id}-camera.png`) });
    const N0 = Math.round(Math.min(seg.seconds, T) * FPS);
    const N = STILLS ? 0 : maxFrames ? Math.min(N0, maxFrames) : N0;
    marks.push({ id: seg.id, from: k, frames: N, T, caption: seg.caption });
    for (let i = 0; i < N; i++, k++) {
      await slider.fill(sv(i / FPS));
      await Promise.all([raf(pop), raf(page)]);
      await Promise.all([
        canvas.screenshot({ type: "jpeg", quality: 90, path: path.join(frames, "v", `${String(k).padStart(5, "0")}.jpg`) }),
        page.screenshot({ type: "jpeg", quality: 90, path: path.join(frames, "d", `${String(k).padStart(5, "0")}.jpg`) }),
      ]);
    }
    for (const [tag, frac] of [["mid", 0.5], ["end", 1.0]]) {
      await slider.fill(sv(Math.min(T, seg.seconds) * frac));
      await Promise.all([raf(pop), raf(page)]);
      await canvas.screenshot({ path: path.join(out, `${seg.id}-3d-${tag}.png`) });
      await page.screenshot({ path: path.join(out, `${seg.id}-dashboard-${tag}.png`) });
    }
    console.log("segment", seg.id, `T=${T} frames=${N}`);
    await pop.close().catch(() => {});
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

// compose: dashboard | 3D, a caption bar with "1x real time" and the simulation time (every segment
// starts at t = 0, frame k shows t = k / FPS), constant FPS
function compose(marks) {
  const frames = path.join(out, "frames");
  const font = "C\\:/Windows/Fonts/segoeui.ttf";
  const esc = (t) => t.replace(/\\/g, "\\\\").replace(/:/g, "\\:").replace(/'/g, "\u2019").replace(/,/g, "\\,").replace(/%/g, "\\%");
  const clock = "1x real time   t = %{eif\\:trunc(t)\\:d}.%{eif\\:mod(trunc(t*100)\\,100)\\:d\\:2} s";
  const parts = [];
  for (const m of marks) {
    const seg = path.join(out, `seg-${m.id}.mp4`);
    const R = W - LEFT;
    const vf = `[0:v]scale=${LEFT}:${H}[d];[1:v]scale=${R}:${H}:force_original_aspect_ratio=decrease,` +
      `pad=${R}:${H}:(ow-iw)/2:(oh-ih)/2:color=0x16181d[v];[d][v]hstack=inputs=2,` +
      `drawbox=x=0:y=ih-64:w=iw:h=64:color=black@0.72:t=fill,` +
      `drawtext=fontfile='${font}':text='${esc(m.caption)}':fontcolor=white:fontsize=22:x=24:y=h-43,` +
      `drawtext=fontfile='${font}':text='${clock}':fontcolor=0xffc04d:fontsize=24:x=w-tw-24:y=h-44`;
    const r = spawnSync("ffmpeg", ["-y", "-loglevel", "error", "-framerate", String(FPS), "-start_number", String(m.from), "-i", path.join(frames, "d", "%05d.jpg"),
      "-framerate", String(FPS), "-start_number", String(m.from), "-i", path.join(frames, "v", "%05d.jpg"),
      "-frames:v", String(m.frames), "-filter_complex", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "25", "-preset", "slow", "-r", String(FPS), seg],
      { stdio: "inherit" });
    if (r.status !== 0) throw new Error(`ffmpeg failed for ${m.id}`);
    parts.push(seg);
  }
  const list = path.join(out, "parts.txt");
  writeFileSync(list, parts.map((p) => `file '${p.replace(/\\/g, "/")}'`).join("\n") + "\n");
  const file = path.join(out, "suction-cup.mp4");
  const r = spawnSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", list, "-c", "copy", file], { stdio: "inherit" });
  if (r.status !== 0) throw new Error("ffmpeg concat failed");
  console.log("wrote", file, `${(statSync(file).size / 1e6).toFixed(1)} MB`);
}
