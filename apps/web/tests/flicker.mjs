// Measures depth fighting: with the game paused, the camera moves by half a metre between two
// pictures, so almost nothing should change. Prints the share of pixels that jump in brightness.
// node tests/flicker.mjs <folder for the pictures> [view]
import { mkdirSync } from "node:fs";
import { chromium } from "playwright";
const [out, view] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
const port = process.env.GAMES_PORT ?? "8831";
const browser = await chromium.launch({ headless: true, args: ["--use-angle=d3d11", "--ignore-gpu-blocklist", "--enable-gpu", "--enable-unsafe-swiftshader"] });
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
await page.goto(`http://127.0.0.1:${port}/f16/?grid=2048&tier=0`);
await page.waitForFunction(() => window.ready, null, { timeout: 120000 });
await page.selectOption("#sky", "0.14");
// Off the south-east coast looking along the shelf, and later over the airfield.
const spots = { coast: [-21000, 3000], shelf: [-16000, 9000], airfield: [-16500, 8000] };
for (const [name, [north, east]] of Object.entries(spots)) {
  await page.evaluate(([n, e, v]) => {
    game.begin();
    game.flight.frame.north = n;
    game.flight.frame.east = e;
    game.rig.view = v ?? "chase";
    game.rig.snap();
  }, [north, east, view]);
  await page.waitForTimeout(500);
  await page.keyboard.press("KeyP");
  await page.evaluate(() => { document.getElementById("pause").hidden = true; });
  await page.waitForTimeout(700);
  for (let i = 0; i < 4; i += 1) {
    await page.evaluate((step) => { game.flight.frame.north += step; }, 0.5);
    await page.waitForTimeout(250);
    await page.screenshot({ path: `${out}/${name}-${i}.png` });
  }
  await page.keyboard.press("KeyP");
}
await browser.close();
