import { expect, test, type Page } from "@playwright/test";

/**
 * W1.2 acceptance (plan 7.2, 7.4 and the work package):
 *
 * 1. select a block, edit its R parameter in the inspector, see the document
 *    change, press Ctrl+Z and see the original value and document restored;
 * 2. a rename that collides with a sibling is refused with a message, a unique
 *    rename updates the canvas, and undo restores the old name.
 *
 * Each test uses its own project and deletes it afterwards, as the canvas
 * suite does, so runs never inherit a model from a previous run.
 */

let project = "";

test.beforeEach(async ({ page }) => {
  project = `w12e2e-${Date.now()}-${test.info().workerIndex}`;
  await page.setViewportSize({ width: 1600, height: 1000 });
});

test.afterEach(async ({ request }) => {
  if (project.length > 0) {
    await request.delete(`/api/projects/${project}`);
  }
});

async function openModel(page: Page): Promise<void> {
  await page.goto(`/?project=${encodeURIComponent(project)}&model=Inspector`);
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

interface StoredNode {
  id: string;
  name: string;
  params?: Record<string, string>;
  constants?: Record<string, unknown>;
  starts?: Record<string, string>;
}

async function readDocument(page: Page): Promise<{ diagram: { nodes: StoredNode[] } }> {
  const text = await page.getByTestId("document-json").textContent();
  return JSON.parse(text ?? "null") as { diagram: { nodes: StoredNode[] } };
}

test("edits R in the inspector and undoes it with Ctrl+Z", async ({ page }) => {
  await openModel(page);
  await dropBlock(page, "DCMotor", 420, 180);
  await expect(page.getByTestId("diagram-node")).toHaveCount(1);

  const motor = page.locator('[data-testid="diagram-node"][data-node-name="DCMotor"]');
  await motor.click();
  await expect(page.getByTestId("inspector-node")).toBeVisible();
  await expect(page.getByTestId("inspector-title")).toHaveText("DCMotor");
  await expect(page.getByTestId("inspector-ref")).toHaveText("stdlib:converters/DCMotor");

  const r = page.getByTestId("inspector-param-R");
  await expect(r).toHaveValue("2.0");
  await expect(page.getByTestId("inspector-param-R-field")).toContainText("Ohm");

  await r.fill("3.5");
  await r.press("Enter");
  await expect(r).toHaveValue("3.5");

  const edited = await readDocument(page);
  expect(edited.diagram.nodes).toHaveLength(1);
  expect(edited.diagram.nodes[0]?.params?.R).toBe("3.5");

  // Enter commits and leaves the field, so the canvas shortcut handles Ctrl+Z
  // as a document undo rather than the input's native text undo.
  await page.keyboard.press("Control+z");
  await expect(r).toHaveValue("2.0");
  const undone = await readDocument(page);
  expect(undone.diagram.nodes[0]?.params?.R).toBe("2.0");

  await page.keyboard.press("Control+y");
  await expect(r).toHaveValue("3.5");
  expect((await readDocument(page)).diagram.nodes[0]?.params?.R).toBe("3.5");

  await page.keyboard.press("Control+z");
  await expect(r).toHaveValue("2.0");
});

test("refuses a rename collision and undoes a unique rename", async ({ page }) => {
  await openModel(page);
  await dropBlock(page, "DCMotor", 380, 160);
  await dropBlock(page, "Ground", 380, 400);
  await expect(page.getByTestId("diagram-node")).toHaveCount(2);

  const motor = page.locator('[data-testid="diagram-node"][data-node-name="DCMotor"]');
  await motor.click();
  const name = page.getByTestId("inspector-name");
  await expect(name).toHaveValue("DCMotor");

  await name.fill("Ground");
  await expect(page.getByTestId("inspector-name-error")).toContainText(
    'already has a block named "Ground"',
  );
  await expect(name).toHaveAttribute("aria-invalid", "true");
  await name.press("Enter");
  expect((await readDocument(page)).diagram.nodes.map((node) => node.name)).toEqual([
    "DCMotor",
    "Ground",
  ]);

  await name.fill("Motor2");
  await expect(page.getByTestId("inspector-name-error")).toHaveCount(0);
  await name.press("Enter");
  await expect(
    page.locator('[data-testid="diagram-node"][data-node-name="Motor2"]'),
  ).toBeVisible();
  expect((await readDocument(page)).diagram.nodes[0]?.name).toBe("Motor2");

  await page.keyboard.press("Control+z");
  await expect(
    page.locator('[data-testid="diagram-node"][data-node-name="DCMotor"]'),
  ).toBeVisible();
  await expect(page.getByTestId("inspector-name")).toHaveValue("DCMotor");
});
