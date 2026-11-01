#!/usr/bin/env node
// Video 1 at 30 fps: real-time recordings (CDP screencast, visible cursor, paced actions) of the real app.
// Output: media/video/frames/intro30/<scene>-<n>/{*.jpg,timeline.json} and intro30/manifest.json
// usage: node capture-intro30.mjs [--scene s02,s05,...]
import { writeFileSync, readFileSync, existsSync } from "node:fs";
import path from "node:path";
import { launchBrowser, BASE, createProject, newPage, openModel, outDir, sleep, framesDir } from "./lib.mjs";
import { installCursor, Recorder, glide, hover, click, dblclick, typeInto, drag, key, wheel, slide } from "./rec.mjs";

const arg = (n) => { const i = process.argv.indexOf(n); return i > 0 ? process.argv[i + 1] : null; };
const only = arg("--scene")?.split(",") ?? null;
const root = outDir("intro30");
const manifestFile = path.join(root, "manifest.json");
const manifest = existsSync(manifestFile) ? JSON.parse(readFileSync(manifestFile, "utf8")) : {};
const HIDE_TOASTS = '[role="status"]:not([data-testid="run-status"]):not([data-testid="worker-status"]):not([data-testid="hover-readout"]), .toast { display: none !important; }';
const DOCK70 = () => { try { localStorage.setItem("bgsim.layout.rows", JSON.stringify({ main: 28, dock: 72 })); } catch {} };

let browser;
const projects = [];
const mk = async (ex) => { const p = await createProject(ex, ex.slice(0, 12)); projects.push(p); return p; };
const T = (page, name, exact = false) => page.getByRole("tab", { name, exact });
let curRec = null;
const status = async (page, s, t = 300000) => {
  const r = curRec && !curRec.stopped ? curRec : null;
  r?.pause();
  await page.waitForFunction((x) => document.querySelector('[data-testid="run-status"]')?.getAttribute("data-status") === x, s, { timeout: t });
  await r?.resume();
};

async function newScenePage(opts = {}) {
  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1, colorScheme: "dark" });
  await installCursor(ctx);
  if (opts.dock70) await ctx.addInitScript(DOCK70);
  return ctx.newPage();
}
class Scene {
  constructor(id) { this.id = id; this.recs = []; }
  async rec(page) { const r = new Recorder(page, root, `${this.id}-${this.recs.length}`); this.recs.push(r); await r.start(); curRec = r; return r; }
  async finish() {
    const out = [];
    for (const r of this.recs) { if (!r.stopped) await r.stop(); out.push(path.relative(root, r.dir).replace(/\\/g, "/")); }
    manifest[this.id] = out;
    writeFileSync(manifestFile, JSON.stringify(manifest, null, 1));
  }
}
/** Mark a still moment, hold it for `hold` seconds. */
async function mark(r, name, hold = 1.4) { r.mark(name); r.marks[r.marks.length - 1].hold = hold; await sleep(hold * 1000); }
/** Load a model with the recording paused (page loads are not interesting), then resume. */
async function go(r, page, project, model, fit = true) {
  r.pause();
  await openModel(page, project, model);
  await page.addStyleTag({ content: HIDE_TOASTS });
  await sleep(1200);
  if (fit) { await page.getByTestId("fit-view").click(); await sleep(1300); }
  await page.mouse.move(960, 600);
  await r.resume();
}
const node = (page, name) => page.locator(`[data-testid="diagram-node"][data-node-name="${name}"]`);
const sig = (page, id) => page.locator(`[data-testid="signal-item"][data-signal-id="${id}"]`);
async function plotSignals(page, ids) {
  await click(page, T(page, "Signals"));
  for (const id of ids) await dblclick(page, sig(page, id), { pause: 350 });
  await click(page, T(page, "Plots"));
  await page.locator('[data-testid="plot-chart"] .u-over').first().waitFor({ timeout: 30000 });
  await sleep(600);
}
async function plotBox(page, idx = 0) { return page.locator('[data-testid="plot-chart"] .u-over').nth(idx).boundingBox(); }
async function sweepPlot(page, f0, f1, ms = 1400, idx = 0) {
  const b = await plotBox(page, idx);
  await glide(page, b.x + b.width * f0, b.y + b.height * 0.5, 500);
  await glide(page, b.x + b.width * f1, b.y + b.height * 0.5, ms);
  await sleep(300);
}
async function dragZoom(page, f0, f1, idx = 0) {
  const b = await plotBox(page, idx);
  const y = b.y + b.height * 0.45;
  await drag(page, { x: b.x + b.width * f0, y }, { x: b.x + b.width * f1, y }, { dragMs: 800 });
  await sleep(700);
}
async function edgePoint(page, id) {
  return page.evaluate((edgeId) => {
    const path = document.querySelector(`[data-testid="edge-${edgeId}"] .react-flow__edge-path`);
    if (!path) return null;
    const m = path.getScreenCTM();
    const p = path.getPointAtLength(path.getTotalLength() / 2).matrixTransform(m);
    return { x: p.x, y: p.y };
  }, id);
}
async function popStill(page, rec, button, file, w = 1400, h = 800) {
  const popP = page.waitForEvent("popup");
  await click(page, page.getByTestId(button));
  const pop = await popP;
  await pop.setViewportSize({ width: w, height: h });
  await sleep(3000);
  await pop.screenshot({ path: file, type: "jpeg", quality: 92 });
  rec.injectStill(file, 2.4);
  rec.marks.push({ name: "6-popout", vt: rec.vt(), hold: 0 });
  await pop.close().catch(() => {});
  await sleep(600);
}

