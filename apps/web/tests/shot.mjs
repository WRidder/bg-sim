// Screenshots of a page for judging the look: node tests/shot.mjs <out.png> <path?query> [script] [seconds]
// The script runs in the page once it is ready; a second, third... picture comes from "seconds" as a
// comma list, each written next to the first with its index.
import { chromium } from "playwright";
const [out, path, script, seconds] = process.argv.slice(2);
const port = process.env.GAMES_PORT ?? "8831";
const browser = await chromium.launch({ headless: true, args: ["--use-angle=d3d11", "--ignore-gpu-blocklist", "--enable-gpu", "--enable-unsafe-swiftshader"] });
const page = await browser.newPage({ viewport: { width: Number(process.env.SHOT_W ?? 1280), height: Number(process.env.SHOT_H ?? 720) } });
const logs = [];
page.on("console", (m) => { if (["error", "warning"].includes(m.type())) logs.push(m.text().slice(0, 600)); });
page.on("pageerror", (e) => logs.push("PAGEERROR " + e.message.slice(0, 600)));
await page.goto(`http://127.0.0.1:${port}/${path}`);
try {
  await page.waitForFunction(() => window.ready, null, { timeout: Number(process.env.SHOT_WAIT ?? 90000) });
  console.log(JSON.stringify(await page.evaluate(() => window.ready)));
} catch (e) { console.log("no ready:", e.message.slice(0, 120)); }
if (script) await page.evaluate(script);
const waits = (seconds ?? "0").split(",").map(Number);
for (const [i, wait] of waits.entries()) {
  await page.waitForTimeout(wait * 1000);
  await page.screenshot({ path: waits.length > 1 ? out.replace(".png", `-${i}.png`) : out });
  console.log(JSON.stringify(await page.evaluate(() => window.game?.state?.() ?? null)));
}
console.log(logs.slice(0, 8).join("\n"));
await browser.close();
