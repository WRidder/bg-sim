// Drives the microduck page in a real browser: the policy loads and runs, real keys walk it, a
// synthetic standard-mapping pad (a stand-in for a DualSense, through navigator.getGamepads) walks
// and switches modes, the one-shots run, and nothing throws.
// node tests/microduck-keys.mjs [out.png]   (dev server on GAMES_PORT, default 8831)
import { chromium } from "playwright";

const port = process.env.GAMES_PORT ?? "8831";
const browser = await chromium.launch({ headless: true, args: ["--use-angle=d3d11", "--ignore-gpu-blocklist", "--enable-gpu", "--enable-unsafe-swiftshader"] });
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
const logs = [];
page.on("console", (m) => { if (["error", "warning"].includes(m.type())) logs.push(m.text().slice(0, 400)); });
page.on("pageerror", (e) => logs.push("PAGEERROR " + e.message.slice(0, 400)));

// A pad the page can read: 4 axes and 17 buttons, as Chrome reports a DualSense with the standard mapping.
await page.addInitScript(() => {
  const pad = {
    id: "DualSense Wireless Controller (STANDARD GAMEPAD Vendor: 054c Product: 0ce6) [synthetic]",
    index: 0, connected: true, mapping: "standard", timestamp: 0,
    axes: [0, 0, 0, 0],
    buttons: Array.from({ length: 17 }, () => ({ pressed: false, touched: false, value: 0 })),
  };
  window.__pad = { pad, plugged: false };
  navigator.getGamepads = () => [window.__pad.plugged ? pad : null, null, null, null];
});
const padSet = (axes, pressed = []) => page.evaluate(([axes, pressed]) => {
  const p = window.__pad.pad;
  p.axes = axes;
  p.buttons = p.buttons.map((_, i) => ({ pressed: pressed.includes(i), touched: pressed.includes(i), value: pressed.includes(i) ? 1 : 0 }));
  p.timestamp = performance.now();
}, [axes, pressed]);

// ?standin: this script checks the page on the stand-in plant (microduck-fmu.mjs checks the FMU).
await page.goto(process.env.GAME_URL ?? `http://127.0.0.1:${port}/microduck/?standin`);
await page.waitForFunction(() => window.ready, null, { timeout: 90000 });
const read = () => page.evaluate(() => game.state());
const check = (name, ok, detail) => { console.log(`${ok ? "ok  " : "FAIL"} ${name} ${JSON.stringify(detail)}`); if (!ok) process.exitCode = 1; };
const until = async (test, ms) => {
  const end = Date.now() + ms;
  for (;;) {
    const state = await read();
    if (test(state) || Date.now() > end) return state;
    await page.waitForTimeout(50);
  }
};
const brief = (s) => ({ plant: s.plant, carry: s.carry, policy: s.policy, enabled: s.enabled, net: s.net, ticks: s.ticks, mode: s.mode, pad: s.pad.slice(0, 20), command: s.command.map((v) => +v.toFixed(3)), actual: s.actual.map((v) => +v.toFixed(3)), loaded: s.loaded, failure: s.failure });

const first = await read();
check("the stand-in plant runs, labelled as such", first.plant === "stand-in" && /Stand-in plant, not the bg-sim model/.test(await page.textContent("#banner")), brief(first));
const running = await until((s) => s.ticks > 50 && s.net === "walk", 10000);
check("the policy loads and runs at about 50 Hz", running.enabled && running.policy === "velstand.onnx" && running.net === "walk" && running.action.length === 14 && running.action.every(Number.isFinite), brief(running));
const t0 = await read();
await page.waitForTimeout(2000);
const t1 = await read();
const rate = (t1.ticks - t0.ticks) / 2;
check("control ticks keep pace with the clock", rate > 40 && rate < 55, { rate });