const scenes = {
  async s02() {
    const S = new Scene("s02");
    const page = await newScenePage();
    await page.goto(BASE + "/");
    await page.waitForFunction(() => document.querySelector('[data-testid="start-page"]')?.getAttribute("data-state") === "ready", null, { timeout: 30000 });
    await sleep(1500);
    const r = await S.rec(page);
    await mark(r, "1-start", 2.0);
    await wheel(page, 960, 700, 700, { steps: 28 });
    await mark(r, "2-gallery", 1.2);
    await wheel(page, 960, 700, 900, { steps: 32 });
    await mark(r, "3-gallery-more", 1.0);
    const card = page.getByTestId("example-card-dc-motor");
    await card.scrollIntoViewIfNeeded();
    await hover(page, card.getByTestId("example-open-dc-motor"), { ms: 800 });
    await mark(r, "4-card", 1.0);
    await click(page, page.getByTestId("example-open-dc-motor"));
    // The imported copy opens on its project overview: pick the model there.
    await page.getByTestId("model-card-iconic").waitFor({ timeout: 60000 });
    await sleep(1200);
    await click(page, page.getByTestId("model-card-iconic"));
    await page.getByTestId("diagram-node").first().waitFor({ timeout: 60000 });
    await sleep(2500);
    await page.addStyleTag({ content: HIDE_TOASTS });
    await click(page, page.getByTestId("fit-view"));
    await sleep(1200);
    await mark(r, "5-opened", 1.8);
    await S.finish(); await page.context().close();
  },

  async s03() {
    const S = new Scene("s03");
    const page = await newScenePage();
    const dc = await mk("dc-motor");
    await openModel(page, dc, "iconic");
    await page.addStyleTag({ content: HIDE_TOASTS });
    await sleep(1200);
    await page.getByTestId("fit-view").click(); await sleep(1300);
    const r = await S.rec(page);
    await mark(r, "1-iconic", 1.8);
    await click(page, node(page, "Motor1"), { pause: 900 });
    await mark(r, "2-iconic-inspector", 1.8);
    const b = await node(page, "Damp1").boundingBox();
    await drag(page, { x: b.x + b.width / 2, y: b.y + b.height / 2 }, { x: b.x + b.width / 2, y: b.y + b.height / 2 + 110 }, { pause: 700 });
    await mark(r, "2b-drag", 1.2);
    await key(page, "Control+Z", 900);
    await go(r, page, dc, "bondgraph");
    await mark(r, "3-bondgraph", 2.4);
    await go(r, page, dc, "speed-control");
    await mark(r, "4-blocks", 2.0);
    const rlc = await mk("rlc-dual");
    await go(r, page, rlc, "rlc-dual");
    await mark(r, "5-subsystems", 1.6);
    await click(page, node(page, "Bondgraph"));
    await page.mouse.dblclick(...(await (async () => { const bb = await node(page, "Bondgraph").boundingBox(); return [bb.x + 8, bb.y + 8]; })()));
    await page.getByTestId("subsystem-breadcrumbs").waitFor();
    await sleep(900);
    await click(page, page.getByTestId("fit-view"));
    await sleep(900);
    await mark(r, "6-subsystem-inside", 2.0);
    await S.finish(); await page.context().close();
  },

  async s04() {
    const S = new Scene("s04");
    const page = await newScenePage();
    const dk = await mk("drivetrain-kalman");
    await openModel(page, dk, "drivetrain-kalman");
    await page.addStyleTag({ content: HIDE_TOASTS });
    await sleep(1200);
    const r = await S.rec(page);
    await click(page, T(page, "Code"));
    await sleep(900);
    await mark(r, "1-code-model", 1.6);
    const select = page.getByTestId("code-source-select");
    await hover(page, select);
    await select.selectOption("project:LQGController");
    await page.locator(".cm-content").waitFor();
    await sleep(1000);
    await mark(r, "2-discrete-controller", 2.4);
    await wheel(page, 900, 450, 300, { steps: 15 });
    await sleep(600);
    const bb = await mk("bouncing-ball");
    await go(r, page, bb, "bouncing-ball", false);
    await click(page, T(page, "Code"));
    await sleep(500);
    const opt = page.getByTestId("code-source-select");
    const values = await opt.locator("option").evaluateAll((o) => o.map((x) => x.value));
    const ball = values.find((v) => /Ball/.test(v));
    if (ball) { await hover(page, opt); await opt.selectOption(ball); }
    await sleep(1000);
    await mark(r, "3-equation-block", 2.4);
    await S.finish(); await page.context().close();
  },

  async s05() {
    const S = new Scene("s05");
    const page = await newScenePage();
    const dc = await mk("dc-motor");
    await openModel(page, dc, "iconic");
    await page.addStyleTag({ content: HIDE_TOASTS });
    await sleep(1200);
    await page.getByTestId("fit-view").click(); await sleep(1300);
    const r = await S.rec(page);
    await click(page, node(page, "Damp1"));
    const d = page.getByTestId("inspector-param-d");
    await d.waitFor();
    await typeInto(page, d, "1e-6*V", { delay: 110, pause: 1500 });
    await click(page, T(page, "Diagnostics"));
    await sleep(1200);
    await mark(r, "1-unit-error", 2.6);
    await click(page, node(page, "Damp1"));
    await typeInto(page, d, "1e-6", { delay: 110, pause: 1400 });
    await mark(r, "2-fixed", 2.0);
    const rlc = await mk("rlc-dual");
    r.pause();
    await openModel(page, rlc, "rlc-dual");
    await page.addStyleTag({ content: HIDE_TOASTS });
    await sleep(1200);
    await node(page, "Bondgraph").click();
    const bb = await node(page, "Bondgraph").boundingBox();
    await page.mouse.dblclick(bb.x + 8, bb.y + 8);
    await page.getByTestId("subsystem-breadcrumbs").waitFor();
    await sleep(1500);
    await page.mouse.move(960, 500);
    await r.resume();
    await mark(r, "3-causality", 2.4);
    await click(page, page.getByTestId("run-button"));
    await status(page, "done", 120000);
    await plotSignals(page, ["Bondgraph/C1/p.e"]);
    await sweepPlot(page, 0.2, 0.35, 900);
    const eids = await page.evaluate(() => [...document.querySelectorAll('[data-testid^="edge-"]')].map((e) => e.getAttribute("data-testid").replace("edge-", "")).filter((x) => document.querySelector(`[data-testid="edge-${x}"] .react-flow__edge-path`)));
    const pt = await edgePoint(page, eids[0]);
    if (pt) { await glide(page, pt.x, pt.y, 1100); await page.getByTestId("hover-readout").waitFor({ timeout: 8000 }).catch(() => {}); await sleep(600); }
    await mark(r, "4-hover-readout", 2.6);
    await S.finish(); await page.context().close();
  },

  async s06() {
    const S = new Scene("s06");
    const page = await newScenePage();
    const pd = await mk("pendulum-triple-fixed");
    await openModel(page, pd, "pendulum-triple-fixed");
    await page.addStyleTag({ content: HIDE_TOASTS });
    await sleep(1200);
    await page.getByTestId("fit-view").click(); await sleep(1300);
    const r = await S.rec(page);
    await mark(r, "1-ready", 1.2);
    await click(page, page.getByTestId("run-button"), { pause: 200 });
    await status(page, "running", 120000);
    await sleep(2500);
    await plotSignals(page, ["Joint1/qdout"]);
    await mark(r, "2-running", 1.0);
    await sleep(3500);
    await mark(r, "2b-running", 1.0);
    await click(page, page.getByTestId("stop-button"), { pause: 600 });
    await sleep(1500);
    await r.stop();
    await page.context().close();

    const p2 = await newScenePage();
    const q = await mk("quarter-car");
    await openModel(p2, q, "quarter-car");
    await p2.addStyleTag({ content: HIDE_TOASTS });
    await sleep(1200);
    const r2 = await S.rec(p2);
    await click(p2, p2.getByTestId("run-button"));
    await status(p2, "done");
    await sleep(800);
    await plotSignals(p2, ["SInt/y", "UInt/y"]);
    await sweepPlot(p2, 0.1, 0.5, 1200);
    await mark(r2, "3-plots", 1.4);
    await dragZoom(p2, 0.1, 0.45);
    await sweepPlot(p2, 0.3, 0.7, 1200);
    await mark(r2, "4-zoom-cursor", 1.4);
    await click(p2, p2.getByTestId("add-plot-panel"));
    await click(p2, T(p2, "Signals"));
    await dblclick(p2, sig(p2, "Susp/a.e"));
    await click(p2, T(p2, "Plots"));
    await sleep(900);
    await sweepPlot(p2, 0.3, 0.55, 1000, 1);
    await mark(r2, "5-two-panels", 1.4);
    await popStill(p2, r2, "detach-plot", path.join(root, "s06-popout.jpg"));
    await S.finish(); await p2.context().close();
  },

  async s07() {
    const S = new Scene("s07");
    const page = await newScenePage();
    const mb = await mk("multibond-pendulum-2d");
    await openModel(page, mb, "pendulum");
    await page.addStyleTag({ content: HIDE_TOASTS });
    await sleep(1200);
    await page.getByTestId("fit-view").click(); await sleep(1300);
    const r = await S.rec(page);
    await mark(r, "1-planar", 1.8);
    const edgeId = await page.evaluate(() => { const e = document.querySelector('[data-testid^="edge-"][data-multibond-strokes]'); return e ? e.getAttribute("data-testid").replace("edge-", "") : null; });
    if (edgeId) {
      let pt = await edgePoint(page, edgeId);
      await glide(page, pt.x, pt.y, 900);
      await sleep(700);
      await mark(r, "2-frame-pill", 1.2);
      pt = await edgePoint(page, edgeId);
      await page.mouse.down(); await sleep(70); await page.mouse.up();
      await page.getByTestId("inspector-connections").waitFor({ timeout: 10000 }).catch(() => {});
      await sleep(600);
      await mark(r, "3-connection-inspector", 2.6);
    }
    const a2 = await mk("robot-arm-2d");
    await go(r, page, a2, "arm");
    await mark(r, "4-arm2d", 1.8);
    const a3 = await mk("robot-arm-3d");
    await go(r, page, a3, "arm");
    await mark(r, "5-arm3d", 1.8);
    const cp = await mk("cube-pyramid-3d");
    await go(r, page, cp, "sequence-contact");
    await mark(r, "6-contact", 1.8);
    await S.finish(); await page.context().close();
  },

  async s08() {
    const S = new Scene("s08");
    const page = await newScenePage();
    const pl = await mk("planar-links");
    await openModel(page, pl, "planar-links");
    await page.addStyleTag({ content: HIDE_TOASTS });
    await sleep(1200);
    await page.getByTestId("fit-view").click(); await sleep(1300);
    const r = await S.rec(page);
    await mark(r, "1-planar-links", 2.0);
    const csv = await page.evaluate(() => { const n = [...document.querySelectorAll('[data-testid="diagram-node"]')].find((e) => /csv/i.test(e.getAttribute("data-node-name") ?? "")); return n ? n.getAttribute("data-node-name") : null; });
    if (csv) { await click(page, page.getByTestId(`tree-node-${csv}`)); await sleep(700); }
    await mark(r, "2-csv-inspector", 2.4);
    const dk = await mk("drivetrain-kalman");
    await go(r, page, dk, "drivetrain-kalman");
    await mark(r, "3-lqg-diagram", 1.8);
    await click(page, page.getByTestId("run-button"));
    await status(page, "done");
    await plotSignals(page, ["IW2/p.f", "LQG/w_load_hat"]);
    await sweepPlot(page, 0.05, 0.5, 1800);
    await mark(r, "4-estimate", 2.0);
    await S.finish(); await page.context().close();
  },

  async s09() {
    const S = new Scene("s09");
    const page = await newScenePage({ dock70: true });
    const a3 = await mk("robot-arm-3d");
    await openModel(page, a3, "arm");
    await page.addStyleTag({ content: HIDE_TOASTS });
    await sleep(1200);
    await page.getByTestId("run-button").click();
    await status(page, "done");
    const r = await S.rec(page);
    await plotSignals(page, ["J1/qout", "J2/qout", "J3/qout"]);
    await sweepPlot(page, 0.1, 0.55, 1500);
    await mark(r, "1-plot-cursor", 1.2);
    await click(page, T(page, "3D View"));
    await page.waitForFunction(() => document.querySelector('[data-testid="scene-view"]')?.getAttribute("data-state") === "loaded", null, { timeout: 90000 });
    await page.waitForFunction(() => document.querySelector('[data-testid="playback-bar"]')?.getAttribute("data-mode") === "playback", null, { timeout: 90000 });
    await sleep(800);
    await click(page, page.getByTestId("scene-tree-toggle"), { pause: 600 }).catch(() => {});
    const slider = page.getByTestId("playback-time");
    const end = Number(await slider.getAttribute("max"));
    await slide(page, slider, end * 0.55, end * 0.05, 700);
    await mark(r, "2-3d-t5", 1.2);
    await click(page, page.getByTestId("playback-toggle"), { pause: 100 });
    await sleep(3800);
    await mark(r, "3-3d-t50", 0.3);
    await click(page, page.getByTestId("playback-toggle"), { pause: 400 });
    await slide(page, slider, end * 0.5, end * 0.95, 1400);
    await mark(r, "4-3d-t95", 1.2);
    await click(page, page.getByTestId("bindings-toggle"), { pause: 900 });
    await mark(r, "5-bindings", 2.4);
    await click(page, page.getByTestId("bindings-toggle"), { pause: 400 });
    await popStill(page, r, "detach-viewer", path.join(root, "s09-popout.jpg"));
    await S.finish(); await page.context().close();
  },

  async s10() {
    const S = new Scene("s10");
    const gutter = async (page, text) => {
      const line = page.locator(".cm-line", { hasText: text }).first();
      await line.scrollIntoViewIfNeeded();
      const lb = await line.boundingBox();
      const gb = await page.locator(".cm-bp-gutter").boundingBox();
      await glide(page, gb.x + gb.width / 2, lb.y + 9, 800);
      await sleep(200);
      await page.mouse.down(); await sleep(70); await page.mouse.up();
      await sleep(600);
    };
    const page = await newScenePage();
    const dk = await mk("drivetrain-kalman");
    await openModel(page, dk, "drivetrain-kalman");
    await page.addStyleTag({ content: HIDE_TOASTS });
    await sleep(1200);
    const r = await S.rec(page);
    await click(page, T(page, "Code"));
    const sel = page.getByTestId("code-source-select");
    await hover(page, sel);
    await sel.selectOption("project:LQGController");
    await page.locator(".cm-content").waitFor();
    await sleep(900);
    await gutter(page, "measurement update");
    await page.locator('[data-testid="bp-marker"][data-line="41"]').waitFor();
    await mark(r, "1-breakpoint", 1.6);
    await click(page, page.getByTestId("debug-button"), { pause: 300 });
    await status(page, "paused", 180000);
    await sleep(900);
    await mark(r, "2-paused", 2.0);
    await click(page, T(page, "Debug"));
    const xhat = page.locator('[data-testid^="var-"][data-testid$="-xhat"]').first();
    await xhat.waitFor({ timeout: 20000 });
    await click(page, xhat.locator("summary"));
    await sleep(600);
    await mark(r, "3-variables", 2.2);
    await click(page, T(page, "Code"));
    await key(page, "F10", 1300);
    await key(page, "F10", 1300);
    await mark(r, "4-stepping", 1.6);
    await key(page, "Shift+F5", 1500);
    await S.finish(); await page.context().close();

    const S2 = new Scene("s10b");
    const p2 = await newScenePage();
    const bb = await mk("bouncing-ball");
    await openModel(p2, bb, "bouncing-ball");
    await p2.addStyleTag({ content: HIDE_TOASTS });
    await sleep(1200);
    await p2.keyboard.press("Control+Enter");
    await status(p2, "done", 180000);
    const r2 = await S2.rec(p2);
    await click(p2, T(p2, "Debug"));
    await click(p2, p2.getByTestId("break-on-events"));
    await click(p2, p2.getByTestId("debug-button"), { pause: 300 });
    await status(p2, "paused", 60000);
    await sleep(900);
    await mark(r2, "5-break-on-event", 2.0);
    await click(p2, T(p2, "Diagram", true));
    await click(p2, node(p2, "Ball1"));
    const e = p2.getByTestId("inspector-param-e");
    await e.waitFor();
    await typeInto(p2, e, "0.6", { delay: 140, pause: 900 });
    await mark(r2, "6-live-edit", 2.2);
    await click(p2, T(p2, "Debug"));
    await click(p2, p2.getByTestId("break-on-events"));
    await click(p2, p2.getByTestId("debug-continue"), { pause: 300 });
    await status(p2, "done", 120000);
    await click(p2, T(p2, "Debug"));
    await sleep(600);
    await mark(r2, "7-edits-replay", 2.0);
    await click(p2, p2.getByTestId("edits-replay"), { pause: 300 });
    await sleep(3500);
    await plotSignals(p2, ["Ball1/h"]).catch(() => {});
    await mark(r2, "8-replayed", 2.0);
    await S2.finish(); await p2.context().close();

    const S3 = new Scene("s10c");
    const p3 = await newScenePage();
    const dc = await mk("dc-motor");
    await openModel(p3, dc, "iconic");
    await p3.addStyleTag({ content: HIDE_TOASTS });
    await sleep(1200);
    await p3.keyboard.press("Control+Enter");
    await status(p3, "done", 180000);
    const r3 = await S3.rec(p3);
    await plotSignals(p3, ["Motor1/i"]);
    await click(p3, T(p3, "Signals"));
    await click(p3, sig(p3, "Motor1/i"), { right: true });
    await click(p3, p3.getByTestId("signal-menu").getByTestId("break-when"));
    await p3.getByTestId("break-when-comparison").selectOption(">");
    await typeInto(p3, p3.getByTestId("break-when-value"), "5", { enter: false, pause: 700 });
    await mark(r3, "9-break-when", 2.0);
    await click(p3, p3.getByTestId("break-when-add"));
    await click(p3, p3.getByTestId("debug-button"), { pause: 300 });
    await status(p3, "paused", 120000);
    await click(p3, T(p3, "Debug"));
    await sleep(900);
    await mark(r3, "10-watch-pause", 2.0);
    await click(p3, T(p3, "Plots"));
    await sweepPlot(p3, 0.1, 0.45, 900);
    const ob = await plotBox(p3);
    await click(p3, p3.locator('[data-testid="plot-chart"] .u-over').first(), { right: true, dx: ob.width * (0.45 - 0.5), dy: 60 - ob.height / 2, pause: 500 });
    await mark(r3, "11-rewind-menu", 1.8);
    await click(p3, p3.getByTestId("plot-rewind"), { pause: 300 });
    await status(p3, "paused", 120000);
    await click(p3, T(p3, "Signals"));
    await click(p3, sig(p3, "Motor1/i"), { right: true });
    await click(p3, p3.getByTestId("signal-menu").getByTestId("explain-signal"));
    await p3.getByTestId("explain-popover").waitFor();
    await sleep(900);
    await mark(r3, "12-explain", 2.4);
    await p3.keyboard.press("Shift+F5");
    await S3.finish(); await p3.context().close();
  },

  async s11() {
    const S = new Scene("s11");
    const page = await newScenePage();
    const q = await mk("quadcopter");
    await openModel(page, q, "quadcopter");
    await page.addStyleTag({ content: HIDE_TOASTS });
    await sleep(1200);
    const r = await S.rec(page);
    await click(page, T(page, "Docs"));
    await page.getByTestId("docs-tab").waitFor();
    await click(page, page.getByTestId("docs-tree-item-overview"));
    await page.locator('[data-testid="docs-preview"] img').first().waitFor({ timeout: 15000 }).catch(() => {});
    await sleep(1200);
    await mark(r, "1-overview", 1.8);
    await wheel(page, 1000, 500, 700, { steps: 30 });
    await mark(r, "2-scrolled", 1.6);
    const dc = await mk("dc-motor");
    await go(r, page, dc, "iconic", false);
    await click(page, T(page, "Docs"));
    await click(page, page.getByTestId("docs-tree-item-physics"));
    await page.locator(".katex").first().waitFor({ timeout: 15000 });
    await sleep(900);
    await mark(r, "3-math", 2.2);
    await click(page, page.getByTestId("docs-tree-item-overview"));
    await hover(page, page.locator('[data-testid="docs-preview"] a[data-link-kind="block"]').first()).catch(() => {});
    await mark(r, "4-links", 2.0);
    await S.finish(); await page.context().close();
  },

  async s12() {
    const S = new Scene("s12");
    const page = await newScenePage();
    const dc = await mk("dc-motor");
    await openModel(page, dc, "iconic");
    await page.addStyleTag({ content: HIDE_TOASTS });
    await sleep(1200);
    await page.getByTestId("fit-view").click(); await sleep(1300);
    const r = await S.rec(page);
    await click(page, page.locator('[data-testid="diagram-node"]').first());
    await key(page, "?", 900);
    await page.getByTestId("shortcuts-overlay").waitFor();
    await mark(r, "1-shortcuts", 2.6);
    await key(page, "Escape", 600);
    await click(page, page.getByTestId("theme-toggle"), { pause: 900 });
    await mark(r, "2-light", 1.6);
    await click(page, page.getByTestId("theme-toggle"), { pause: 900 });
    await mark(r, "3-dark", 1.4);
    r.pause();
    await page.goto(BASE + "/");
    await page.waitForFunction(() => document.querySelector('[data-testid="start-page"]')?.getAttribute("data-state") === "ready", null, { timeout: 30000 });
    await sleep(1200);
    await r.resume();
    await mark(r, "4-gallery", 2.4);
    await S.finish(); await page.context().close();
  },
};

browser = await launchBrowser();
for (const s of Object.keys(scenes).filter((x) => !only || only.includes(x))) {
  console.log("scene", s);
  try { await scenes[s](); } catch (e) { console.log("FAIL", s, String(e).split("\n").slice(0, 3).join(" | ")); }
}
for (const p of projects) await fetch(`${BASE}/api/projects/${p}`, { method: "DELETE" }).catch(() => {});
await browser.close();
