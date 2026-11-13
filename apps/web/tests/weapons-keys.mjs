// Flies the interception mode with real keys: target, lock, launch. node tests/weapons-keys.mjs [out.png]
import { chromium } from "playwright";

const port = process.env.GAMES_PORT ?? "8831";
const browser = await chromium.launch({
  headless: true,
  args: ["--use-angle=d3d11", "--ignore-gpu-blocklist", "--enable-gpu", "--enable-unsafe-swiftshader"],
});
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
const logs = [];
page.on("console", (m) => { if (["error", "warning"].includes(m.type())) logs.push(m.text().slice(0, 400)); });
page.on("pageerror", (e) => logs.push("PAGEERROR " + e.message.slice(0, 400)));

await page.goto(process.env.GAME_URL ?? `http://127.0.0.1:${port}/f16/?grid=1024`);
await page.waitForFunction(() => window.ready, null, { timeout: 90000 });
const read = () => page.evaluate(() => game.state());
const check = (name, ok, detail) => {
  console.log(`${ok ? "ok  " : "FAIL"} ${name} ${JSON.stringify(detail)}`);
  if (!ok) process.exitCode = 1;
};

await page.click('#mode button[data-value="intercept"]');
await page.click("#fly");
await page.waitForTimeout(2200);
const before = await read();
check("intercept mode with three drones", before.mode === "intercept" && before.drones === 3, before);
check("seeker has a lock", before.lock.locked === true, before.lock);

await page.keyboard.press("KeyM");
await page.waitForFunction(() => game.state().lock.locked, null, { timeout: 5000 });
await page.keyboard.press("KeyM");
await page.waitForTimeout(500);
const fired = await read();
check("M launches both AIM-9X", fired.missiles === 0, fired);

await page.screenshot({ path: process.argv[2] ?? "weapons.png" });
await page.waitForTimeout(6000);
const reloaded = await read();
check("the wingtips reload after five seconds", reloaded.missiles === 2, reloaded);
const after = await read();
check("the target is destroyed and replaced", after.drones === 3 && after.lock.selectedId !== before.lock.selectedId
  || after.drones < 3, after);
console.log(logs.slice(0, 8).join("\n"));
await browser.close();
