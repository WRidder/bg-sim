#!/usr/bin/env node
/**
 * Captures the example gallery thumbnails (W5.4).
 *
 *   npm run capture-thumbnails [-- --example dc-motor --example drivetrain] [--fake] [--port N]
 *
 * For every example the backend lists, a private backend (`uv run bgsim`, the real Julia worker so
 * every block draws with its real ports, a temporary projects root, a free port) imports the example
 * through POST /api/projects like the app does, opens the model, and Chromium renders the diagram
 * (and, for a model with a scene, the 3D view as an inset). Output, all committed:
 *
 *   src/examples/thumbnails/<example>.png   480 x 300 (smaller for dense scenes), each well under 100 kB
 *   src/examples/gallery.json               title, one-line description (from the example's README),
 *                                           models and whether a scene exists
 *
 * Nothing is written into `examples/`. `--fake` uses the fixture worker (fast, but blocks beyond the
 * minimal catalog draw without ports); the committed thumbnails come from the real worker.
 * The backend serves the existing `web/dist`: run `npm run build` first.
 *
 * A scene whose objects are placed only by a run (aircraft, vehicles) shows as tiny dots before one:
 * `--run` (or `"capture": {"run": true}` in the example's gallery.json entry) runs the model, seeks the
 * playback to `--at` (a fraction of the run, default 0.5) or `--time` seconds, fits the view, zooms
 * `--zoom` wheel notches and only then shoots the inset. `--out DIR` writes the PNGs and gallery.json
 * there instead of into src/examples. See scripts/README.md.
 */
import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

import { captureSettings } from "./thumbnail-capture-settings.mjs";

const webDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(webDir, "..");
const outDir = path.join(webDir, "src", "examples", "thumbnails");
const manifestFile = path.join(webDir, "src", "examples", "gallery.json");

const THUMB = { width: 480, height: 300 };
const MAX_BYTES = 100 * 1024;
const BUDGET_BYTES = 80 * 1024;
/** Report output goes to stdout. */
function out(text) {
  process.stdout.write(`${text}
`);
}
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const USAGE =
  "usage: node scripts/capture-thumbnails.mjs [--example NAME]... [--fake] [--port N] [--out DIR]\n" +
  "         [--model NAME] [--run] [--no-run] [--at FRACTION] [--time SECONDS] [--zoom NOTCHES] [--view iso|top|front|side] [--orbit DX,DY]";

function parseArgs(argv) {
  const options = { examples: [], fake: false, port: null, out: null, capture: {} };
  const number = (text, name) => {
    const value = Number(text);
    if (!Number.isFinite(value)) {
      console.error(`${name} needs a number, got ${JSON.stringify(text)}\n${USAGE}`);
      process.exit(2);
    }
    return value;
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--fake") options.fake = true;
    else if (arg === "--example") options.examples.push(argv[++i]);
    else if (arg === "--port") options.port = Number(argv[++i]);
    else if (arg === "--out") options.out = path.resolve(argv[++i]);
    else if (arg === "--model") options.capture.model = argv[++i];
    else if (arg === "--run") options.capture.run = true;
    else if (arg === "--no-run") options.capture.run = false;
    else if (arg === "--at") options.capture.at = number(argv[++i], "--at");
    else if (arg === "--time") options.capture.time = number(argv[++i], "--time");
    else if (arg === "--zoom") options.capture.zoom = number(argv[++i], "--zoom");
    else if (arg === "--view") options.capture.view = argv[++i];
    else if (arg === "--orbit") options.capture.orbit = argv[++i].split(",").map((part) => number(part, "--orbit"));
    else {
      console.error(USAGE);
      process.exit(2);
    }
  }
  return options;
}

function freePort() {
  return new Promise((resolve, reject) => {
    const socket = net.createServer();
    socket.on("error", reject);
    socket.listen(0, "127.0.0.1", () => {
      const { port } = socket.address();
      socket.close(() => resolve(port));
    });
  });
}

function killTree(child) {
  if (!child || child.exitCode !== null || child.pid === undefined) return;
  if (process.platform === "win32") spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
  else child.kill("SIGKILL");
}

