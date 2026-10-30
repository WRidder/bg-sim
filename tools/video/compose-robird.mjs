#!/usr/bin/env node
// Robird video (60 fps): title card, UI recording (resampled to 60 fps, captions), whole-figure playback with plots,
// slow-motion close-up with flap angle and motor current, end card -> media/video/robird.mp4
// Needs: capture-robird.mjs --seg lap / --seg close, capture-robird-ui.mjs.  usage: node compose-robird.mjs [--crf 19]
import { existsSync, readFileSync, writeFileSync, mkdirSync, statSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { chromium, framesDir, repoRoot } from "./lib.mjs";
import { writeHtml, fileUrl, esc } from "./theme.mjs";

const arg = (n) => { const i = process.argv.indexOf(n); return i > 0 ? process.argv[i + 1] : null; };
const crf = arg("--crf") ?? "19";
const root = path.join(framesDir, "robird60");
const clips = path.join(root, "clips");
mkdirSync(clips, { recursive: true });
function ffmpegBin() {
  if (spawnSync("ffmpeg", ["-version"], { stdio: "ignore" }).status === 0) return "ffmpeg";
  const r = spawnSync("uv", ["run", "--with", "imageio-ffmpeg", "python", "-c", "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"], { cwd: repoRoot, encoding: "utf8" });
  return r.stdout.trim().split(/\r?\n/).pop();
}
const FF = ffmpegBin();
const run = (args) => { const r = spawnSync(FF, args, { stdio: ["ignore", "ignore", "pipe"], encoding: "utf8", maxBuffer: 1 << 28 }); if (r.status !== 0) throw new Error(r.stderr.slice(-1000)); };
const ENC = ["-c:v", "libx264", "-preset", "medium", "-crf", crf, "-pix_fmt", "yuv420p", "-r", "60", "-movflags", "+faststart"];
const fwd = (p) => p.replace(/\\/g, "/");
const escF = (p) => fwd(p).replace(/:/g, "\\:");
const FONT = "C\\:/Windows/Fonts/segoeui.ttf", FONTB = "C\\:/Windows/Fonts/segoeuib.ttf";
const still = (png, sec, out) => run(["-y", "-loop", "1", "-framerate", "60", "-t", String(sec), "-i", png, "-vf", "scale=1920:1080,format=yuv420p", ...ENC, out]);

const PANEL = `
.hdr{position:absolute;left:0;top:0;right:0;height:84px;padding:0 40px;display:flex;align-items:center;background:#0a0e14;border-bottom:2px solid #1f2733}
.hdr .l{display:flex;align-items:baseline;gap:22px}
.hdr .n{font-size:24px;letter-spacing:3px;color:#f5a524;font-weight:600}
.hdr .t{font-size:40px;font-weight:700}
.hdr .s{font-size:28px;color:#9aa7b4;margin-left:30px}
.pn{position:absolute;background:#10161e;border:2px solid #232d3a;border-radius:10px;overflow:hidden}
.pn .lab{position:absolute;left:14px;top:10px;font-size:20px;letter-spacing:2px;color:#f5a524;text-transform:uppercase;font-weight:600;background:rgba(10,14,20,.8);padding:2px 10px;border-radius:6px;z-index:2}
.big{font-size:56px;font-weight:700;color:#f5a524}
.kv{display:flex;gap:70px;margin-top:50px}
.kv div{font-size:30px;color:#9aa7b4}
.kv b{display:block;font-size:76px;color:#e6edf3;font-weight:700;letter-spacing:-1px}
.note{margin-top:60px;font-size:34px;color:#9aa7b4;max-width:1500px;line-height:1.4}
`;
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
async function shot(name, body) {
  const url = writeHtml("rb-" + name, `<div style="position:relative;width:1920px;height:1080px">${body}</div>`, PANEL);
  await page.goto(url);
  await page.evaluate(() => document.fonts.ready);
  await page.waitForFunction(() => [...document.images].every((i) => i.complete));
  const png = path.join(clips, name + ".png");
  await page.screenshot({ path: png });
  return png;
}
async function sizes(files) {
  await page.goto(writeHtml("rb-sizes", files.map((f) => `<img src="${fileUrl(f)}">`).join("")));
  await page.waitForFunction(() => [...document.images].every((i) => i.complete));
  return page.evaluate(() => [...document.images].map((i) => [i.naturalWidth, i.naturalHeight]));
}
const hdr = (sub) => `<div class="hdr"><div class="l"><span class="n">ROBIRD</span><span class="t">Flapping-wing robotic falcon</span><span class="s">${esc(sub)}</span></div></div>`;

const items = [];
// 1. title card
const titlePng = await shot("title", `<div class="card"><div class="bar"></div><div class="num">bg-sim example</div><h2 style="font-size:78px">Robird: a flapping-wing<br>robotic falcon in bond graphs</h2><p class="sub">After B. A. van der Grinten, G. A. Folkertsma, N. Nijenhuis and S. Stramigioli, University of Twente, 2015.</p></div>`);
const title = path.join(clips, "01-title.mp4"); still(titlePng, 5, title); items.push(title);

// 2. UI recording -> 60 fps with captions
{
  const tl = JSON.parse(readFileSync(path.join(root, "ui", "timeline.json"), "utf8"));
  const base = Math.min(...tl.frames.map((f) => f.vt));
  const frames = tl.frames.map((f) => ({ ...f, vt: f.vt - base })).sort((a, b) => a.vt - b.vt);
  const end = tl.end - base;
  const lines = [];
  frames.forEach((f, i) => { lines.push(`file '${fwd(f.file)}'`, `duration ${(i + 1 < frames.length ? Math.max(0.001, (frames[i + 1].vt - f.vt) / 1000) : 0.04).toFixed(4)}`); });
  lines.push(`file '${fwd(frames[frames.length - 1].file)}'`);
  const list = path.join(tl.dir ?? path.join(root, "ui"), "list.txt");
  writeFileSync(list, lines.join("\n") + "\n");
  const CAP = { pan: "The model: fuselage, wings, flapping drive, aerodynamics and controller", crank: "Flapping drive: motor, gear and crank", body: "Fuselage: a free spatial rigid body", aero: "StripAero: strip-theory aerodynamics on a wing segment", ctrl: "FlightCtrl: the discrete cycle-averaged flight controller", docs: "The Docs tab: documentation next to the model", docs2: "Structure, wing and aerodynamics pages with math and figures" };
  const filters = ["scale=1920:950:force_original_aspect_ratio=decrease", "pad=1920:1080:(ow-iw)/2:(950-ih)/2:0x0d1117", "drawbox=x=0:y=950:w=1920:h=130:color=0x080b10:t=fill", "drawbox=x=0:y=950:w=1920:h=4:color=0xf5a524:t=fill"];
  let prev = 0, k = 0;
  const marks = tl.marks.map((m) => ({ ...m, vt: m.vt - base })).sort((a, b) => a.vt - b.vt);
  for (const m of marks) {
    const e = Math.min(end, m.vt + (m.hold ?? 1.4) * 1000) / 1000;
    if (CAP[m.name]) {
      const f1 = path.join(root, "ui", `cap${k}-a.txt`), f2 = path.join(root, "ui", `cap${k}-b.txt`);
      writeFileSync(f1, "THE MODEL"); writeFileSync(f2, CAP[m.name]);
      const st = Math.max(prev, m.vt / 1000 - 5.5);
      const en = `enable='between(t,${st.toFixed(3)},${e.toFixed(3)})'`;
      filters.push(`drawtext=fontfile='${FONTB}':textfile='${escF(f1)}':fontcolor=0xf5a524:fontsize=24:x=60:y=966:${en}`);
      filters.push(`drawtext=fontfile='${FONTB}':textfile='${escF(f2)}':fontcolor=0xe6edf3:fontsize=44:x=60:y=1000:${en}`);
      k++;
    }
    prev = e;
  }
  const tail = Math.max(0, (end - frames[frames.length - 1].vt) / 1000 - 0.04);
  filters.push(`tpad=stop_mode=clone:stop_duration=${tail.toFixed(3)}`, "fps=60", "format=yuv420p");
  const out = path.join(clips, "02-ui.mp4");
  run(["-y", "-f", "concat", "-safe", "0", "-i", list, "-vf", filters.join(","), "-fps_mode", "cfr", ...ENC, out]);
  items.push(out);
}

// 3a. the whole figure (top view): diagram | plots | 3D
async function playClip(seg, sub, layout) {
  const dir = path.join(root, seg);
  const meta = JSON.parse(readFileSync(dir + "/meta.json", "utf8"));
  const diag = path.join(framesDir, "examples", "robird", "diagram.png");
  const hasDiag = layout === "lap";
  const files = [dir + "/p/00000.jpg", dir + "/v/00000.jpg"].concat(hasDiag ? [diag] : []);
  const sz = await sizes(files);
  const [pw, ph] = sz[0];
  const S = meta.s.toFixed(6);
  const t0 = meta.t0 ?? 0;
  const spTxt = meta.s >= 0.95 ? `${+meta.s.toFixed(1)}x` : `${meta.s.toFixed(2)}x`;
  let bgBody, filt;
  const tText = `drawtext=fontfile='${FONT}':fontcolor=0xc9d4df:fontsize=34:x=w-tw-40:y=24:text='t = %{eif\\:floor(${t0}+n*${S}/60)\\:d}.%{eif\\:mod(floor((${t0}+n*${S}/60)*100),100)\\:d\\:2} s  ·  ${spTxt}'`;
  if (layout === "lap") {
    const plotH = Math.min(520, Math.round((1060 * ph) / pw));
    const dBoxH = 956 - plotH - 16;
    bgBody = `${hdr(sub)}<div class="pn" style="left:20px;top:104px;width:1060px;height:${dBoxH}px"><span class="lab">Model</span></div><div class="pn" style="left:20px;top:${104 + dBoxH + 16}px;width:1060px;height:${plotH}px"></div><div class="pn" style="left:1100px;top:104px;width:800px;height:956px"><span class="lab">3D view (top)</span></div>`;
    filt = [
      `[1:v]scale=1056:${dBoxH - 4}:force_original_aspect_ratio=decrease[dg]`, `[2:v]scale=1056:${plotH - 4}[pl]`, `[3:v]scale=796:952:force_original_aspect_ratio=decrease[vw]`,
      `color=c=0xf5a524:s=1920x5:r=60[bar]`,
      `[0:v][dg]overlay=x=22+(1056-w)/2:y=106+(${dBoxH - 4}-h)/2[a]`, `[a][pl]overlay=x=22:y=${104 + dBoxH + 16 + 2}[b]`, `[b][vw]overlay=x=1102+(796-w)/2:y=106+(952-h)/2[c]`,
      `[c][bar]overlay=x='-1920+1920*n/${meta.N}':y=84:shortest=1[d]`, `[d]${tText}[o]`,
    ].join(";\n");
  } else {
    const plotW = 840, plotH = Math.round((plotW * ph) / pw);
    bgBody = `${hdr(sub)}<div class="pn" style="left:20px;top:104px;width:1020px;height:956px"><span class="lab">3D view (close-up)</span></div><div class="pn" style="left:1060px;top:104px;width:840px;height:956px"><span class="lab">Flap angle and motor current</span></div>`;
    filt = [
      `[1:v]scale=1016:952:force_original_aspect_ratio=decrease[vw]`, `[2:v]scale=${plotW - 4}:-2[pl]`, `color=c=0xf5a524:s=1920x5:r=60[bar]`,
      `[0:v][vw]overlay=x=22+(1016-w)/2:y=106+(952-h)/2[a]`, `[a][pl]overlay=x=1062:y=${104 + Math.round((956 - plotH) / 2)}[c]`,
      `[c][bar]overlay=x='-1920+1920*n/${meta.N}':y=84:shortest=1[d]`, `[d]${tText}[o]`,
    ].join(";\n");
  }
  const bg = await shot(`bg-${seg}`, bgBody);
  const fscript = path.join(clips, `f-${seg}.txt`);
  writeFileSync(fscript, filt);
  const out = path.join(clips, seg === "lap" ? "03-lap.mp4" : "04-close.mp4");
  const inputs = ["-y", "-loop", "1", "-framerate", "60", "-i", bg, "-framerate", "60", "-i", dir + "/v/%05d.jpg", "-framerate", "60", "-i", dir + "/p/%05d.jpg"];
  if (hasDiag) { inputs.splice(1, 0); }
  const args = layout === "lap"
    ? ["-y", "-loop", "1", "-framerate", "60", "-i", bg, "-loop", "1", "-framerate", "60", "-i", diag, "-framerate", "60", "-i", dir + "/p/%05d.jpg", "-framerate", "60", "-i", dir + "/v/%05d.jpg"]
    : inputs;
  run([...args, "-filter_complex_script", fscript, "-map", "[o]", "-frames:v", String(meta.N), ...ENC, out]);
  items.push(out);
  console.log("clip", seg, meta.N, "frames", spTxt);
}
await playClip("lap", "whole figure of eight from above, fast forward", "lap");
await playClip("close", "close-up in slow motion: about three flap cycles", "close");

// 4. end card
const endPng = await shot("end", `<div class="card"><div class="bar"></div><div class="num">Results</div><h2>A closed-loop flapping flight, nothing kinematic</h2>
<div class="kv"><div><b>0.42 m</b>cross-track error, RMS</div><div><b>220 x 84 m</b>figure of eight</div><div><b>12 m/s</b>flight speed</div><div><b>about 4 Hz</b>flapping</div></div>
<p class="note">Assumed parameters, quasi-steady aerodynamics: a feasibility model, not a validated model of the real Robird.</p></div>`);
const endMp4 = path.join(clips, "05-end.mp4"); still(endPng, 8, endMp4); items.push(endMp4);
await browser.close();
const listFile = path.join(clips, "list.txt");
writeFileSync(listFile, items.map((f) => `file '${fwd(f)}'`).join("\n") + "\n");
const outFile = path.join(repoRoot, "media/video/robird.mp4");
run(["-y", "-f", "concat", "-safe", "0", "-i", listFile, "-c", "copy", "-movflags", "+faststart", outFile]);
console.log(`${outFile}: ${(statSync(outFile).size / 1e6).toFixed(1)} MB`);
