// The microduck page on the bg-sim FMU (src/microduck/model.gen.ts built by build_wasm.py) in a
// real browser: the page picks the FMU, velstand runs on it in lockstep, and the script reports
// the FMU's wall time per 20 ms control tick (its real-time factor in the browser) and what the
// robot does: standing at zero command, then W (full forward, 0.4 m/s asked) for a few seconds.
// It judges the plumbing, not the walking: a fall or a stopped plant is reported, not failed.
// node tests/microduck-fmu.mjs [out.png]   (dev server on GAMES_PORT, default 8831)
import { chromium } from "playwright";

const port = process.env.GAMES_PORT ?? "8831";
const browser = await chromium.launch({ headless: true, args: ["--use-angle=d3d11", "--ignore-gpu-blocklist", "--enable-gpu", "--enable-unsafe-swiftshader"] });
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
const logs = [];
page.on("console", (m) => { if (["error", "warning"].includes(m.type())) logs.push(m.text().slice(0, 400)); });
page.on("pageerror", (e) => logs.push("PAGEERROR " + e.message.slice(0, 400)));

await page.goto(process.env.GAME_URL ?? `http://127.0.0.1:${port}/microduck/`);
await page.waitForFunction(() => window.ready, null, { timeout: 90000 });
const read = () => page.evaluate(() => game.state());
const check = (name, ok, detail) => { console.log(`${ok ? "ok  " : "FAIL"} ${name} ${JSON.stringify(detail)}`); if (!ok) process.exitCode = 1; };
const report = (name, detail) => console.log(`--   ${name} ${JSON.stringify(detail)}`);
const until = async (test, ms) => {
  const end = Date.now() + ms;
  for (;;) {
    const state = await read();
    if (test(state) || Date.now() > end) return state;
    await page.waitForTimeout(50);
  }
};
const tilt = (s) => +((Math.acos(Math.max(-1, Math.min(1, -s.gravity[2]))) * 180 / Math.PI).toFixed(1));
const brief = (s) => ({ plant: s.plant, t: +s.plantTime.toFixed(2), ticks: s.ticks, net: s.net, failure: s.failure, position: s.position.map((v) => +v.toFixed(3)), tiltDeg: tilt(s), contact: s.contact, command: s.command.map((v) => +v.toFixed(2)), timing: s.timing && { meanMs: +s.timing.meanMs.toFixed(2), maxMs: +s.timing.maxMs.toFixed(2), lastMs: +s.timing.lastMs.toFixed(2) }, stop: s.stop });

const first = await read();
check("the page runs the bg-sim FMU", first.plant === "fmu" && /bg-sim model/.test(await page.textContent("#banner")), brief(first));
const running = await until((s) => s.ticks > 50 && s.net === "walk", 15000);
check("velstand runs on it", running.enabled && running.net === "walk" && running.action.every(Number.isFinite), brief(running));
const t0 = await read();
const w0 = Date.now();
await page.waitForTimeout(5000);
const t1 = await read();
const wall = (Date.now() - w0) / 1000;
const rate = (t1.ticks - t0.ticks) / wall;
check("control ticks keep pace with the clock (the FMU runs faster than real time)", rate > 40 && rate < 55, { rate: +rate.toFixed(1), plantSecondsPerWallSecond: +((t1.plantTime - t0.plantTime) / wall).toFixed(3) });
report("FMU wall time per 20 ms tick in the browser", { meanMs: +t1.timing.meanMs.toFixed(2), maxMs: +t1.timing.maxMs.toFixed(2), realTimeFactor: +(t1.timing.meanMs / 20).toFixed(3), ticks: t1.timing.ticks });
report("standing at zero command", brief(t1));
await page.screenshot({ path: process.argv[2] ?? "microduck-fmu.png" });

await page.keyboard.down("KeyW");
const samples = [];
for (let i = 0; i < 8; i += 1) {
  await page.waitForTimeout(500);
  const s = await read();
  samples.push(brief(s));
  if (s.failure || s.plant !== "fmu") break;
}
await page.keyboard.up("KeyW");
report("W held (full forward)", samples);
await page.screenshot({ path: (process.argv[2] ?? "microduck-fmu.png").replace(/\.png$/, "-forward.png") });
const end = await read();
report("after", brief(end));

check("no page errors or console errors", logs.length === 0, logs);
await browser.close();