async function waitForHealth(url, child, timeoutMs, needReady) {
  const deadline = Date.now() + timeoutMs;
  let last = "no answer";
  while (Date.now() < deadline) {
    if (child.exitCode !== null) throw new Error(`the backend exited early with code ${child.exitCode}`);
    try {
      const response = await fetch(`${url}/api/health`, { signal: AbortSignal.timeout(2000) });
      if (response.ok) {
        const health = await response.json();
        if (!needReady || health.worker === "ready") return;
        last = `worker ${JSON.stringify(health.worker)}`;
      } else last = `HTTP ${response.status}`;
    } catch (error) {
      last = error instanceof Error ? error.message : String(error);
    }
    await sleep(250);
  }
  throw new Error(`the backend did not become healthy (${last})`);
}

/** Strip the Markdown of one README line to plain text. */
function plain(text) {
  return text
    .replace(/`([^`]*)`/g, "$1")
    .replace(/\*\*([^*]*)\*\*/g, "$1")
    .replace(/\*([^*]*)\*/g, "$1")
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

/** Title and one-line description from an example's README: the H1 and the first prose paragraph. */
function readmeInfo(example) {
  const file = path.join(repoRoot, "examples", example, "README.md");
  if (!existsSync(file)) return {};
  const lines = readFileSync(file, "utf8").split(/\r?\n/);
  const heading = lines.find((line) => /^#\s+/.test(line));
  const title = heading
    ? plain(heading.replace(/^#\s+/, ""))
        .replace(/\s*\((?:plan|milestone|M\d|[A-Z]\d+\.\d+)[^)]*\)\s*$/i, "")
        .replace(/^Example:\s*/i, "")
        .trim()
    : undefined;
  // "# dc-motor — a tagline": the slug becomes the title and the tagline the description.
  const dash = title ? /^(.+?)\s+[—–-]\s+(.+)$/.exec(title) : null;
  if (dash) {
    const left = /^[a-z0-9]+([-_][a-z0-9]+)*$/.test(dash[1]) ? dash[1].replace(/[-_]+/g, " ") : dash[1];
    const tagline = dash[2].replace(/[.\s]+$/, "");
    return {
      title: left.charAt(0).toUpperCase() + left.slice(1),
      description: `${tagline.charAt(0).toUpperCase()}${tagline.slice(1)}.`,
    };
  }
  let paragraph = [];
  let seen = false;
  for (const line of lines) {
    if (/^#\s+/.test(line)) {
      seen = true;
      continue;
    }
    if (!seen) continue;
    const trimmed = line.trim();
    if (trimmed === "") {
      if (paragraph.length > 0) break;
      continue;
    }
    if (/^(#|\||```|[-*]\s|\d+\.\s|>)/.test(trimmed)) {
      if (paragraph.length > 0) break;
      continue;
    }
    paragraph.push(trimmed);
  }
  let description = plain(paragraph.join(" "));
  // One line: the first sentence, capped.
  const sentence = /^(.{20,}?[.!?])(\s|$)/.exec(description);
  if (sentence) description = sentence[1];
  if (description.length > 170) description = `${description.slice(0, 167).replace(/\s+\S*$/, "")}…`;
  return { title: title || undefined, description: description || undefined };
}

async function json(baseUrl, route, init) {
  const response = await fetch(`${baseUrl}${route}`, init);
  if (!response.ok) throw new Error(`${init?.method ?? "GET"} ${route} -> ${response.status}: ${(await response.text()).slice(0, 300)}`);
  return response.json();
}

async function settleViewport(page) {
  const viewport = page.locator(".react-flow__viewport");
  let previous = "";
  let stable = 0;
  for (let i = 0; i < 60 && stable < 3; i += 1) {
    const current = (await viewport.getAttribute("style")) ?? "";
    stable = current === previous && current !== "" ? stable + 1 : 0;
    previous = current;
    await sleep(100);
  }
}

const HIDE_CHROME =
  '[role="tooltip"], [role="status"], [role="alert"], .toast, .react-flow__attribution, .react-flow__panel, .react-flow__minimap, .react-flow__controls { display: none !important; }';

const HIDE_VIEWER_BUTTONS =
  '[data-testid^="viewer-preset"], [data-testid="viewer-fit"], [data-testid="viewer-ortho"], [data-testid="detach-viewer"] { visibility: hidden !important; }';

