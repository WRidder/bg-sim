import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { expandLibrary } from "./library";

/**
 * Background shapes on the diagram canvas (`diagram.shapes`):
 *
 * 1. "Add rectangle" in the canvas menu adds a shape behind everything; a
 *    block dropped on a filled shape sits in front of it, drags over it and
 *    connects its ports over it; a press inside the filled shape selects and
 *    drags the shape;
 * 2. the shape menu reorders (bring to front, send backward, send to back);
 *    a locked shape does not drag, survives Del and the selection rectangle
 *    skips it; the inspector unlocks it; duplicate copies it;
 * 3. lines and arrows drag their end points; notes stay above shapes; the
 *    order survives a reload. Screenshots of both themes go to
 *    BGSIM_SCREENSHOT_DIR when set. The menus and the inspector are axe-clean.
 */

const shots = process.env.BGSIM_SCREENSHOT_DIR ?? "";
let project = "";

test.beforeEach(async ({ page }) => {
  project = `w-canvas-shapes-${Date.now()}-${test.info().workerIndex}`;
  await page.setViewportSize({ width: 1600, height: 1000 });
});

test.afterEach(async ({ request }) => {
  if (project.length > 0) {
    await request.delete(`/api/projects/${project}`);
  }
});

interface StoredShape {
  id: string;
  kind: string;
  x: number;
  y: number;
  w: number;
  h: number;
  fill?: string;
  stroke?: string;
  strokeStyle?: string;
  text?: string;
  locked?: boolean;
}

interface StoredDoc {
  diagram: {
    shapes?: StoredShape[];
    nodes: { id: string; name: string; position: { x: number; y: number } }[];
    connections: unknown[];
    annotations?: unknown[];
  };
}

async function openModel(page: Page, model: string): Promise<void> {
  await page.goto(`/?project=${encodeURIComponent(project)}&model=${model}`);
  await expandLibrary(page);
  await expect(page.getByTestId("canvas-surface")).toBeVisible();
}

async function canvasPoint(page: Page, x: number, y: number): Promise<{ x: number; y: number }> {
  const box = await page.getByTestId("canvas-surface").boundingBox();
  if (box === null) {
    throw new Error("the canvas is not visible");
  }
  return { x: box.x + x, y: box.y + y };
}

async function readDoc(page: Page): Promise<StoredDoc> {
  const text = await page.getByTestId("document-json").textContent();
  return JSON.parse(text ?? "null") as StoredDoc;
}

async function shapeOrder(page: Page): Promise<string[]> {
  return ((await readDoc(page)).diagram.shapes ?? []).map((shape) => shape.id);
}

async function expectMenuAxeClean(page: Page): Promise<void> {
  const result = await new AxeBuilder({ page }).include('[data-testid="canvas-menu"]').analyze();
  expect(result.violations.map((violation) => violation.id)).toEqual([]);
}

async function addShapeByMenu(
  page: Page,
  kind: string,
  x: number,
  y: number,
  options: { axe?: boolean } = {},
): Promise<void> {
  const point = await canvasPoint(page, x, y);
  await page.mouse.click(point.x, point.y, { button: "right" });
  await expect(page.getByTestId("canvas-menu")).toBeVisible();
  if (options.axe === true) {
    await expectMenuAxeClean(page);
  }
  await page.getByTestId(`add-shape-${kind}`).click();
  await expect(page.getByTestId("canvas-menu")).toHaveCount(0);
}

const shape = (page: Page, id: string) =>
  page.locator(`[data-testid="canvas-shape"][data-shape-id="${id}"]`);

/** The canvas id of the topmost xyflow node at a viewport point, or null. */
async function nodeAt(page: Page, point: { x: number; y: number }): Promise<string | null> {
  return page.evaluate(
    ({ x, y }) =>
      document.elementFromPoint(x, y)?.closest(".react-flow__node")?.getAttribute("data-id") ?? null,
    point,
  );
}

async function box(_page: Page, locator: ReturnType<Page["locator"]>) {
  const result = await locator.boundingBox();
  if (result === null) {
    throw new Error("not visible");
  }
  return result;
}

