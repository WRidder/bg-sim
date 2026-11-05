/**
 * The F-16's gear in the browser: the keys, and pictures to look at. A running game on GAMES_PORT.
 *   GAMES_PORT=8843 node tests/gear-shots.mjs <outdir>
 */

import { mkdirSync } from "node:fs";
import { chromium } from "playwright";

const out = process.argv[2] ?? "shots";
mkdirSync(out, { recursive: true });
const port = process.env.GAMES_PORT ?? "5173";
const browser = await chromium.launch({ headless: true, args: ["--use-angle=d3d11", "--ignore-gpu-blocklist", "--enable-webgl"] });
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));

await page.goto(`http://127.0.0.1:${port}/f16/?grid=1024`);
await page.waitForFunction(() => window.ready, null, { timeout: 120000 });

const start = async (label) => {
  await page.evaluate((text) => {
    const select = document.getElementById("start");
    select.value = [...select.options].find((o) => o.text.startsWith(text)).value;
    game.setMode("free");
    game.begin();
  }, label);
  await page.waitForTimeout(600);
};
const read = () => page.evaluate(() => {
  const f = game.flight;
  return {
    ...game.state(), kt: Math.round(f.get("cas_mps") * 1.94), alt: Math.round(f.altitude()), heading: Math.round(f.heading()),
    gear: Number(f.get("gear_pos").toFixed(2)), onGround: f.onGround, braking: f.braking, landing: f.landing,
  };
});
const shot = (name) => page.screenshot({ path: `${out}/${name}.png` });
const look = (azimuth, elevation, distance, height = 5.5) => page.evaluate(([a, e, d, h]) => {
  game.rig.dragging = true;
  game.rig.azimuth = a;
  game.rig.elevation = e;
  game.rig.distance = d;
  game.rig.options.height = h;
}, [azimuth, elevation, distance, height]);

await start("Runway 25");
console.log("on the runway", await read());
await page.waitForTimeout(800);
await shot("runway-chase");
await look(1.5, 0, 11, 0.2);
await page.waitForTimeout(800);
await shot("runway-side");
await look(2.5, 0.03, 9, 0.1);
await page.waitForTimeout(800);
await shot("runway-front");
await look(0, 0, 27);
await page.evaluate(() => { game.rig.dragging = false; });
await page.keyboard.press("KeyC");
await page.waitForTimeout(800);
await shot("runway-cockpit");
await page.keyboard.press("KeyC");
await page.keyboard.press("KeyC");
await page.keyboard.down("KeyB");
await page.waitForTimeout(300);
console.log("brake held", await read());
await page.keyboard.up("KeyB");
await page.keyboard.press("KeyG");
await page.waitForTimeout(500);
console.log("gear handle on the ground", await read());

await start("Final to runway");
console.log("on final", await read());
await page.waitForTimeout(1500);
await shot("final-chase");
await page.keyboard.press("KeyG");
await page.waitForTimeout(2500);
console.log("gear going up", await read());
await look(1.5, -0.1, 12, 0.2);
await page.waitForTimeout(300);
await shot("gear-moving");
await page.waitForTimeout(3500);
console.log("gear up", await read());
await shot("gear-up");
await page.keyboard.press("KeyT");
await page.waitForTimeout(800);
await shot("telemetry");

// A landing flown by a script between two frames, to see how the game takes it.
await page.keyboard.press("KeyT");
await start("Final to runway");
await page.evaluate(() => {
  const f = game.flight;
  for (let i = 0; i < 40000 && !f.crashed && f.landing !== "stopped"; i += 1) {
    const height = f.get("alt_m") - 1.7;
    if (f.touchdowns.length > 0) {
      f.setControls(0, 0, 0, 0);
      f.setBrakes(f.get("tas_mps") < 70 ? 1 : 0);
    } else {
      const gamma = height > 7 ? -3 : -0.4;
      const wantNz = Math.cos((f.get("gamma_deg") * Math.PI) / 180) + (gamma - f.get("gamma_deg")) * 0.08;
      const power = height > 7 ? f.u[3] + (76 - f.get("tas_mps")) * 0.0002 : 0;
      f.setControls((wantNz - 1) * 0.3 + (wantNz - f.get("nz_g")) * 0.04 - f.get("q_dps") * 0.012, 0, 0, power);
    }
    f.advance(f.pacer.step);
  }
});
await page.waitForTimeout(1500);
console.log("after the landing", await read());
console.log(await page.evaluate(() => ({
  title: document.getElementById("over-title").textContent,
  score: document.getElementById("over-score").textContent,
  text: document.getElementById("over-text").textContent,
  lines: [...document.querySelectorAll("#over-lines .line")].map((row) => row.textContent),
})));
await shot("sheet");

console.log(errors.length ? errors : "no errors");
await browser.close();