/** Run the open model and wait until the run is done; returns the wall seconds. */
async function runModel(page, timeoutS) {
  const t0 = Date.now();
  const button = page.getByTestId("run-button");
  await button.waitFor({ state: "visible", timeout: 60_000 });
  await page.waitForFunction(() => document.querySelector('[data-testid="run-button"]')?.disabled === false, null, { timeout: 120_000 });
  await button.click();
  await page.waitForFunction(
    () => {
      const status = document.querySelector('[data-testid="run-status"]')?.getAttribute("data-status");
      if (status === "failed" || status === "cancelled") throw new Error(`the run ended ${status}`);
      return status === "done";
    },
    null,
    { timeout: timeoutS * 1000, polling: 500 },
  );
  return (Date.now() - t0) / 1000;
}

/**
 * After a run: wait for the 3D view to hold the run, pause it, seek to `settings.time` seconds or the
 * `settings.at` fraction (default 0.5), set the camera preset, fit and zoom.
 */
async function frameAfterRun(page, settings) {
  await page.waitForFunction(
    () => {
      const bar = document.querySelector('[data-testid="playback-bar"]');
      const note = document.querySelector('[data-testid="playback-note"]');
      if (note?.getAttribute("role") === "alert") throw new Error(`the 3D view could not load the run: ${note.textContent}`);
      return bar?.getAttribute("data-mode") === "playback";
    },
    null,
    { timeout: 120_000, polling: 250 },
  );
  const bar = page.getByTestId("playback-bar");
  if ((await bar.getAttribute("data-playing")) === "true") await page.getByTestId("playback-toggle").click();
  const slider = page.getByTestId("playback-time");
  const start = Number((await slider.getAttribute("min")) ?? "0");
  const end = Number(await slider.getAttribute("max"));
  const step = Number((await slider.getAttribute("step")) ?? "0") || 0.001;
  const target = settings.time ?? start + (end - start) * (settings.at ?? 0.5);
  const clamped = Math.min(end, Math.max(start, Math.round(target / step) * step));
  await slider.fill(String(Number(clamped.toFixed(6))));
  await sleep(400);
  if (settings.view) await page.getByTestId(`viewer-preset-${settings.view}`).dispatchEvent("click");
  await page.getByTestId("viewer-fit").dispatchEvent("click");
  await sleep(700);
  await page.addStyleTag({ content: HIDE_VIEWER_BUTTONS });
  const box = await page.getByTestId("viewer-canvas").boundingBox();
  if (box) {
    // the view zooms toward, and orbits around, the scene point under the cursor: the centre of the view
    const cx = box.x + box.width / 2;
    const cy = box.y + box.height / 2;
    await page.mouse.move(cx, cy);
    const notches = Math.abs(settings.zoom ?? 0);
    for (let z = 0; z < notches; z += 1) {
      await page.mouse.wheel(0, settings.zoom > 0 ? -300 : 300);
      await sleep(120);
    }
    if (settings.orbit) {
      await page.mouse.down();
      await page.mouse.move(cx + settings.orbit[0], cy + settings.orbit[1], { steps: 10 });
      await page.mouse.up();
    }
    await page.mouse.move(2, 2);
  }
  await sleep(600);
  return Number(await bar.getAttribute("data-time"));
}

/**
 * Open `model` of `project` and return PNG buffers of the diagram and (with a scene) the 3D view.
 * With `settings.run` the model runs first and the 3D view is framed on the run (see {@link frameAfterRun}).
 */
async function shoot(page, baseUrl, project, model, nodeCount, hasScene, settings = {}) {
  await page.goto(`${baseUrl}/?project=${encodeURIComponent(project)}&model=${encodeURIComponent(model)}`);
  await page.waitForFunction((n) => document.querySelectorAll('[data-testid="diagram-node"]').length >= n, nodeCount, {
    timeout: 60_000,
  });
  await page.evaluate(() => document.fonts.ready);
  await page.getByTestId("fit-view").click();
  await settleViewport(page);
  await page.addStyleTag({ content: HIDE_CHROME });
  await page.mouse.move(2, 2);
  const diagram = await page.locator(".react-flow").screenshot({ animations: "disabled" });
  const background = await page.evaluate(
    () => getComputedStyle(document.querySelector(".react-flow")).backgroundColor || "transparent",
  );
  let scene = null;
  let framed = null;
  if (hasScene) {
    const runSeconds = settings.run ? await runModel(page, settings.runTimeout ?? 900) : null;
    // a framed shot gets a taller dock, so the 3D view is closer to the inset's 1.6 aspect and the inset's
    // centre crop does not cut the framed objects
    if (settings.run) await page.setViewportSize({ width: 1280, height: 1600 });
    await page.getByRole("tab", { name: "3D View" }).click();
    await page.getByTestId("scene-view").waitFor({ state: "visible", timeout: 30_000 });
    await page.waitForFunction(() => document.querySelector('[data-testid="scene-view"]')?.getAttribute("data-state") === "loaded", null, {
      timeout: 60_000,
    });
    await page.waitForFunction(() => {
      const viewer = document.querySelector('[data-testid="viewer"]');
      return viewer !== null && Number(viewer.getAttribute("data-frames") ?? "0") > 2;
    }, null, { timeout: 30_000 });
    if (runSeconds !== null) framed = { runSeconds, time: await frameAfterRun(page, settings) };
    await sleep(600);
    scene = await page.getByTestId("viewer-canvas").screenshot({ animations: "disabled" });
  }
  return { diagram, scene, background, framed };
}

