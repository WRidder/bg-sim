#!/usr/bin/env node
// The ACTILINK video: the dashboard and the 3D view of the rotary double pendulum on a Synapticon
// ACTILINK-JD10 actuator (pendulum-double-rotary, models actilink-*): the swing-up from hanging with
// the catch into the 1 kHz EtherCAT LQR, then the push on the link-2 tip and its recovery.
//
// Same scheme as capture-vdp-belt.mjs: every run happens off camera (auto re-run switched off), then the
// playback slider of the detached viewer is stepped in real time (t_k = k / FPS) and the dashboard (main
// window) and the 3D canvas (pop-out) are screenshotted. compose: ffmpeg hstack, caption bar with the
// simulation time, H.264.
//
// usage: node tools/video/capture-actilink.mjs <out-dir> [--fps 30] [--max-frames n] [--zoom 3]
//          [--zoom-at 0.5,0.45] [--wheel 120] [--orbit 0,0] [--stills] [--compose-only]
//   BGSIM_VIDEO_URL=http://127.0.0.1:<port> (a private backend, see README.md)
import { mkdirSync, readFileSync, writeFileSync, rmSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { launchBrowser, createProject, newPage, openModel, runAndWait, sleep, BASE } from "./lib.mjs";

const out = path.resolve(process.argv[2] ?? "actilink-video");
const arg = (n) => { const i = process.argv.indexOf(n); return i > 0 ? process.argv[i + 1] : null; };
const pair = (s, d) => (s ?? d).split(",").map(Number);
const FPS = Number(arg("--fps") ?? 30);
const maxFrames = Number(arg("--max-frames") ?? 0);
const ZOOM = Number(arg("--zoom") ?? 2);
const [ZX, ZY] = pair(arg("--zoom-at"), "0.5,0.45");
const [OX, OY] = pair(arg("--orbit"), "0,0");
const WHEEL = Number(arg("--wheel") ?? 120);
const STILLS = process.argv.includes("--stills");
const W = 1920, H = 1080, LEFT = 1000;
mkdirSync(out, { recursive: true });

const segments = [
  { id: "swingup", model: "actilink-swingup", seconds: 8,
    caption: "ACTILINK-JD10, 0.3 m arm, 2 x 0.6 m links: collocation swing-up + TVLQR, catch into the 1 kHz LQR on AS5048 readings" },
  { id: "push", model: "actilink-push", seconds: 6,
    caption: "Balancing upright; at 2 s a 0.3 N, 50 ms push on the link-2 tip: the arm swings out and the LQR recovers" },
];

const raf = (pg) => pg.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
const sv = (x) => String(Number((Math.round(x / 0.001) * 0.001).toFixed(3)));

const marks = process.argv.includes("--compose-only")
  ? JSON.parse(readFileSync(path.join(out, "marks.json"), "utf8")).marks
  : await capture();
if (marks) compose(marks);

async function capture() {
  const browser = await launchBrowser();
  const project = await createProject("pendulum-double-rotary", "actilink");
  try {
    const frames = path.join(out, "frames");
    if (!STILLS) {
      rmSync(frames, { recursive: true, force: true });
      mkdirSync(path.join(frames, "d"), { recursive: true });
      mkdirSync(path.join(frames, "v"), { recursive: true });
    }
    const marks = [];
    let k = 0;
    for (const seg of segments) {
      const page = await newPage(browser, { viewport: { width: LEFT, height: H } });
      await page.addInitScript(() => { try { localStorage.setItem("bgsim.layout.rows", JSON.stringify({ main: 100, dock: 0 })); } catch {} });
      await openModel(page, project, seg.model);
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
      await runAndWait(page, 1800000);                // off camera
      await pop.waitForFunction(() => document.querySelector('[data-testid="playback-bar"]')?.getAttribute("data-mode") === "playback", null, { timeout: 90000 });
      const slider = pop.getByTestId("playback-time");
      const T = Number(await slider.getAttribute("max"));
      await slider.fill(sv(Math.min(T, seg.seconds) * 0.9));
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
      for (let z = 0; z < ZOOM; z++) { await pop.mouse.wheel(0, -WHEEL); await sleep(120); }
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
          canvas.screenshot({ type: "jpeg", quality: 92, path: path.join(frames, "v", `${String(k).padStart(5, "0")}.jpg`) }),
          page.screenshot({ type: "jpeg", quality: 92, path: path.join(frames, "d", `${String(k).padStart(5, "0")}.jpg`) }),
        ]);
      }
      for (const [tag, tt] of [["mid", seg.seconds * 0.5], ["end", seg.seconds]]) {
        await slider.fill(sv(Math.min(T, tt)));
        await Promise.all([raf(pop), raf(page)]);
        await canvas.screenshot({ path: path.join(out, `${seg.id}-3d-${tag}.png`) });
        await page.screenshot({ path: path.join(out, `${seg.id}-dashboard-${tag}.png`) });
      }
      console.log("segment", seg.id, `T=${T} frames=${N}`);
      await page.context().close();
    }
    if (STILLS) return null;
    writeFileSync(path.join(out, "marks.json"), JSON.stringify({ fps: FPS, marks }, null, 2));
    return marks;
  } finally {
    await fetch(`${BASE}/api/projects/${project}`, { method: "DELETE" }).catch(() => {});
    await browser.close();
  }
}

// compose: dashboard | 3D, a caption bar with the simulation time, constant FPS
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
      `drawtext=fontfile='${font}':text='${esc(m.caption)}':fontcolor=white:fontsize=22:x=24:y=h-43,` +
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
  const r = spawnSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", list, "-c", "copy", path.join(out, "actilink.mp4")], { stdio: "inherit" });
  if (r.status !== 0) throw new Error("ffmpeg concat failed");
  console.log("wrote", path.join(out, "actilink.mp4"));
}
