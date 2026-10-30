// Encode a list of {png, seconds} into an H.264 1920x1080 yuv420p MP4 with ffmpeg
// (ffmpeg on PATH, else the imageio-ffmpeg binary through uv).
import { spawnSync } from "node:child_process";
import { writeFileSync, statSync } from "node:fs";
import path from "node:path";
import { repoRoot } from "./lib.mjs";

function ffmpegCmd() {
  const probe = spawnSync("ffmpeg", ["-version"], { stdio: "ignore" });
  if (probe.status === 0) return ["ffmpeg"];
  const r = spawnSync("uv", ["run", "--with", "imageio-ffmpeg", "python", "-c", "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"], { cwd: repoRoot, encoding: "utf8" });
  return [r.stdout.trim().split(/\r?\n/).pop()];
}

export function encode(items, out, listFile) {
  const lines = [];
  for (const it of items) {
    lines.push(`file '${it.png.replace(/\\/g, "/")}'`, `duration ${it.seconds}`);
  }
  lines.push(`file '${items[items.length - 1].png.replace(/\\/g, "/")}'`); // concat quirk: repeat the last file
  writeFileSync(listFile, lines.join("\n") + "\n");
  const [bin] = ffmpegCmd();
  const args = ["-y", "-f", "concat", "-safe", "0", "-i", listFile, "-vf", "fps=25,scale=1920:1080,format=yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-movflags", "+faststart", out];
  const r = spawnSync(bin, args, { stdio: "inherit" });
  if (r.status !== 0) throw new Error("ffmpeg failed");
  const total = items.reduce((s, i) => s + i.seconds, 0);
  console.log(`${out}: ${total.toFixed(1)} s, ${(statSync(out).size / 1e6).toFixed(1)} MB`);
}
