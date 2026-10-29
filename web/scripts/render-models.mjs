#!/usr/bin/env node
/**
 * Headless model render tool: draws `examples/<name>/models/*.bgmodel.json` as the
 * editor does, writes one PNG per model and prints a layout lint.
 *
 *   node scripts/render-models.mjs --example robot-arm-2d [--model arm] [--out DIR]
 *        [--width 1800 --height 1100] [--port auto|N] [--build]
 *        [--zoom F] [--region x,y,w,h] [--real]
 *        [--subsystem <nodeId>[/<nodeId>...]]   (render the interior of a subsystem)
 *
 * Isolation: a private backend (`uv run`, fake worker, free port, temporary projects
 * root) imports the example through POST /api/projects, exactly like the app. The
 * backend serves the existing `web/dist`, or, with --build, a fresh build in a temp
 * directory (web/dist is never touched). Nothing is written into `examples/`.
 */
import { spawn, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  renameSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

const webDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(webDir, "..");

/** Report output goes to stdout; diagnostics of the tool itself go to stderr. */
function out(text) {
  process.stdout.write(`${text}
`);
}

function usage(message) {
  if (message) console.error(`error: ${message}\n`);
  console.error(
    "usage: node scripts/render-models.mjs --example <name> [--model <name>] [--out <dir>]\n" +
      "         [--width 1800] [--height 1100] [--port auto|<n>] [--build]\n" +
      "         [--zoom <factor>] [--region x,y,w,h] [--real]\n" +
      "         [--subsystem <nodeId>[/<nodeId>...]]",
  );
  process.exit(2);
}

function parseArgs(argv) {
  const options = { width: 1800, height: 1100, port: "auto", build: false };
  const flags = new Set(["build", "real", "help"]);
  const withValue = new Set(["example", "model", "out", "width", "height", "port", "zoom", "region", "subsystem"]);
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (!arg.startsWith("--")) usage(`unexpected argument ${arg}`);
    const key = arg.slice(2);
    if (key === "help") usage();
    else if (flags.has(key)) options[key] = true;
    else if (withValue.has(key)) {
      i += 1;
      const value = argv[i];
      if (value === undefined) usage(`--${key} needs a value`);
      options[key] = value;
    } else usage(`unknown option ${arg}`);
  }
  if (!options.example) usage("--example is required");
  options.width = Number(options.width);
  options.height = Number(options.height);
  if (!(options.width > 200 && options.height > 200)) usage("bad --width/--height");
  if (options.zoom !== undefined) {
    options.zoom = Number(options.zoom);
    if (!(options.zoom > 0)) usage("bad --zoom");
  }
  if (options.subsystem !== undefined) {
    options.subsystem = options.subsystem.split("/").filter((p) => p !== "");
    if (options.subsystem.length === 0) usage("bad --subsystem");
  }
  if (options.region !== undefined) {
    const parts = options.region.split(",").map(Number);
    if (parts.length !== 4 || parts.some((n) => !Number.isFinite(n)) || parts[2] <= 0 || parts[3] <= 0) {
      usage("--region must be x,y,w,h in model coordinates");
    }
    options.region = parts;
  }
  if (options.port !== "auto") {
    options.port = Number(options.port);
    if (!Number.isInteger(options.port) || options.port <= 0 || options.port === 8765) {
      usage("--port must be auto or a free port other than 8765");
    }
  }
  return options;
}

