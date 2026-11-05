// Flies with real key presses: the take-off, the levers, the views, pause and restart, then a whole
// landing from short final down to the score sheet. node tests/cessna-keys.mjs [out.png]
import { chromium } from "playwright";
const port = process.env.GAMES_PORT ?? "8831";
const browser = await chromium.launch({ headless: true, args: ["--use-angle=d3d11", "--ignore-gpu-blocklist", "--enable-gpu", "--enable-unsafe-swiftshader"] });
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
const logs = [];
page.on("console", (m) => { if (["error", "warning"].includes(m.type())) logs.push(m.text().slice(0, 400)); });
page.on("pageerror", (e) => logs.push("PAGEERROR " + e.message.slice(0, 400)));
await page.goto(process.env.GAME_URL ?? `http://127.0.0.1:${port}/cessna/?grid=1024&tier=2`);
await page.waitForFunction(() => window.ready, null, { timeout: 90000 });
const read = () => page.evaluate(() => {
  const f = game.flight;
  return { ...game.state(), kias: +f.get("kias").toFixed(1), agl: +f.get("agl_ft").toFixed(1), fpm: Math.round(f.get("vs_fpm")), theta: +f.get("theta_deg").toFixed(1), phi: +f.get("phi_deg").toFixed(1), rpm: Math.round(f.get("rpm")), throttle: +f.throttle.toFixed(2), flaps: f.flaps, ground: f.get("on_ground"), brakes: f.brakes, trim: +f.trim.toFixed(3), north: Math.round(f.north()), east: Math.round(f.east()), hdg: Math.round(f.heading()) };
});
const check = (name, ok, detail) => { console.log(`${ok ? "ok  " : "FAIL"} ${name} ${JSON.stringify(detail)}`); if (!ok) process.exitCode = 1; };
const until = async (test, ms) => {
  const end = Date.now() + ms;
  for (;;) {
    const state = await read();
    if (test(state) || Date.now() > end) return state;
    await page.waitForTimeout(40);
  }
};

check("the title is up", (await read()).phase === "title", {});
await page.click("#fly");
await page.waitForTimeout(600);
const lined = await read();
check("lined up on the runway", lined.phase === "flying" && lined.ground === 1 && lined.kias < 3, lined);
await page.keyboard.down("PageUp");
const full = await until((s) => s.throttle >= 0.99, 4000);
await page.keyboard.up("PageUp");
check("page up opens the throttle", full.throttle >= 0.99 && full.rpm > 1000, full);
await page.keyboard.press("KeyV");
await page.waitForTimeout(200);
check("V takes the flaps up", (await read()).flaps === 0, {});
await page.keyboard.press("KeyF");
await page.waitForTimeout(200);
check("F puts them down", (await read()).flaps === 1, {});
const fast = await until((s) => s.kias > 54, 30000);
check("rolls up to flying speed", fast.kias > 54 && fast.ground === 1, fast);
await page.keyboard.down("ArrowDown");
const off = await until((s) => s.ground === 0 && s.agl > 6, 9000);
await page.keyboard.up("ArrowDown");
check("down arrow rotates, and it flies", off.ground === 0 && off.agl > 6 && !off.crashed, off);
await page.waitForTimeout(3000);
const climbing = await read();
check("still climbing with the yoke let go", climbing.agl > off.agl && !climbing.crashed, climbing);
await page.keyboard.down("ArrowLeft");
await page.waitForTimeout(800);
await page.keyboard.up("ArrowLeft");
const banked = await read();
check("left arrow banks left", banked.phi < -5, banked);
await page.keyboard.down("BracketRight");
await page.waitForTimeout(400);
await page.keyboard.up("BracketRight");
check("trim moves", (await read()).trim > 0.03, await read());
await page.screenshot({ path: process.argv[2] ?? "cessna-keys.png" });
await page.keyboard.press("KeyC");
check("C goes to the cockpit", (await read()).view === "cockpit", {});
await page.waitForTimeout(600);
await page.keyboard.press("KeyC");
await page.keyboard.press("KeyC");
check("and round to the chase", (await read()).view === "chase", {});
await page.keyboard.press("KeyP");
const paused = await read();
await page.waitForTimeout(500);
const still = await read();
check("P pauses", paused.phase === "paused" && paused.time === still.time, still);
await page.keyboard.press("KeyP");
await page.waitForTimeout(300);
check("P resumes", (await read()).phase === "flying", {});
await page.keyboard.press("KeyR");
await page.waitForTimeout(300);
const fresh = await read();
check("R restarts on the runway", fresh.time < 1 && fresh.ground === 1, fresh);

