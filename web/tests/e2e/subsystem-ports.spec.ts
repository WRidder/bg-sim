import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

/**
 * Subsystem port terminals, fake worker. The model is the contract fixture
 * `model.subsystem-port-ui.json` (Step1 -> Plant.u, Plant.vc -> R2) with an
 * unconnected Gain K1 added inside Plant:
 *
 * 1. entering Plant shows a terminal per exposed port, the boundary wires and
 *    the badge on the exposed internal port;
 * 2. the terminal's outside link leaves Plant and selects the connection;
 * 3. dragging K1.y onto "+ output" exposes it: the outer block has the port;
 * 4. the new port is renamed in the inspector, deleted with Delete and
 *    restored with Ctrl+Z; a connected port asks before it goes.
 *
 * Run with `$env:BGSIM_E2E_PORT="8794"; npx playwright test tests/e2e/subsystem-ports.spec.ts`.
 */

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "../../..");

let project = "";

interface StoredPort {
  name: string;
  node: string;
  port: string;
  ui?: { position: { x: number; y: number } };
}

interface StoredDoc {
  diagram: {
    nodes: { id: string; block: { subsystem?: { ports: StoredPort[] } } }[];
    connections: { id: string; to: { node: string; port?: string } }[];
  };
}

function model(): unknown {
  const doc = JSON.parse(
    readFileSync(
      path.join(repoRoot, "contracts", "fixtures", "model", "valid", "model.subsystem-port-ui.json"),
      "utf8",
    ),
  ) as {
    $comment?: string;
    diagram: { nodes: { id: string; block: { subsystem?: { diagram: { nodes: unknown[] } } } }[] };
  };
  delete doc.$comment;
  doc.diagram.nodes
    .find((node) => node.id === "plant")
    ?.block.subsystem?.diagram.nodes.push({
      id: "p9",
      name: "K1",
      block: { ref: "stdlib:continuous/Gain" },
      position: { x: 280, y: 380 },
      rotation: 0,
      flipX: false,
      params: {},
      constants: {},
      starts: {},
      ui: { showLabel: true, color: null },
    });
  return doc;
}

test.beforeEach(async ({ page }) => {
  project = `subsystem-ports-${Date.now()}-${test.info().workerIndex}`;
  await page.setViewportSize({ width: 1600, height: 1000 });
  expect((await page.request.post("/api/projects", { data: { name: project } })).status()).toBe(201);
  const put = await page.request.put(`/api/projects/${project}/models/Ports`, { data: model() });
  expect(put.status(), await put.text()).toBe(200);
});

test.afterEach(async ({ request }) => {
  await request.delete(`/api/projects/${project}`);
});

function node(page: Page, name: string) {
  return page.locator(`[data-testid="diagram-node"][data-node-name="${name}"]`);
}

async function readDocument(page: Page): Promise<StoredDoc> {
  const text = await page.getByTestId("document-json").textContent();
  return JSON.parse(text ?? "null") as StoredDoc;
}

async function plantPorts(page: Page): Promise<StoredPort[]> {
  const doc = await readDocument(page);
  return doc.diagram.nodes.find((entry) => entry.id === "plant")?.block.subsystem?.ports ?? [];
}

async function openPlant(page: Page): Promise<void> {
  await page.goto(`/?project=${project}&model=Ports`);
  await expect(node(page, "Plant")).toBeVisible({ timeout: 30_000 });
  await node(page, "Plant").dblclick({ position: { x: 8, y: 8 } });
  await expect(page.getByTestId("breadcrumb-1")).toHaveAttribute("data-breadcrumb-name", "Plant");
  await expect(page.getByTestId("diagram-node")).toHaveCount(5);
  await fit(page);
}

/** Fit the view and wait for its 200 ms animation, so measured boxes hold still. */
async function fit(page: Page): Promise<void> {
  await page.getByTestId("fit-view").click();
  await page.waitForTimeout(400);
}