/** Fingerprint of everything the block catalog depends on (stdlib, Julia sources, project library). */
function catalogKey(example) {
  const hash = createHash("sha1");
  const walk = (dir) => {
    if (!existsSync(dir)) return;
    for (const entry of readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(full);
      else {
        const st = statSync(full);
        hash.update(`${full}|${st.size}|${Math.round(st.mtimeMs)}
`);
      }
    }
  };
  walk(path.join(repoRoot, "julia", "BGSim", "src"));
  walk(path.join(repoRoot, "julia", "BGSim", "stdlib"));
  walk(path.join(repoRoot, "examples", example, "library"));
  return hash.digest("hex").slice(0, 12);
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
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
  } else {
    child.kill("SIGKILL");
  }
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/** Model files of the example on disk: name and diagram (nodes, connections). */
function readExampleModels(example, only, subsystemPath) {
  const dir = path.join(repoRoot, "examples", example, "models");
  if (!existsSync(dir)) usage(`no such example: examples/${example}/models`);
  const models = [];
  for (const file of readdirSync(dir).sort()) {
    if (!file.endsWith(".bgmodel.json")) continue;
    const name = file.slice(0, -".bgmodel.json".length);
    if (only && name !== only) continue;
    const doc = JSON.parse(readFileSync(path.join(dir, file), "utf8"));
    let diagram = doc.diagram ?? {};
    const topNodes = (diagram.nodes ?? []).length;
    for (const id of subsystemPath ?? []) {
      const node = (diagram.nodes ?? []).find((n) => n.id === id);
      if (!node?.block?.subsystem) usage(`no subsystem node ${id} in ${name}`);
      diagram = node.block.subsystem.diagram ?? {};
    }
    models.push({
      name,
      topNodes,
      diagram: { nodes: diagram.nodes ?? [], connections: diagram.connections ?? [] },
    });
  }
  if (models.length === 0) usage(only ? `no model ${only} in ${example}` : "no models found");
  return models;
}

/** Runs inside the page: measure nodes and edges in model (flow) coordinates. */
function measureInPage(connections) {
  const viewport = document.querySelector(".react-flow__viewport");
  const m = new DOMMatrix(getComputedStyle(viewport).transform);
  const scale = m.a;
  const pane = document.querySelector(".react-flow").getBoundingClientRect();
  const paneToFlow = (x, y) => ({ x: (x - pane.left - m.e) / scale, y: (y - pane.top - m.f) / scale });
  const box = (r) => {
    const a = paneToFlow(r.left, r.top);
    const b = paneToFlow(r.right, r.bottom);
    return { x0: a.x, y0: a.y, x1: b.x, y1: b.y };
  };
  const nodes = [...document.querySelectorAll('[data-testid="diagram-node"]')].map((el) => {
    const label = el.querySelector('[data-testid^="node-label-"]');
    return {
      name: el.getAttribute("data-node-name"),
      ...box(el.getBoundingClientRect()),
      labelBox: label ? box(label.getBoundingClientRect()) : null,
    };
  });
  const edges = connections.map((c) => {
    const g = document.querySelector(`[data-testid="edge-${c.id}"]`);
    if (!g) return { id: c.id, missing: true, points: [] };
    let best = null;
    let bestLength = 0;
    for (const p of g.querySelectorAll("path")) {
      if (typeof p.getTotalLength !== "function") continue;
      const len = p.getTotalLength();
      if (len > bestLength) {
        best = p;
        bestLength = len;
      }
    }
    const points = [];
    if (best) {
      const ctm = best.getScreenCTM();
      const steps = Math.max(2, Math.ceil(bestLength / 4));
      for (let i = 0; i <= steps; i += 1) {
        const pt = best.getPointAtLength((bestLength * i) / steps);
        const f = paneToFlow(ctm.a * pt.x + ctm.c * pt.y + ctm.e, ctm.b * pt.x + ctm.d * pt.y + ctm.f);
        points.push([f.x, f.y]);
      }
    }
    return { id: c.id, missing: false, points };
  });
  const wireLabels = [...document.querySelectorAll(".editor-edge__label")].map((el) => ({
    text: (el.textContent ?? "").trim(),
    ...box(el.getBoundingClientRect()),
  }));
  return { nodes, edges, wireLabels, scale };
}

const GAP = 4; // minimum clear distance between node boxes, model units

function overlapInfo(a, b) {
  return {
    ox: Math.min(a.x1, b.x1) - Math.max(a.x0, b.x0),
    oy: Math.min(a.y1, b.y1) - Math.max(a.y0, b.y0),
  };
}

const f0 = (n) => Math.round(n);

