#!/usr/bin/env node
// The fanuc-pick showcase video (1280x720) and screenshots: Playwright records the real app with the real
// Julia worker. The optimum pick and place of a carton, the loose ball and the loose bottle (semi-transparent
// carton), and a pick that is too fast for the gripper. Each scene plays the 3D view back at reduced speed with
// a caption; the runs and model switches between the scenes are cut out.
//
// usage (backend with the real worker on BGSIM_VIDEO_URL, see README.md):
//   node tools/video/capture-fanuc.mjs <out.mp4> [--shots <dir>] [--theme dark|light]
// --shots writes a 3D-view and a dashboard screenshot (1600x1000) of every scene into <dir>.
import { mkdirSync, readdirSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import os from "node:os";
import path from "node:path";
import { launchBrowser, createProject, openModel, runAndWait, sleep, BASE } from "./lib.mjs";

const arg = (name, dflt) => (process.argv.includes(name) ? process.argv[process.argv.indexOf(name) + 1] : dflt);
const out = path.resolve(process.argv[2] ?? "fanuc-pick.mp4");
const theme = arg("--theme", "dark");
const shots = arg("--shots", null);
if (shots) mkdirSync(shots, { recursive: true });
const work = path.join(os.tmpdir(), `bgsim-fanuc-video-${Date.now().toString(36)}`);
mkdirSync(work, { recursive: true });

// scene list: model, caption, sub caption, playback window [from, to] in s, speed
const SCENES = JSON.parse(arg("--scenes", "null")) ?? [
  ["pick-place-best", "FANUC LR-10iA/10 with a five-zone suction gripper: the fastest safe pick",
    "Cylinders extend the cups, one ejector per zone. Cups: blue = low load, red = U at 1. Optimised trajectory.", null, "0.25"],
  ["loose-sphere-best", "A loose 0.5 kg ball in the carton (carton drawn see-through)",
    "The ball rolls against the walls; the trajectory is the fastest that keeps a holding margin of 0.3.", null, "0.25"],
  ["loose-cylinder-best", "A loose 0.5 kg bottle lying in the carton",
    "It slides and tips against the walls during the transfer.", null, "0.25"],
  ["too-aggressive", "Too fast for the gripper",
    "The cups peel off one after the other and the carton drops.", null, "0.25"],
];

const layout = ([th, main]) => {
  try {
    localStorage.setItem("bgsim.layout.rows", JSON.stringify({ main, dock: 100 - main }));
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
      el.style.cssText = "position:fixed;left:84px;bottom:52px;z-index:99999;max-width:700px;padding:10px 16px;" +
        "border-radius:8px;background:rgba(15,17,22,0.86);color:#fff;font:600 19px/1.3 'Segoe UI',sans-serif;" +
        "border-left:4px solid #f5a623;box-shadow:0 4px 18px rgba(0,0,0,0.35)";
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

async function play(page, from, to, speed) {
  const slider = page.getByTestId("playback-time");
  await page.getByTestId("playback-speed").selectOption(speed);
  await slider.fill(String(+Number(from).toFixed(3)));
  await sleep(300);
  await page.getByTestId("playback-toggle").click();
  await page.waitForFunction((t) => Number(document.querySelector('[data-testid="playback-time"]')?.value) >= t, to,
    { timeout: 180000, polling: 50 });
  await page.getByTestId("playback-toggle").click();
}

const segments = [];
let t0 = 0;
let segStart = null;
const MARGIN = 0.3;
const keep = () => { segStart = (Date.now() - t0) / 1000 + MARGIN; };
const cut = () => {
  if (segStart !== null) segments.push([segStart, (Date.now() - t0) / 1000 - MARGIN]);
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
// zoomed in further, at 55 % of the playback window
async function stills() {
  for (const [model, , , win] of SCENES) {
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
        const [from, to] = win ?? [0, tEnd - 0.05];
        await frameView(p, 6);
        await p.getByTestId("playback-time").fill(String(+(from + 0.55 * (to - from)).toFixed(3)));
        await sleep(1500);
        await p.getByTestId("viewer-canvas").screenshot({ path: path.join(shots, `${model}-3d.png`) });
      }
      await c.close();
      console.log("still", model, kind);
    }
  }
}

const browser = await launchBrowser();
const project = await createProject("fanuc-pick", "fpvid");
try {
  // warm-up (not recorded): compile every model once
  for (const [model] of SCENES) {
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
  for (const [model, title, sub, win, speed] of SCENES) {
    cut();
    await openModel(page, project, model);
    await runNow(page);
    await page.getByRole("tab", { name: "3D View" }).click();
    await page.waitForFunction(() => document.querySelector('[data-testid="scene-view"]')?.getAttribute("data-state") === "loaded", null, { timeout: 90000 });
    await sleep(1000);
    const tEnd = Number(await page.getByTestId("playback-time").getAttribute("max"));
    const [from, to] = win ?? [0, tEnd - 0.05];
    await page.getByTestId("playback-time").fill(String(+Number(from).toFixed(3)));
    await frameView(page);
    await page.addStyleTag({ content: '[data-testid^="viewer-preset"], [data-testid="viewer-fit"], [data-testid="viewer-ortho"] { visibility: hidden !important; }' });
    await caption(page, title, sub);
    keep();
    await sleep(1200);
    await play(page, from, to, speed);
    await sleep(800);
    cut();
    await page.evaluate(() => document.getElementById("vid-caption")?.remove());
  }
  await ctx.close();
  if (shots) await stills();

  const webm = readdirSync(work).find((f) => f.endsWith(".webm"));
  const src = path.join(work, webm);
  writeFileSync(path.join(work, "marks.json"), JSON.stringify({ segments }));
  const total = segments.reduce((s, [a, b]) => s + b - a, 0);
  const ff = spawnSync("ffmpeg", ["-version"]);
  if (ff.status === 0 && out.endsWith(".mp4")) {
    const parts = segments.map(([a, b], i) => `[0:v]trim=start=${a.toFixed(3)}:end=${b.toFixed(3)},setpts=PTS-STARTPTS[s${i}]`);
    const filter = `${parts.join(";")};${segments.map((_, i) => `[s${i}]`).join("")}concat=n=${segments.length}:v=1:a=0[v]`;
    const r = spawnSync("ffmpeg", ["-y", "-i", src, "-filter_complex", filter, "-map", "[v]",
      "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23", "-preset", "slow", "-r", "25", "-an", out], { stdio: "inherit" });
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
