#!/usr/bin/env node
// The fanuc-pick showcase video (1280x720) and screenshots: Playwright records the real app with the real
// Julia worker. Every pick is shown at 1x (real time, labelled "1x real time"); slow-motion repeats are
// labelled with their factor. Side-by-side scenes put the old optimum (best of the four fixed trajectory
// families) next to the free optimum (family 5: free timing, waiter's tilt, yaw spreading, overlapped
// vacuum timing) of the same load, both at 1x and started together; the faster one finishes first. The runs
// and model switches between the scenes are cut out.
//
// usage (backend with the real worker on BGSIM_VIDEO_URL, see README.md):
//   node tools/video/capture-fanuc.mjs <out.mp4> [--shots <dir>] [--theme dark|light]
// --shots writes a 3D-view and a dashboard screenshot (1600x1000) of every model shown into <dir>.
import { mkdirSync, readdirSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import os from "node:os";
import path from "node:path";
import { launchBrowser, createProject, openModel, runAndWait, sleep, BASE } from "./lib.mjs";

const arg = (name, dflt) => (process.argv.includes(name) ? process.argv[process.argv.indexOf(name) + 1] : dflt);
const out = path.resolve(process.argv[2] ?? "fanuc-pick-v2.mp4");
const theme = arg("--theme", "dark");
const shots = arg("--shots", null);
if (shots) mkdirSync(shots, { recursive: true });
const work = path.join(os.tmpdir(), `bgsim-fanuc-video-${Date.now().toString(36)}`);
mkdirSync(work, { recursive: true });

// Scenes: {model, title, sub, speed, pair}. `pair: "L"|"R"` scenes are recorded one after the other and
// composed side by side (the centre 640 px of each, the shorter one held on its last frame).
const SCENES = JSON.parse(arg("--scenes", "null")) ?? [
  { model: "pick-place-opt", speed: "1", title: "FANUC LR-10iA/10, five-zone suction gripper: the fastest safe pick",
    sub: "Free timing, waiter's tilt and spread yaw (family 5). Cups: blue = low load, red = U at 1." },
  { model: "pick-place-opt", speed: "0.25", title: "The same pick in slow motion",
    sub: "The tool tilts into the acceleration so the cups pull along their axes; level again at the place." },
  { model: "pick-place-best", speed: "1", pair: "L", title: "Best fixed family, tool level", sub: "" },
  { model: "pick-place-tilt-best", speed: "1", pair: "R", title: "Same families with the waiter's tilt", sub: "" },
  { model: "pick-place-best", speed: "1", pair: "L", title: "Before: best fixed family", sub: "" },
  { model: "pick-place-opt", speed: "1", pair: "R", title: "After: free optimum", sub: "" },
  { model: "loose-sphere-opt", speed: "1", title: "A loose 0.5 kg ball in the carton (drawn see-through)",
    sub: "The free optimum for the ball; the ball rolls against the walls." },
  { model: "loose-sphere-best", speed: "1", pair: "L", title: "Before: best fixed family", sub: "" },
  { model: "loose-sphere-opt", speed: "1", pair: "R", title: "After: free optimum", sub: "" },
  { model: "loose-cylinder-opt", speed: "1", title: "A loose 0.5 kg bottle lying in the carton",
    sub: "The free optimum for the bottle; it slides and tips against the walls." },
  { model: "too-aggressive", speed: "1", title: "Too fast for the gripper",
    sub: "The robot can drive it, the cups cannot: they peel and the carton drops." },
  { model: "too-aggressive", speed: "0.25", title: "The drop in slow motion", sub: "" },
];

const speedLabel = (s) => (Number(s) === 1 ? "1x real time" : `slow motion ${s}x`);

const layout = ([th, main]) => {
  try {
    localStorage.setItem("bgsim.layout.rows", JSON.stringify({ main, dock: 100 - main }));
    localStorage.setItem("bgsim.layout.columns", JSON.stringify({ library: 4, center: 92, inspector: 4 }));
    localStorage.setItem("bgsim.theme", th);
  } catch {}
};

// caption (bottom left; for a side-by-side half inside its centre 640 px) and the speed badge (top)
async function caption(page, title, sub, speed, half) {
  await page.evaluate(([t, s, badge, h]) => {
    for (const id of ["vid-caption", "vid-badge"]) document.getElementById(id)?.remove();
    const el = document.createElement("div");
    el.id = "vid-caption";
    el.style.cssText = `position:fixed;left:${h ? 336 : 84}px;bottom:52px;z-index:99999;max-width:${h ? 600 : 700}px;` +
      "padding:10px 16px;border-radius:8px;background:rgba(15,17,22,0.86);color:#fff;" +
      "font:600 19px/1.3 'Segoe UI',sans-serif;border-left:4px solid #f5a623;box-shadow:0 4px 18px rgba(0,0,0,0.35)";
    const a = document.createElement("div");
    a.textContent = t;
    el.appendChild(a);
    if (s) {
      const b = document.createElement("div");
      b.textContent = s;
      b.style.cssText = "font-weight:400;font-size:15px;color:#d8dbe2;margin-top:3px";
      el.appendChild(b);
    }
    document.body.appendChild(el);
    const bd = document.createElement("div");
    bd.id = "vid-badge";
    const rt = badge.startsWith("1x");
    bd.style.cssText = `position:fixed;left:${h ? 336 : 84}px;top:64px;z-index:99999;padding:5px 12px;border-radius:6px;` +
      `font:700 17px/1.2 'Segoe UI',sans-serif;color:#10131a;background:${rt ? "#5fd38d" : "#f5a623"}`;
    bd.textContent = badge;
    document.body.appendChild(bd);
  }, [title, sub, speedLabel(speed), !!half]);
}

async function play(page, from, to, speed) {
  const slider = page.getByTestId("playback-time");
  await page.getByTestId("playback-speed").selectOption(speed);
  await slider.fill(String(+Number(from).toFixed(3)));
  await sleep(300);
  await page.getByTestId("playback-toggle").click();
  await page.waitForFunction((t) => Number(document.querySelector('[data-testid="playback-time"]')?.value) >= t, to,
    { timeout: 180000, polling: 20 });
  await page.getByTestId("playback-toggle").click();
}

const segments = [];
let t0 = 0;
let segStart = null;
const keep = () => { segStart = (Date.now() - t0) / 1000; };
const cut = (meta) => {
  if (segStart !== null) segments.push({ a: segStart, b: (Date.now() - t0) / 1000, ...meta });
  segStart = null;
};

async function runNow(page) {
  await page.getByTestId("run-button").click();
  await page.waitForFunction(() => document.querySelector('[data-testid="run-status"]')?.getAttribute("data-status") === "done",
    null, { timeout: 1200000, polling: 200 });
  await page.waitForFunction(() => {
    const bar = document.querySelector('[data-testid="playback-bar"]');
    return bar === null || bar.getAttribute("data-mode") === "playback";
  }, null, { timeout: 90000 });
  await sleep(600);
}

async function frameView(page, steps = 4) {
  const tree = page.getByTestId("scene-tree-toggle");
  if (await tree.count()) { const exp = await tree.getAttribute("aria-expanded"); if (exp !== "false") await tree.click().catch(() => {}); }
  await page.getByTestId("viewer-fit").click();
  await sleep(400);
  await page.getByTestId("viewer-preset-iso").dispatchEvent("click").catch(() => {});
  await sleep(400);
  const cb = await page.getByTestId("viewer-canvas").boundingBox();
  const cx = cb.x + cb.width / 2, cy = cb.y + cb.height / 2;
  await page.mouse.move(cx + cb.width * 0.08, cy + cb.height * 0.05);
  for (let z = 0; z < steps; z++) { await page.mouse.wheel(0, -300); await sleep(100); }
  await sleep(400);
}

// stills (not recorded, 1600x1000): the dashboard with a tall main area, and the 3D view with a tall dock,
// zoomed in further, at 55 % of the run
async function stills() {
  const models = [...new Set(SCENES.map((s) => s.model))];
  for (const model of models) {
    for (const kind of ["dashboard", "3d"]) {
      const c = await browser.newContext({ viewport: { width: 1600, height: 1000 }, colorScheme: theme });
      const p = await c.newPage();
      await p.addInitScript(layout, [theme, kind === "dashboard" ? 78 : 22]);
      await openModel(p, project, model);
      await runNow(p);
      if (kind === "dashboard") {
        await p.getByRole("tab", { name: "Dashboard" }).click();
        await sleep(2000);
        await p.screenshot({ path: path.join(shots, `${model}-dashboard.png`) });
      } else {
        await p.getByRole("tab", { name: "3D View" }).click();
        await p.waitForFunction(() => document.querySelector('[data-testid="scene-view"]')?.getAttribute("data-state") === "loaded", null, { timeout: 90000 });
        await sleep(1000);
        const tEnd = Number(await p.getByTestId("playback-time").getAttribute("max"));
        await frameView(p, 6);
        await p.getByTestId("playback-time").fill(String(+(0.55 * tEnd).toFixed(3)));
        await sleep(1500);
        await p.getByTestId("viewer-canvas").screenshot({ path: path.join(shots, `${model}-3d.png`) });
      }
      await c.close();
      console.log("still", model, kind);
    }
  }
}

function compose(src) {
  // group the side-by-side pairs: an L segment and the R segment after it
  const items = [];
  for (let i = 0; i < segments.length; i++) {
    const s = segments[i];
    if (s.pair === "L" && segments[i + 1]?.pair === "R") { items.push([s, segments[i + 1]]); i++; } else items.push([s]);
  }
  const parts = [];
  const labels = [];
  items.forEach((it, k) => {
    if (it.length === 1) {
      parts.push(`[0:v]trim=start=${it[0].a.toFixed(3)}:end=${it[0].b.toFixed(3)},setpts=PTS-STARTPTS[v${k}]`);
    } else {
      const [L, R] = it;
      const dl = L.b - L.a, dr = R.b - R.a, d = Math.max(dl, dr);
      for (const [s, tag, dd] of [[L, "l", dl], [R, "r", dr]]) {
        parts.push(`[0:v]trim=start=${s.a.toFixed(3)}:end=${s.b.toFixed(3)},setpts=PTS-STARTPTS,crop=640:720:320:0,` +
          `tpad=stop_mode=clone:stop_duration=${(d - dd + 0.04).toFixed(3)}[${tag}${k}]`);
      }
      parts.push(`[l${k}][r${k}]hstack=inputs=2,trim=duration=${d.toFixed(3)}[v${k}]`);
    }
    labels.push(`[v${k}]`);
  });
  const filter = `${parts.join(";")};${labels.join("")}concat=n=${labels.length}:v=1:a=0[v]`;
  const r = spawnSync("ffmpeg", ["-y", "-i", src, "-filter_complex", filter, "-map", "[v]",
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "24", "-preset", "slow", "-r", "25", "-an", out], { stdio: "inherit" });
  if (r.status !== 0) throw new Error("ffmpeg failed");
}

const browser = await launchBrowser();
const project = await createProject("fanuc-pick", "fpvid");
try {
  // warm-up (not recorded): compile every model once
  for (const model of new Set(SCENES.map((s) => s.model))) {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 } });
    const page = await ctx.newPage();
    await openModel(page, project, model);
    await runAndWait(page, 1800000);
    await ctx.close();
    console.log("warm", model);
  }
  const ctx = await browser.newContext({
    viewport: { width: 1280, height: 720 }, colorScheme: theme,
    recordVideo: { dir: work, size: { width: 1280, height: 720 } },
  });
  const page = await ctx.newPage();
  t0 = Date.now();
  await page.addInitScript(layout, [theme, 30]);
  let current = null;
  for (const sc of SCENES) {
    if (sc.model !== current) {
      await openModel(page, project, sc.model);
      await runNow(page);
      await page.getByRole("tab", { name: "3D View" }).click();
      await page.waitForFunction(() => document.querySelector('[data-testid="scene-view"]')?.getAttribute("data-state") === "loaded", null, { timeout: 90000 });
      await sleep(1000);
      await frameView(page);
      await page.addStyleTag({ content: '[data-testid^="viewer-preset"], [data-testid="viewer-fit"], [data-testid="viewer-ortho"] { visibility: hidden !important; }' });
      current = sc.model;
    }
    const tEnd = Number(await page.getByTestId("playback-time").getAttribute("max"));
    await page.getByTestId("playback-speed").selectOption(sc.speed);
    await page.getByTestId("playback-time").fill("0");
    await caption(page, sc.title, sc.sub, sc.speed, !!sc.pair);
    await sleep(500);
    // a side-by-side half starts at the first frame (both halves start together); the others get a lead-in
    keep();
    if (!sc.pair) await sleep(1000);
    else segStart += 0.1;
    await play(page, 0, tEnd - 0.01, sc.speed);
    await sleep(sc.pair ? 300 : 800);
    cut({ pair: sc.pair ?? null, model: sc.model, speed: sc.speed });
    await page.evaluate(() => { for (const id of ["vid-caption", "vid-badge"]) document.getElementById(id)?.remove(); });
  }
  await ctx.close();
  if (shots) await stills();

  const webm = readdirSync(work).find((f) => f.endsWith(".webm"));
  const src = path.join(work, webm);
  writeFileSync(path.join(path.dirname(out), "fanuc-pick-v2-marks.json"), JSON.stringify({ segments }, null, 1));
  const ff = spawnSync("ffmpeg", ["-version"]);
  if (ff.status === 0 && out.endsWith(".mp4")) compose(src);
  else renameSync(src, out.replace(/\.mp4$/, ".webm"));
  console.log("video", out, `(${segments.length} segments)`);
} catch (e) {
  console.error("FAILED", e);
  process.exitCode = 1;
} finally {
  await fetch(`${BASE}/api/projects/${project}`, { method: "DELETE" }).catch(() => {});
  await browser.close();
  try { rmSync(work, { recursive: true, force: true }); } catch {}
}
