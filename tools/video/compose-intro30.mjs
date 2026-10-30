#!/usr/bin/env node
// Video 1 at 30 fps: resample the real-time screencasts (variable frame timing) to a constant 30 fps with ffmpeg
// (concat list with per-frame durations + fps=30), add the caption bar, prepend the scene title cards, concatenate.
// Needs the cards of `compose-intro.mjs --no-encode` (frames/out1/*.png).  usage: node compose-intro30.mjs [--crf 19]
import { existsSync, readFileSync, writeFileSync, mkdirSync, statSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { framesDir, repoRoot } from "./lib.mjs";
import { SCENES } from "./intro-plan.mjs";

const arg = (n) => { const i = process.argv.indexOf(n); return i > 0 ? process.argv[i + 1] : null; };
const crf = arg("--crf") ?? "19";
const root = path.join(framesDir, "intro30");
const out1 = path.join(framesDir, "out1");
const clips = path.join(root, "clips");
mkdirSync(clips, { recursive: true });
const manifest = JSON.parse(readFileSync(path.join(root, "manifest.json"), "utf8"));

function ffmpegBin() {
  if (spawnSync("ffmpeg", ["-version"], { stdio: "ignore" }).status === 0) return "ffmpeg";
  const r = spawnSync("uv", ["run", "--with", "imageio-ffmpeg", "python", "-c", "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"], { cwd: repoRoot, encoding: "utf8" });
  return r.stdout.trim().split(/\r?\n/).pop();
}
const FF = ffmpegBin();
const run = (args) => { const r = spawnSync(FF, args, { stdio: ["ignore", "ignore", "pipe"], encoding: "utf8", maxBuffer: 1 << 28 }); if (r.status !== 0) throw new Error(r.stderr.slice(-1200)); };
const ENC = ["-c:v", "libx264", "-preset", "medium", "-crf", crf, "-pix_fmt", "yuv420p", "-r", "30", "-movflags", "+faststart"];
const FONT = "C\\:/Windows/Fonts/segoeui.ttf", FONTB = "C\\:/Windows/Fonts/segoeuib.ttf";
const fwd = (p) => p.replace(/\\/g, "/");
const esc = (p) => fwd(p).replace(/:/g, "\\:");

function card(png, seconds, out) { run(["-y", "-loop", "1", "-framerate", "30", "-t", String(seconds), "-i", png, "-vf", "scale=1920:1080,format=yuv420p", ...ENC, out]); }

/** One recording -> one 30 fps clip with captions. */
function clip(tl0, scene, captions, out) {
  const base = Math.min(...tl0.frames.map((f) => f.vt));
  let tl = { ...tl0, frames: tl0.frames.map((f) => ({ ...f, vt: f.vt - base })), marks: tl0.marks.map((m) => ({ ...m, vt: m.vt - base })), end: tl0.end - base };
  const frames = tl.frames.slice().sort((a, b) => a.vt - b.vt);
  const lines = [];
  for (let i = 0; i < frames.length; i++) {
    const last = i + 1 >= frames.length;
    const dur = last ? 0.04 : Math.max(0.001, (frames[i + 1].vt - frames[i].vt) / 1000);
    lines.push(`file '${fwd(frames[i].file)}'`, `duration ${dur.toFixed(4)}`);
  }
  lines.push(`file '${fwd(frames[frames.length - 1].file)}'`);
  const list = path.join(tl.dir, "list.txt");
  writeFileSync(list, lines.join("\n") + "\n");
  // caption intervals: from the end of the previous mark's hold to the end of this mark's hold
  const marks = tl.marks.slice().sort((a, b) => a.vt - b.vt);
  let prev = 0;
  const filters = [
    "scale=1920:950:force_original_aspect_ratio=decrease",
    "pad=1920:1080:(ow-iw)/2:(950-ih)/2:0x0d1117",
    "drawbox=x=0:y=950:w=1920:h=130:color=0x080b10:t=fill",
    "drawbox=x=0:y=950:w=1920:h=4:color=0xf5a524:t=fill",
  ];
  let k = 0;
  for (const m of marks) {
    const end = Math.min(tl.end, m.vt + (m.hold ?? 1.4) * 1000) / 1000;
    const cap = captions.get(m.name);
    if (cap) {
      const f1 = path.join(tl.dir, `cap${k}-a.txt`), f2 = path.join(tl.dir, `cap${k}-b.txt`);
      writeFileSync(f1, scene.title.toUpperCase());
      writeFileSync(f2, cap);
      const en = `enable='between(t,${prev.toFixed(3)},${end.toFixed(3)})'`;
      filters.push(`drawtext=fontfile='${FONTB}':textfile='${esc(f1)}':fontcolor=0xf5a524:fontsize=24:x=60:y=966:${en}`);
      filters.push(`drawtext=fontfile='${FONTB}':textfile='${esc(f2)}':fontcolor=0xe6edf3:fontsize=44:x=60:y=1000:${en}`);
      k++;
    }
    prev = end;
  }
  const tail = Math.max(0, (tl.end - frames[frames.length - 1].vt) / 1000 - 0.04);
  filters.push(`tpad=stop_mode=clone:stop_duration=${tail.toFixed(3)}`, "fps=30", "format=yuv420p");
  run(["-y", "-f", "concat", "-safe", "0", "-i", list, "-vf", filters.join(","), "-fps_mode", "cfr", ...ENC, out]);
}

const items = [];
const title = path.join(clips, "00-title.mp4"); card(path.join(out1, "00-title.png"), 5, title); items.push(title);
let n = 1;
for (const sc of SCENES) {
  const num = String(n++).padStart(2, "0");
  const cardPng = path.join(out1, `${num}-${sc.id}-card.png`);
  const cardMp4 = path.join(clips, `${num}-${sc.id}-card.mp4`);
  card(cardPng, 1.8, cardMp4); items.push(cardMp4);
  const captions = new Map(sc.stills);
  const keys = Object.keys(manifest).filter((k) => k === sc.id || new RegExp(`^${sc.id}[a-z]$`).test(k)).sort();
  let j = 0;
  for (const key of keys) {
    for (const rel of manifest[key]) {
      const tl = JSON.parse(readFileSync(path.join(root, rel, "timeline.json"), "utf8"));
      tl.dir = path.join(root, rel);
      const out = path.join(clips, `${num}-${sc.id}-${j++}.mp4`);
      clip(tl, sc, captions, out);
      items.push(out);
      console.log("clip", rel, `${tl.frames.length} source frames`);
    }
  }
}
const end = path.join(clips, "99-end.mp4"); card(path.join(out1, "99-end.png"), 4, end); items.push(end);
const listFile = path.join(clips, "list.txt");
writeFileSync(listFile, items.map((f) => `file '${fwd(f)}'`).join("\n") + "\n");
const outFile = path.join(repoRoot, "media/video/bg-sim-intro.mp4");
run(["-y", "-f", "concat", "-safe", "0", "-i", listFile, "-c", "copy", "-movflags", "+faststart", outFile]);
console.log(`${outFile}: ${(statSync(outFile).size / 1e6).toFixed(1)} MB`);
