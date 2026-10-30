#!/usr/bin/env node
// Robird video, part 2: real-time (CDP screencast, visible cursor) recording of the model: pan/zoom over the diagram,
// a few blocks in the inspector, the Docs tab. Output: media/video/frames/robird60/ui/ (timeline.json + frames)
import { chromium, BASE, createProject, openModel, outDir, sleep, framesDir } from "./lib.mjs";
import { installCursor, Recorder, glide, click, wheel, drag } from "./rec.mjs";
import path from "node:path";

const root = outDir("robird60");
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1, colorScheme: "dark" });
await installCursor(ctx);
const page = await ctx.newPage();
const project = await createProject("robird", "robird-ui");
try {
  await openModel(page, project, "robird");
  await page.addStyleTag({ content: '[role="status"]:not([data-testid="run-status"]):not([data-testid="worker-status"]), .toast { display: none !important; }' });
  await sleep(2500);
  await page.getByTestId("fit-view").click();
  await sleep(1500);
  await page.mouse.move(960, 600);
  const rec = new Recorder(page, root, "ui");
  await rec.start();
  const mark = async (name, hold = 1.2) => { rec.mark(name); rec.marks[rec.marks.length - 1].hold = hold; await sleep(hold * 1000); };
  await mark("pan", 1.5);
  // slow zoom and pan over the whole diagram
  await wheel(page, 800, 500, 500, { steps: 24, dt: 40 });
  await drag(page, { x: 1100, y: 700 }, { x: 700, y: 450 }, { dragMs: 1600 });
  await drag(page, { x: 700, y: 450 }, { x: 1000, y: 350 }, { dragMs: 1600 });
  await sleep(500);
  const fit = async () => { await click(page, page.getByTestId("fit-view"), { pause: 900 }); };
  await fit();
  for (const [name, mk] of [["Crank", "crank"], ["Body", "body"], ["AeroL1", "aero"], ["Fctl", "ctrl"]]) {
    const n = page.locator(`[data-testid="diagram-node"][data-node-name="${name}"]`);
    const b = await n.boundingBox();
    if (!b) { console.log("no node", name); continue; }
    const x = b.x + b.width / 2, y = b.y + b.height / 2;
    await glide(page, x, y, 900);
    await sleep(300);
    for (let i = 0; i < 18; i++) { await page.mouse.wheel(0, -300); await sleep(45); }
    await sleep(500);
    await page.mouse.down(); await sleep(70); await page.mouse.up();
    await sleep(900);
    await mark(mk, 2.0);
    await fit();
  }
  await click(page, page.getByRole("tab", { name: "Docs" }));
  await page.getByTestId("docs-tab").waitFor();
  await click(page, page.getByTestId("docs-tree-item-overview"));
  await sleep(1500);
  await mark("docs", 1.5);
  await wheel(page, 1000, 500, 900, { steps: 36, dt: 35 });
  await mark("docs2", 1.5);
  await rec.stop();
  console.log("ui recorded", rec.frames.length, "frames");
} finally {
  await fetch(`${BASE}/api/projects/${project}`, { method: "DELETE" }).catch(() => {});
  await browser.close();
}
