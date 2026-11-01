#!/usr/bin/env node
// The quad-pendulum video: the dashboard and the detached 3D viewer of the quadruple inverted pendulum,
// in real time: the cart swing-up and balance (quad-pendulum-swingup), the rotary-arm version
// (quad-rotary-swingup or quad-rotary-balance) and the cart balance with a tip push and 3 ms of actuator
// delay set on the dashboard. `--set travel` records the two cart controllers instead: the cart swing-up with
// the full-travel controller, the switch of the dashboard's Controller select (highlighted) and the swing-up
// with the short-travel controller (+-0.5 m limit lines on the cart plot and in the scene)
// (quad-pendulum-short-travel.mp4).
//
// Same scheme as capture-vdp-belt.mjs: every run happens off camera (auto re-run switched off), then the
// playback slider of the detached viewer is stepped in real time (t_k = k / FPS) and the dashboard (main
// window) and the 3D canvas (pop-out) are screenshotted. compose: ffmpeg hstack, caption bar with the
// simulation time, H.264.
//
// usage: node tools/video/capture-quad-pendulum.mjs <out-dir> [--set main|travel] [--fps 30] [--max-frames n]
//          [--only id,id] [--stills] [--compose-only]
//   BGSIM_VIDEO_URL=http://127.0.0.1:<port> (a private backend, see README.md)
import { mkdirSync, readFileSync, writeFileSync, rmSync, existsSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { launchBrowser, createProject, newPage, openModel, runAndWait, sleep, BASE } from "./lib.mjs";

const out = path.resolve(process.argv[2] ?? "quad-pendulum-video");
const arg = (n) => { const i = process.argv.indexOf(n); return i > 0 ? process.argv[i + 1] : null; };
const FPS = Number(arg("--fps") ?? 30);
const maxFrames = Number(arg("--max-frames") ?? 0);
const ONLY = arg("--only")?.split(",") ?? null;
const STILLS = process.argv.includes("--stills");
const SET = arg("--set") ?? "main";
const VIDEO = SET === "travel" ? "quad-pendulum-short-travel.mp4" : "quad-pendulum.mp4";
const W = 1920, H = 1080, LEFT = 1000;            // dashboard 1000 px wide, 3D 920 px
mkdirSync(out, { recursive: true });

// view: an orbit drag (px) and wheel notches after the fit, per segment. A segment runs its model once per
// phase (on the same page); a phase may first set dashboard selects, shown as a short highlighted switch.
const MAIN = [
  { id: "cart", model: "quad-pendulum-swingup", seconds: 10, orbit: [0, -40], zoom: 2, inputs: {},
    caption: "Cart: a precomputed swing-up tracked by a time-varying LQR, then the 1 kHz LQR balances all four links" },
  { id: "rotary", model: process.env.QP_ROTARY_MODEL ?? "quad-rotary-swingup", seconds: 10, orbit: [80, -30], zoom: 1, inputs: {},
    caption: "Rotary arm (Furuta): the same method with a torque on the arm; the links swing perpendicular to the arm" },
  { id: "push", model: "quad-pendulum-balance", seconds: 7, orbit: [0, -40], zoom: 2, inputs: { "in_delay": "3" },
    caption: "Cart, balance only: start leaning 2 deg, 3 ms actuator delay, a tip push at 3 s; the LQR recovers" },
];
const TRAVEL = [
  { id: "cart", model: "quad-pendulum-swingup", seconds: 10, orbit: [0, -40], zoom: 1, inputs: {},
    phases: [
      { caption: "Cart, full-travel controller: the swing-up uses up to 0.58 m of the +-1.5 m rail" },
      { selects: { controller: "1" }, caption: "Cart, short-travel controller: same plant, swing-up planned and tuned to stay within +-0.5 m (green lines)" },
    ] },
];
const ALL = SET === "travel" ? TRAVEL : MAIN;
const segments = ALL.filter((s) => !ONLY || ONLY.includes(s.id));

const raf = (pg) => pg.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
const sv = (x) => String(Number((Math.round(x / 0.001) * 0.001).toFixed(3)));

const marks = process.argv.includes("--compose-only")
  ? JSON.parse(readFileSync(path.join(out, "marks.json"), "utf8")).marks
  : await capture();
if (marks) compose(marks);

async function capture() {
  const browser = await launchBrowser();
  const project = await createProject("quad-pendulum", "quad");
  const frames = path.join(out, "frames");
  if (!STILLS) {
    rmSync(frames, { recursive: true, force: true });
    mkdirSync(path.join(frames, "d"), { recursive: true });
    mkdirSync(path.join(frames, "v"), { recursive: true });
  }
  const marks = [];
  let k = 0;
  try {
    for (const seg of segments) {
      const page = await newPage(browser, { viewport: { width: LEFT, height: H } });
      await page.addInitScript(() => { try { localStorage.setItem("bgsim.layout.rows", JSON.stringify({ main: 100, dock: 0 })); } catch {} });
      await openModel(page, project, seg.model);
      await page.getByRole("tab", { name: "Dashboard" }).click();
      await page.getByTestId("dashboard").waitFor();
      const auto = page.getByTestId("dash-auto-rerun");
      if (await auto.isChecked()) await auto.uncheck();
      for (const [cid, v] of Object.entries(seg.inputs)) {
        await page.getByTestId(`dash-slider-${cid}`).fill(String(v));
        await sleep(300);
      }
      for (const [cid, v] of Object.entries(seg.selects ?? {})) {
        await page.getByTestId(`dash-select-${cid}`).selectOption(String(v));
        await sleep(300);
      }
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
      // setting a slider scrolls it into view: back to the top (indicators and readouts)
      await page.getByTestId("dashboard").evaluate((el) => { for (let p = el; p; p = p.parentElement) p.scrollTop = 0; });
      await sleep(500);
      const canvas = pop.getByTestId("viewer-canvas");
      const phases = seg.phases ?? [{ caption: seg.caption }];
      for (let ph = 0; ph < phases.length; ph++) {
        const phase = phases[ph];
        const tag = phases.length > 1 ? `${seg.id}${ph}` : seg.id;
        if (phase.selects) {
          // the switch on the dashboard: highlighted, held 0.8 s before and 1.2 s after (3D at the end pose)
          const sel = Object.keys(phase.selects).map((cid) => `[data-testid="dash-select-${cid}"]`).join(", ");
          const hl = await page.addStyleTag({ content: `${sel} { outline: 3px solid #ffc04d !important; outline-offset: 2px; }` });
          await page.getByTestId("dashboard").evaluate((el) => { for (let p = el; p; p = p.parentElement) p.scrollTop = 0; });
          const hold = async (n) => {
            for (let i = 0; i < n; i++, k++) {
              await Promise.all([raf(pop), raf(page)]);
              await Promise.all([
                canvas.screenshot({ type: "jpeg", quality: 92, path: path.join(frames, "v", `${String(k).padStart(5, "0")}.jpg`) }),
                page.screenshot({ type: "jpeg", quality: 92, path: path.join(frames, "d", `${String(k).padStart(5, "0")}.jpg`) }),
              ]);
            }
          };
          const n1 = STILLS ? 0 : Math.round(0.8 * FPS), n2 = STILLS ? 0 : Math.round(1.2 * FPS);
          const from = k;
          await hold(n1);
          for (const [cid, v] of Object.entries(phase.selects)) await page.getByTestId(`dash-select-${cid}`).selectOption(String(v));
          await sleep(300);
          await hold(n2);
          if (STILLS) await page.screenshot({ path: path.join(out, `${tag}-switch.png`) });
          marks.push({ id: `${tag}-switch`, from, frames: n1 + n2, T: 0, caption: "Dashboard: Controller select switched to the short-travel controller (no recompile)", still: true });
          await hl.evaluate((el) => el.remove());
        }
        const started = Date.now();
        const prev = await page.getByTestId("run-status").getAttribute("data-status").catch(() => null);
        await page.getByTestId("run-button").click();
        if (prev === "done") {
          await page.waitForFunction(() => document.querySelector('[data-testid="run-status"]')?.getAttribute("data-status") !== "done", null, { timeout: 60000, polling: 100 }).catch(() => {});
        }
        await page.waitForFunction(() => document.querySelector('[data-testid="run-status"]')?.getAttribute("data-status") === "done", null, { timeout: 1800000, polling: 500 });
        console.log("run", seg.model, tag, `${((Date.now() - started) / 1000).toFixed(1)} s`);
        await page.getByTestId("dashboard").evaluate((el) => { for (let p = el; p; p = p.parentElement) p.scrollTop = 0; });
        await pop.waitForFunction(() => document.querySelector('[data-testid="playback-bar"]')?.getAttribute("data-mode") === "playback", null, { timeout: 90000 });
        const slider = pop.getByTestId("playback-time");
        const T = Number(await slider.getAttribute("max"));
        if (ph === 0) {
          // frame the rig: fit at the end of the run (upright), orbit, zoom
          await slider.fill(sv(T));
          await pop.getByTestId("viewer-fit").dispatchEvent("click");
          await sleep(700);
          const cb = await canvas.boundingBox();
          const cx = cb.x + cb.width / 2, cy = cb.y + cb.height / 2;
          const [ox, oy] = seg.orbit;
          if (ox || oy) {
            await pop.mouse.move(cx, cy);
            await pop.mouse.down(); await pop.mouse.move(cx + ox, cy + oy, { steps: 12 }); await pop.mouse.up();
            await sleep(300);
          }
          await pop.mouse.move(cx, cy);
          for (let z = 0; z < seg.zoom; z++) { await pop.mouse.wheel(0, -120); await sleep(120); }
          await pop.mouse.move(cb.x + cb.width - 2, cb.y + 2);
          await sleep(600);
          await canvas.screenshot({ path: path.join(out, `${seg.id}-camera.png`) });
        }
        const N0 = Math.round(Math.min(seg.seconds, T) * FPS);
        const N = STILLS ? 0 : maxFrames ? Math.min(N0, maxFrames) : N0;
        marks.push({ id: tag, from: k, frames: N, T, caption: phase.caption });
        for (let i = 0; i < N; i++, k++) {
          await slider.fill(sv(i / FPS));
          await Promise.all([raf(pop), raf(page)]);
          await Promise.all([
            canvas.screenshot({ type: "jpeg", quality: 92, path: path.join(frames, "v", `${String(k).padStart(5, "0")}.jpg`) }),
            page.screenshot({ type: "jpeg", quality: 92, path: path.join(frames, "d", `${String(k).padStart(5, "0")}.jpg`) }),
          ]);
        }
        for (const [st, ts] of [["mid", Math.min(T, seg.seconds) * 0.45], ["end", Math.min(T, seg.seconds)]]) {
          await slider.fill(sv(ts));
          await Promise.all([raf(pop), raf(page)]);
          await canvas.screenshot({ path: path.join(out, `${tag}-3d-${st}.png`) });
          await page.screenshot({ path: path.join(out, `${tag}-dashboard-${st}.png`) });
        }
        // leave the 3D view at the end pose (the switch frames of the next phase show it)
        await slider.fill(sv(T));
        await Promise.all([raf(pop), raf(page)]);
      }
      console.log("segment", seg.id);
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

function compose(marks) {
  const frames = path.join(out, "frames");
  const font = "C\\:/Windows/Fonts/segoeui.ttf";
  const esc = (t) => t.replace(/\\/g, "\\\\").replace(/:/g, "\\:").replace(/'/g, "\u2019").replace(/,/g, "\\,");
  const clock = "t = %{eif\\:trunc(t)\\:d}.%{eif\\:mod(trunc(t*100)\\,100)\\:d\\:2} s";
  const parts = [];
  for (const m of marks) {
    if (!m.frames) continue;
    const seg = path.join(out, `seg-${m.id}.mp4`);
    const clk = m.still ? "" : `,drawtext=fontfile='${font}':text='${clock}':fontcolor=0xffc04d:fontsize=26:x=w-tw-24:y=h-45`;
    const R = W - LEFT;
    const vf = `[0:v]scale=${LEFT}:${H}[d];[1:v]scale=${R}:${H}:force_original_aspect_ratio=decrease,` +
      `pad=${R}:${H}:(ow-iw)/2:(oh-ih)/2:color=0x16181d[v];[d][v]hstack=inputs=2,` +
      `drawbox=x=0:y=ih-64:w=iw:h=64:color=black@0.72:t=fill,` +
      `drawtext=fontfile='${font}':text='${esc(m.caption)}':fontcolor=white:fontsize=24:x=24:y=h-44` + clk;
    const r = spawnSync("ffmpeg", ["-y", "-loglevel", "error", "-framerate", String(FPS), "-start_number", String(m.from), "-i", path.join(frames, "d", "%05d.jpg"),
      "-framerate", String(FPS), "-start_number", String(m.from), "-i", path.join(frames, "v", "%05d.jpg"),
      "-frames:v", String(m.frames), "-filter_complex", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "22", "-preset", "slow", "-r", String(FPS), seg],
      { stdio: "inherit" });
    if (r.status !== 0) throw new Error(`ffmpeg failed for ${m.id}`);
    parts.push(seg);
  }
  const list = path.join(out, "parts.txt");
  writeFileSync(list, parts.map((p) => `file '${p.replace(/\\/g, "/")}'`).join("\n") + "\n");
  const r = spawnSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", list, "-c", "copy", path.join(out, VIDEO)], { stdio: "inherit" });
  if (r.status !== 0) throw new Error("ffmpeg concat failed");
  console.log("wrote", path.join(out, VIDEO));
}
