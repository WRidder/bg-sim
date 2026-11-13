// Flies Island Lift with real key presses: lift off, climb, turn, speed up, sidestep, brake, set down,
// views, pause, restart, and the stability handling's lever. node tests/a109-keys.mjs [out.png]
// GAME_URL points it at another build, such as file:///.../dist-single/a109.html
import { chromium } from "playwright";
const port = process.env.GAMES_PORT ?? "8831";
const browser = await chromium.launch({ headless: true, args: ["--use-angle=d3d11", "--ignore-gpu-blocklist", "--enable-gpu", "--enable-unsafe-swiftshader"] });
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
// Other games in this dev server would reload the page halfway through.
if (!process.env.GAME_URL) {
  await page.addInitScript(() => { const Real = WebSocket; window.WebSocket = function (url, p) { return new Real(String(url).replace(/:\d+/, ":1"), p); }; window.WebSocket.prototype = Real.prototype; });
}
const logs = [];
page.on("console", (m) => { if (["error", "warning"].includes(m.type()) && !/WebSocket|send error|GPU stall/.test(m.text())) logs.push(m.text().slice(0, 400)); });
page.on("pageerror", (e) => logs.push("PAGEERROR " + e.message.slice(0, 400)));
await page.goto(process.env.GAME_URL ?? `http://127.0.0.1:${port}/a109/?grid=1024`);
await page.waitForFunction(() => window.ready, null, { timeout: 90000 });
const read = () => page.evaluate(() => { const f = game.flight; return { ...game.state(), kts: Math.round(f.get("kts")), climb: +f.get("vs_mps").toFixed(1), heading: Math.round(f.get("psi_deg")), bank: Math.round(f.get("phi_deg")), side: +f.get("beta_deg").toFixed(0), lever: +f.u[0].toFixed(2), wow: f.get("wow"), speed: +f.groundSpeed().toFixed(1) }; });
const check = (name, ok, detail) => { console.log(`${ok ? "ok  " : "FAIL"} ${name} ${JSON.stringify(detail)}`); if (!ok) process.exitCode = 1; };
const until = async (test, ms) => { const end = Date.now() + ms; let s = await read(); while (!test(s) && Date.now() < end) { await page.waitForTimeout(200); s = await read(); } return s; };

const title = await read();
check("the title screen flies by itself", title.phase === "title" && !title.crashed, title);
await page.waitForTimeout(6000);
const behind = await read();
check("the helicopter leaves the pad behind the title", behind.radar > 0.3, behind);
await page.click("#fly");
await page.waitForTimeout(600);
const parked = await read();
check("Fly starts on the pad", parked.phase === "flying" && parked.radar < 0.5 && parked.leg === 1, parked);

await page.keyboard.down("KeyW");
const off = await until((s) => s.radar > 15 || s.crashed, 25000);
await page.keyboard.up("KeyW");
check("W lifts off and climbs", off.radar > 15 && !off.crashed, off);
const heading = off.heading;
await page.keyboard.down("KeyD");
await page.waitForTimeout(2000);
await page.keyboard.up("KeyD");
const turned = await read();
const swung = ((turned.heading - heading + 540) % 360) - 180;
check("D swings the nose right", swung > 10, { ...turned, swung });
await page.waitForTimeout(2000);
const hover = await read();
check("hands off it hovers", hover.speed < 3 && Math.abs(hover.climb) < 2.5, hover);
await page.keyboard.down("ArrowUp");
const fast = await until((s) => s.kts > 35 || s.crashed, 25000);
await page.keyboard.up("ArrowUp");
check("up arrow makes speed", fast.kts > 35 && !fast.crashed, fast);
await page.keyboard.down("ArrowRight");
await page.waitForTimeout(1800);
await page.keyboard.up("ArrowRight");
const banked = await read();
check("right arrow banks right at speed", banked.bank > 8, banked);
await page.screenshot({ path: process.argv[2] ?? "a109-keys.png" });
await page.keyboard.down("Space");
const stopped = await until((s) => s.speed < 3 || s.crashed, 50000);
await page.keyboard.up("Space");
check("Space brakes to a hover", stopped.speed < 3 && !stopped.crashed, stopped);

await page.keyboard.press("KeyC");
check("C goes to the cockpit", (await read()).view === "cockpit", {});
await page.keyboard.press("KeyC");
check("C goes to the flyby", (await read()).view === "flyby", {});
await page.keyboard.press("KeyC");
await page.keyboard.press("KeyP");
const paused = await read();
await page.waitForTimeout(600);
const still = await read();
check("P pauses", paused.phase === "paused" && paused.time === still.time, still);
await page.keyboard.press("KeyP");
await page.waitForTimeout(300);
check("P resumes", (await read()).phase === "flying", {});

await page.keyboard.down("KeyS");
const down = await until((s) => s.radar < 0.25 || s.crashed, 90000);
await page.waitForTimeout(600);
await page.keyboard.up("KeyS");
const landed = await read();
check("S sets it down", down.radar < 0.25 && !landed.crashed, landed);

await page.keyboard.press("KeyR");
await page.waitForTimeout(400);
const fresh = await read();
check("R restarts", fresh.time < 2 && fresh.radar < 0.5, fresh);

// The same keys in the stability handling are the lever and the stick.
await page.evaluate(() => game.setAid("scas"));
await page.keyboard.press("KeyR");
await page.waitForTimeout(400);
await page.keyboard.down("KeyW");
await page.waitForTimeout(3000);
await page.keyboard.up("KeyW");
const lever = await read();
check("W raises the lever by hand", lever.lever > 0.6, lever);
await page.keyboard.press("KeyS");
await page.keyboard.press("KeyH");
check("H takes the stability off", await page.evaluate(() => game.flight.scas === false), {});

// Into the ground, for the crash and the result.
await page.evaluate(() => { game.setAid("assist"); game.begin(); game.flight.crash("Terrain"); });
const over = await until((s) => s.phase === "over", 6000);
check("a crash ends in the result screen", over.phase === "over", over);
check("the result tells what happened", (await page.textContent("#over-title")) === "Crashed" && (await page.isVisible("#again")), await page.textContent("#over-text"));
await page.click("#again");
await page.waitForTimeout(300);
check("Fly again flies again", (await read()).phase === "flying", {});
await page.keyboard.press("KeyP");
await page.click("#quit");
await page.waitForTimeout(300);
check("the menu comes back", (await read()).phase === "title" && (await page.isVisible("#fly")), {});
console.log(logs.slice(0, 6).join("\n"));
await browser.close();
