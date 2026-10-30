#!/usr/bin/env node
// Video 2: compose the example cards and 3-panel frames, then encode media/video/bg-sim-examples.mjs.
// usage: node compose-examples.mjs [--only a,b] [--no-encode]
import { existsSync, readFileSync, mkdirSync } from "node:fs";
import path from "node:path";
import { chromium, framesDir, repoRoot } from "./lib.mjs";
import { writeHtml, fileUrl, esc } from "./theme.mjs";
import { encode } from "./encode.mjs";

const arg = (n) => { const i = process.argv.indexOf(n); return i > 0 ? process.argv[i + 1] : null; };
const only = arg("--only")?.split(",") ?? null;
const cards = JSON.parse(readFileSync(new URL("./cards.json", import.meta.url), "utf8"));
const outDir = path.join(framesDir, "out2");
mkdirSync(outDir, { recursive: true });

const PANEL = `
.col{position:absolute;left:20px;top:104px;width:1060px;height:956px;display:flex;flex-direction:column;gap:16px}
.col .dg{position:relative;flex:1;min-height:0}
.col .pl{position:relative;flex:none;background:#10161e}
.col .pl img{position:static;width:100%;height:auto;display:block;padding-top:34px}

.hdr{position:absolute;left:0;top:0;right:0;height:84px;padding:0 40px;display:flex;align-items:center;justify-content:space-between;background:#0a0e14;border-bottom:2px solid #1f2733}
.hdr .l{display:flex;align-items:baseline;gap:22px}
.hdr .n{font-size:24px;letter-spacing:3px;color:${"#f5a524"};font-weight:600}
.hdr .t{font-size:40px;font-weight:700}
.hdr .r{font-size:34px;font-variant-numeric:tabular-nums;color:#c9d4df}
.prog{position:absolute;left:0;top:84px;height:5px;background:#f5a524}
.pn{position:absolute;background:#10161e;border:2px solid #232d3a;border-radius:10px;overflow:hidden}
.pn img{position:absolute;inset:0;width:100%;height:100%;object-fit:contain}
.pn .lab{position:absolute;left:14px;top:10px;font-size:20px;letter-spacing:2px;color:#f5a524;text-transform:uppercase;font-weight:600;background:rgba(10,14,20,.8);padding:2px 10px;border-radius:6px;z-index:2}
`;

function appFrame(card, idx, total, info, dir, i) {
  const t = info.times?.[i];
  const frac = t !== undefined && info.end ? t / info.end : 0;
  return `<div class="shot">
  <div class="hdr"><div class="l"><span class="n">${String(idx + 1).padStart(2, "0")} / ${total}</span><span class="t">${esc(card.title)}</span></div>
   <div class="r">t = ${t !== undefined ? t.toFixed(2) : "–"} s <span style="color:#6b7886">/ ${info.end?.toFixed(1)} s</span></div></div>
  <div class="prog" style="width:${(frac * 1920).toFixed(0)}px"></div>
  <div class="col"><div class="pn dg"><span class="lab">Model</span><img src="${fileUrl(dir + "/diagram.png")}"></div>
  <div class="pn pl"><span class="lab">Plots</span><img src="${fileUrl(dir + `/p-${i}.png`)}"></div></div>
  <div class="pn" style="left:1100px;top:104px;width:800px;height:956px"><span class="lab">3D view</span><img src="${fileUrl(dir + `/v-${i}.png`)}"></div>
  </div>`;
}

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
async function shot(name, body, extra = "") {
  const url = writeHtml(name, body, extra);
  await page.goto(url);
  await page.evaluate(() => document.fonts.ready);
  await page.waitForFunction(() => [...document.images].every((i) => i.complete));
  const png = path.join(outDir, name + ".png");
  await page.screenshot({ path: png });
  return png;
}

const items = [];
const total = cards.length;
// title card
items.push({ png: await shot("00-title", `<div class="card"><div class="bar"></div><div class="num">Example tour</div><h1>bg-sim <span class="accent">examples</span></h1><p class="sub">${total} models, from a DC motor to an aerial manipulator, each run on the real Julia worker.</p></div>`), seconds: 4 });
for (let idx = 0; idx < cards.length; idx++) {
  const card = cards[idx];
  if (only && !only.includes(card.id)) continue;
  const dir = path.join(framesDir, "examples", card.id);
  if (!existsSync(dir + "/info.json")) { console.log("skip (no frames)", card.id); continue; }
  const info = JSON.parse(readFileSync(dir + "/info.json", "utf8"));
  const num = String(idx + 1).padStart(2, "0");
  items.push({
    png: await shot(`${num}-${card.id}-card`, `<div class="card"><div class="bar"></div><div class="num">Example ${num} of ${total}</div><h2>${esc(card.title)}</h2><ul>${card.lines.map((l) => `<li>${esc(l)}</li>`).join("")}</ul><div class="tags">${card.tags.map((t) => `<span class="tag">${esc(t)}</span>`).join("")}</div></div>`),
    seconds: 3.8,
  });
  const n = info.times.length;
  for (let i = 0; i < n; i++) {
    items.push({ png: await shot(`${num}-${card.id}-${i}`, appFrame(card, idx, total, info, dir, i), PANEL), seconds: 1.2 });
  }
  if (card.compare) {
    const d2 = path.join(framesDir, "examples", card.compare);
    for (const i of [2, 4]) {
      items.push({ png: await shot(`${num}-${card.id}-cmp${i}`, `<div class="shot"><div class="hdr"><div class="l"><span class="n">${num} / ${total}</span><span class="t">${esc(card.title)}</span></div><div class="r">resonance-aware controller vs. naive PID</div></div>
        <div class="pn" style="left:20px;top:104px;width:940px;height:956px"><span class="lab">Resonance-aware: trajectory + Kalman + LQR</span><img src="${fileUrl(dir + `/p-${i}.png`)}" style="top:60px;height:auto;position:absolute"></div>
        <div class="pn" style="left:980px;top:104px;width:920px;height:956px"><span class="lab">Naive PID</span><img src="${fileUrl(d2 + `/p-${i}.png`)}" style="top:60px;height:auto;position:absolute"></div></div>`, PANEL), seconds: 1.8 });
    }
  }
  console.log("composed", card.id);
}
// closing card
items.push({ png: await shot("99-end", `<div class="card"><div class="bar"></div><h2>Every model above runs in <span class="accent">bg-sim</span></h2><p class="sub">Open any example from the gallery: it becomes your own project copy.</p></div>`), seconds: 4 });
await browser.close();
if (!process.argv.includes("--no-encode")) {
  mkdirSync(path.join(repoRoot, "media/video"), { recursive: true });
  encode(items, path.join(repoRoot, "media/video/bg-sim-examples.mp4"), path.join(outDir, "list.txt"));
}
