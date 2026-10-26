import { expect, test, type Locator, type Page } from "@playwright/test";

/**
 * The diagram visual language follow-up:
 *
 * 1. a bond-graph element is its letter, not a card, and its port faces the
 *    bond that leaves it;
 * 2. the instance name hangs outside the letter (and moves off a port side);
 * 3. holding Ctrl and dragging an element starts a connection from its nearest
 *    source port, while Ctrl+click still selects;
 * 4. the toolbar toggles the grid and snapping, and a snapped drop lands on the
 *    20 px grid.
 */

let project = "";

test.beforeEach(async ({ page }) => {
  project = `w-canvas-style-${Date.now()}-${test.info().workerIndex}`;
  await page.setViewportSize({ width: 1600, height: 1000 });
});

test.afterEach(async ({ request }) => {
  if (project.length > 0) {
    await request.delete(`/api/projects/${project}`);
  }
});

async function openModel(page: Page): Promise<void> {
  await page.goto(`/?project=${encodeURIComponent(project)}&model=CanvasStyle`);
  await expect(page.getByTestId("library-item-Se")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("canvas-surface")).toBeVisible();
}

async function dropBlock(page: Page, name: string, x: number, y: number): Promise<void> {
  const item = page.getByTestId(`library-item-${name}`).first();
  await item.scrollIntoViewIfNeeded();
  await item.dragTo(page.getByTestId("canvas-surface"), { targetPosition: { x, y } });
}

function node(page: Page, name: string) {
  return page.locator(`[data-testid="diagram-node"][data-node-name="${name}"]`);
}

async function connectPorts(
  page: Page,
  from: Locator,
  fromPort: string,
  to: Locator,
  toPort: string,
): Promise<void> {
  const handle = from.locator(`[data-port="${fromPort}"]`).first();
  const target = to.locator(`[data-port="${toPort}"]`).first();
  const fromBox = await handle.boundingBox();
  const toBox = await target.boundingBox();
  if (fromBox === null || toBox === null) {
    throw new Error("a port is not visible");
  }
  await page.mouse.move(fromBox.x + fromBox.width / 2, fromBox.y + fromBox.height / 2);
  await page.mouse.down();
  await page.mouse.move(fromBox.x + fromBox.width / 2 + 12, fromBox.y + fromBox.height / 2 + 8, {
    steps: 3,
  });
  await page.mouse.move(toBox.x + toBox.width / 2, toBox.y + toBox.height / 2, { steps: 12 });
  await page.mouse.up();
}

test("a bond-graph element is its letter with the port on the bond side", async ({ page }) => {
  await openModel(page);
  await dropBlock(page, "Se", 80, 200);
  await dropBlock(page, "I", 420, 200);

  const source = node(page, "Se");
  const inertia = node(page, "I");
  await expect(source).toHaveAttribute("data-node-bond", "true");
  await expect(source.locator(".block-node")).toHaveCount(0);
  await expect(source.locator(".bond-node__glyph")).toHaveText("Se");
  await expect(source.locator('[data-testid^="node-label-"]')).toHaveText("Se");

  await connectPorts(page, source, "p", inertia, "p");
  await expect(page.locator('[data-testid^="edge-"]')).toHaveCount(1);

  const sourceId = await source.getAttribute("data-node-id");
  const targetId = await inertia.getAttribute("data-node-id");
  await expect(page.getByTestId(`port-${sourceId}-p`)).toHaveAttribute("data-side", "right");
  await expect(page.getByTestId(`port-${targetId}-p`)).toHaveAttribute("data-side", "left");
  // The label avoids the port side (right) and stays below the letter.
  await expect(source).toHaveAttribute("data-label-side", "bottom");
});

test("Ctrl-drag connects from the nearest source port and Ctrl+click still selects", async ({
  page,
}) => {
  await openModel(page);
  await dropBlock(page, "Se", 80, 200);
  await dropBlock(page, "Resistor", 420, 200);

  const source = node(page, "Se");
  const resistor = node(page, "Resistor");
  const sourceBox = await source.boundingBox();
  const portBox = await resistor.locator('[data-port="p"]').first().boundingBox();
  if (sourceBox === null || portBox === null) {
    throw new Error("source or target is not visible");
  }

  await page.keyboard.down("Control");
  await expect(page.locator(".react-flow.is-quick-connect")).toHaveCount(1);
  await page.mouse.move(sourceBox.x + sourceBox.width / 2, sourceBox.y + sourceBox.height / 2);
  await page.mouse.down();
  await page.mouse.move(sourceBox.x + sourceBox.width / 2 + 20, sourceBox.y + 40, { steps: 4 });
  await expect(page.getByTestId("quick-connect-line")).toBeVisible();
  await page.mouse.move(portBox.x + portBox.width / 2, portBox.y + portBox.height / 2, {
    steps: 12,
  });
  await page.mouse.up();
  await page.keyboard.up("Control");

  await expect(page.locator('[data-testid^="edge-"]')).toHaveCount(1);
  await expect(page.locator('[data-testid^="edge-"]').first()).toHaveAttribute(
    "data-kind",
    "bond",
  );

  // A plain Ctrl+click is still additive selection, not a connection.
  await page.locator(".react-flow__pane").click({ position: { x: 700, y: 100 } });
  await page.keyboard.down("Control");
  await expect(page.locator(".react-flow.is-quick-connect")).toHaveCount(1);
  await source.click();
  await resistor.click();
  await page.keyboard.up("Control");
  await expect(source).toHaveClass(/is-selected/);
  await expect(resistor).toHaveClass(/is-selected/);
  await expect(page.locator('[data-testid^="edge-"]')).toHaveCount(1);
});

test("the toolbar toggles the grid and snapping", async ({ page }) => {
  await openModel(page);
  const grid = page.getByTestId("toggle-grid");
  await expect(grid).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".react-flow__background")).toHaveCount(1);
  await grid.click();
  await expect(grid).toHaveAttribute("aria-pressed", "false");
  await expect(page.locator(".react-flow__background")).toHaveCount(0);
  await grid.click();
  await expect(page.locator(".react-flow__background")).toHaveCount(1);

  const snap = page.getByTestId("toggle-snap");
  await expect(snap).toHaveAttribute("aria-pressed", "false");
  await snap.click();
  await expect(snap).toHaveAttribute("aria-pressed", "true");

  await dropBlock(page, "Se", 137, 213);
  const stored = JSON.parse((await page.getByTestId("document-json").textContent()) ?? "null") as {
    diagram: { nodes: { position: { x: number; y: number } }[] };
  };
  expect(stored.diagram.nodes).toHaveLength(1);
  const position = stored.diagram.nodes[0]?.position;
  expect(position?.x).toBe(Math.round((position?.x ?? 0) / 20) * 20);
  expect(position?.y).toBe(Math.round((position?.y ?? 0) / 20) * 20);
  expect(position?.x).not.toBe(0);
  expect(position?.y).not.toBe(0);
});