/** Compose the PNG (480 x 300 at scale 1): the diagram, with the 3D view as an inset when there is one. */
async function compose(browser, shots, theme, scale = 1) {
  const size = { width: Math.round(THUMB.width * scale), height: Math.round(THUMB.height * scale) };
  const page = await browser.newPage({ viewport: size });
  const data = (buffer) => `data:image/png;base64,${buffer.toString("base64")}`;
  const surface = theme === "dark" ? "#171c24" : "#ffffff";
  const border = theme === "dark" ? "#3b4655" : "#b3bcc7";
  await page.setContent(`<!doctype html><html><body style="margin:0;width:${size.width}px;height:${size.height}px;overflow:hidden;background:${
    shots.background === "rgba(0, 0, 0, 0)" ? surface : shots.background
  };position:relative">
    <img src="${data(shots.diagram)}" style="position:absolute;inset:0;width:100%;height:100%;object-fit:contain">
    ${
      shots.scene
        ? `<img src="${data(shots.scene)}" style="position:absolute;right:${Math.round(8 * scale)}px;bottom:${Math.round(8 * scale)}px;width:${Math.round(196 * scale)}px;height:${Math.round(122 * scale)}px;object-fit:cover;border:1px solid ${border};border-radius:4px;box-shadow:0 2px 8px rgb(0 0 0 / 45%)">`
        : ""
    }
  </body></html>`);
  await page.waitForFunction(() => [...document.images].every((image) => image.complete));
  const png = await page.screenshot({ clip: { x: 0, y: 0, ...size } });
  await page.close();
  return png;
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (!existsSync(path.join(webDir, "dist", "index.html"))) {
    throw new Error("web/dist is not built; run `npm run build` first");
  }
  const projectsRoot = mkdtempSync(path.join(os.tmpdir(), "bgsim-thumbs-"));
  const port = options.port ?? (await freePort());
  const baseUrl = `http://127.0.0.1:${port}`;
  const environment = { ...process.env, BGSIM_PORT_HTTP: String(port), BGSIM_PROJECTS_ROOT: projectsRoot };
  delete environment.BGSIM_FAKE_WORKER;
  if (options.fake) environment.BGSIM_FAKE_WORKER = "1";

  const started = Date.now();
  const backend = spawn(process.platform === "win32" ? "uv.exe" : "uv", ["run", "bgsim"], {
    cwd: repoRoot,
    env: environment,
    stdio: "ignore",
  });
  let browser = null;
  const cleanup = async () => {
    try {
      if (browser) await browser.close();
    } catch {
      // already gone
    }
    killTree(backend);
    for (let attempt = 0; attempt < 10; attempt += 1) {
      try {
        rmSync(projectsRoot, { recursive: true, force: true });
        break;
      } catch {
        await sleep(300);
      }
    }
  };
  process.on("SIGINT", () => void cleanup().finally(() => process.exit(130)));
  process.on("exit", () => killTree(backend));

  try {
    // a cold Julia worker (first start after a change of the package) can take several minutes
    await waitForHealth(baseUrl, backend, 900_000, !options.fake);
    out(`backend ${baseUrl} ready after ${((Date.now() - started) / 1000).toFixed(1)} s (${options.fake ? "fake" : "real"} worker)`);

    const listed = (await json(baseUrl, "/api/examples")).examples;
    const examples = options.examples.length > 0 ? options.examples : listed;
    for (const name of examples) if (!listed.includes(name)) throw new Error(`unknown example ${name}; available: ${listed.join(", ")}`);

    // --out writes the PNGs and a gallery.json copy elsewhere; the settings still come from the committed manifest
    const thumbDir = options.out ?? outDir;
    const manifestTarget = options.out ? path.join(options.out, "gallery.json") : manifestFile;
    mkdirSync(thumbDir, { recursive: true });
    const manifest = existsSync(manifestFile) ? JSON.parse(readFileSync(manifestFile, "utf8")) : {};
    const settingsOf = new Map(examples.map((name) => [name, captureSettings(manifest[name]?.capture, options.capture)]));

    // Software GL: a hardware context per example exhausted the GPU memory after about ten examples.
    browser = await chromium.launch({ args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });

    for (const example of examples) {
      const t0 = Date.now();
      // A fresh context per example releases its WebGL context with it.
      const context = await browser.newContext({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 });
      // A tall dock, so the 3D view has room.
      await context.addInitScript(() => {
        try {
          localStorage.setItem("bgsim.theme", "dark");
          localStorage.setItem("bgsim.layout.rows", JSON.stringify({ main: 62, dock: 38 }));
        } catch {
          // storage unavailable
        }
      });
      const page = await context.newPage();
      const project = `thumb-${example}`;
      const opened = await json(baseUrl, "/api/projects", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ name: project, example }),
      });
      const models = opened.models.filter((entry) => entry.inProject).map((entry) => entry.name);
      const docs = [];
      for (const model of models) {
        docs.push({ name: model, doc: await json(baseUrl, `/api/projects/${project}/models/${model}`) });
      }
      const settings = settingsOf.get(example) ?? {};
      const withScene = docs.find((entry) => entry.doc.scene?.file);
      const named = settings.model === undefined ? undefined : docs.find((entry) => entry.name === settings.model);
      if (settings.model !== undefined && named === undefined) {
        throw new Error(`${example}: capture model ${settings.model} is not one of ${models.join(", ")}`);
      }
      const chosen = named ?? withScene ?? docs.find((entry) => entry.name === "iconic") ?? docs[0];
      if (chosen === undefined) {
        await context.close();
        out(`${example}: no models, skipped`);
        continue;
      }
      const nodeCount = (chosen.doc.diagram?.nodes ?? []).length;
      const shots = await shoot(page, baseUrl, project, chosen.name, nodeCount, Boolean(chosen.doc.scene?.file), settings);
      await context.close();
      // A dense diagram or a busy 3D view can exceed the budget at full size: step the size down.
      let png = null;
      for (const scale of [1, 0.85, 0.7, 0.55]) {
        png = await compose(browser, shots, "dark", scale);
        if (png.length <= BUDGET_BYTES) break;
      }
      if (png.length > MAX_BYTES) throw new Error(`${example}.png is ${png.length} bytes, over the ${MAX_BYTES} byte budget`);
      writeFileSync(path.join(thumbDir, `${example}.png`), png);

      const info = readmeInfo(example);
      const capture = manifest[example]?.capture;
      manifest[example] = {
        ...(info.title ? { title: info.title } : {}),
        ...(info.description ? { description: info.description } : {}),
        hasScene: docs.some((entry) => entry.doc.scene?.file),
        models,
        ...(capture ? { capture } : {}), // the committed per-example settings stay
      };
      await fetch(`${baseUrl}/api/projects/${project}`, { method: "DELETE" });
      writeFileSync(manifestTarget, `${JSON.stringify(Object.fromEntries(Object.entries(manifest).sort(([a], [b]) => a.localeCompare(b))), null, 2)}
`);
      const framed = shots.framed ? `, run ${shots.framed.runSeconds.toFixed(1)} s, framed at t = ${shots.framed.time.toFixed(2)} s` : "";
      out(
        `${example}: ${chosen.name} (${nodeCount} nodes${shots.scene ? ", 3D inset" : ""}${framed}) -> ${(statSync(path.join(thumbDir, `${example}.png`)).size / 1024).toFixed(1)} kB, ${((Date.now() - t0) / 1000).toFixed(1)} s`,
      );
    }

    const sorted = Object.fromEntries(Object.entries(manifest).sort(([a], [b]) => a.localeCompare(b)));
    writeFileSync(manifestTarget, `${JSON.stringify(sorted, null, 2)}\n`);
    out(`wrote ${path.relative(webDir, manifestTarget)} (${Object.keys(sorted).length} examples) in ${((Date.now() - started) / 1000).toFixed(1)} s`);
  } catch (error) {
    process.exitCode = 1;
    console.error(error instanceof Error ? error.stack ?? error.message : error);
  } finally {
    await cleanup();
  }
}

await main();
