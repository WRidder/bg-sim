#!/usr/bin/env node
// Video 1 capture: full-window 1920x1080 stills of the real app, one function per scene.
// Output: media/video/frames/intro/<scene>-<name>.png
// usage: node capture-intro.mjs [--scene s02,s03,...]   (default: all)
// Flows and selectors are taken from web/tests/e2e/{walkthrough,debug,domain-visual,example-docs,polish,plot-v2}.spec.ts
import { launchBrowser, BASE, createProject, newPage, openModel, runAndWait, outDir, sleep } from "./lib.mjs";

const arg = (n) => { const i = process.argv.indexOf(n); return i > 0 ? process.argv[i + 1] : null; };
const only = arg("--scene")?.split(",") ?? null;
const dir = outDir("intro");
const HIDE_TOASTS = '[role="status"]:not([data-testid="run-status"]):not([data-testid="worker-status"]):not([data-testid="hover-readout"]), .toast { display: none !important; }';

let browser;
const projects = [];

async function mk(example) {
  const p = await createProject(example, example.slice(0, 12));
  projects.push(p);
  return p;
}
async function snap(page, scene, name, opts = {}) {
  await page.mouse.move(opts.keepMouse ? opts.keepMouse[0] : 1900, opts.keepMouse ? opts.keepMouse[1] : 1060);
  await sleep(opts.wait ?? 350);
  await page.screenshot({ path: `${dir}/${scene}-${name}.png` });
  console.log("  snap", `${scene}-${name}`);
}
async function fit(page) {
  await page.getByTestId("fit-view").click();
  await sleep(1200);
}
async function tab(page, name, exact = false) {
  await page.getByRole("tab", { name, exact }).click();
  await sleep(400);
}
async function plot(page, ids) {
  await tab(page, "Signals");
  for (const id of ids) {
    await page.locator(`[data-testid="signal-item"][data-signal-id="${id}"]`).dblclick();
    await sleep(250);
  }
  await tab(page, "Plots");
  await page.locator('[data-testid="plot-chart"] .u-over').first().waitFor({ timeout: 30000 });
  await sleep(500);
}
async function hoverPlot(page, f, idx = 0) {
  const over = page.locator('[data-testid="plot-chart"] .u-over').nth(idx);
  const b = await over.boundingBox();
  await page.mouse.move(b.x + b.width * f, b.y + b.height * 0.5, { steps: 4 });
  await sleep(450);
}
async function dragRange(page, idx, from, to) {
  const over = page.locator('[data-testid="plot-chart"] .u-over').nth(idx);
  const b = await over.boundingBox();
  const y = b.y + b.height * 0.45;
  await page.mouse.move(b.x + b.width * from, y);
  await page.mouse.down();
  await page.mouse.move(b.x + b.width * to, y, { steps: 12 });
  await page.mouse.up();
  await sleep(900);
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
async function open(page, project, model) {
  await openModel(page, project, model);
  await page.addStyleTag({ content: HIDE_TOASTS });
  await sleep(1200);
}
async function viewer(page) {
  await tab(page, "3D View");
  await page.waitForFunction(() => document.querySelector('[data-testid="scene-view"]')?.getAttribute("data-state") === "loaded", null, { timeout: 90000 });
  await page.waitForFunction(() => document.querySelector('[data-testid="playback-bar"]')?.getAttribute("data-mode") === "playback", null, { timeout: 90000 });
  await sleep(800);
}
async function setTime(page, f) {
  const slider = page.getByTestId("playback-time");
  const end = Number(await slider.getAttribute("max"));
  const step = 0.001;
  await slider.fill(String(Number((Math.round((end * f) / step) * step).toFixed(3))));
  await sleep(600);
}

const scenes = {
  // ---- 2: start page and gallery
  async s02() {
    const page = await newPage(browser);
    await page.goto(BASE + "/");
    await page.getByTestId("start-page").waitFor({ timeout: 30000 });
    await page.waitForFunction(() => document.querySelector('[data-testid="start-page"]')?.getAttribute("data-state") === "ready", null, { timeout: 30000 });
    await sleep(1500);
    await snap(page, "s02", "1-start");
    await page.getByTestId("example-gallery").scrollIntoViewIfNeeded();
    await page.mouse.move(960, 700);
    await page.mouse.wheel(0, 700);
    await sleep(800);
    await snap(page, "s02", "2-gallery", { keepMouse: [1900, 1060] });
    await page.mouse.move(960, 700);
    await page.mouse.wheel(0, 900);
    await sleep(800);
    await snap(page, "s02", "3-gallery-more");
    await page.getByTestId("example-card-dc-motor").scrollIntoViewIfNeeded();
    await page.getByTestId("example-card-dc-motor").hover();
    await sleep(500);
    await snap(page, "s02", "4-card", { keepMouse: [960, 540] });
    await page.getByTestId("example-open-dc-motor").click();
    // The imported copy opens on its project overview: pick the model there.
    await page.getByTestId("model-card-iconic").click({ timeout: 60000 });
    await page.getByTestId("diagram-node").first().waitFor({ timeout: 60000 });
    await sleep(2500);
    await page.addStyleTag({ content: HIDE_TOASTS });
    await fit(page);
    await snap(page, "s02", "5-opened");
    await page.context().close();
  },

  // ---- 3: diagram editor
  async s03() {
    const page = await newPage(browser);
    const dc = await mk("dc-motor");
    await open(page, dc, "iconic");
    await fit(page);
    await snap(page, "s03", "1-iconic");
    await page.locator('[data-testid="diagram-node"][data-node-name="Motor1"]').click();
    await sleep(700);
    await snap(page, "s03", "2-iconic-inspector", { keepMouse: [1100, 900] });
    await open(page, dc, "bondgraph");
    await fit(page);
    await snap(page, "s03", "3-bondgraph");
    await open(page, dc, "speed-control");
    await fit(page);
    await snap(page, "s03", "4-blocks");
    const rlc = await mk("rlc-dual");
    await open(page, rlc, "rlc-dual");
    await fit(page);
    await snap(page, "s03", "5-subsystems");
    const bg = page.locator('[data-testid="diagram-node"][data-node-name="Bondgraph"]');
    await bg.click();
    await bg.dblclick({ position: { x: 8, y: 8 } });
    await page.getByTestId("subsystem-breadcrumbs").waitFor();
    await sleep(900);
    await fit(page);
    await snap(page, "s03", "6-subsystem-inside");
    await page.context().close();
  },

  // ---- 4: code tab
  async s04() {
    const page = await newPage(browser);
    const dk = await mk("drivetrain-kalman");
    await open(page, dk, "drivetrain-kalman");
    await tab(page, "Code");
    const select = page.getByTestId("code-source-select");
    await sleep(800);
    await snap(page, "s04", "1-code-model");
    await select.selectOption("project:LQGController");
    await page.locator(".cm-content").waitFor();
    await sleep(1000);
    await snap(page, "s04", "2-discrete-controller");
    const bb = await mk("bouncing-ball");
    await open(page, bb, "bouncing-ball");
    await tab(page, "Code");
    await sleep(500);
    const opt = page.getByTestId("code-source-select");
    const values = await opt.locator("option").evaluateAll((o) => o.map((x) => x.value));
    const ball = values.find((v) => /Ball/.test(v));
    if (ball) await opt.selectOption(ball);
    await sleep(1000);
    await snap(page, "s04", "3-equation-block");
    await page.context().close();
  },

  // ---- 5: check and diagnostics
  async s05() {
    const page = await newPage(browser);
    const dc = await mk("dc-motor");
    await open(page, dc, "iconic");
    await fit(page);
    // a unit error through the real inspector
    await page.locator('[data-testid="diagram-node"][data-node-name="Damp1"]').click();
    const d = page.getByTestId("inspector-param-d");
    await d.waitFor();
    await d.fill("1e-6*V");
    await d.press("Enter");
    await sleep(2500);
    await tab(page, "Diagnostics");
    await sleep(800);
    await snap(page, "s05", "1-unit-error", { keepMouse: [1100, 950] });
    // fix it again
    await page.locator('[data-testid="diagram-node"][data-node-name="Damp1"]').click();
    await d.fill("1e-6");
    await d.press("Enter");
    await sleep(2000);
    await snap(page, "s05", "2-fixed", { keepMouse: [1100, 950] });
    // causality + hover readout on the bond graph
    const rlc = await mk("rlc-dual");
    await open(page, rlc, "rlc-dual");
    const bg = page.locator('[data-testid="diagram-node"][data-node-name="Bondgraph"]');
    await bg.click();
    await bg.dblclick({ position: { x: 8, y: 8 } });
    await page.getByTestId("subsystem-breadcrumbs").waitFor();
    await sleep(1500);
    await snap(page, "s05", "3-causality");
    await page.getByTestId("run-button").click();
    await page.waitForFunction(() => document.querySelector('[data-testid="run-status"]')?.getAttribute("data-status") === "done", null, { timeout: 120000 });
    await plot(page, ["Bondgraph/C1/p.e"]);
    await hoverPlot(page, 0.35);
    const eids = await page.evaluate(() => [...document.querySelectorAll('[data-testid^="edge-"]')].map((e) => e.getAttribute("data-testid").replace("edge-", "")).filter((x) => document.querySelector(`[data-testid="edge-${x}"] .react-flow__edge-path`)));
    console.log("  edges", eids.join(","));
    let got = null;
    for (const id of eids) {
      const pt = await edgePoint(page, id);
      if (!pt) continue;
      await page.mouse.move(Math.round(pt.x) - 8, Math.round(pt.y) - 8);
      await page.mouse.move(Math.round(pt.x), Math.round(pt.y), { steps: 4 });
      const ok = await page.getByTestId("hover-readout").waitFor({ timeout: 2500 }).then(() => true, () => false);
      console.log("  hover", id, pt, ok);
      if (ok) { got = pt; break; }
    }
    if (got) {
      await sleep(500);
      await snap(page, "s05", "4-hover-readout", { keepMouse: [Math.round(got.x), Math.round(got.y)] });
    }
    await page.context().close();
  },

  // ---- 6: run, live plots, zoom, cursor, multiple plots, pop-out
  async s06() {
    const pre = await newPage(browser);
    const pd = await mk("pendulum-triple-fixed");
    await open(pre, pd, "pendulum-triple-fixed");
    await fit(pre);
    await snap(pre, "s06", "1-ready");
    await pre.getByTestId("run-button").click();
    await pre.waitForFunction(() => document.querySelector('[data-testid="run-status"]')?.getAttribute("data-status") === "running", null, { timeout: 120000 });
    await sleep(6000);
    await tab(pre, "Signals");
    await pre.locator('[data-testid="signal-item"][data-signal-id="Joint1/qdout"]').dblclick();
    await tab(pre, "Plots");
    await sleep(1500);
    await snap(pre, "s06", "2-running", { keepMouse: [900, 800] });
    await sleep(4000);
    await snap(pre, "s06", "2b-running", { keepMouse: [900, 800] });
    await pre.getByTestId("stop-button").click().catch(() => {});
    await sleep(2500);
    await pre.context().close();
    const page = await newPage(browser);
    const q = await mk("quarter-car");
    await open(page, q, "quarter-car");
    await page.getByTestId("run-button").click();
    await page.waitForFunction(() => document.querySelector('[data-testid="run-status"]')?.getAttribute("data-status") === "done", null, { timeout: 300000 });
    await plot(page, ["SInt/y", "UInt/y"]);
    await snap(page, "s06", "3-plots", { keepMouse: [900, 800] });
    await dragRange(page, 0, 0.1, 0.45);
    await hoverPlot(page, 0.5);
    await snap(page, "s06", "4-zoom-cursor", { keepMouse: [960, 880] });
    await tab(page, "Plots");
    await page.getByTestId("add-plot-panel").click();
    await tab(page, "Signals");
    await page.locator('[data-testid="signal-item"][data-signal-id="Susp/a.e"]').dblclick();
    await tab(page, "Plots");
    await sleep(900);
    await hoverPlot(page, 0.4);
    await snap(page, "s06", "5-two-panels", { keepMouse: [960, 880] });
    const popupP = page.waitForEvent("popup");
    await page.getByTestId("detach-plot").click();
    const popup = await popupP;
    await popup.setViewportSize({ width: 1400, height: 800 });
    await popup.getByTestId("plot-panel").waitFor();
    await sleep(1200);
    await popup.screenshot({ path: dir + "/s06-6-popout.png" });
    console.log("  snap s06-6-popout");
    await popup.close().catch(() => {});
    await page.context().close();
  },

  // ---- 7: multibond mechanics
  async s07() {
    const page = await newPage(browser);
    const mb = await mk("multibond-pendulum-2d");
    await open(page, mb, "pendulum");
    await fit(page);
    const edgeId = await page.evaluate(() => { const e = document.querySelector('[data-testid^="edge-"][data-multibond-strokes]'); return e ? e.getAttribute("data-testid").replace("edge-", "") : null; });
    console.log("  multibond edge", edgeId);
    await snap(page, "s07", "1-planar");
    if (edgeId) {
      let pt = await edgePoint(page, edgeId);
      await page.mouse.move(Math.round(pt.x), Math.round(pt.y), { steps: 3 });
      await sleep(600);
      await snap(page, "s07", "2-frame-pill", { keepMouse: [Math.round(pt.x), Math.round(pt.y)] });
      pt = await edgePoint(page, edgeId);
      await page.mouse.click(Math.round(pt.x), Math.round(pt.y));
      await page.getByTestId("inspector-connections").waitFor({ timeout: 10000 }).catch(() => {});
      await sleep(600);
      await snap(page, "s07", "3-connection-inspector", { keepMouse: [1100, 1000] });
    }
    const a2 = await mk("robot-arm-2d");
    await open(page, a2, "arm");
    await fit(page);
    await snap(page, "s07", "4-arm2d");
    const a3 = await mk("robot-arm-3d");
    await open(page, a3, "arm");
    await fit(page);
    await snap(page, "s07", "5-arm3d");
    const cp = await mk("cube-pyramid-3d");
    await open(page, cp, "sequence-contact");
    await fit(page);
    await snap(page, "s07", "6-contact");
    await page.context().close();
  },

  // ---- 8: inputs and controllers
  async s08() {
    const page = await newPage(browser);
    const pl = await mk("planar-links");
    await open(page, pl, "planar-links");
    await fit(page);
    await snap(page, "s08", "1-planar-links");
    const csv = await page.evaluate(() => { const n = [...document.querySelectorAll('[data-testid="diagram-node"]')].find((e) => /csv|ref|src/i.test(e.getAttribute("data-node-name") ?? "")); return n ? n.getAttribute("data-node-name") : null; });
    console.log("  csv node", csv);
    if (csv) {
      await page.getByTestId(`tree-node-${csv}`).click();
      await sleep(900);
      await snap(page, "s08", "2-csv-inspector", { keepMouse: [1100, 1000] });
    }
    const dk = await mk("drivetrain-kalman");
    await open(page, dk, "drivetrain-kalman");
    await fit(page);
    await snap(page, "s08", "3-lqg-diagram");
    await page.getByTestId("run-button").click();
    await page.waitForFunction(() => document.querySelector('[data-testid="run-status"]')?.getAttribute("data-status") === "done", null, { timeout: 300000 });
    await plot(page, ["IW2/p.f", "LQG/w_load_hat"]);
    await hoverPlot(page, 0.3);
    await snap(page, "s08", "4-estimate", { keepMouse: [960, 880] });
    await page.context().close();
  },

  // ---- 9: 3D view
  async s09() {
    const page = await newPage(browser);
    await page.addInitScript(() => { try { localStorage.setItem("bgsim.layout.rows", JSON.stringify({ main: 28, dock: 72 })); } catch {} });
    const a3 = await mk("robot-arm-3d");
    await open(page, a3, "arm");
    await page.getByTestId("run-button").click();
    await page.waitForFunction(() => document.querySelector('[data-testid="run-status"]')?.getAttribute("data-status") === "done", null, { timeout: 300000 });
    await plot(page, ["J1/qout", "J2/qout", "J3/qout"]);
    await hoverPlot(page, 0.5);
    await snap(page, "s09", "1-plot-cursor", { keepMouse: [960, 880] });
    await viewer(page);
    await page.getByTestId("scene-tree-toggle").click().catch(() => {});
    await sleep(500);
    for (const [k, f] of [[2, 0.05], [3, 0.5], [4, 0.95]]) {
      await setTime(page, f);
      await snap(page, "s09", `${k}-3d-t${Math.round(f * 100)}`, { keepMouse: [1100, 700] });
    }
    await page.getByTestId("bindings-toggle").click();
    await sleep(900);
    await snap(page, "s09", "5-bindings");
    await page.getByTestId("bindings-toggle").click();
    const popupP = page.waitForEvent("popup");
    await page.getByTestId("detach-viewer").click();
    const popup = await popupP;
    await popup.setViewportSize({ width: 1400, height: 800 });
    await sleep(3000);
    await popup.screenshot({ path: dir + "/s09-6-popout.png" });
    console.log("  snap s09-6-popout");
    await popup.close().catch(() => {});
    await page.context().close();
  },

  // ---- 10: debugger (flows of web/tests/e2e/debug.spec.ts)
  async s10() {
    const gutter = async (page, text) => {
      const line = page.locator(".cm-line", { hasText: text }).first();
      await line.scrollIntoViewIfNeeded();
      const lb = await line.boundingBox();
      const gb = await page.locator(".cm-bp-gutter").boundingBox();
      await page.mouse.click(gb.x + gb.width / 2, lb.y + 9);
    };
    const status = (state, t = 180000) => (p) => p.waitForFunction((s) => document.querySelector('[data-testid="run-status"]')?.getAttribute("data-status") === s, state, { timeout: t });
    const paused = status("paused");
    const done = status("done");
    const page = await newPage(browser);
    const dk = await mk("drivetrain-kalman");
    await open(page, dk, "drivetrain-kalman");
    await tab(page, "Code");
    await page.getByTestId("code-source-select").selectOption("project:LQGController");
    await page.locator(".cm-content").waitFor();
    await sleep(800);
    await gutter(page, "measurement update");
    await page.locator('[data-testid="bp-marker"][data-line="41"]').waitFor();
    await snap(page, "s10", "1-breakpoint");
    await page.getByTestId("debug-button").click();
    await paused(page);
    await sleep(800);
    await snap(page, "s10", "2-paused");
    await tab(page, "Debug");
    const xhat = page.locator('[data-testid^="var-"][data-testid$="-xhat"]').first();
    await xhat.waitFor({ timeout: 20000 });
    await xhat.locator("summary").click();
    await sleep(500);
    await snap(page, "s10", "3-variables");
    await tab(page, "Code");
    await page.keyboard.press("F10");
    await sleep(1200);
    await page.keyboard.press("F10");
    await sleep(1200);
    await snap(page, "s10", "4-stepping");
    await page.keyboard.press("Shift+F5");
    await sleep(1500);
    await page.context().close();

    const p2 = await newPage(browser);
    const bb = await mk("bouncing-ball");
    await open(p2, bb, "bouncing-ball");
    await p2.keyboard.press("Control+Enter");
    await done(p2);
    await tab(p2, "Debug");
    await p2.getByTestId("break-on-events").check();
    await p2.getByTestId("debug-button").click();
    await paused(p2);
    await sleep(900);
    await snap(p2, "s10", "5-break-on-event");
    await tab(p2, "Diagram", true);
    await p2.locator('[data-testid="diagram-node"][data-node-name="Ball1"]').click();
    const e = p2.getByTestId("inspector-param-e");
    await e.waitFor();
    await e.fill("0.6");
    await e.press("Enter");
    await sleep(900);
    await snap(p2, "s10", "6-live-edit", { keepMouse: [1100, 1000] });
    await tab(p2, "Debug");
    await p2.getByTestId("break-on-events").uncheck();
    await sleep(500);
    await p2.getByTestId("debug-continue").click();
    await done(p2);
    await tab(p2, "Debug");
    await sleep(600);
    await snap(p2, "s10", "7-edits-replay");
    await p2.getByTestId("edits-replay").click();
    await sleep(3500);
    await plot(p2, ["Ball1/h"]).catch(() => {});
    await snap(p2, "s10", "8-replayed", { keepMouse: [960, 880] });
    await p2.context().close();

    const p3 = await newPage(browser);
    const dc = await mk("dc-motor");
    await open(p3, dc, "iconic");
    await p3.keyboard.press("Control+Enter");
    await done(p3);
    await plot(p3, ["Motor1/i"]);
    await tab(p3, "Signals");
    await p3.locator('[data-testid="signal-item"][data-signal-id="Motor1/i"]').click({ button: "right" });
    await p3.getByTestId("signal-menu").getByTestId("break-when").click();
    await p3.getByTestId("break-when-comparison").selectOption(">");
    await p3.getByTestId("break-when-value").fill("5");
    await sleep(500);
    await snap(p3, "s10", "9-break-when");
    await p3.getByTestId("break-when-add").click();
    await p3.getByTestId("debug-button").click();
    await paused(p3);
    await tab(p3, "Debug");
    await sleep(900);
    await snap(p3, "s10", "10-watch-pause");
    await tab(p3, "Plots");
    await hoverPlot(p3, 0.45);
    const over = p3.locator('[data-testid="plot-chart"] .u-over').first();
    const ob = await over.boundingBox();
    await over.click({ button: "right", position: { x: ob.width * 0.45, y: 60 } });
    await sleep(500);
    await snap(p3, "s10", "11-rewind-menu", { keepMouse: [Math.round(ob.x + ob.width * 0.45), Math.round(ob.y + 60)] });
    await p3.getByTestId("plot-rewind").click();
    await paused(p3);
    await tab(p3, "Signals");
    await p3.locator('[data-testid="signal-item"][data-signal-id="Motor1/i"]').click({ button: "right" });
    await p3.getByTestId("signal-menu").getByTestId("explain-signal").click();
    await p3.getByTestId("explain-popover").waitFor();
    await sleep(900);
    await snap(p3, "s10", "12-explain", { keepMouse: [1100, 1000] });
    await p3.keyboard.press("Shift+F5");
    await p3.context().close();
  },

  // ---- 11: docs
  async s11() {
    const page = await newPage(browser);
    const q = await mk("quadcopter");
    await open(page, q, "quadcopter");
    await tab(page, "Docs");
    await page.getByTestId("docs-tab").waitFor();
    await page.getByTestId("docs-tree-item-overview").click();
    await page.locator('[data-testid="docs-preview"] img').first().waitFor({ timeout: 15000 }).catch(() => {});
    await sleep(1500);
    await snap(page, "s11", "1-overview");
    await page.getByTestId("docs-preview").evaluate((e) => { e.scrollTop = 700; });
    await sleep(700);
    await snap(page, "s11", "2-scrolled");
    const dc = await mk("dc-motor");
    await open(page, dc, "iconic");
    await tab(page, "Docs");
    await page.getByTestId("docs-tree-item-physics").click();
    await page.locator(".katex").first().waitFor({ timeout: 15000 });
    await sleep(1000);
    await snap(page, "s11", "3-math");
    await page.getByTestId("docs-tree-item-overview").click();
    await sleep(800);
    await page.locator('[data-testid="docs-preview"] a[data-link-kind="block"]').first().hover().catch(() => {});
    await sleep(500);
    await page.screenshot({ path: dir + "/s11-4-links.png" });
    console.log("  snap s11-4-links");
    await page.context().close();
  },

  // ---- 12: polish
  async s12() {
    const page = await newPage(browser);
    const dc = await mk("dc-motor");
    await open(page, dc, "iconic");
    await fit(page);
    await page.locator('[data-testid="diagram-node"]').first().click();
    await page.keyboard.press("?");
    await page.getByTestId("shortcuts-overlay").waitFor();
    await sleep(700);
    await snap(page, "s12", "1-shortcuts");
    await page.keyboard.press("Escape");
    await page.getByTestId("theme-toggle").click();
    await sleep(900);
    await snap(page, "s12", "2-light");
    await page.getByTestId("theme-toggle").click();
    await sleep(900);
    await snap(page, "s12", "3-dark");
    await page.goto(BASE + "/");
    await page.waitForFunction(() => document.querySelector('[data-testid="start-page"]')?.getAttribute("data-state") === "ready", null, { timeout: 30000 });
    await sleep(1500);
    await snap(page, "s12", "4-gallery");
    await page.context().close();
  },
};

browser = await launchBrowser();
const todo = Object.keys(scenes).filter((s) => !only || only.includes(s));
for (const s of todo) {
  console.log("scene", s);
  try { await scenes[s](); } catch (e) { console.log("FAIL", s, String(e).split("\n").slice(0, 3).join(" | ")); }
}
for (const p of projects) await fetch(`${BASE}/api/projects/${p}`, { method: "DELETE" }).catch(() => {});
await browser.close();
