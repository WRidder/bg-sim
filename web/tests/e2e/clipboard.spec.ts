import { mkdirSync } from "node:fs";
import path from "node:path";

import { expect, test, type BrowserContext, type Page, type Route } from "@playwright/test";

import type { Model, ModelNode } from "../../src/contracts/model";
import { waitForLibrary } from "./library";

/**
 * Copy and paste through the system clipboard (src/clipboard/):
 *
 * - same project, another model, another page (two pages of one browser context share
 *   the clipboard): Ctrl+C in one page, Ctrl+V over the canvas of the other; the global
 *   the copied Gain reads comes along, the paste lands at the pointer, one Undo removes it;
 * - another project: a subsystem with an image and a project library block inside, a
 *   global closure and a note that shows a docs image; the library file, the globals and
 *   the image are created in the target, and the notice says what stayed behind;
 * - a project that already has a different block and global: one dialog, "Import as"
 *   for the block, "use this model's" for the global.
 *
 * The fake worker's catalog never lists project blocks, so the specs play the Julia
 * worker's part and stub /api/catalog with the project library (as code-to-library does).
 * With BGSIM_E2E_REAL=1 the same specs run against the Julia worker without the stub.
 * Screenshots go to BGSIM_SCREENSHOT_DIR when it is set.
 */

const real = process.env.BGSIM_E2E_REAL === "1";
const shots = process.env.BGSIM_SCREENSHOT_DIR ?? "";

const LAG = `@block MyLag begin
    @inputs u::Real
    @outputs y::Real
    @parameters begin
        tau::Real = 0.5, [unit = "s"]
    end
    @variables x::Real = 0.0
    @equations begin
        ddt(x) ~ (u - x) / tau
        y ~ x
    end
end
`;
const OTHER_LAG = LAG.replace("ddt(x) ~ (u - x) / tau", "ddt(x) ~ 2 * (u - x) / tau");

/** A 2x2 PNG (blue). */
const PNG =
  "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFklEQVR42mNkYPj/n4GBgYGJAQoAAP//AwBGBgL+4TnEPwAAAABJRU5ErkJggg==";

const projects: string[] = [];

function settings(): Model["settings"] {
  return {
    t_start: 0,
    t_end: 1,
    solver: "auto",
    reltol: 1e-6,
    abstol: 1e-8,
    max_step: null,
    output: { mode: "points", points: 5000 },
    event_limit: 10000,
  };
}

function model(name: string, nodes: ModelNode[], extra: Partial<Model> = {}): Model {
  return {
    format: "bgsim.model",
    language: "0.1.0",
    name,
    diagram: { nodes, connections: [], subsystemPorts: [], annotations: [] },
    settings: settings(),
    plots: [],
    scene: null,
    bindings: [],
    ...extra,
  };
}

function node(id: string, name: string, ref: string, x: number, y: number, params: Record<string, string> = {}): ModelNode {
  return { id, name, block: { ref }, position: { x, y }, rotation: 0, flipX: false, params, constants: {}, starts: {}, ui: { showLabel: true, color: null } };
}

async function createProject(page: Page, tag: string): Promise<string> {
  const name = `clip-${tag}-${Date.now()}-${test.info().workerIndex}`;
  expect((await page.request.post("/api/projects", { data: { name } })).status()).toBe(201);
  projects.push(name);
  return name;
}

async function putModel(page: Page, project: string, document: Model): Promise<void> {
  expect((await page.request.put(`/api/projects/${project}/models/${document.name}`, { data: document })).ok()).toBeTruthy();
}

async function putLibrary(page: Page, project: string, name: string, source: string): Promise<void> {
  const response = await page.request.put(`/api/projects/${project}/library/${name}`, {
    headers: { "content-type": "text/plain; charset=utf-8" },
    data: source,
  });
  expect(response.ok()).toBeTruthy();
}

/**
 * Play the Julia worker's part for the catalog: list every file of the project library
 * of the requested project as a `project:<Name>` block.
 */
async function publishProjectLibrary(context: BrowserContext): Promise<void> {
  if (real) {
    return; // The Julia worker lists the project library itself.
  }
  await context.route(/\/api\/catalog(\?.*)?$/, async (route: Route) => {
    const response = await route.fetch();
    const catalog = (await response.json()) as { blocks: Record<string, unknown>[] };
    const project = new URL(route.request().url()).searchParams.get("project");
    if (project !== null) {
      const base = catalog.blocks.find((block) => block.ref === "stdlib:continuous/Integrator");
      const info = (await (await context.request.get(`/api/projects/${project}`)).json()) as { library: { name: string }[] };
      for (const entry of info.library) {
        const source = await (await context.request.get(`/api/projects/${project}/library/${entry.name}`)).text();
        catalog.blocks.push({
          ...base,
          ref: `project:${entry.name}`,
          name: entry.name,
          group: "Project",
          description: `${entry.name} from the project library`,
          parameters: [],
          source,
          path: `library/${entry.name}.jl`,
        });
      }
    }
    await route.fulfill({ response, json: catalog });
  });
}