async function drag(
  page: Page,
  from: { x: number; y: number },
  to: { x: number; y: number },
): Promise<void> {
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(from.x + (to.x - from.x) / 3, from.y + (to.y - from.y) / 3, { steps: 4 });
  await page.mouse.move(to.x, to.y, { steps: 8 });
  await page.mouse.up();
}

async function dropBlock(page: Page, name: string, x: number, y: number): Promise<void> {
  const item = page.getByTestId(`library-item-${name}`).first();
  await item.scrollIntoViewIfNeeded();
  await item.dragTo(page.getByTestId("canvas-surface"), { targetPosition: { x, y } });
}

const blockNode = (page: Page, name: string) =>
  page.locator(`[data-testid="diagram-node"][data-node-name="${name}"]`);

async function waitSaved(page: Page): Promise<void> {
  await expect(page.getByTestId("save-status")).toHaveAttribute("data-state", "saved", {
    timeout: 15_000,
  });
}

test("a filled shape sits behind blocks that drag and connect over it", async ({ page }) => {
  await openModel(page, "ShapesBehind");
  await addShapeByMenu(page, "rectangle", 80, 80, { axe: true });
  const rect = shape(page, "s1");
  await expect(rect).toBeVisible();
  await expect(page.getByTestId("shape-inspector")).toBeVisible();
  await page.getByTestId("shape-fill-blue").click();
  await expect(rect).toHaveAttribute("data-fill", "blue");

  // Grow it from its bottom-right corner so two blocks fit inside.
  const handle = rect.locator(".react-flow__resize-control.handle.bottom.right");
  const corner = await box(page, handle);
  await drag(
    page,
    { x: corner.x + corner.width / 2, y: corner.y + corner.height / 2 },
    { x: corner.x + 420, y: corner.y + 300 },
  );
  const area = await box(page, rect);
  expect(area.width).toBeGreaterThan(500);
  const surface = await box(page, page.getByTestId("canvas-surface"));

  await dropBlock(page, "VoltageSource", area.x - surface.x + 90, area.y - surface.y + 110);
  await dropBlock(page, "Ground", area.x - surface.x + 380, area.y - surface.y + 260);
  const source = blockNode(page, "VoltageSource");
  const ground = blockNode(page, "Ground");
  await expect(source).toBeVisible();
  await expect(ground).toBeVisible();

  // The block is in front of the shape.
  const sourceBox = await box(page, source);
  const top = await nodeAt(page, {
    x: sourceBox.x + sourceBox.width / 2,
    y: sourceBox.y + sourceBox.height / 2,
  });
  expect(top).not.toBeNull();
  expect(top?.startsWith("shape:")).toBe(false);

  // Ports connect over the shape.
  const from = await box(page, source.locator('[data-port="n"]').first());
  const to = await box(page, ground.locator('[data-port="p"]').first());
  await drag(
    page,
    { x: from.x + from.width / 2, y: from.y + from.height / 2 },
    { x: to.x + to.width / 2, y: to.y + to.height / 2 },
  );
  await expect.poll(async () => (await readDoc(page)).diagram.connections.length).toBe(1);

  // The block drags over the shape; the shape stays put.
  const shapeBefore = (await readDoc(page)).diagram.shapes?.[0];
  const before = (await readDoc(page)).diagram.nodes.find((n) => n.name === "VoltageSource")?.position;
  await drag(
    page,
    { x: sourceBox.x + sourceBox.width / 2, y: sourceBox.y + 12 },
    { x: sourceBox.x + sourceBox.width / 2 + 80, y: sourceBox.y + 72 },
  );
  const after = (await readDoc(page)).diagram.nodes.find((n) => n.name === "VoltageSource")?.position;
  expect((after?.x ?? 0) - (before?.x ?? 0)).toBeGreaterThan(50);
  expect((await readDoc(page)).diagram.shapes?.[0]).toEqual(shapeBefore);

  // A press on the empty inside of the filled shape selects it, and a drag moves it.
  const inside = { x: area.x + area.width - 40, y: area.y + 30 };
  expect(await nodeAt(page, inside)).toBe("shape:s1");
  // (Retried: the click right after a drag can land before the canvas settles.)
  await expect(async () => {
    await page.mouse.click(inside.x, inside.y);
    await expect(rect).toHaveClass(/is-selected/, { timeout: 1000 });
  }).toPass();
  await expect(page.getByTestId("shape-inspector")).toBeVisible();
  await drag(page, inside, { x: inside.x + 60, y: inside.y + 40 });
  const moved = (await readDoc(page)).diagram.shapes?.[0];
  expect((moved?.x ?? 0) - (shapeBefore?.x ?? 0)).toBeGreaterThan(40);

  // An unfilled shape lets a press on its inside through to the canvas.
  await page.getByTestId("shape-fill-none").click();
  await expect(rect).toHaveAttribute("data-fill", "none");
  const hollow = await box(page, rect);
  expect(await nodeAt(page, { x: hollow.x + hollow.width - 40, y: hollow.y + 40 })).toBeNull();
});