// The whole of a landing, on the keys alone: leave the trim alone down the path, then idle and flare.
await page.keyboard.press("Escape");
await page.click("#quit");
await page.click('[data-value="spot"]');
await page.click("#fly");
await page.waitForTimeout(400);
const final = await read();
check("spot landing starts on final", final.mode === "spot" && final.ground === 0 && final.flaps === 3, final);
// Taps on the arrows, the way a pilot nudges an aeroplane back onto the extended centre line.
let tapping = null;
const steer = async (s) => {
  const wantHeading = 252 - Math.max(-12, Math.min(12, s.across * 0.35));
  const wantBank = Math.max(-8, Math.min(8, wantHeading - s.hdg));
  const key = s.phi < wantBank - 2.5 ? "ArrowRight" : s.phi > wantBank + 2.5 ? "ArrowLeft" : null;
  if (key !== tapping) {
    if (tapping) await page.keyboard.up(tapping);
    if (key) await page.keyboard.down(key);
    tapping = key;
  }
};
for (let i = 0; i < 4000; i += 1) {
  const s = await read();
  if (s.agl < 40 || s.crashed) break;
  await steer(s);
  await page.waitForTimeout(30);
}
if (tapping) await page.keyboard.up(tapping);
tapping = null;
await page.keyboard.down("PageDown");
await until((s) => s.throttle <= 0.02 || s.agl < 12, 4000);
await page.keyboard.up("PageDown");
console.log(JSON.stringify(await read()));
for (let i = 0; i < 700; i += 1) {
  const s = await read();
  if (s.agl < 20 || s.ground === 1 || s.crashed) break;
  await steer(s);
  await page.waitForTimeout(30);
}
if (tapping) await page.keyboard.up(tapping);
tapping = null;
let held = false;
for (let i = 0; i < 400; i += 1) {
  const s = await read();
  if (s.ground === 1 || s.crashed) break;
  await steer(s);
  const want = held ? -(70 + 6 * s.agl) : -(95 + 7 * s.agl);
  if (s.fpm < want && !held) {
    await page.keyboard.down("ArrowDown");
    held = true;
  } else if (s.fpm >= want && held) {
    await page.keyboard.up("ArrowDown");
    held = false;
  }
  await page.waitForTimeout(16);
}
if (held) await page.keyboard.up("ArrowDown");
if (tapping) await page.keyboard.up(tapping);
const down = await read();
check("on the ground, in one piece", down.ground === 1 && !down.crashed, down);
await page.keyboard.down("KeyB");
const done = await until((s) => s.phase === "over" || s.crashed, 40000);
await page.keyboard.up("KeyB");
check("the brakes stop it and the sheet comes up", done.phase === "over" && !done.crashed, done);
const sheet = await page.evaluate(() => ({ score: document.getElementById("over-score").textContent, title: document.getElementById("over-title").textContent, lines: [...document.querySelectorAll("#over-lines .line")].map((l) => l.textContent) }));
check("the sheet has a score", Number(sheet.score) > 0 && sheet.lines.length >= 4, sheet);
await page.screenshot({ path: (process.argv[2] ?? "cessna-keys.png").replace(".png", "-sheet.png") });
await page.click("#over-quit");
await page.waitForTimeout(300);
check("back to the title", (await read()).phase === "title", {});
console.log(logs.slice(0, 6).join("\n"));
await browser.close();
