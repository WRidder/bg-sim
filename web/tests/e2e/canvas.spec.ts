import { expect, test, type Page } from "@playwright/test";

/**
 * W1.1 acceptance (plan 7.4 and the work package):
 *
 * 1. build the iconic DC motor by dragging VoltageSource, DCMotor, Ground, two
 *    FixedShafts and a RotationalDamper from the library and wiring them;
 * 2. save, reload, and see the identical document;
 * 3. undo/redo across ten operations returns to the loaded state.
 *
 * A second test drags an Electrical port onto a Rotation port and asserts the
 * exact refusal tooltip of plan 7.3.
 *
 * Each test uses its own project (a URL parameter) and deletes it afterwards,
 * so runs never inherit a model from a previous run.
 */

let project = "";

test.beforeEach(async ({ page }) => {
  project = `w1e2e-${Date.now()}-${test.info().workerIndex}`;
  await page.setViewportSize({ width: 1600, height: 1000 });
});

test.afterEach(async ({ request }) => {
  if (project.length > 0) {
    await request.delete(`/api/projects/${project}`);
  }
});

async function openModel(page: Page, model = "DCMotorSpeed"): Promise<void> {
  await page.goto(`/?project=${encodeURIComponent(project)}&model=${model}`);
  await expect(page.getByTestId("library-item-DCMotor")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("canvas-surface")).toBeVisible();
}

async function dropBlock(page: Page, name: string, x: number, y: number): Promise<void> {
  const item = page.getByTestId(`library-item-${name}`).first();
  await item.scrollIntoViewIfNeeded();
  await item.dragTo(page.getByTestId("canvas-surface"), {
    targetPosition: { x, y },
  });
}

function node(page: Page, name: string) {
  return page.locator(`[data-testid="diagram-node"][data-node-name="${name}"]`);
}

async function connect(
  page: Page,
  fromName: string,
  fromPort: string,
  toName: string,
  toPort: string,
): Promise<void> {
  const handle = node(page, fromName).locator(`[data-port="${fromPort}"]`).first();
  const target = node(page, toName).locator(`[data-port="${toPort}"]`).first();
  const fromBox = await handle.boundingBox();
  const toBox = await target.boundingBox();
  if (fromBox === null || toBox === null) {
    throw new Error(`port ${fromName}.${fromPort} -> ${toName}.${toPort} is not visible`);
  }
  const start = { x: fromBox.x + fromBox.width / 2, y: fromBox.y + fromBox.height / 2 };
  const end = { x: toBox.x + toBox.width / 2, y: toBox.y + toBox.height / 2 };
  await page.mouse.move(start.x, start.y);
  await page.mouse.down();
  await page.mouse.move(start.x + 12, start.y + 8, { steps: 3 });
  await page.mouse.move(end.x, end.y, { steps: 12 });
  await page.mouse.up();
}

async function readDocument(page: Page): Promise<Record<string, unknown>> {
  const text = await page.getByTestId("document-json").textContent();
  return JSON.parse(text ?? "null") as Record<string, unknown>;
}

