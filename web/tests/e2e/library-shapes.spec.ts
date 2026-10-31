import { mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { expandLibrary } from "./library";

/**
 * The library's Shapes category: a rectangle dragged from the list or from the grid lands on the
 * canvas as a background shape (not a block) at the drop point, selected, in one undo step; a click
 * on a shape tile adds it in the middle of the canvas. The category is axe-clean in both themes;
 * each theme writes library-shapes-<theme>.png (grid view, Shapes open) to BGSIM_SCREENSHOT_DIR
 * (default: the OS temp directory).
 *
 * Run with `$env:BGSIM_E2E_PORT="8778"; npx playwright test tests/e2e/library-shapes.spec.ts`.
 */

let project = "";

test.beforeEach(async ({ page }) => {
  project = `library-shapes-${Date.now()}-${test.info().workerIndex}`;
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.emulateMedia({ reducedMotion: "reduce" });
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
}

interface StoredDoc {
  diagram: { shapes?: StoredShape[]; nodes: unknown[] };
}

async function readDoc(page: Page): Promise<StoredDoc> {
  const text = await page.getByTestId("document-json").textContent();
  return JSON.parse(text ?? "null") as StoredDoc;
}

async function openModel(page: Page, view: "list" | "grid"): Promise<void> {
  await page.goto(`/?project=${encodeURIComponent(project)}&model=ShapeDrop`);
  await expandLibrary(page);
  await expect(page.getByTestId("canvas-surface")).toBeVisible();
  if (view === "grid") {
    await page.getByRole("button", { name: "Grid view" }).click();
  }
  await expect(page.getByTestId("library-browser")).toHaveAttribute("data-view", view);
  await expect(page.getByTestId("library-group-toggle-Shapes")).toHaveAttribute("aria-expanded", "true");
}

const shape = (page: Page, id: string) =>
  page.locator(`[data-testid="canvas-shape"][data-shape-id="${id}"]`);

for (const view of ["list", "grid"] as const) {
  test(`drags a rectangle from the ${view} view onto the canvas`, async ({ page }) => {
    await openModel(page, view);
    const item = page.getByTestId("library-item-shape-rectangle");
    await item.scrollIntoViewIfNeeded();
    await expect(item).toContainText("Rectangle");

    const surface = await page.getByTestId("canvas-surface").boundingBox();
    expect(surface).not.toBeNull();
    await item.dragTo(page.getByTestId("canvas-surface"), { targetPosition: { x: 300, y: 240 } });

    const rect = shape(page, "s1");
    await expect(rect).toBeVisible();
    await expect(rect).toHaveClass(/is-selected/);
    await expect(page.getByTestId("shape-inspector")).toBeVisible();
    const doc = await readDoc(page);
    expect(doc.diagram.nodes).toEqual([]);
    expect(doc.diagram.shapes).toHaveLength(1);
    const stored = doc.diagram.shapes?.[0];
    expect(stored?.kind).toBe("rectangle");
    // Snapped to the 20 px grid like the canvas menu's Add.
    expect((stored?.x ?? 1) % 20).toBe(0);
    expect((stored?.y ?? 1) % 20).toBe(0);
    // Its top-left corner sits at the drop point (within a grid step at the canvas zoom).
    const frame = await rect.boundingBox();
    expect(frame).not.toBeNull();
    expect(Math.abs(frame!.x - (surface!.x + 300))).toBeLessThan(25);
    expect(Math.abs(frame!.y - (surface!.y + 240))).toBeLessThan(25);

    // One undo step removes it again.
    await page.keyboard.press("Control+z");
    await expect(shape(page, "s1")).toHaveCount(0);
    expect((await readDoc(page)).diagram.shapes ?? []).toEqual([]);
  });
}

test("a click on a shape tile adds it in the middle of the canvas", async ({ page }) => {
  await openModel(page, "grid");
  const tile = page.getByTestId("library-item-shape-ellipse");
  await tile.scrollIntoViewIfNeeded();
  await tile.getByRole("button").click();
  const ellipse = shape(page, "s1");
  await expect(ellipse).toBeVisible();
  await expect(ellipse).toHaveClass(/is-selected/);
  expect((await readDoc(page)).diagram.shapes?.[0]?.kind).toBe("ellipse");
  const surface = await page.getByTestId("canvas-surface").boundingBox();
  const frame = await ellipse.boundingBox();
  const centre = { x: frame!.x + frame!.width / 2, y: frame!.y + frame!.height / 2 };
  expect(Math.abs(centre.x - (surface!.x + surface!.width / 2))).toBeLessThan(30);
  expect(Math.abs(centre.y - (surface!.y + surface!.height / 2))).toBeLessThan(30);
});

for (const theme of ["dark", "light"] as const) {
  test(`the Shapes category is axe-clean and screenshotted (${theme})`, async ({ page }) => {
    await page.addInitScript((value) => localStorage.setItem("bgsim.theme", value), theme);
    await openModel(page, "grid");
    const group = page.getByTestId("library-group-Shapes");
    await group.scrollIntoViewIfNeeded();
    await page.getByTestId("library-item-shape-roundedRectangle").hover();

    const result = await new AxeBuilder({ page }).include('[data-testid="left-panel"]').analyze();
    const serious = result.violations
      .filter((violation) => violation.impact === "serious" || violation.impact === "critical")
      .map((violation) => `${violation.id}: ${violation.nodes.map((node) => node.target.join(" ")).join(", ")}`);
    expect(serious).toEqual([]);

    const directory = process.env.BGSIM_SCREENSHOT_DIR ?? tmpdir();
    mkdirSync(directory, { recursive: true });
    await page.getByTestId("left-panel").screenshot({ path: path.join(directory, `library-shapes-${theme}.png`) });
  });
}
