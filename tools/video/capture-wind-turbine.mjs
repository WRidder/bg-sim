#!/usr/bin/env node
// The wind-turbine video: the dashboard and the 3D view of the NREL 5 MW turbine through the IEC extreme
// operating gust (model wind-turbine-gust), in real time.
//
// Same scheme as capture-vdp-belt.mjs: the run happens off camera (auto re-run switched off), then the
// playback slider of the detached viewer is stepped in real time (t_k = t0 + k / FPS) and the dashboard
// (main window) and the 3D canvas (pop-out) are screenshotted. compose: ffmpeg hstack, caption bar with
// the simulation time, H.264.
//
// usage: node tools/video/capture-wind-turbine.mjs <out-dir> [--fps 25] [--max-frames n] [--zoom 3]
//          [--zoom-at 0.5,0.5] [--wheel 120] [--orbit 0,0] [--from 12] [--seconds 30] [--stills] [--compose-only]
//   BGSIM_VIDEO_URL=http://127.0.0.1:<port> (a private backend, see README.md)
import { mkdirSync, readFileSync, writeFileSync, rmSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { launchBrowser, createProject, newPage, openModel, runAndWait, sleep, BASE } from "./lib.mjs";

const out = path.resolve(process.argv[2] ?? "wind-turbine-video");
const arg = (n) => { const i = process.argv.indexOf(n); return i > 0 ? process.argv[i + 1] : null; };
const pair = (s, d) => (s ?? d).split(",").map(Number);
const FPS = Number(arg("--fps") ?? 25);
const maxFrames = Number(arg("--max-frames") ?? 0);
const ZOOM = Number(arg("--zoom") ?? 3);
const [ZX, ZY] = pair(arg("--zoom-at"), "0.5,0.5");
const [OX, OY] = pair(arg("--orbit"), "0,0");
const WHEEL = Number(arg("--wheel") ?? 120);
const FROM = Number(arg("--from") ?? 12);
const SECONDS = Number(arg("--seconds") ?? 30);
const STILLS = process.argv.includes("--stills");
const MODEL = "wind-turbine-gust";
const W = 1920, H = 1080, LEFT = 1000;
mkdirSync(out, { recursive: true });

const caption = "NREL 5 MW turbine, IEC extreme operating gust on 12 m/s: the pitch catches the overspeed (tower sway drawn x20)";
const raf = (pg) => pg.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
const sv = (x) => String(Number((Math.round(x / 0.001) * 0.001).toFixed(3)));

const marks = process.argv.includes("--compose-only")
  ? JSON.parse(readFileSync(path.join(out, "marks.json"), "utf8")).marks
  : await capture();
if (marks) compose(marks);

async function capture() {
  const browser = await launchBrowser();
  const project = await createProject("wind-turbine", "gust");
  try {
    const page = await newPage(browser, { viewport: { width: LEFT, height: H } });
    await page.addInitScript(() => { try { localStorage.setItem("bgsim.layout.rows", JSON.stringify({ main: 100, dock: 0 })); } catch {} });
    await openModel(page, project, MODEL);
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
    const canvas = pop.getByTestId("viewer-canvas");
    const frames = path.join(out, "frames");
    if (!STILLS) {
      rmSync(frames, { recursive: true, force: true });
      mkdirSync(path.join(frames, "d"), { recursive: true });
      mkdirSync(path.join(frames, "v"), { recursive: true });
    }
    await runAndWait(page, 900000);                 // off camera
    await pop.waitForFunction(() => document.querySelector('[data-testid="playback-bar"]')?.getAttribute("data-mode") === "playback", null, { timeout: 90000 });
    const slider = pop.getByTestId("playback-time");
    const T = Number(await slider.getAttribute("max"));
    await slider.fill(sv(FROM));
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
    await page.screenshot({ path: path.join(out, "dashboard.png") });
    const N0 = Math.round(Math.min(SECONDS, T - FROM) * FPS);
    const N = STILLS ? 0 : maxFrames ? Math.min(N0, maxFrames) : N0;
    const marks = [{ id: "gust", from: 0, frames: N, t0: FROM, T, caption }];
    for (let k = 0; k < N; k++) {
      await slider.fill(sv(FROM + k / FPS));
      await Promise.all([raf(pop), raf(page)]);
      await Promise.all([
        canvas.screenshot({ type: "jpeg", quality: 90, path: path.join(frames, "v", `${String(k).padStart(5, "0")}.jpg`) }),
        page.screenshot({ type: "jpeg", quality: 90, path: path.join(frames, "d", `${String(k).padStart(5, "0")}.jpg`) }),
      ]);
      if (k % 100 === 0) console.log("frame", k, "of", N);
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

// compose: dashboard | 3D, a caption bar with the simulation time
function compose(marks) {
  const frames = path.join(out, "frames");
  const font = "C\\:/Windows/Fonts/segoeui.ttf";
  const esc = (t) => t.replace(/\\/g, "\\\\").replace(/:/g, "\\:").replace(/'/g, "\u2019").replace(/,/g, "\\,");
  const m = marks[0];
  const clock = `t = %{eif\\:trunc(t+${m.t0})\\:d}.%{eif\\:mod(trunc((t+${m.t0})*10)\\,10)\\:d} s`;
  const R = W - LEFT;
  const vf = `[0:v]scale=${LEFT}:${H}[d];[1:v]scale=${R}:${H}:force_original_aspect_ratio=decrease,` +
    `pad=${R}:${H}:(ow-iw)/2:(oh-ih)/2:color=0x16181d[v];[d][v]hstack=inputs=2,` +
    `drawbox=x=0:y=ih-64:w=iw:h=64:color=black@0.72:t=fill,` +
    `drawtext=fontfile='${font}':text='${esc(m.caption)}':fontcolor=white:fontsize=24:x=24:y=h-44,` +
    `drawtext=fontfile='${font}':text='${clock}':fontcolor=0xffc04d:fontsize=26:x=w-tw-24:y=h-45`;
  const dst = path.join(out, "wind-turbine-gust.mp4");
  const r = spawnSync("ffmpeg", ["-y", "-loglevel", "error", "-framerate", String(FPS), "-start_number", "0", "-i", path.join(frames, "d", "%05d.jpg"),
    "-framerate", String(FPS), "-start_number", "0", "-i", path.join(frames, "v", "%05d.jpg"),
    "-frames:v", String(m.frames), "-filter_complex", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "24", "-preset", "slow", "-r", String(FPS), dst],
    { stdio: "inherit" });
  if (r.status !== 0) throw new Error("ffmpeg failed");
  console.log("wrote", dst);
}
