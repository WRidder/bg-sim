// Frame times of the interception mode around a launch: node tests/weapons-perf.mjs
// Uncapped frame rate (no vsync), so the numbers show the head room, not the display's 60 Hz.
// PERF_HEADED=1 opens a window; PERF_SIZE=1920x1080 changes the viewport; PERF_TIER fixes the tier.
import { chromium } from "playwright";

const port = process.env.GAMES_PORT ?? "8831";
const [width, height] = (process.env.PERF_SIZE ?? "1920x1080").split("x").map(Number);
const browser = await chromium.launch({
  headless: !process.env.PERF_HEADED,
  args: [
    "--use-angle=d3d11", "--ignore-gpu-blocklist", "--enable-gpu",
    "--disable-gpu-vsync", "--disable-frame-rate-limit",
  ],
});
const page = await browser.newPage({ viewport: { width, height } });
const logs = [];
page.on("console", (m) => { if (["error", "warning"].includes(m.type())) logs.push(m.text().slice(0, 400)); });
page.on("pageerror", (e) => logs.push("PAGEERROR " + e.message.slice(0, 400)));

await page.addInitScript(() => {
  const perf = { frames: [], links: [], marks: [] };
  window.perf = perf;
  let last = performance.now();
  const tick = (now) => {
    perf.frames.push([now, now - last]);
    last = now;
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
  const link = WebGL2RenderingContext.prototype.linkProgram;
  WebGL2RenderingContext.prototype.linkProgram = function (program) {
    perf.links.push(performance.now());
    return link.call(this, program);
  };
  perf.mark = (name) => perf.marks.push([name, performance.now()]);
});

const tier = process.env.PERF_TIER ? `&tier=${process.env.PERF_TIER}` : "";
await page.goto(process.env.GAME_URL ?? `http://127.0.0.1:${port}/f16/?grid=1024${tier}`);
await page.waitForFunction(() => window.ready, null, { timeout: 90000 });
console.log(await page.evaluate(() => {
  const gl = document.createElement("canvas").getContext("webgl2");
  const ext = gl.getExtension("WEBGL_debug_renderer_info");
  return ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : "unknown renderer";
}));

const mark = (name) => page.evaluate((n) => window.perf.mark(n), name);
await page.click('#mode button[data-value="intercept"]');
await page.click("#fly");
await mark("fly");
await page.waitForFunction(() => game.state().lock.locked, null, { timeout: 15000 });
await page.waitForTimeout(2500);
await mark("launch 1");
await page.keyboard.press("KeyM");
await page.waitForTimeout(1500);
await page.waitForFunction(() => game.state().lock.locked, null, { timeout: 15000 }).catch(() => {});
await mark("launch 2");
await page.keyboard.press("KeyM");
await page.waitForTimeout(8000);
await mark("end");

const { frames, links, marks, state } = await page.evaluate(() => ({ ...window.perf, state: game.state() }));
const stats = (from, to) => {
  const dts = frames.filter(([t]) => t >= from && t < to).map(([, dt]) => dt).sort((a, b) => a - b);
  if (dts.length === 0) return "no frames";
  const at = (p) => dts[Math.min(dts.length - 1, Math.floor(p * dts.length))].toFixed(1);
  const mean = dts.reduce((a, b) => a + b, 0) / dts.length;
  const linked = links.filter((t) => t >= from && t < to).length;
  return `${dts.length} frames, mean ${mean.toFixed(1)} ms (${(1000 / mean).toFixed(0)} fps), p50 ${at(0.5)}, p99 ${at(0.99)}, ` +
    `max ${dts[dts.length - 1].toFixed(1)} ms, over 20 ms: ${dts.filter((d) => d > 20).length}, programs linked: ${linked}`;
};
console.log(`tier ${state.tier}, ${width}x${height}`);
for (let i = 0; i < marks.length - 1; i += 1) {
  const [name, from] = marks[i];
  const to = marks[i + 1][1];
  // The first 400 ms after a mark apart: that is where a hitch from the key press would be.
  console.log(`${name.padEnd(9)} first 0.4 s: ${stats(from, Math.min(to, from + 400))}`);
  console.log(`${"".padEnd(9)} then       : ${stats(from + 400, to)}`);
}
const start = marks[0][1];
const name = (t) => [...marks].reverse().find(([, at]) => at <= t);
for (const [t, dt] of frames.filter(([t, dt]) => t >= start && dt > 60)) {
  const [label, at] = name(t);
  console.log(`long frame ${dt.toFixed(0)} ms, ${((t - at) / 1000).toFixed(2)} s after "${label}"`);
}
console.log(logs.slice(0, 8).join("\n"));
await browser.close();
