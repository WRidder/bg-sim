// Shared look of the video cards and frames: dark background, one accent colour, a clean sans font.
import { pathToFileURL } from "node:url";
import { writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";
import { framesDir } from "./lib.mjs";

export const ACCENT = "#f5a524";
export const css = `
*{box-sizing:border-box;margin:0;padding:0}
html,body{width:1920px;height:1080px;overflow:hidden;background:#0d1117;color:#e6edf3;
 font-family:"Segoe UI","Inter","Helvetica Neue",Arial,sans-serif}
.accent{color:${ACCENT}}
.card{position:relative;width:1920px;height:1080px;padding:120px 160px;display:flex;flex-direction:column;justify-content:center;
 background:radial-gradient(1200px 700px at 85% 10%,#1a2230 0%,#0d1117 60%)}
.card .bar{width:96px;height:8px;background:${ACCENT};border-radius:4px;margin-bottom:44px}
.card h1{font-size:104px;font-weight:700;letter-spacing:-1px;line-height:1.05}
.card h2{font-size:84px;font-weight:700;letter-spacing:-.5px;line-height:1.08}
.card .sub{font-size:40px;color:#9aa7b4;margin-top:36px;line-height:1.35;max-width:1500px}
.card ul{list-style:none;margin-top:44px;max-width:1560px}
.card li{font-size:40px;line-height:1.38;color:#d3dbe3;margin-bottom:20px;padding-left:44px;position:relative}
.card li:before{content:"";position:absolute;left:0;top:.62em;width:16px;height:16px;border-radius:50%;background:${ACCENT}}
.card .num{font-size:30px;letter-spacing:4px;color:${ACCENT};text-transform:uppercase;margin-bottom:22px;font-weight:600}
.tags{margin-top:30px;display:flex;gap:14px;flex-wrap:wrap}
.tag{font-size:26px;padding:8px 20px;border:2px solid #3a4655;border-radius:999px;color:#9aa7b4}
.shot{position:relative;width:1920px;height:1080px;background:#0d1117}
.shot img.full{position:absolute;inset:0;width:1920px;height:1080px}
.cap{position:absolute;left:0;right:0;bottom:0;padding:34px 80px 38px;background:linear-gradient(0deg,rgba(8,11,16,.96) 0%,rgba(8,11,16,.9) 70%,rgba(8,11,16,0) 100%);
 display:flex;align-items:baseline;gap:28px}
.cap .scene{font-size:26px;letter-spacing:3px;color:${ACCENT};text-transform:uppercase;font-weight:600;white-space:nowrap}
.cap .text{font-size:44px;font-weight:600;line-height:1.2}
`;

export function writeHtml(name, body, extraCss = "") {
  const dir = path.join(framesDir, "_html");
  mkdirSync(dir, { recursive: true });
  const file = path.join(dir, name + ".html");
  writeFileSync(file, `<!doctype html><html><head><meta charset="utf-8"><style>${css}${extraCss}</style></head><body>${body}</body></html>`);
  return pathToFileURL(file).href;
}
export const fileUrl = (p) => pathToFileURL(p).href;
export const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