test("the shape menu reorders, locks, unlocks and duplicates", async ({ page }) => {
  await openModel(page, "ShapesOrder");
  await addShapeByMenu(page, "rectangle", 100, 100);
  // The rectangle has no fill yet, so a right-click inside it is on the canvas.
  await addShapeByMenu(page, "ellipse", 180, 130);
  await page.getByTestId("shape-fill-green").click();
  expect(await shapeOrder(page)).toEqual(["s1", "s2"]);
  const rectBox = await box(page, shape(page, "s1"));
  const ellipseBox = await box(page, shape(page, "s2"));
  // An unfilled shape is picked by its outline.
  await page.mouse.click(rectBox.x + 2, rectBox.y + rectBox.height / 2);
  await expect(shape(page, "s1")).toHaveClass(/is-selected/);
  await page.getByTestId("shape-fill-blue").click();
  await expect(shape(page, "s1")).toHaveAttribute("data-fill", "blue");
  // A point inside both: the ellipse (added last) is in front.
  const overlap = { x: ellipseBox.x + 40, y: ellipseBox.y + ellipseBox.height / 2 };
  expect(overlap.x).toBeLessThan(rectBox.x + rectBox.width);
  expect(await nodeAt(page, overlap)).toBe("shape:s2");

  // Bring the rectangle to front (its menu is axe-clean).
  const rectOnly = { x: rectBox.x + 20, y: rectBox.y + 20 };
  await page.mouse.click(rectOnly.x, rectOnly.y, { button: "right" });
  await expect(page.getByTestId("shape-order-front")).toBeEnabled();
  await expect(page.getByTestId("shape-order-back")).toBeDisabled();
  await expectMenuAxeClean(page);
  await page.getByTestId("shape-order-front").click();
  expect(await shapeOrder(page)).toEqual(["s2", "s1"]);
  expect(await nodeAt(page, overlap)).toBe("shape:s1");

  // Send it backward again, then the ellipse to back.
  await page.mouse.click(rectOnly.x, rectOnly.y, { button: "right" });
  await page.getByTestId("shape-order-backward").click();
  expect(await shapeOrder(page)).toEqual(["s1", "s2"]);
  await page.mouse.click(overlap.x, overlap.y, { button: "right" });
  await page.getByTestId("shape-order-back").click();
  expect(await shapeOrder(page)).toEqual(["s2", "s1"]);
  // The order is one undo step each.
  await page.keyboard.press("Control+z");
  expect(await shapeOrder(page)).toEqual(["s1", "s2"]);

  // Lock the rectangle.
  await page.mouse.click(rectOnly.x, rectOnly.y, { button: "right" });
  await page.getByTestId("shape-lock").click();
  const rect = shape(page, "s1");
  await expect(rect).toHaveAttribute("data-locked", "true");
  await page.mouse.click(rectOnly.x, rectOnly.y);
  await expect(rect).toHaveClass(/is-selected/);
  await expect(rect.getByTestId("canvas-shape-lock")).toBeVisible();
  await expect(page.getByTestId("shape-inspector-locked")).toBeChecked();
  await expect(rect.locator(".react-flow__resize-control.handle")).toHaveCount(0);

  // It does not drag and survives Del.
  const lockedBefore = (await readDoc(page)).diagram.shapes?.find((s) => s.id === "s1");
  await drag(page, rectOnly, { x: rectOnly.x + 120, y: rectOnly.y + 90 });
  expect((await readDoc(page)).diagram.shapes?.find((s) => s.id === "s1")).toEqual(lockedBefore);
  await page.mouse.click(rectOnly.x, rectOnly.y);
  await page.keyboard.press("Delete");
  expect(await shapeOrder(page)).toEqual(["s1", "s2"]);

  // The menu offers Unlock, and Delete is disabled.
  await page.mouse.click(rectOnly.x, rectOnly.y, { button: "right" });
  await expect(page.getByTestId("shape-unlock")).toBeVisible();
  await expect(page.getByTestId("shape-delete")).toBeDisabled();
  await expectMenuAxeClean(page);
  await page.keyboard.press("Escape");
  const empty = await canvasPoint(page, 900, 560);
  await page.mouse.click(empty.x, empty.y);
  await expect(page.getByTestId("canvas-menu")).toHaveCount(0);

  // A selection rectangle over both selects only the unlocked ellipse.
  const start = await canvasPoint(page, 20, 20);
  await drag(page, start, { x: ellipseBox.x + ellipseBox.width + 40, y: ellipseBox.y + ellipseBox.height + 40 });
  await expect(shape(page, "s2")).toHaveClass(/is-selected/);
  await expect(rect).not.toHaveClass(/is-selected/);

  // The inspector unlocks it; then Del deletes it and Ctrl+Z brings it back.
  await page.mouse.click(rectOnly.x, rectOnly.y);
  await expect(page.getByTestId("shape-inspector")).toBeVisible();
  const axe = await new AxeBuilder({ page }).include('[data-testid="shape-inspector"]').analyze();
  expect(axe.violations.map((violation) => violation.id)).toEqual([]);
  await page.getByTestId("shape-inspector-locked").uncheck();
  await expect(rect).toHaveAttribute("data-locked", "false");
  // Del on the canvas (the checkbox keeps its keys).
  await page.mouse.click(rectOnly.x, rectOnly.y);
  await expect(rect).toHaveClass(/is-selected/);
  await page.keyboard.press("Delete");
  await expect.poll(() => shapeOrder(page)).toEqual(["s2"]);
  await page.keyboard.press("Control+z");
  expect(await shapeOrder(page)).toEqual(["s1", "s2"]);

  // Duplicate puts an unlocked copy in front.
  await page.mouse.click(overlap.x + 80, overlap.y, { button: "right" });
  await page.getByTestId("shape-duplicate").click();
  expect(await shapeOrder(page)).toEqual(["s1", "s2", "s3"]);
  const copy = (await readDoc(page)).diagram.shapes?.[2];
  expect(copy).toMatchObject({ kind: "ellipse", fill: "green" });
  expect(copy?.locked).toBeUndefined();
});

