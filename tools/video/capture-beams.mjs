// Stills of the cantilever-sections example (three beam sections under one tip force): the
// settled static bend with the stress colours, close-ups of the sections, and a frame of the
// resonant sine, set through the dashboard's load select like a user would.
//
//   node tools/video/capture-beams.mjs <out dir>
//
// Needs a private backend on BGSIM_VIDEO_URL (default http://127.0.0.1:8810), see README.md.
import path from "node:path";
import { mkdirSync } from "node:fs";
import { createProject, launchBrowser, newPage, openModel, runAndWait, sleep } from "./lib.mjs";

const out = path.resolve(process.argv[2] ?? "beams-shots");
mkdirSync(out, { recursive: true });

async function setTime(page, t) {
  await page.getByTestId("playback-time").fill(String(t));
  await sleep(500);
}

async function camera(page, { preset = null, orbitX = 0, orbitY = 0, zoom = 0 } = {}) {
  await page.getByTestId("viewer-fit").click();
  await sleep(500);
  if (preset !== null) await page.getByTestId(`viewer-preset-${preset}`).dispatchEvent("click");
  await sleep(500);
  const box = await page.getByTestId("viewer-canvas").boundingBox();
  const cx = box.x + box.width / 2;
  const cy = box.y + box.height / 2;
  if (orbitX !== 0) {
    await page.mouse.move(cx - orbitX / 2, cy);
    await page.mouse.down();
    await page.mouse.move(cx + orbitX / 2, cy, { steps: 12 });
    await page.mouse.up();
  }
  if (orbitY !== 0) {
    await page.mouse.move(cx, cy - orbitY / 2);
    await page.mouse.down();
    await page.mouse.move(cx, cy + orbitY / 2, { steps: 10 });
    await page.mouse.up();
  }
  await page.mouse.move(cx, cy);
  for (let i = 0; i < zoom; i += 1) {
    await page.mouse.wheel(0, -120);
    await sleep(30);
  }
  await page.mouse.move(box.x + box.width - 2, box.y + 2);
  await sleep(800);
}

async function shoot(page, name) {
  const file = path.join(out, `${name}.png`);
  await page.getByTestId("viewer-canvas").screenshot({ path: file });
  console.log(file);
}

const browser = await launchBrowser();
try {
  const project = await createProject("cantilever-sections", "beams");
  const page = await newPage(browser, { viewport: { width: 1440, height: 1800 } });
  await openModel(page, project, "cantilever-sections");

  // 1. the default run: a 250 N step at 0.2 s
  await runAndWait(page);
  await page.getByRole("tab", { name: "3D View" }).click();
  await page.getByTestId("scene-view").and(page.locator('[data-state="loaded"]')).waitFor({ timeout: 60000 });
  await page.getByTestId("playback-bar").and(page.locator('[data-mode="playback"]')).waitFor({ timeout: 60000 });
  await setTime(page, 9.9);
  await camera(page, { preset: "iso", zoom: 5 });
  await shoot(page, "1-static-bend-x10");
  await camera(page, { preset: "iso", orbitX: 250, zoom: 12 });
  await shoot(page, "2-static-wall-closeup-x10");
  await setTime(page, 0.28);
  await camera(page, { preset: "iso", zoom: 5 });
  await shoot(page, "3-step-peak-x10");
  await page.getByTestId("deformation-exaggeration").selectOption("1");
  await setTime(page, 9.9);
  await shoot(page, "4-static-bend-true-scale");
  await page.getByTestId("deformation-exaggeration").selectOption("10");

  // 2. the dashboard: load "1 · sine" at the default 6.42 Hz (the round bar's f1), 10 N
  await page.getByRole("tab", { name: "Dashboard" }).click();
  await page.getByTestId("dash-select-mode").waitFor({ timeout: 30000 });
  await page.getByTestId("dash-select-mode").selectOption("1");
  await sleep(300);
  await page.screenshot({ path: path.join(out, "5-dashboard-sine-selected.png") });
  await runAndWait(page);
  await sleep(1500);
  await page.screenshot({ path: path.join(out, "6-dashboard-after-sine-run.png") });
  await page.getByRole("tab", { name: "3D View" }).click();
  await page.getByTestId("playback-bar").and(page.locator('[data-mode="playback"]')).waitFor({ timeout: 60000 });
  // two opposite crests of the round bar's steady oscillation (period 0.1557 s)
  await setTime(page, 9.930);
  await camera(page, { preset: "iso", zoom: 5 });
  await shoot(page, "7-sine-resonance-down-x10");
  await setTime(page, 9.852);
  await shoot(page, "8-sine-resonance-up-x10");
} finally {
  await browser.close();
}