function nodeChecks(model, measured, warnings) {
  const { nodes } = measured;
  if (nodes.length !== model.diagram.nodes.length) {
    warnings.push(`rendered ${nodes.length} nodes but the model has ${model.diagram.nodes.length}`);
  }
  for (let i = 0; i < nodes.length; i += 1) {
    for (let j = i + 1; j < nodes.length; j += 1) {
      const { ox, oy } = overlapInfo(nodes[i], nodes[j]);
      if (ox > 0 && oy > 0) {
        warnings.push(`OVERLAP ${nodes[i].name} / ${nodes[j].name} (${f0(ox)} x ${f0(oy)})`);
      } else if (ox > -GAP && oy > -GAP) {
        warnings.push(`TOUCHING ${nodes[i].name} / ${nodes[j].name} (gap < ${GAP})`);
      }
    }
  }
  for (const n of nodes) {
    if (!n.labelBox) continue;
    for (const other of nodes) {
      if (other === n) continue;
      const { ox, oy } = overlapInfo(n.labelBox, other);
      if (ox > 0 && oy > 0) warnings.push(`LABEL of ${n.name} overlaps node ${other.name}`);
    }
  }
  for (const n of model.diagram.nodes) {
    const { x, y } = n.position;
    if (x < -2000 || y < -2000 || x > 6000 || y > 6000) {
      warnings.push(`OUTSIDE sane area: ${n.name} at (${x}, ${y})`);
    }
    if (x % 10 !== 0 || y % 10 !== 0) warnings.push(`OFF-GRID node ${n.name} at (${x}, ${y})`);
  }
  if (nodes.length > 0) {
    const w = Math.max(...nodes.map((n) => n.x1)) - Math.min(...nodes.map((n) => n.x0));
    const h = Math.max(...nodes.map((n) => n.y1)) - Math.min(...nodes.map((n) => n.y0));
    if (w > 3000 || h > 2200) warnings.push(`SPREAD model spans ${f0(w)} x ${f0(h)} (sparse layout)`);
    if (measured.scale < 0.4) {
      warnings.push(`SMALL fit-view zoom ${measured.scale.toFixed(2)}: text hard to read; compact the layout`);
    }
  }
}

/** Reduce a sampled polyline to its corner vertices. */
function vertices(points) {
  const verts = [points[0]];
  for (let k = 1; k < points.length - 1; k += 1) {
    const [px, py] = points[k - 1];
    const [cx, cy] = points[k];
    const [nx, ny] = points[k + 1];
    if (Math.abs((cx - px) * (ny - cy) - (cy - py) * (nx - cx)) > 1.5) verts.push(points[k]);
  }
  verts.push(points[points.length - 1]);
  return verts;
}

function edgeChecks(model, measured, warnings) {
  const idToName = new Map(model.diagram.nodes.map((n) => [n.id, n.name]));
  const segs = [];
  for (const c of model.diagram.connections) {
    const e = measured.edges.find((x) => x.id === c.id);
    const route = c.route ?? [];
    const label = `${c.id} (${idToName.get(c.from.node)}.${c.from.port} -> ${idToName.get(c.to.node)}.${c.to.port})`;
    if (!e || e.missing || e.points.length < 2) {
      warnings.push(`EDGE ${label} not rendered`);
      continue;
    }
    const ends = new Set([idToName.get(c.from.node), idToName.get(c.to.node)]);
    const hit = new Set();
    for (const [x, y] of e.points) {
      for (const n of measured.nodes) {
        const shrink = ends.has(n.name) ? 8 : 0; // own end nodes: only flag a path deep inside the box
        if (x > n.x0 + shrink && x < n.x1 - shrink && y > n.y0 + shrink && y < n.y1 - shrink) hit.add(n.name);
      }
    }
    for (const name of hit) warnings.push(`CROSSES NODE: edge ${label} passes through ${name}`);
    for (let k = 1; k < route.length; k += 1) {
      if (route[k - 1].x === route[k].x && route[k - 1].y === route[k].y) {
        warnings.push(`EDGE ${c.id}: duplicate waypoint (${route[k].x}, ${route[k].y})`);
      }
    }
    for (const p of route) {
      if (p.x % 10 !== 0 || p.y % 10 !== 0) warnings.push(`OFF-GRID waypoint of ${c.id} at (${p.x}, ${p.y})`);
    }
    const verts = vertices(e.points);
    for (let k = 1; k < verts.length; k += 1) {
      const [x0, y0] = verts[k - 1];
      const [x1, y1] = verts[k];
      if (Math.hypot(x1 - x0, y1 - y0) < 1) continue;
      segs.push({ id: c.id, x0, y0, x1, y1, ends: [c.from.node, c.to.node] });
    }
  }
  const crossings = [];
  for (let i = 0; i < segs.length; i += 1) {
    for (let j = i + 1; j < segs.length; j += 1) {
      const a = segs[i];
      const b = segs[j];
      if (a.id === b.id) continue;
      const shares = a.ends.some((end) => b.ends.includes(end));
      const aH = Math.abs(a.y1 - a.y0) < 1;
      const bH = Math.abs(b.y1 - b.y0) < 1;
      const aV = Math.abs(a.x1 - a.x0) < 1;
      const bV = Math.abs(b.x1 - b.x0) < 1;
      if ((aH && bH && Math.abs(a.y0 - b.y0) < 2) || (aV && bV && Math.abs(a.x0 - b.x0) < 2)) {
        const lo = (s) => Math.min(aH ? s.x0 : s.y0, aH ? s.x1 : s.y1);
        const hi = (s) => Math.max(aH ? s.x0 : s.y0, aH ? s.x1 : s.y1);
        const shared = Math.min(hi(a), hi(b)) - Math.max(lo(a), lo(b));
        if (shared > 12 && !shares) warnings.push(`OVERLAPPING WIRES ${a.id} / ${b.id} share ${f0(shared)} units`);
      } else if ((aH && bV) || (aV && bH)) {
        const h = aH ? a : b;
        const v = aH ? b : a;
        const inX = v.x0 > Math.min(h.x0, h.x1) + 2 && v.x0 < Math.max(h.x0, h.x1) - 2;
        const inY = h.y0 > Math.min(v.y0, v.y1) + 2 && h.y0 < Math.max(v.y0, v.y1) - 2;
        if (inX && inY) crossings.push(`${a.id} x ${b.id}`);
      }
    }
  }
  if (crossings.length > 0) {
    const shown = crossings.slice(0, 8).join(", ");
    warnings.push(`CROSSINGS ${crossings.length} wire crossing(s): ${shown}${crossings.length > 8 ? ", ..." : ""}`);
  }
}