test("lines and arrows drag their ends; notes stay above shapes; both themes", async ({ page }) => {
  await openModel(page, "ShapesLines");
  // A labelled, filled rounded rectangle with a note and a block on it.
  await addShapeByMenu(page, "roundedRectangle", 60, 60);
  await page.getByTestId("shape-fill-green").click();
  await page.getByTestId("shape-stroke-green").click();
  await page.getByTestId("shape-inspector-text").fill("Controller");
  const rounded = await box(page, shape(page, "s1"));
  const handle = shape(page, "s1").locator(".react-flow__resize-control.handle.bottom.right");
  const corner = await box(page, handle);
  await drag(
    page,
    { x: corner.x + corner.width / 2, y: corner.y + corner.height / 2 },
    { x: corner.x + 260, y: corner.y + 200 },
  );
  await expect(shape(page, "s1").getByTestId("canvas-shape-label")).toHaveText("Controller");
  const surface = await box(page, page.getByTestId("canvas-surface"));
  const left = rounded.x - surface.x;
  const top = rounded.y - surface.y;

  // N over the shape adds a note there, in front of the shape.
  const empty = await canvasPoint(page, 900, 560);
  await page.mouse.click(empty.x, empty.y);
  const notePoint = await canvasPoint(page, left + 20, top + 120);
  await page.mouse.move(notePoint.x, notePoint.y);
  await page.keyboard.press("n");
  await page.getByTestId("sticky-note-editor").fill("Shapes sit behind notes");
  await page.keyboard.press("Escape");
  const note = await box(page, page.getByTestId("sticky-note").first());
  expect(await nodeAt(page, { x: note.x + 30, y: note.y + 30 })).toMatch(/^note:/);

  // A block in front of the shape, an ellipse and a dashed grey line.
  await dropBlock(page, "Se", left + 300, top + 80);
  await addShapeByMenu(page, "ellipse", 640, 80);
  await page.getByTestId("shape-fill-pink").click();
  await page.getByTestId("shape-stroke-none").click();
  await page.getByTestId("shape-inspector-text").fill("Plant");
  await addShapeByMenu(page, "line", 80, 480);
  await page.getByTestId("shape-stroke-grey").click();
  await page.getByTestId("shape-stroke-style").selectOption("dashed");
  await page.getByTestId("shape-stroke-width").selectOption("3");

  // An arrow: drag its end point down and to the right.
  await addShapeByMenu(page, "arrow", 640, 360);
  await page.getByTestId("shape-stroke-blue").click();
  const arrow = shape(page, "s4");
  const end = await box(page, arrow.getByTestId("canvas-shape-end"));
  const before = (await readDoc(page)).diagram.shapes?.find((s) => s.id === "s4");
  expect(before).toMatchObject({ kind: "arrow", w: 200, h: 0 });
  await drag(
    page,
    { x: end.x + end.width / 2, y: end.y + end.height / 2 },
    { x: end.x + end.width / 2 + 60, y: end.y + end.height / 2 + 120 },
  );
  const after = (await readDoc(page)).diagram.shapes?.find((s) => s.id === "s4");
  expect(after?.x).toBe(before?.x);
  expect(after?.y).toBe(before?.y);
  expect((after?.h ?? 0)).toBeGreaterThan(100);
  expect((after?.w ?? 0)).toBeGreaterThan(220);
  // One undo step restores the end.
  await page.keyboard.press("Control+z");
  expect((await readDoc(page)).diagram.shapes?.find((s) => s.id === "s4")).toEqual(before);
  await page.keyboard.press("Control+y");

  // Lock the ellipse; select the rounded rectangle for the picture.
  await shape(page, "s2").getByTestId("canvas-shape-label").click({ button: "right" });
  await page.getByTestId("shape-lock").click();
  await shape(page, "s1").getByTestId("canvas-shape-label").click();
  await expect(shape(page, "s1")).toHaveClass(/is-selected/);

  // Persisted, in order.
  await waitSaved(page);
  const order = await shapeOrder(page);
  expect(order).toEqual(["s1", "s2", "s3", "s4"]);
  await page.reload();
  await expect(page.getByTestId("library-item-Se")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("canvas-shape")).toHaveCount(4);
  expect(await shapeOrder(page)).toEqual(order);
  const stored = (await readDoc(page)).diagram.shapes ?? [];
  expect(stored[1]).toMatchObject({ kind: "ellipse", fill: "pink", stroke: "none", text: "Plant", locked: true });
  expect(stored[2]).toMatchObject({ kind: "line", stroke: "grey", strokeStyle: "dashed", strokeWidth: 3 });

  await shape(page, "s1").getByTestId("canvas-shape-label").click();
  await shape(page, "s2").getByTestId("canvas-shape-label").hover();
  await expect(shape(page, "s2").getByTestId("canvas-shape-lock")).toBeVisible();
  for (const theme of ["dark", "light"] as const) {
    await page.evaluate((value) => document.documentElement.setAttribute("data-theme", value), theme);
    // Labels on their fills meet the contrast ratio in this theme.
    const result = await new AxeBuilder({ page }).include('[data-testid="canvas-shape"]').analyze();
    expect(result.violations.map((violation) => violation.id)).toEqual([]);
    const area = await box(page, page.getByTestId("canvas-surface"));
    if (shots.length > 0) {
      await page.screenshot({
        path: `${shots}/canvas-shapes-${theme}.png`,
        clip: { x: area.x, y: area.y, width: Math.min(area.width, 1100), height: 640 },
      });
    }
  }
});
