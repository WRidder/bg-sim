// Drives with real key presses: the lights, pedals, steering, a whole lap, the ghost, a crash, the
// other car. node tests/cars-keys.mjs [out.png]; GAME_URL points it at the single file.
import { chromium } from "playwright";
const port = process.env.GAMES_PORT ?? "8831";
const browser = await chromium.launch({ headless: true, args: ["--use-angle=d3d11", "--ignore-gpu-blocklist", "--enable-gpu", "--enable-unsafe-swiftshader"] });
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
const logs = [];
page.on("console", (m) => { if (m.type() === "error") logs.push(m.text().slice(0, 400)); });
page.on("pageerror", (e) => logs.push("PAGEERROR " + e.message.slice(0, 400)));
page.on("response", (r) => { if (r.status() >= 400) logs.push(`${r.status()} ${r.url()}`); });
const url = process.env.GAME_URL ?? `http://127.0.0.1:${port}/cars/`;
await page.goto(`${url}${url.includes("?") ? "&" : "?"}grid=1024&track=harbour`);
await page.waitForFunction(() => window.ready, null, { timeout: 90000 });
const read = () => page.evaluate(() => ({ ...game.state(), yaw: game.car.get("yaw"), speed: game.car.get("speed"), soc: game.car.get("soc"), reverse: game.car.reversing }));
const check = (name, ok, detail) => {
  console.log(`${ok ? "ok  " : "FAIL"} ${name} ${JSON.stringify(detail)}`);
  if (!ok) {
    console.log(logs.join("\n"));
    process.exitCode = 1;
  }
};
const until = async (test, seconds) => {
  const end = Date.now() + seconds * 1000;
  for (;;) {
    const state = await read();
    if (test(state) || Date.now() > end) {
      return state;
    }
    await page.waitForTimeout(40);
  }
};
const wrap = (a) => Math.atan2(Math.sin(a), Math.cos(a));

const title = await read();
check("the car drives itself behind the title", title.phase === "title" && !(await page.isHidden("#title")), title);
await page.waitForTimeout(1500);
check("attract lap under way", (await read()).kmh > 10, await read());

await page.selectOption("#laps", "1");
await page.click("#go");
await page.keyboard.down("ArrowUp");
await page.waitForTimeout(1200);
const held = await read();
check("the lights hold the car", held.phase === "grid" && held.kmh === 0, held);
const lit = await until((s) => s.lights >= 3, 4);
check("the lights come on one by one", lit.lights >= 3, lit);
const going = await until((s) => s.phase === "driving", 8);
check("lights out starts the run", going.phase === "driving", going);
await page.waitForTimeout(1600);
const quick = await read();
check("up arrow accelerates", quick.kmh > 30, quick);
await page.keyboard.up("ArrowUp");
await page.keyboard.down("ArrowDown");
await page.waitForTimeout(700);
await page.keyboard.up("ArrowDown");
const slowed = await read();
check("down arrow brakes", slowed.kmh < quick.kmh - 15, slowed);
await page.keyboard.down("ArrowRight");
await page.keyboard.down("ArrowUp");
await page.waitForTimeout(500);
await page.keyboard.up("ArrowRight");
const right = await read();
check("right arrow turns right", wrap(right.yaw - slowed.yaw) < -0.02, right);
await page.keyboard.up("ArrowUp");

for (const view of ["cockpit", "nose", "tv", "chase"]) {
  await page.keyboard.press("KeyC");
  check(`C goes to ${view}`, (await read()).view === view, {});
}
await page.keyboard.press("KeyP");
const paused = await read();
await page.waitForTimeout(500);
const still = await read();
check("P pauses", paused.phase === "paused" && paused.time === still.time && !(await page.isHidden("#pause")), still);
await page.keyboard.press("KeyP");
await page.waitForTimeout(250);
check("P resumes", (await read()).phase === "driving", {});
await page.keyboard.press("KeyR");
await page.waitForTimeout(200);
check("R goes back to the grid", (await read()).phase === "grid", await read());
await page.keyboard.down("ArrowUp");
await until((s) => s.phase === "driving", 8);