function labelChecks(measured, warnings) {
  const labels = measured.wireLabels;
  for (let i = 0; i < labels.length; i += 1) {
    const l = labels[i];
    for (const n of measured.nodes) {
      for (const [what, b] of [["node", n], ["name label of", n.labelBox]]) {
        if (!b) continue;
        const { ox, oy } = overlapInfo(l, b);
        if (ox > 0 && oy > 0) warnings.push(`WIRE LABEL "${l.text}" overlaps ${what} ${n.name}`);
      }
    }
    for (let j = i + 1; j < labels.length; j += 1) {
      const { ox, oy } = overlapInfo(l, labels[j]);
      if (ox > 0 && oy > 0) warnings.push(`WIRE LABEL "${l.text}" overlaps wire label "${labels[j].text}"`);
    }
  }
}

function lint(model, measured) {
  const warnings = [];
  labelChecks(measured, warnings);
  nodeChecks(model, measured, warnings);
  edgeChecks(model, measured, warnings);
  return warnings;
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
    await sleep(200);
  }
  throw new Error(`the backend did not become healthy (${last})`);
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

function applyView({ zoom, region }) {
  const viewport = document.querySelector(".react-flow__viewport");
  const pane = document.querySelector(".react-flow").getBoundingClientRect();
  const m = new DOMMatrix(getComputedStyle(viewport).transform);
  let scale;
  let tx;
  let ty;
  if (region) {
    const [x, y, w, h] = region;
    scale = Math.min(pane.width / w, pane.height / h);
    tx = (pane.width - w * scale) / 2 - x * scale;
    ty = (pane.height - h * scale) / 2 - y * scale;
  } else {
    const cx = pane.width / 2;
    const cy = pane.height / 2;
    scale = m.a * zoom;
    tx = cx - (cx - m.e) * zoom;
    ty = cy - (cy - m.f) * zoom;
  }
  viewport.style.transform = `translate(${tx}px, ${ty}px) scale(${scale})`;
}