await page.keyboard.down("KeyW");
const walking = await until((s) => s.command[0] > 0.3, 4000);
check("W asks for forward speed through the EMA", walking.command[0] > 0.3 && walking.net === "walk", brief(walking));
await page.waitForTimeout(800);
const moved = await read();
check("the trunk is carried forward on the stand-in", moved.position[0] > 0.1 && moved.actual[0] > 0.2, { position: moved.position, actual: moved.actual });
await page.keyboard.up("KeyW");
const stopped = await until((s) => Math.abs(s.command[0]) < 0.01, 4000);
check("letting go stops asking", Math.abs(stopped.command[0]) < 0.01, brief(stopped));

// The synthetic DualSense: connect, left stick up, D-pad up for head mode, Cross to sit.
await page.evaluate(() => {
  window.__pad.plugged = true;
  window.dispatchEvent(Object.assign(new Event("gamepadconnected"), { gamepad: window.__pad.pad }));
});
await padSet([0, -1, 0, 0]);
const padWalk = await until((s) => s.command[0] > 0.35, 4000);
check("the pad's left stick up walks forward at up to 0.4 m/s", padWalk.pad.startsWith("DualSense") && padWalk.command[0] > 0.35 && padWalk.command[0] <= 0.4, brief(padWalk));
await padSet([1, 0, 0, 0]);
const padTurn = await until((s) => s.command[2] < -0.9, 4000);
check("in head + move, the start mode, the left stick right turns right (negative yaw rate)", padTurn.command[2] < -0.9, brief(padTurn));
await padSet([0, 0, 0, 0], [12]);
await page.waitForTimeout(100);
await padSet([0, 0, 0, 0]);
check("D-pad up selects head mode", (await read()).mode === "head", {});
await padSet([0, 0, 0, 0], [14]);
await page.waitForTimeout(100);
await padSet([0, 0, 0, 0]);
check("D-pad left goes back to move", (await read()).mode === "drive", {});
const shot = await page.screenshot({ path: process.argv[2] ?? "microduck-keys.png" });
check("screenshot taken", shot.length > 10000, { bytes: shot.length });

await until((s) => s.loaded.includes("sitstand") && s.loaded.includes("kick_left"), 15000);
await padSet([0, 0, 0, 0], [0]);
await page.waitForTimeout(100);
await padSet([0, 0, 0, 0]);
const sat = await until((s) => s.net === "sit", 3000);
check("Cross sits, on the sit-stand network", sat.net === "sit", brief(sat));
await page.waitForTimeout(2300);
const seated = await read();
check("sitting does not carry the trunk (the posture flag is not a speed)", Math.abs(seated.actual[0]) < 0.05 && seated.net === "sit", brief(seated));
await page.keyboard.press("Space");
const rose = await until((s) => s.net === "rise", 3000);
check("Space stands it up again", rose.net === "rise", brief(rose));
await until((s) => s.net === "walk", 3000);
await page.keyboard.press("KeyZ");
const kicked = await until((s) => s.net === "kick_left", 2000);
check("Z kicks left", kicked.net === "kick_left", brief(kicked));
await page.screenshot({ path: (process.argv[2] ?? "microduck-keys.png").replace(/\.png$/, "-kick.png") });
const back = await until((s) => s.net === "walk", 3000);
check("and hands back to walking", back.net === "walk", brief(back));
await page.keyboard.press("Enter");
const off = await until((s) => !s.enabled, 2000);
check("Enter turns the policy off", !off.enabled, brief(off));
await page.keyboard.press("Enter");
await page.keyboard.press("KeyK");
const foot = await read();
check("K carries the trunk round the stance foot", foot.carry === "foot" && /stance foot/.test(await page.textContent("#banner")), brief(foot));
await page.keyboard.press("KeyT");
await page.waitForTimeout(800);
const side = await page.evaluate(() => game.side.state);
check("T opens the telemetry", side.open === "KeyT", side);
await page.screenshot({ path: (process.argv[2] ?? "microduck-keys.png").replace(/\.png$/, "-telemetry.png") });

check("no page errors or console errors", logs.length === 0, logs);
await browser.close();
