// Pictures of the game from a build that the dev server's reloads cannot reach:
// GAME_URL=file:///.../cessna/index.html node tests/cessna-shot.mjs <out.png> "<query>" "<page script>" "8,6"
import { chromium } from "playwright";
const [out, query, script, seconds] = process.argv.slice(2);
const browser = await chromium.launch({ headless: true, args: ["--use-angle=d3d11", "--ignore-gpu-blocklist", "--enable-gpu", "--enable-unsafe-swiftshader"] });
const page = await browser.newPage({ viewport: { width: Number(process.env.SHOT_W ?? 1280), height: Number(process.env.SHOT_H ?? 720) } });
const logs = [];
page.on("console", (m) => { if (["error", "warning"].includes(m.type())) logs.push(m.text().slice(0, 400)); });
page.on("pageerror", (e) => logs.push("PAGEERROR " + e.message.slice(0, 400)));
await page.goto(`${process.env.GAME_URL}?${query}`);
await page.waitForFunction(() => window.ready, null, { timeout: 90000 });
if (script) await page.evaluate(script);
const waits = (seconds ?? "0").split(",").map(Number);
for (const [i, wait] of waits.entries()) {
  await page.waitForTimeout(wait * 1000);
  await page.screenshot({ path: waits.length > 1 ? out.replace(".png", `-${i}.png`) : out });
  const s = await page.evaluate(() => ({ ...game.state(), agl: game.flight.get("agl_ft") }));
  console.log(i, s.phase, s.mode, s.view, s.pilot, "t", s.time.toFixed(1), s.crashed ? s.crash : "", "along", Math.round(s.along), "across", Math.round(s.across), "agl", Math.round(s.agl));
}
console.log(logs.slice(0, 6).join("\n"));
await browser.close();