async function centre(page: Page, selector: string): Promise<{ x: number; y: number }> {
  const box = await page.locator(selector).first().boundingBox();
  if (box === null) {
    throw new Error(`${selector} is not visible`);
  }
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

test("terminals show the subsystem interface inside it and edit it in place", async ({ page }) => {
  await openPlant(page);

  // 1. One terminal per exposed port, with its outside connection and a boundary wire.
  const u = page.getByTestId("port-terminal-u");
  const vc = page.getByTestId("port-terminal-vc");
  await expect(u).toBeVisible();
  await expect(vc).toBeVisible();
  await expect(page.getByTestId("port-terminal-link-u")).toHaveText("← Step1.y");
  await expect(page.getByTestId("port-terminal-link-vc")).toHaveText("↔ R2.p");
  await expect(u).toHaveAttribute("data-maps-to", "V1.u");
  await expect(page.getByTestId("boundary-wire-u")).toHaveCount(1);
  await expect(page.getByTestId("boundary-wire-vc")).toHaveCount(1);
  // The shape tells the kind: u is a tag pointing toward its wire, vc a hexagon.
  await expect(u).toHaveAttribute("data-shape", "tag-in");
  await expect(u).toHaveAttribute("data-handle-side", "right");
  await expect(u).toHaveAttribute("data-point", "right");
  await expect(vc).toHaveAttribute("data-shape", "hexagon");
  await expect(page.getByTestId("boundary-mark-u")).toHaveAttribute("data-mark-at", "internal");
  await expect(page.getByTestId("boundary-mark-vc")).toHaveAttribute("data-mark", "half-arrow");
  await expect(page.getByTestId("port-ghost-output")).toHaveAttribute("data-shape", "tag-out");
  await expect(page.getByTestId("port-exposed-p1-u")).toHaveCount(1);
  await expect(page.getByTestId("port-exposed-p3-p")).toHaveCount(1);
  // The terminal is selectable and the inspector shows the port.
  await u.click({ position: { x: 12, y: 8 } });
  await expect(u).toHaveClass(/is-selected/);
  await expect(page.getByTestId("inspector-port")).toHaveAttribute("data-port-name", "u");
  await expect(page.getByTestId("inspector-port-maps-to")).toHaveText("V1.u");

  // 2. The outside link goes up one level and selects the outside connection.
  await page.getByTestId("port-terminal-link-u").click();
  await expect(page.getByTestId("breadcrumb-1")).toHaveCount(0);
  await expect(page.getByTestId("edge-c1")).toHaveClass(/is-selected/);
  await expect(page.getByTestId("inspector-connections")).toBeVisible();

  // 3. Drag K1.y onto "+ output": the subsystem gets an output named y.
  await node(page, "Plant").dblclick({ position: { x: 8, y: 8 } });
  await expect(page.getByTestId("port-terminal-u")).toBeVisible();
  await fit(page);
  const from = await centre(page, '[data-testid="port-p9-y"]');
  const to = await centre(page, '[data-testid="port-ghost-output"]');
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(from.x + 12, from.y + 8, { steps: 3 });
  await page.mouse.move(to.x, to.y, { steps: 12 });
  await expect(page.getByTestId("port-ghost-output")).toHaveAttribute("data-state", "compatible");
  await page.mouse.up();
  await expect(page.getByTestId("port-terminal-y")).toBeVisible();
  await expect(page.getByTestId("port-terminal-y")).toHaveAttribute("data-shape", "tag-out");
  await expect(page.getByTestId("boundary-mark-y")).toHaveAttribute("data-mark-at", "terminal");
  await expect(page.getByTestId("port-terminal-link-y")).toHaveText("unconnected");
  await expect(page.getByTestId("port-exposed-p9-y")).toHaveCount(1);
  expect((await plantPorts(page)).map((port) => port.name)).toEqual(["u", "vc", "y"]);
  // The new port is selected and its name field has the focus for a rename.
  const name = page.getByTestId("inspector-port-name");
  await expect(name).toBeFocused();
  await name.fill("gain_out");
  await name.press("Enter");
  await expect(page.getByTestId("port-terminal-gain_out")).toBeVisible();
  expect((await plantPorts(page)).map((port) => port.name)).toEqual(["u", "vc", "gain_out"]);
  // A refused drop says why: K1.y is exposed already.
  const again = await centre(page, '[data-testid="port-p9-y"]');
  const ghost = await centre(page, '[data-testid="port-ghost-output"]');
  await page.mouse.move(again.x, again.y);
  await page.mouse.down();
  await page.mouse.move(again.x + 12, again.y + 8, { steps: 3 });
  await page.mouse.move(ghost.x, ghost.y, { steps: 12 });
  await expect(page.getByTestId("port-ghost-output")).toHaveAttribute("data-state", "incompatible");
  await page.mouse.up();
  await expect(page.getByTestId("connection-refusal")).toContainText("K1.y is already exposed as gain_out.");

  // 4. The outer block has the port at once.
  await page.getByTestId("subsystem-back").click();
  await expect(page.locator('[data-testid="port-plant-gain_out"]')).toHaveCount(1);
  await node(page, "Plant").dblclick({ position: { x: 8, y: 8 } });
  await expect(page.getByTestId("port-terminal-gain_out")).toBeVisible();

  // Delete the unconnected port: no question; Ctrl+Z restores it.
  await page.getByTestId("port-terminal-gain_out").click({ position: { x: 12, y: 8 } });
  await expect(page.getByTestId("port-terminal-gain_out")).toHaveClass(/is-selected/);
  await page.keyboard.press("Delete");
  await expect(page.getByTestId("port-terminal-gain_out")).toHaveCount(0);
  expect((await plantPorts(page)).map((port) => port.name)).toEqual(["u", "vc"]);
  await page.keyboard.press("Control+z");
  await expect(page.getByTestId("port-terminal-gain_out")).toBeVisible();

  // A connected port asks first; Cancel keeps it, Delete removes the outside connection too.
  await vc.click({ position: { x: 12, y: 8 } });
  await page.keyboard.press("Delete");
  await expect(page.getByTestId("port-delete-dialog")).toBeVisible();
  await expect(page.getByTestId("port-delete-dialog")).toContainText("Plant.vc → R2.p");
  await page.getByTestId("port-delete-cancel").click();
  await expect(page.getByTestId("port-delete-dialog")).toHaveCount(0);
  await expect(vc).toBeVisible();
  await page.keyboard.press("Delete");
  await page.getByTestId("port-delete-confirm").click();
  await expect(vc).toHaveCount(0);
  let doc = await readDocument(page);
  expect(doc.diagram.connections.map((connection) => connection.id)).toEqual(["c1", "c3"]);
  await page.keyboard.press("Control+z");
  await expect(vc).toBeVisible();
  doc = await readDocument(page);
  expect(doc.diagram.connections.map((connection) => connection.id)).toEqual(["c1", "c2", "c3"]);
});

test("a dragged terminal stores its position and a double-click goes up", async ({ page }) => {
  await openPlant(page);
  const vc = page.getByTestId("port-terminal-vc");
  const start = await centre(page, '[data-testid="port-terminal-vc"]');
  await page.mouse.move(start.x, start.y - 8);
  await page.mouse.down();
  await page.mouse.move(start.x + 20, start.y + 30, { steps: 4 });
  await page.mouse.move(start.x + 60, start.y + 80, { steps: 8 });
  await page.mouse.up();
  const stored = (await plantPorts(page)).find((port) => port.name === "vc");
  expect(stored?.ui?.position).toBeDefined();
  // The boundary wire follows the terminal.
  await expect(page.getByTestId("boundary-wire-vc")).toHaveCount(1);
  await page.keyboard.press("Control+z");
  await expect
    .poll(async () => (await plantPorts(page)).find((port) => port.name === "vc")?.ui)
    .toBeUndefined();

  // The context menu on an internal port exposes it too (K1.u: `u` is taken).
  await page.getByTestId("port-p9-u").click({ button: "right" });
  await page.getByTestId("expose-port").click();
  await expect(page.getByTestId("port-terminal-K1_u")).toBeVisible();
  await expect(page.getByTestId("port-terminal-K1_u")).toHaveAttribute("data-kind", "input");
  await expect(page.getByTestId("port-exposed-p9-u")).toHaveCount(1);
  // Exposing it again is refused with the reason.
  await page.getByTestId("port-p9-u").click({ button: "right" });
  await page.getByTestId("expose-port").click();
  await expect(page.getByTestId("connection-refusal")).toContainText("K1.u is already exposed as K1_u.");

  await vc.dblclick({ position: { x: 12, y: 8 } });
  await expect(page.getByTestId("breadcrumb-1")).toHaveCount(0);
  await expect(page.getByTestId("edge-c2")).toHaveClass(/is-selected/);
});
