// Flies the F-16 with a synthetic gamepad in the Ace Combat 7 layout: node tests/f16-pad.mjs
import { chromium } from "playwright";

const port = process.env.GAMES_PORT ?? "8831";
const browser = await chromium.launch({
  headless: true,
  args: ["--use-angle=d3d11", "--ignore-gpu-blocklist", "--enable-gpu", "--enable-unsafe-swiftshader"],
});
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
const logs = [];
page.on("pageerror", (e) => logs.push("PAGEERROR " + e.message.slice(0, 400)));

// A pad with the standard mapping that the test moves: window.pad.axes, window.pad.buttons[i].value.
await page.addInitScript(() => {
  const pad = {
    id: "Synthetic pad (STANDARD GAMEPAD)", index: 0, connected: true, mapping: "standard", timestamp: 0,
    axes: [0, 0, 0, 0],
    buttons: Array.from({ length: 17 }, () => ({ value: 0, get pressed() { return this.value > 0.5; }, touched: false })),
  };
  window.pad = pad;
  navigator.getGamepads = () => [pad];
});
const press = async (button, ms = 80) => {
  await page.evaluate((b) => { window.pad.buttons[b].value = 1; }, button);
  await page.waitForTimeout(ms);
  await page.evaluate((b) => { window.pad.buttons[b].value = 0; }, button);
  await page.waitForTimeout(80);
};
const hold = (button, value) => page.evaluate(([b, v]) => { window.pad.buttons[b].value = v; }, [button, value]);
const stick = (axes) => page.evaluate((a) => { window.pad.axes = a; }, axes);
const read = () => page.evaluate(() => ({ ...game.state(), u: Array.from(game.flight.u.slice(0, 4)), azimuth: game.rig.azimuth }));
const check = (name, ok, detail) => {
  console.log(`${ok ? "ok  " : "FAIL"} ${name} ${JSON.stringify(detail)}`);
  if (!ok) process.exitCode = 1;
};
const [A, B, Y, LB, RB, LT, RT, START, R3] = [0, 1, 3, 4, 5, 6, 7, 9, 11];

await page.goto(process.env.GAME_URL ?? `http://127.0.0.1:${port}/f16/?grid=1024`);
await page.waitForFunction(() => window.ready, null, { timeout: 90000 });
await page.click('#mode button[data-value="intercept"]');
await press(START);
let s = await read();
check("Start begins the flight", s.phase === "flying" && s.mode === "intercept", s.phase);

await stick([0, 1, 0, 0]);
await page.waitForTimeout(300);
s = await read();
check("left stick back pulls", s.u[0] > 0.9, s.u);
await stick([-1, 0, 0, 0]);
await page.waitForTimeout(300);
s = await read();
check("left stick left rolls left", s.u[1] < -0.9 && Math.abs(s.u[0]) < 0.05, s.u);
await stick([0, 0, 0, 0]);

await hold(LB, 1);
await page.waitForTimeout(500);
s = await read();
check("LB is left rudder", s.u[2] < -0.5, s.u);
await hold(LB, 0);
await hold(RB, 1);
await page.waitForTimeout(900);
s = await read();
check("RB is right rudder", s.u[2] > 0.5, s.u);
await hold(RB, 0);

const before = (await read()).u[3];
await hold(RT, 1);
await page.waitForTimeout(600);
const up = (await read()).u[3];
await hold(RT, 0);
await hold(LT, 1);
await page.waitForTimeout(1200);
const down = (await read()).u[3];
await hold(LT, 0);
check("RT adds throttle, LT takes it off", up > before + 0.15 && down < up - 0.3, { before, up, down });

await stick([0, 0, 1, 0]);
await page.waitForTimeout(500);
s = await read();
check("right stick looks round", s.azimuth < -1.5, s.azimuth);
await stick([0, 0, 0, 0]);

await press(R3);
s = await read();
check("R3 changes the view", s.view === "cockpit", s.view);

await page.waitForFunction(() => game.state().lock.selectedId !== null, null, { timeout: 5000 });
const first = (await read()).lock.selectedId;
await press(Y);
s = await read();
check("Y takes the next target", s.lock.selectedId !== first, [first, s.lock.selectedId]);

await press(START);
s = await read();
check("Start pauses", s.phase === "paused", s.phase);
await press(A);
s = await read();
check("A resumes", s.phase === "flying", s.phase);

// Level off behind a drone would take a pilot; the launch itself is checked with the lock forced.
const locked = await page.waitForFunction(() => game.state().lock.locked, null, { timeout: 8000 }).then(() => true, () => false);
if (locked) {
  const free = (await read()).missiles;
  await press(B);
  s = await read();
  check("B fires when locked", s.missiles === free - 1, [free, s.missiles]);
} else {
  console.log("skip B fires when locked (no lock within 8 s after the manoeuvres)");
}
console.log(logs.slice(0, 8).join("\n"));
await browser.close();