test("builds the DC motor, saves, reloads and undoes ten operations", async ({ page }) => {
  await openModel(page);
  await expect(page.getByTestId("canvas-empty")).toBeVisible();

  await dropBlock(page, "VoltageSource", 60, 210);
  await dropBlock(page, "DCMotor", 300, 120);
  await dropBlock(page, "Ground", 300, 380);
  await dropBlock(page, "FixedShaft", 300, 20);
  await dropBlock(page, "RotationalDamper", 555, 120);
  await dropBlock(page, "FixedShaft", 555, 380);
  await expect(page.getByTestId("diagram-node")).toHaveCount(6);
  await expect(node(page, "DCMotor")).toBeVisible();
  await expect(node(page, "FixedShaft2")).toBeVisible();
  await expect(page.getByTestId("dirty-marker")).toBeVisible();

  await connect(page, "VoltageSource", "p", "DCMotor", "p");
  await connect(page, "DCMotor", "n", "Ground", "p");
  await connect(page, "DCMotor", "housing", "FixedShaft", "a");
  await connect(page, "DCMotor", "shaft", "RotationalDamper", "a");
  await connect(page, "RotationalDamper", "b", "FixedShaft2", "a");
  await expect(page.locator('[data-testid^="edge-"]')).toHaveCount(5);
  await expect(page.getByTestId("connection-refusal")).toHaveCount(0);

  // All five power connections are wires (no Generic port), per plan 5.5.
  for (const kind of await page
    .locator('[data-testid^="edge-"]')
    .evaluateAll((edges) => edges.map((edge) => edge.getAttribute("data-kind")))) {
    expect(kind).toBe("wire");
  }

  const built = await readDocument(page);
  const builtNodes = built.diagram as { nodes: unknown[]; connections: unknown[] };
  expect(builtNodes.nodes).toHaveLength(6);
  expect(builtNodes.connections).toHaveLength(5);

  // Ten undos remove one operation each; the first drag was the VoltageSource.
  for (let step = 0; step < 10; step += 1) {
    await page.getByTestId("undo").click();
  }
  await expect(page.getByTestId("diagram-node")).toHaveCount(1);
  await expect(page.locator('[data-testid^="edge-"]')).toHaveCount(0);
  for (let step = 0; step < 10; step += 1) {
    await page.getByTestId("redo").click();
  }
  await expect(page.getByTestId("diagram-node")).toHaveCount(6);
  await expect(page.locator('[data-testid^="edge-"]')).toHaveCount(5);
  expect(await readDocument(page)).toEqual(built);

  await expect(page.getByTestId("save-status")).toHaveText("Saved", { timeout: 20_000 });
  await expect(page.getByTestId("dirty-marker")).toHaveCount(0);

  // The backend has the same document before the reload.
  const stored = await page.request.get(`/api/projects/${project}/models/DCMotorSpeed`);
  expect(stored.ok()).toBe(true);
  expect(await stored.json()).toEqual(built);

  await page.reload();
  await expect(page.getByTestId("canvas-surface")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("diagram-node")).toHaveCount(6);
  await expect(page.locator('[data-testid^="edge-"]')).toHaveCount(5);
  const reloaded = await readDocument(page);
  expect(reloaded).toEqual(built);

  // Ten more operations after the reload: ten rotations of the motor. Ten
  // undos must return exactly to the loaded document.
  await node(page, "DCMotor").click();
  await expect(node(page, "DCMotor")).toHaveClass(/is-selected/);
  await expect(page.getByTestId("tree-node-DCMotor")).toHaveAttribute("aria-current", "true");
  for (let step = 0; step < 10; step += 1) {
    await page.keyboard.press("r");
  }
  const rotated = await readDocument(page);
  expect(rotated).not.toEqual(reloaded);
  for (let step = 0; step < 10; step += 1) {
    await page.getByTestId("undo").click();
  }
  expect(await readDocument(page)).toEqual(reloaded);
  for (let step = 0; step < 10; step += 1) {
    await page.getByTestId("redo").click();
  }
  expect(await readDocument(page)).toEqual(rotated);
});