async function open(page: Page, project: string, name: string): Promise<void> {
  if (real) {
    // The catalog answers 503 until the Julia worker has warmed up.
    await expect
      .poll(async () => (await page.request.get(`/api/catalog?project=${encodeURIComponent(project)}`)).status(), {
        timeout: 900_000,
        intervals: [5_000],
      })
      .toBe(200);
  }
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(`/?project=${encodeURIComponent(project)}&model=${encodeURIComponent(name)}`);
  await waitForLibrary(page, real ? 120_000 : 30_000);
  await expect(page.getByTestId("canvas-surface")).toBeVisible();
}

async function documentJson(page: Page): Promise<Model> {
  return JSON.parse((await page.getByTestId("document-json").textContent()) ?? "null") as Model;
}

function canvasNode(page: Page, name: string) {
  return page.locator(`[data-testid="diagram-node"][data-node-name="${name}"]`);
}

async function shot(page: Page, name: string): Promise<void> {
  if (shots.length === 0) {
    return;
  }
  mkdirSync(shots, { recursive: true });
  await page.screenshot({ path: path.join(shots, name) });
}

/** Move the pointer over the canvas at a fraction of its box. */
async function hoverCanvas(page: Page, fx: number, fy: number): Promise<{ x: number; y: number }> {
  const box = await page.getByTestId("canvas-surface").boundingBox();
  if (box === null) throw new Error("no canvas");
  const point = { x: box.x + box.width * fx, y: box.y + box.height * fy };
  await page.mouse.move(point.x, point.y);
  return point;
}

test.beforeEach(() => {
  // The real worker compiles the catalog of every new project.
  test.setTimeout(real ? 1_200_000 : 60_000);
});

test.afterEach(async ({ request }) => {
  for (const name of projects.splice(0)) {
    await request.delete(`/api/projects/${name}`);
  }
});

