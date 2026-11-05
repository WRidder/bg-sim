// The side windows in every game, with real key presses and a look at the result: telemetry, the
// setup, that one closes the other, and that a slider reaches the running model.
// node tests/telemetry-keys.mjs [out-dir] [game ...]; GAMES_PORT picks the dev server.
import { chromium } from "playwright";

const port = process.env.GAMES_PORT ?? "8831";
const out = process.argv[2] ?? ".";
const only = process.argv.slice(3);
const browser = await chromium.launch({ headless: true, args: ["--use-angle=d3d11", "--ignore-gpu-blocklist", "--enable-gpu", "--enable-unsafe-swiftshader"] });
const check = (name, ok, detail) => {
  console.log(`${ok ? "ok  " : "FAIL"} ${name} ${JSON.stringify(detail)}`);
  if (!ok) {
    process.exitCode = 1;
  }
};

const GAMES = [
  { name: "f16", path: "f16/", start: "#fly", keys: ["ArrowDown"], setup: true },
  { name: "cessna", path: "cessna/", start: "#fly", keys: ["ArrowDown"], setup: false },
  { name: "a109", path: "a109/", start: "#fly", keys: ["ArrowUp"], setup: false },
  { name: "cars", path: "cars/?grid=1024&track=harbour", start: "#go", keys: ["ArrowUp"], wait: 7000, setup: true },
];

for (const game of GAMES.filter((g) => only.length === 0 || only.includes(g.name))) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  const errors = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text().slice(0, 300)));
  page.on("pageerror", (e) => errors.push(`PAGEERROR ${e.message.slice(0, 300)}`));
  await page.goto(`http://127.0.0.1:${port}/${game.path}`);
  await page.waitForFunction(() => window.ready, null, { timeout: 90000 });
  const state = () => page.evaluate(() => ({ ...window.game.side.state, ...window.game.telemetry.state }));
  const hidden = (id) => page.evaluate((name) => document.getElementById(name)?.hidden ?? true, id);
  const windows = async () => ({ telemetry: !(await hidden("telemetry")), setup: !(await hidden("setup")) });

  check(`${game.name}: nothing open to begin with`, (await state()).open === null, await state());
  await page.keyboard.press("t");
  await page.waitForTimeout(300);
  check(`${game.name}: telemetry stays away on the title`, await hidden("telemetry"), {});
  await page.click(game.start);
  await page.waitForTimeout(game.wait ?? 1500);
  for (const key of game.keys) {
    await page.keyboard.down(key);
  }
  await page.waitForTimeout(4000);
  for (const key of game.keys) {
    await page.keyboard.up(key);
  }
  const running = await state();
  check(`${game.name}: shows and records in the run`, running.open === "KeyT" && !(await hidden("telemetry")) && running.samples > 30, running);
  await page.screenshot({ path: `${out}/telemetry-${game.name}.png` });

  await page.keyboard.press("p");
  await page.waitForTimeout(300);
  const before = (await state()).samples;
  await page.waitForTimeout(500);
  check(`${game.name}: a pause freezes the trace`, (await state()).samples === before, { before, after: (await state()).samples });
  await page.keyboard.press("p");
  await page.waitForTimeout(200);

  if (game.setup) {
    await page.keyboard.press("y");
    await page.waitForTimeout(200);
    const both = await windows();
    check(`${game.name}: Y opens the setup and closes telemetry`, both.setup && !both.telemetry, both);
    await page.keyboard.press("t");
    await page.waitForTimeout(200);
    const back = await windows();
    check(`${game.name}: T opens telemetry and closes the setup`, back.telemetry && !back.setup, back);
    await page.keyboard.press("y");
    await page.waitForTimeout(200);
    await page.screenshot({ path: `${out}/setup-${game.name}.png` });
    await page.keyboard.press("y");
    await page.waitForTimeout(200);
    const none = await windows();
    check(`${game.name}: Y closes the setup`, !none.setup && !none.telemetry, none);
  } else {
    await page.keyboard.press("y");
    await page.waitForTimeout(200);
    check(`${game.name}: a model with no parameters has no setup, and Y leaves telemetry be`, (await windows()).telemetry, await windows());
    await page.keyboard.press("t");
    await page.waitForTimeout(200);
  }

  await page.keyboard.press("Shift+T");
  await page.waitForTimeout(300);
  check(`${game.name}: Shift+T moves it across`, (await state()).side === "left" && (await windows()).telemetry, await state());
  await page.screenshot({ path: `${out}/left-${game.name}.png` });
  await page.keyboard.press("t");
  await page.waitForTimeout(200);
  check(`${game.name}: T takes it away`, await hidden("telemetry"), {});

  if (game.name === "cars") {
    const tlim = () => page.evaluate(() => window.game.car.get("motor_r_tlim"));
    const rawTlim = await tlim();
    const pending = () => page.evaluate(() => window.game.car.tuning.pending);
    await page.keyboard.press("y");
    await page.waitForTimeout(200);
    await page.evaluate(() => {
      const input = document.querySelector('#setup input[aria-label="Motor torque"]');
      input.value = "150";
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    check("cars: a change waits for the restart, and the window says so", (await pending()) && (await page.textContent(".setup-note")).includes("restart"), await page.textContent(".setup-note"));
    check("cars: the running car is still the old one", (await tlim()) === rawTlim, await tlim());
    await page.keyboard.press("r");
    await page.waitForTimeout(600);
    const limit = await tlim();
    check("cars: after a restart the FMU has the value", limit <= 150.0001 && !(await pending()), { limit, before: rawTlim });
    await page.reload();
    await page.waitForFunction(() => window.ready, null, { timeout: 90000 });
    await page.waitForTimeout(500);
    const kept = await page.evaluate(() => window.game.car.tuning.changed);
    check("cars: the setup is remembered", kept["MotorR/T_max"] === 150, kept);
    await page.click("#setup header button");
    check("cars: Stock puts it back", Object.keys(await page.evaluate(() => window.game.car.tuning.changed)).length === 0, {});
  } else {
    await page.reload();
    await page.waitForFunction(() => window.ready, null, { timeout: 90000 });
  }
  check(`${game.name}: the side is remembered`, (await state()).side === "left", await state());
  check(`${game.name}: no errors`, errors.length === 0, errors);
  await page.close();
}
await browser.close();