async function renderModel(page, baseUrl, project, model, options, outDir) {
  await page.goto(`${baseUrl}/?project=${encodeURIComponent(project)}&model=${encodeURIComponent(model.name)}`);
  if (options.subsystem) {
    await page.waitForFunction(
      (n) => document.querySelectorAll('[data-testid="diagram-node"]').length >= n,
      model.topNodes,
      { timeout: 15_000 },
    );
    await sleep(500);
    // Enter the subsystem the way a user does: double-click its node, level by level.
    for (const id of options.subsystem) {
      await page.getByTestId("fit-view").click();
      await settleViewport(page);
      const target = page.locator(`[data-testid="diagram-node"][data-node-id="${id}"]`);
      await target.click();
      await target.dblclick({ position: { x: 8, y: 8 } });
      await sleep(500);
    }
  }
  await page.waitForFunction(
    (n) => document.querySelectorAll('[data-testid="diagram-node"]').length >= n,
    model.diagram.nodes.length,
    { timeout: 15_000 },
  );
  const ids = model.diagram.connections.map((c) => c.id);
  // Inline-block ports only exist after a worker check, so inside a subsystem some edges may
  // never render; the lint reports them instead of failing the render.
  await page
    .waitForFunction(
      (list) => list.every((id) => document.querySelector(`[data-testid="edge-${id}"]`)),
      ids,
      { timeout: options.subsystem ? 3_000 : 15_000 },
    )
    .catch((error) => {
      if (!options.subsystem) throw error;
    });
  await page.evaluate(() => document.fonts.ready);
  await page.getByTestId("fit-view").click();
  await settleViewport(page);

  const measured = await page.evaluate(measureInPage, model.diagram.connections);
  const warnings = lint(model, measured);

  await page.addStyleTag({
    content:
      '[role="tooltip"], [role="status"], [role="alert"], .toast, .tooltip, .react-flow__attribution, .react-flow__panel { display: none !important; }',
  });
  await page.mouse.move(options.width - 2, options.height - 2);
  if (options.zoom !== undefined || options.region !== undefined) {
    await page.evaluate(applyView, { zoom: options.zoom, region: options.region });
    await sleep(150);
  }

  let suffix = "";
  if (options.subsystem) suffix = `-${options.subsystem.join("-")}`;
  if (options.region) suffix += "-region";
  else if (options.zoom) suffix += `-zoom${options.zoom}`;
  const file = path.join(outDir, `${options.example}-${model.name}${suffix}.png`);
  await page.locator(".react-flow").screenshot({ path: file, animations: "disabled" });
  return { file, warnings, scale: measured.scale, nodes: measured.nodes.length, edges: ids.length };
}