test("same project, another model in another window: the global comes along, one undo", async ({ context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  const setup = await context.newPage();
  const project = await createProject(setup, "same");
  await putModel(
    setup,
    project,
    model("Source", [node("n1", "Src", "stdlib:sources/Constant", 120, 160), node("n2", "Amp", "stdlib:continuous/Gain", 360, 160, { k: "gain_k" })], {
      diagram: {
        nodes: [
          node("n1", "Src", "stdlib:sources/Constant", 120, 160),
          node("n2", "Amp", "stdlib:continuous/Gain", 360, 160, { k: "gain_k" }),
        ],
        connections: [{ id: "c1", kind: "signal", from: { node: "n1", port: "y" }, to: { node: "n2", port: "u" } }],
        annotations: [],
      },
      parameters: [
        { name: "base", value: "1.5" },
        { name: "gain_k", value: "2*base", unit: "1" },
        { name: "unrelated", value: "9" },
      ],
    }),
  );
  await putModel(setup, project, model("Target", []));
  await setup.close();

  const first = await context.newPage();
  await open(first, project, "Source");
  await canvasNode(first, "Src").click();
  await canvasNode(first, "Amp").click({ modifiers: ["Control"] });
  await expect(first.getByTestId("inspector-multi")).toBeVisible();
  await first.keyboard.press("Control+c");
  const text = await first.evaluate(() => navigator.clipboard.readText());
  const envelope = JSON.parse(text) as { format: string; nodes: { name: string }[]; dependencies: { globals: { name: string }[] } };
  expect(envelope.format).toBe("bgsim-clipboard");
  expect(envelope.nodes.map((entry) => entry.name)).toEqual(["Src", "Amp"]);
  expect(envelope.dependencies.globals.map((entry) => entry.name)).toEqual(["base", "gain_k"]);

  const second = await context.newPage();
  await open(second, project, "Target");
  const point = await hoverCanvas(second, 0.6, 0.55);
  await second.keyboard.press("Control+v");
  await expect(second.getByTestId("diagram-node")).toHaveCount(2);
  await expect(second.getByTestId("paste-notice")).toContainText("Global parameters added: base, gain_k");
  await expect(second.getByTestId("paste-notice")).toContainText("Pasted 2 blocks, 1 connection from Source");
  let document = await documentJson(second);
  expect(document.parameters?.map((entry) => `${entry.name}=${entry.value}`)).toEqual(["base=1.5", "gain_k=2*base"]);
  expect(document.diagram.nodes.find((entry) => entry.name === "Amp")?.params).toEqual({ k: "gain_k" });
  // The group is centred near the pointer (whole grid steps).
  const amp = await canvasNode(second, "Amp").boundingBox();
  const src = await canvasNode(second, "Src").boundingBox();
  expect(amp).not.toBeNull();
  expect(src).not.toBeNull();
  const middle = ((src?.x ?? 0) + (amp?.x ?? 0) + (amp?.width ?? 0)) / 2;
  expect(Math.abs(middle - point.x)).toBeLessThan(160);
  await shot(second, "clipboard-same-project.png");

  // One undo removes the blocks and the globals.
  await second.getByTestId("undo").click();
  await expect(second.getByTestId("diagram-node")).toHaveCount(0);
  document = await documentJson(second);
  expect(document.parameters ?? []).toEqual([]);

  // Cut: Ctrl+X puts the block on the clipboard and removes it; Ctrl+V brings it back.
  await second.keyboard.press("Control+v");
  await expect(second.getByTestId("diagram-node")).toHaveCount(2);
  await canvasNode(second, "Amp").click();
  await second.keyboard.press("Control+x");
  await expect(second.getByTestId("diagram-node")).toHaveCount(1);
  expect(await second.evaluate(() => navigator.clipboard.readText())).toContain('"name":"Amp"');
  await hoverCanvas(second, 0.3, 0.3);
  await second.keyboard.press("Control+v");
  await expect(second.getByTestId("diagram-node")).toHaveCount(2);
  expect((await documentJson(second)).diagram.nodes.map((entry) => entry.name)).toEqual(["Src", "Amp"]);

  // Text fields keep their own paste: the clipboard JSON goes into the input, not the canvas.
  await second.getByTestId("library-search").fill("");
  await second.getByTestId("library-search").focus();
  await second.keyboard.press("Control+v");
  await expect(second.getByTestId("diagram-node")).toHaveCount(2);
  await expect(second.getByTestId("library-search")).toHaveValue(/bgsim-clipboard/);
});

test("another project: library block, globals, subsystem image and note image come along", async ({ context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await publishProjectLibrary(context);
  const setup = await context.newPage();
  const from = await createProject(setup, "from");
  const to = await createProject(setup, "to");
  const conflicted = await createProject(setup, "conflict");
  await putLibrary(setup, from, "MyLag", LAG);
  // The source model must exist before its docs can hold an image.
  await putModel(setup, from, model("Rig", []));
  const upload = await setup.request.post(`/api/projects/${from}/docs/Rig/assets`, {
    multipart: { file: { name: "wiring.png", mimeType: "image/png", buffer: Buffer.from(PNG, "base64") } },
  });
  expect(upload.ok()).toBeTruthy();
  const asset = ((await upload.json()) as { file: string }).file;
  const plant: ModelNode = {
    id: "n1",
    name: "Plant",
    position: { x: 200, y: 200 },
    block: {
      subsystem: {
        ports: [],
        diagram: {
          nodes: [node("n2", "Lag", "project:MyLag", 100, 100, { tau: "tau_fast" })],
          connections: [],
          annotations: [{ id: "a1", kind: "text", text: `Wiring: ![wiring](assets/${asset})`, x: 0, y: 220, w: 200, h: 80 }],
        },
      },
    },
    ui: { showLabel: true, color: null, image: { mime: "image/png", data: PNG, fit: "contain" } },
  };
  await putModel(
    setup,
    from,
    model("Rig", [plant], {
      parameters: [
        { name: "tau0", value: "0.3", unit: "s" },
        { name: "tau_fast", value: "tau0/10", unit: "s" },
      ],
    }),
  );
  await putModel(setup, to, model("Bench", []));
  await putLibrary(setup, conflicted, "MyLag", OTHER_LAG);
  await putModel(setup, conflicted, model("Bench", [], { parameters: [{ name: "tau0", value: "1" }] }));
  await setup.close();

  const first = await context.newPage();
  await open(first, from, "Rig");
  await canvasNode(first, "Plant").locator(".block-node__header").click();
  await first.keyboard.press("Control+c");

  // 1. A project without any of it: everything is created.
  const second = await context.newPage();
  await open(second, to, "Bench");
  await second.keyboard.press("Control+v");
  await expect(second.getByTestId("diagram-node")).toHaveCount(1);
  const notice = second.getByTestId("paste-notice");
  await expect(notice).toContainText(`Pasted 1 block from ${from}/Rig`);
  await expect(notice).toContainText("Library blocks added: MyLag.");
  await expect(notice).toContainText("Global parameters added: tau0, tau_fast.");
  await expect(notice).toContainText("Docs images copied for the notes: 1.");
  await expect(notice).toContainText("Not carried along: docs pages and their links to the copied blocks.");
  await expect(notice).toContainText("files written to the project stay");
  await expect(second.locator('[data-testid^="node-image-"]')).toHaveAttribute("data-mime", "image/png");
  await shot(second, "clipboard-other-project.png");
  const library = await second.request.get(`/api/projects/${to}/library/MyLag`);
  expect(await library.text()).toBe(LAG);
  expect((await second.request.get(`/api/projects/${to}/docs/Bench/assets/${asset}`)).ok()).toBeTruthy();
  const document = await documentJson(second);
  expect(document.parameters?.map((entry) => entry.name)).toEqual(["tau0", "tau_fast"]);
  const pasted = document.diagram.nodes[0];
  const inner = pasted !== undefined && "subsystem" in pasted.block ? pasted.block.subsystem.diagram.nodes[0] : undefined;
  expect(inner?.block).toEqual({ ref: "project:MyLag" });
  // Ids are unique across the document, nested levels included.
  expect(inner?.id).not.toBe(pasted?.id);

  // 2. A project with a different MyLag and tau0: one dialog, safe defaults.
  const third = await context.newPage();
  await open(third, conflicted, "Bench");
  await third.keyboard.press("Control+v");
  const dialog = third.getByTestId("paste-conflict-dialog");
  await expect(dialog).toBeVisible();
  await expect(third.getByTestId("paste-choice-library-MyLag")).toHaveValue("existing");
  await expect(third.getByTestId("paste-choice-global-tau0")).toHaveValue("existing");
  await expect(dialog).toContainText("Undo removes the pasted elements, but not those files");
  await third.getByTestId("paste-choice-library-MyLag").selectOption("rename");
  await shot(third, "clipboard-conflicts.png");
  await third.getByTestId("paste-conflict-confirm").click();
  await expect(dialog).toHaveCount(0);
  await expect(third.getByTestId("diagram-node")).toHaveCount(1);
  await expect(third.getByTestId("paste-notice")).toContainText("Library blocks added: MyLag as MyLag2.");
  await expect(third.getByTestId("paste-notice")).toContainText("Kept the target's own global tau0 = 1");
  expect(await (await third.request.get(`/api/projects/${conflicted}/library/MyLag2`)).text()).toMatch(/^@block MyLag2 begin/);
  expect(await (await third.request.get(`/api/projects/${conflicted}/library/MyLag`)).text()).toBe(OTHER_LAG);
  const conflictedDoc = await documentJson(third);
  expect(conflictedDoc.parameters?.map((entry) => `${entry.name}=${entry.value}`)).toEqual(["tau0=1", "tau_fast=tau0/10"]);
  const conflictedPlant = conflictedDoc.diagram.nodes[0];
  const conflictedLag =
    conflictedPlant !== undefined && "subsystem" in conflictedPlant.block ? conflictedPlant.block.subsystem.diagram.nodes[0] : undefined;
  expect(conflictedLag?.block).toEqual({ ref: "project:MyLag2" });
  await shot(third, "clipboard-conflicts-pasted.png");

  // Undo is one step: the subsystem and the added global go; the library file stays.
  await third.getByTestId("undo").click();
  await expect(third.getByTestId("diagram-node")).toHaveCount(0);
  expect((await documentJson(third)).parameters?.map((entry) => entry.name)).toEqual(["tau0"]);
  expect((await third.request.get(`/api/projects/${conflicted}/library/MyLag2`)).ok()).toBeTruthy();

  // Pasting the same clipboard twice gives unique names.
  await third.getByTestId("paste-notice-close").click();
  for (let round = 0; round < 2; round += 1) {
    await third.keyboard.press("Control+v");
    await third.getByTestId("paste-conflict-confirm").click();
    await expect(third.getByTestId("diagram-node")).toHaveCount(round + 1);
  }
  await expect(third.getByTestId("diagram-node")).toHaveCount(2);
  const twice = await documentJson(third);
  expect(twice.diagram.nodes.map((entry) => entry.name)).toEqual(["Plant", "Plant2"]);
});
