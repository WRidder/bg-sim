#!/usr/bin/env node
// Video 2 at 60 fps: intro cards (from compose-examples.mjs --no-encode) + the sim60 frame sequences laid out as
// model | plots | 3D view with ffmpeg, then concatenated into media/video/bg-sim-examples.mp4.
// usage: node compose-sim60.mjs [--only a,b] [--crf 19]
import { existsSync, readFileSync, writeFileSync, mkdirSync, statSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { chromium, framesDir, repoRoot } from "./lib.mjs";
import { writeHtml, fileUrl, esc } from "./theme.mjs";

const arg = (n) => { const i = process.argv.indexOf(n); return i > 0 ? process.argv[i + 1] : null; };
const only = arg("--only")?.split(",") ?? null;
const crf = arg("--crf") ?? "19";
const cards = JSON.parse(readFileSync(new URL("./cards.json", import.meta.url), "utf8"));
const out2 = path.join(framesDir, "out2");
const clips = path.join(framesDir, "clips60");
mkdirSync(clips, { recursive: true });

function ffmpegBin() {
  if (spawnSync("ffmpeg", ["-version"], { stdio: "ignore" }).status === 0) return "ffmpeg";
  const r = spawnSync("uv", ["run", "--with", "imageio-ffmpeg", "python", "-c", "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"], { cwd: repoRoot, encoding: "utf8" });
  return r.stdout.trim().split(/\r?\n/).pop();
}
const FF = ffmpegBin();
const run = (args) => { const r = spawnSync(FF, args, { stdio: ["ignore", "ignore", "pipe"], encoding: "utf8" }); if (r.status !== 0) throw new Error(r.stderr.slice(-800)); };
const ENC = ["-c:v", "libx264", "-preset", "medium", "-crf", crf, "-pix_fmt", "yuv420p", "-r", "60", "-movflags", "+faststart"];
const still = (png, seconds, out) => run(["-y", "-loop", "1", "-framerate", "60", "-t", String(seconds), "-i", png, "-vf", "scale=1920:1080,format=yuv420p", ...ENC, out]);

const PANEL = `
.hdr{position:absolute;left:0;top:0;right:0;height:84px;padding:0 40px;display:flex;align-items:center;background:#0a0e14;border-bottom:2px solid #1f2733}
.hdr .l{display:flex;align-items:baseline;gap:22px}
.hdr .n{font-size:24px;letter-spacing:3px;color:#f5a524;font-weight:600}
.hdr .t{font-size:40px;font-weight:700}
.pn{position:absolute;background:#10161e;border:2px solid #232d3a;border-radius:10px;overflow:hidden}
.pn .lab{position:absolute;left:14px;top:10px;font-size:20px;letter-spacing:2px;color:#f5a524;text-transform:uppercase;font-weight:600;background:rgba(10,14,20,.8);padding:2px 10px;border-radius:6px;z-index:2}
`;
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
async function sizes(files) {
  const html = files.map((f) => `<img src="${fileUrl(f)}">`).join("");
  const url = writeHtml("sizes", html);
  await page.goto(url);
  await page.waitForFunction(() => [...document.images].every((i) => i.complete));
  return page.evaluate(() => [...document.images].map((i) => [i.naturalWidth, i.naturalHeight]));
}
async function bgPng(card, idx, total, name, lay) {
  const body = `<div style="position:relative;width:1920px;height:1080px;background:#0d1117">
  <div class="hdr"><div class="l"><span class="n">${String(idx + 1).padStart(2, "0")} / ${total}</span><span class="t">${esc(card.title)}</span></div></div>
  <div class="pn" style="left:20px;top:104px;width:1060px;height:${lay.dh}px"><span class="lab">Model</span></div>
  <div class="pn" style="left:20px;top:${104 + lay.dh + 16}px;width:1060px;height:${lay.ph}px;border-color:#2b3646"></div>
  <div class="pn" style="left:1100px;top:104px;width:800px;height:956px"><span class="lab">3D view</span></div></div>`;
  const url = writeHtml("bg-" + name, body, PANEL);
  await page.goto(url);
  await page.evaluate(() => document.fonts.ready);
  const png = path.join(clips, `bg-${name}.png`);
  await page.screenshot({ path: png });
  return png;
}

const total = cards.length;
const list = [];
const add = (f) => list.push(f);
const title = path.join(clips, "00-title.mp4"); still(path.join(out2, "00-title.png"), 4, title); add(title);
for (let idx = 0; idx < cards.length; idx++) {
  const c = cards[idx];
  if (only && !only.includes(c.id)) continue;
  const num = String(idx + 1).padStart(2, "0");
  const sim = path.join(framesDir, "sim60", c.id);
  if (!existsSync(sim + "/done.json")) { console.log("no sim60 frames:", c.id); continue; }
  const meta = JSON.parse(readFileSync(sim + "/meta.json", "utf8"));
  const card = path.join(out2, `${num}-${c.id}-card.png`);
  const cardMp4 = path.join(clips, `${num}-${c.id}-card.mp4`);
  still(card, 3.8, cardMp4); add(cardMp4);
  // layout
  const dir = path.join(framesDir, "examples", c.id);
  const [[dw, dh0], [pw, ph0], [vw, vh]] = await sizes([dir + "/diagram.png", sim + "/p/00000.jpg", sim + "/v/00000.jpg"]);
  const plotH = Math.min(520, Math.round((1060 * ph0) / pw));
  const dBoxH = 956 - plotH - 16;
  const bg = await bgPng(c, idx, total, c.id, { dh: dBoxH, ph: plotH });
  const speed = meta.s;
  const spTxt = speed >= 0.95 ? `${+speed.toFixed(1)}x` : speed < 0.01 ? `${speed.toPrecision(1)}x` : `${speed.toFixed(2)}x`;
  const S = speed.toFixed(6);
  const filt = [
    `[1:v]scale=1056:${dBoxH - 4}:force_original_aspect_ratio=decrease[dg]`,
    `[2:v]scale=1056:${plotH - 4}[pl]`,
    `[3:v]scale=796:952:force_original_aspect_ratio=decrease[vw]`,
    `color=c=0xf5a524:s=1920x5:r=60[bar]`,
    `[0:v][dg]overlay=x=22+(1056-w)/2:y=106+(${dBoxH - 4}-h)/2[a]`,
    `[a][pl]overlay=x=22:y=${104 + dBoxH + 16 + 2}[b]`,
    `[b][vw]overlay=x=1102+(796-w)/2:y=106+(952-h)/2[c]`,
    `[c][bar]overlay=x='-1920+1920*n/${meta.N}':y=84:shortest=1[d]`,
    `[d]drawtext=fontfile='C\\:/Windows/Fonts/segoeui.ttf':fontcolor=0xc9d4df:fontsize=34:x=w-tw-40:y=24:text='t = %{eif\\:floor(n*${S}/60)\\:d}.%{eif\\:mod(floor(n*${S}*100/60),100)\\:d\\:2} s  ·  ${spTxt}'[o]`,
  ].join(";\n");
  const fscript = path.join(clips, `f-${c.id}.txt`);
  writeFileSync(fscript, filt);
  const clip = path.join(clips, `${num}-${c.id}-sim.mp4`);
  run(["-y", "-loop", "1", "-framerate", "60", "-i", bg, "-loop", "1", "-framerate", "60", "-i", dir + "/diagram.png",
    "-framerate", "60", "-i", sim + "/p/%05d.jpg", "-framerate", "60", "-i", sim + "/v/%05d.jpg",
    "-filter_complex_script", fscript, "-map", "[o]", "-frames:v", String(meta.N), ...ENC, clip]);
  add(clip);
  if (c.compare) {
    for (const i of [2, 4]) {
      const f = path.join(out2, `${num}-${c.id}-cmp${i}.png`);
      if (existsSync(f)) { const m = path.join(clips, `${num}-${c.id}-cmp${i}.mp4`); still(f, 1.8, m); add(m); }
    }
  }
  console.log("composed", c.id, `${meta.N} frames, ${spTxt}`);
}
const end = path.join(clips, "99-end.mp4"); still(path.join(out2, "99-end.png"), 4, end); add(end);
await browser.close();
const listFile = path.join(clips, "list.txt");
writeFileSync(listFile, list.map((f) => `file '${f.replace(/\\/g, "/")}'`).join("\n") + "\n");
const outFile = path.join(repoRoot, "media/video/bg-sim-examples.mp4");
run(["-y", "-f", "concat", "-safe", "0", "-i", listFile, "-c", "copy", "-movflags", "+faststart", outFile]);
console.log(`${outFile}: ${(statSync(outFile).size / 1e6).toFixed(1)} MB`);