// A whole lap by keyboard: look ahead along the road, tap left or right, hold about 80 km/h.
const pressed = new Set();
const hold = async (code, on) => {
  if (on !== pressed.has(code)) {
    await (on ? page.keyboard.down(code) : page.keyboard.up(code));
    if (on) pressed.add(code);
    else pressed.delete(code);
  }
};
pressed.add("ArrowUp");
const steerState = () => page.evaluate(() => {
  const { car, track } = game;
  const speed = car.get("speed");
  const ahead = track.pose(car.s + 7 + speed * 0.45, 0);
  const x = car.get("chassis_px");
  const y = car.get("chassis_py");
  const off = Math.atan2(ahead.y - y, ahead.x - x) - car.get("yaw");
  return { off: Math.atan2(Math.sin(off), Math.cos(off)), speed, phase: game.state().phase, laps: game.state().laps };
});
const lapBegan = Date.now();
let state = await steerState();
while (state.phase === "driving" && Date.now() - lapBegan < 170000) {
  await hold("ArrowLeft", state.off > 0.035);
  await hold("ArrowRight", state.off < -0.035);
  await hold("ArrowUp", state.speed < 21);
  await hold("ArrowDown", state.speed > 24);
  await page.waitForTimeout(25);
  state = await steerState();
}
for (const code of [...pressed]) {
  await hold(code, false);
}
const done = await read();
check("a keyboard lap ends on the result screen", done.phase === "over" && done.laps === 1 && !(await page.isHidden("#over")), done);
const rows = await page.locator("#over-laps li").count();
const shown = await page.textContent("#over-laps");
check("the lap is on the list", rows === 1, shown);
await page.screenshot({ path: process.argv[2] ?? "cars-keys.png" });
const kept = await page.evaluate(() => ({ best: localStorage.getItem("apex-dust-best-harbour"), ghost: (localStorage.getItem("apex-dust-ghost-harbour") ?? "").length }));
check("best time and ghost are kept", Number(kept.best) > 0 && kept.ghost > 500, kept);

await page.click("#again");
await until((s) => s.phase === "driving", 9);
await page.keyboard.down("ArrowUp");
await page.waitForTimeout(1500);
const ghosted = await read();
check("the ghost rides along", ghosted.ghost === true, ghosted);

// Hard right into whatever is there: the game has to catch it and put the car back.
await page.keyboard.down("ArrowRight");
const hit = await until((s) => s.crashed, 25);
await page.keyboard.up("ArrowRight");
await page.keyboard.up("ArrowUp");
check("a barrier stops the car", hit.crashed, hit);
const back = await until((s) => !s.crashed, 6);
check("back on the road", !back.crashed && Math.abs(back.d) < 12, back);
await page.keyboard.press("Escape");
await page.click("#quit");
const menu = await read();
check("Esc and the menu button leave", menu.phase === "title", menu);

await page.click('#car button[data-value="buggy"]');
const buggy = await until((s) => s.kind === "buggy" && !(s.phase !== "title"), 30);
await page.waitForFunction(() => document.getElementById("switching").hidden, null, { timeout: 30000 });
check("the buggy goes to a dirt stage", buggy.kind === "buggy" && buggy.track !== "harbour", buggy);
await page.click("#go");
await until((s) => s.phase === "driving", 9);
await page.keyboard.down("ArrowUp");
await page.waitForTimeout(2000);
await page.keyboard.up("ArrowUp");
const dirt = await read();
check("the buggy drives", dirt.kmh > 25 && !dirt.crashed, dirt);
await page.keyboard.down("ArrowDown");
await until((s) => s.kmh < 1, 8);
await page.keyboard.up("ArrowDown");
await page.waitForTimeout(300);
await page.keyboard.press("KeyV");
await page.keyboard.down("ArrowUp");
await page.waitForTimeout(1500);
await page.keyboard.up("ArrowUp");
const backward = await page.evaluate(() => ({ reverse: game.car.reversing, u: game.car.get("u") }));
check("V and the accelerator back the car up", backward.reverse && backward.u < -0.5, backward);

check("no page errors", logs.length === 0, logs);
await browser.close();
