#!/usr/bin/env node
// Video 1: title cards + caption overlays on the stills of capture-intro.mjs, encoded to media/video/bg-sim-intro.mp4
// usage: node compose-intro.mjs [--no-encode]
import { existsSync, mkdirSync } from "node:fs";
import path from "node:path";
import { chromium, framesDir, repoRoot } from "./lib.mjs";
import { writeHtml, fileUrl, esc } from "./theme.mjs";
import { encode } from "./encode.mjs";

import { SCENES } from "./intro-plan.mjs";

const CAP = `
.shot .cap2{position:absolute;left:0;right:0;bottom:0;height:130px;padding:0 60px;display:flex;align-items:center;gap:32px;background:rgba(8,11,16,.93);border-top:4px solid #f5a524}
.cap2 .sc{font-size:26px;letter-spacing:3px;color:#f5a524;text-transform:uppercase;font-weight:700;white-space:nowrap}
.cap2 .tx{font-size:46px;font-weight:600;line-height:1.15}
.shot img.full{inset:auto;left:50%;top:0;transform:translateX(-50%);width:auto;height:950px}
.shot .win{position:absolute;left:0;top:0;width:1920px;height:950px;object-fit:contain;background:#0d1117}
`;
const outDir = path.join(framesDir, "out1");
mkdirSync(outDir, { recursive: true });
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
async function shot(name, body) {
  const url = writeHtml("i-" + name, body, CAP);
  await page.goto(url);
  await page.evaluate(() => document.fonts.ready);
  await page.waitForFunction(() => [...document.images].every((i) => i.complete));
  const png = path.join(outDir, name + ".png");
  await page.screenshot({ path: png });
  return png;
}

const items = [];
items.push({ png: await shot("00-title", `<div class="card"><div class="bar"></div><h1><span class="accent">bg-sim</span></h1><h2 style="font-size:64px;margin-top:20px">Bond graphs, block diagrams and equations.<br>One modelling and simulation tool.</h2><p class="sub">A React editor, a FastAPI backend and a Julia / ModelingToolkit simulation worker.</p></div>`), seconds: 5 });
let n = 1;
for (const sc of SCENES) {
  const num = String(n++).padStart(2, "0");
  items.push({ png: await shot(`${num}-${sc.id}-card`, `<div class="card"><div class="bar"></div><div class="num">${sc.id.replace("s", "Feature ")}</div><h2>${esc(sc.title)}</h2><p class="sub">${esc(sc.sub)}</p></div>`), seconds: 2.2 });
  for (const [name, caption] of sc.stills) {
    const f = path.join(framesDir, "intro", `${sc.id}-${name}.png`);
    if (!existsSync(f)) { console.log("missing", f); continue; }
    const popup = /popout/.test(name);
    const img = popup ? `<img class="win" src="${fileUrl(f)}">` : `<img class="full" src="${fileUrl(f)}">`;
    items.push({ png: await shot(`${num}-${sc.id}-${name}`, `<div class="shot">${img}<div class="cap2"><span class="sc">${esc(sc.title)}</span><span class="tx">${esc(caption)}</span></div></div>`), seconds: caption.length > 60 ? 2.4 : 2.0 });
  }
}
items.push({ png: await shot("99-end", `<div class="card"><div class="bar"></div><h2>Open an example and <span class="accent">try it</span></h2><p class="sub">bg-sim: models, simulation, debugging and 3D playback in one tool.</p></div>`), seconds: 4 });
await browser.close();
if (!process.argv.includes("--no-encode")) {
  mkdirSync(path.join(repoRoot, "media/video"), { recursive: true });
  encode(items, path.join(repoRoot, "media/video/bg-sim-intro.mp4"), path.join(outDir, "list.txt"));
}