function buildInto(distDir) {
  const npx = process.platform === "win32" ? "npx.cmd" : "npx";
  const built = spawnSync(npx, ["vite", "build", "--outDir", distDir, "--emptyOutDir"], {
    cwd: webDir,
    stdio: ["ignore", "ignore", "inherit"],
    shell: process.platform === "win32",
  });
  if (built.status !== 0) throw new Error("vite build failed");
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const models = readExampleModels(options.example, options.model, options.subsystem);
  const outDir = path.resolve(options.out ?? mkdtempSync(path.join(os.tmpdir(), "bgsim-render-out-")));
  mkdirSync(outDir, { recursive: true });

  const temps = [];
  let backend = null;
  let browser = null;
  let cleaned = false;
  const cleanup = async () => {
    if (cleaned) return;
    cleaned = true;
    try {
      if (browser) await browser.close();
    } catch {
      // the browser is already gone
    }
    killTree(backend);
    for (const dir of temps) {
      for (let attempt = 0; attempt < 10; attempt += 1) {
        try {
          rmSync(dir, { recursive: true, force: true });
          break;
        } catch {
          await sleep(300);
        }
      }
    }
  };
  const onSignal = () => {
    killTree(backend);
    void cleanup().finally(() => process.exit(130));
  };
  process.on("SIGINT", onSignal);
  process.on("SIGTERM", onSignal);
  process.on("exit", () => killTree(backend));

  const started = Date.now();
  try {
    let distDir = path.join(webDir, "dist");
    if (options.build) {
      distDir = mkdtempSync(path.join(os.tmpdir(), "bgsim-render-dist-"));
      temps.push(distDir);
      buildInto(distDir);
    } else if (!existsSync(path.join(distDir, "index.html"))) {
      throw new Error("web/dist is not built; run with --build to build into a temporary directory");
    }

    const projectsRoot = mkdtempSync(path.join(os.tmpdir(), "bgsim-render-projects-"));
    temps.push(projectsRoot);
    // The fake worker only knows a minimal catalog, so it serves a real catalog captured once
    // from the Julia worker (cached per example and source fingerprint in the temp dir).
    const cacheDir = path.join(os.tmpdir(), "bgsim-render-cache");
    const cacheFile = path.join(cacheDir, `${options.example}-${catalogKey(options.example)}.catalog.json`);
    // Inline blocks get their ports from a worker check, which the fake worker cannot answer:
    // such examples always run on the real worker (the catalog is still cached for the others).
    const hasInline = readdirSync(path.join(repoRoot, "examples", options.example, "models"))
      .filter((f) => f.endsWith(".bgmodel.json"))
      .some((f) => /"inline"s*:/.test(readFileSync(path.join(repoRoot, "examples", options.example, "models", f), "utf8")));
    if (hasInline && !options.real) out("example has inline blocks: using the real worker");
    const useReal = options.real || hasInline;
    const useFake = !useReal && existsSync(cacheFile);
    const capture = !useReal && !useFake;
    const port = options.port === "auto" ? await freePort() : options.port;
    const baseUrl = `http://127.0.0.1:${port}`;
    const environment = {
      ...process.env,
      BGSIM_PORT_HTTP: String(port),
      BGSIM_PROJECTS_ROOT: projectsRoot,
      BGSIM_REPO: repoRoot,
      BGSIM_WEB_DIST: distDir,
    };
    delete environment.BGSIM_FAKE_WORKER;
    delete environment.BGSIM_CATALOG_JSON;
    if (useFake) {
      environment.BGSIM_FAKE_WORKER = "1";
      environment.BGSIM_CATALOG_JSON = cacheFile;
    } else {
      out("starting the Julia worker for the real block catalog (about 40 s; cached for later runs)");
    }
    backend = spawn(
      process.platform === "win32" ? "uv.exe" : "uv",
      ["run", "python", path.join("web", "scripts", "serve_render.py")],
      {
        cwd: repoRoot,
        env: environment,
        stdio: "ignore",
      },
    );
    await waitForHealth(baseUrl, backend, 300_000, !useFake);

    const project = `render-${process.pid}-${Date.now().toString(36)}`;
    const response = await fetch(`${baseUrl}/api/projects`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ name: project, example: options.example }),
    });
    if (!response.ok) {
      throw new Error(`POST /api/projects -> ${response.status}: ${(await response.text()).slice(0, 400)}`);
    }

    if (capture) {
      const cat = await fetch(`${baseUrl}/api/catalog?project=${encodeURIComponent(project)}`);
      if (!cat.ok) throw new Error(`GET /api/catalog -> ${cat.status}`);
      mkdirSync(cacheDir, { recursive: true });
      const partial = `${cacheFile}.${process.pid}.tmp`;
      writeFileSync(partial, await cat.text());
      renameSync(partial, cacheFile);
    }

    browser = await chromium.launch();
    const context = await browser.newContext({ viewport: { width: options.width, height: options.height } });
    const page = await context.newPage();
    out(`backend ${baseUrl} ready after ${((Date.now() - started) / 1000).toFixed(1)} s`);

    for (const model of models) {
      const t0 = Date.now();
      try {
        const r = await renderModel(page, baseUrl, project, model, options, outDir);
        out(
          `\n${model.name}: ${r.file}\n  ${r.nodes} nodes, ${r.edges} connections, fit zoom ${r.scale.toFixed(2)}, ` +
            `${((Date.now() - t0) / 1000).toFixed(1)} s`,
        );
        if (r.warnings.length === 0) out("  lint: clean");
        for (const w of r.warnings) out(`  lint: ${w}`);
      } catch (error) {
        process.exitCode = 1;
        const shot = path.join(outDir, `${options.example}-${model.name}-FAILED.png`);
        await page.screenshot({ path: shot }).catch(() => undefined);
        const seen = await page
          .evaluate(() => ({
            nodes: document.querySelectorAll('[data-testid="diagram-node"]').length,
            edges: document.querySelectorAll('[data-testid^="edge-"]').length,
          }))
          .catch(() => ({ nodes: -1, edges: -1 }));
        out(`  page showed ${seen.nodes} nodes and ${seen.edges} edge elements; screenshot ${shot}`);
        out(`\n${model.name}: FAILED ${error instanceof Error ? error.message : String(error)}`);
      }
    }
    out(`\ndone in ${((Date.now() - started) / 1000).toFixed(1)} s, output ${outDir}`);
  } catch (error) {
    console.error(`render-models: ${error instanceof Error ? error.message : String(error)}`);
    process.exitCode = 1;
  } finally {
    await cleanup();
  }
}

await main();
