#!/usr/bin/env node
// Video 1: title cards + caption overlays on the stills of capture-intro.mjs, encoded to media/video/bg-sim-intro.mp4
// usage: node compose-intro.mjs [--no-encode]
import { existsSync, mkdirSync } from "node:fs";
import path from "node:path";
import { chromium, framesDir, repoRoot } from "./lib.mjs";
import { writeHtml, fileUrl, esc } from "./theme.mjs";
import { encode } from "./encode.mjs";

const SCENES = [
  { id: "s02", title: "Start page and example gallery", sub: "Open an example: it becomes your own project copy.", stills: [
    ["1-start", "Start page: new project, recent projects, 27 examples"],
    ["2-gallery", "The example gallery, every sample with a thumbnail"],
    ["3-gallery-more", "From a DC motor to a quadcopter and an aerial manipulator"],
    ["4-card", "Open sample: creates a project copy"],
    ["5-opened", "The copy opens in the editor, ready to edit and run"] ] },
  { id: "s03", title: "Diagram editor", sub: "Iconic components, bond graphs, block diagrams and subsystems.", stills: [
    ["1-iconic", "Iconic components: voltage source, motor, damper, shafts"],
    ["2-iconic-inspector", "Select a block: parameters, units and ports in the inspector"],
    ["3-bondgraph", "The same motor as a bond graph: letter-only elements, causal strokes, domain colours"],
    ["4-blocks", "Block diagrams: step, PID, discrete controller"],
    ["5-subsystems", "Subsystems keep large models readable"],
    ["6-subsystem-inside", "Double-click to enter: breadcrumbs show where you are"] ] },
  { id: "s04", title: "Code tab", sub: "The modelling language: equation blocks and @discrete controllers.", stills: [
    ["1-code-model", "Every model is also text: the Code tab"],
    ["2-discrete-controller", "A @discrete LQG firmware, written as an equation block"],
    ["3-equation-block", "An equation block with an event: the bouncing ball"] ] },
  { id: "s05", title: "Check and diagnostics", sub: "Units, causality and live feedback while you edit.", stills: [
    ["1-unit-error", "Diagnostics: an undeclared name is reported with its block and a fix hint"],
    ["2-fixed", "Parameters carry units (N·m·s/rad); fix the value and the diagnostics clear"],
    ["3-causality", "Causality: one causal stroke on every bond end"],
    ["4-hover-readout", "Hover a bond: effort, flow and power at the plot cursor"] ] },
  { id: "s06", title: "Run", sub: "The real Julia worker, streamed live into the plots.", stills: [
    ["1-ready", "Press Run: the real Julia / ModelingToolkit worker compiles and simulates"],
    ["2-running", "While the run is still going, the signals already stream into the plot"],
    ["2b-running", "The curve keeps growing live as the worker integrates"],
    ["3-plots", "Plot any signal: double-click it in the signal browser"],
    ["4-zoom-cursor", "Drag to zoom; the cursor reads every curve"],
    ["5-two-panels", "Several plot panels share one cursor"],
    ["6-popout", "Pop a plot out into its own window"] ] },
  { id: "s07", title: "Multibond mechanics", sub: "2D and 3D rigid bodies, joints and contact.", stills: [
    ["1-planar", "Planar multibonds: two strokes per bond"],
    ["2-frame-pill", "Each bond carries its reference frame"],
    ["3-connection-inspector", "The connection inspector: frame, domain and component units"],
    ["4-arm2d", "A planar 2-link arm"],
    ["5-arm3d", "A six-axis arm: three strokes per spatial bond"],
    ["6-contact", "Contact: compliant ground, Hunt-Crossley force, friction"] ] },
  { id: "s08", title: "Inputs and controllers", sub: "CSV sources and discrete LQR / Kalman controllers.", stills: [
    ["1-planar-links", "planar-links: three arms driven by CSV input sources"],
    ["2-csv-inspector", "A CsvSource block with its file parameter"],
    ["3-lqg-diagram", "drivetrain-kalman: plant plus a discrete LQG controller"],
    ["4-estimate", "The Kalman estimate of the load speed against the plant"] ] },
  { id: "s09", title: "3D view", sub: "SDF scenes driven by signal bindings, synced with the plot cursor.", stills: [
    ["1-plot-cursor", "Move the plot cursor..."],
    ["2-3d-t5", "...and the 3D scene follows: the arm at the start"],
    ["3-3d-t50", "Halfway through the motion"],
    ["4-3d-t95", "Near the target pose"],
    ["5-bindings", "Signal bindings map model signals to joint positions"],
    ["6-popout", "Pop the viewer out into its own window"] ] },
  { id: "s10", title: "Debugger", sub: "Breakpoints, stepping, Break when, Watch, Explain, live edit, Replay and Rewind.", stills: [
    ["1-breakpoint", "A breakpoint in the controller code"],
    ["2-paused", "The run pauses on the highlighted line"],
    ["3-variables", "Variables: the estimator state vector"],
    ["4-stepping", "Step statement by statement (F10)"],
    ["5-break-on-event", "Break on events: paused at the first bounce"],
    ["6-live-edit", "Live edit: change the restitution while paused"],
    ["7-edits-replay", "The edit is listed; Replay re-runs it from the start"],
    ["8-replayed", "The replayed run with the edit applied"],
    ["9-break-when", "Break when: Motor1/i > 5"],
    ["10-watch-pause", "The watch fires and the run pauses"],
    ["11-rewind-menu", "Rewind to an earlier cursor time"],
    ["12-explain", "Explain: where an eliminated signal comes from"] ] },
  { id: "s11", title: "Docs tab", sub: "Per-model Markdown with KaTeX math, images and model links.", stills: [
    ["1-overview", "Documentation lives with the model"],
    ["2-scrolled", "Images and figures from the project"],
    ["3-math", "KaTeX math"],
    ["4-links", "Links jump to blocks and signals of the model"] ] },
  { id: "s12", title: "Polish", sub: "Keyboard shortcuts and a dark theme.", stills: [
    ["1-shortcuts", "Press ? for the keyboard shortcuts"],
    ["2-light", "A light theme..."],
    ["3-dark", "...and the dark theme"],
    ["4-gallery", "Back to the gallery: open an example and try it"] ] },
];

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