test("reverses a bond from the context menu and deletes it with Del", async ({ page }) => {
  await openModel(page, "BondMenu");
  await dropBlock(page, "Se", 100, 240);
  await dropBlock(page, "junction-0", 360, 240);
  await dropBlock(page, "Resistor", 620, 240);
  await expect(page.getByTestId("diagram-node")).toHaveCount(3);
  await connect(page, "Se", "p", "Junction0", "");
  await connect(page, "Junction0", "", "Resistor", "p");
  await expect(page.locator('[data-testid^="edge-"]')).toHaveCount(2);
  await expect(page.getByTestId("connection-refusal")).toHaveCount(0);

  const before = await readDocument(page);
  const beforeConnections = (before.diagram as {
    connections: { id: string; from: { node: string }; to: { node: string } }[];
  }).connections;
  const first = beforeConnections[0];
  if (first === undefined) {
    throw new Error("the bond was not created");
  }

  await page
    .locator('[data-testid^="edge-"]')
    .first()
    .dispatchEvent("contextmenu", {
      bubbles: true,
      button: 2,
      clientX: 600,
      clientY: 400,
    });
  await expect(page.getByTestId("canvas-menu")).toBeVisible();
  await expect(page.getByTestId("reverse-bond")).toBeVisible();
  await page.getByTestId("reverse-bond").click();

  const after = await readDocument(page);
  const afterConnections = (after.diagram as {
    connections: { id: string; from: { node: string }; to: { node: string } }[];
  }).connections;
  const reversed = afterConnections.find((connection) => connection.id === first.id);
  expect(reversed?.from.node).toBe(first.to.node);
  expect(reversed?.to.node).toBe(first.from.node);

  await page
    .locator('[data-testid^="edge-"]')
    .last()
    .dispatchEvent("click", { bubbles: true, button: 0 });
  await page.keyboard.press("Delete");
  await expect(page.locator('[data-testid^="edge-"]')).toHaveCount(1);
  await page.getByTestId("undo").click();
  await expect(page.locator('[data-testid^="edge-"]')).toHaveCount(2);

  // Multi-select: Ctrl-click adds a second node to the selection.
  await node(page, "Se").click();
  await expect(node(page, "Se")).toHaveClass(/is-selected/);
  await node(page, "Resistor").click({ modifiers: ["Control"] });
  await expect(node(page, "Se")).toHaveClass(/is-selected/);
  await expect(node(page, "Resistor")).toHaveClass(/is-selected/);

  // Moving a node is one undo step (the gesture coalesces).
  await node(page, "Se").click();
  const beforeMove = await readDocument(page);
  const seBox = await node(page, "Se").boundingBox();
  if (seBox === null) {
    throw new Error("Se is not visible");
  }
  await page.mouse.move(seBox.x + 24, seBox.y + 12);
  await page.mouse.down();
  await page.mouse.move(seBox.x + 84, seBox.y + 42, { steps: 6 });
  await page.mouse.up();
  const moved = await readDocument(page);
  expect(moved).not.toEqual(beforeMove);
  await page.getByTestId("undo").click();
  expect(await readDocument(page)).toEqual(beforeMove);
});

test("refuses Electrical to Rotation with the plan's tooltip", async ({ page }) => {
  await openModel(page, "Refusal");
  await dropBlock(page, "VoltageSource", 120, 220);
  await dropBlock(page, "DCMotor", 420, 200);
  await expect(page.getByTestId("diagram-node")).toHaveCount(2);

  const source = node(page, "VoltageSource").locator('[data-port="p"]').first();
  const shaft = node(page, "DCMotor").locator('[data-port="shaft"]').first();
  const fromBox = await source.boundingBox();
  const toBox = await shaft.boundingBox();
  if (fromBox === null || toBox === null) {
    throw new Error("ports are not visible");
  }
  const start = { x: fromBox.x + fromBox.width / 2, y: fromBox.y + fromBox.height / 2 };
  const end = { x: toBox.x + toBox.width / 2, y: toBox.y + toBox.height / 2 };
  await page.mouse.move(start.x, start.y);
  await page.mouse.down();
  await page.mouse.move(end.x, end.y, { steps: 12 });

  // While dragging, the incompatible ports fade and the compatible ones
  // highlight (plan 7.3).
  await expect(page.locator('[data-port="shaft"][data-state="incompatible"]')).toHaveCount(1);
  await expect(page.locator('[data-port="p"][data-state="compatible"]')).toHaveCount(1);

  await page.mouse.up();
  const tooltip = page.getByTestId("connection-refusal");
  await expect(tooltip).toBeVisible();
  await expect(tooltip).toHaveText(
    "Electrical port cannot connect to Rotation; use a converter (DC motor, EM converter)",
  );
  await expect(page.locator('[data-testid^="edge-"]')).toHaveCount(0);

  // The same pair connects when the domains agree.
  await connect(page, "VoltageSource", "p", "DCMotor", "p");
  await expect(page.locator('[data-testid^="edge-"]')).toHaveCount(1);
  await expect(page.locator('[data-testid^="edge-"]').first()).toHaveAttribute(
    "data-kind",
    "wire",
  );
});
