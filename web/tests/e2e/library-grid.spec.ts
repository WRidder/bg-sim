import { mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { expandLibrary } from "./library";

/**
 * The library grid view: the title toggle switches the library to three-column tiles (icon and
 * name only), the choice survives a reload, a tile drags onto the canvas like a list entry, and
 * the grid is axe-clean in both themes. Each theme writes library-grid-<theme>.png to
 * BGSIM_SCREENSHOT_DIR (default: the OS temp directory).
 *
 * Run with `$env:BGSIM_E2E_PORT="8778"; npx playwright test tests/e2e/library-grid.spec.ts`.
 */

let project = "";

test.beforeEach(async ({ page }) => {
  project = `library-grid-${Date.now()}-${test.info().workerIndex}`;
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.emulateMedia({ reducedMotion: "reduce" });
});

test.afterEach(async ({ request }) => {
  if (project.length > 0) {
    await request.delete(`/api/projects/${project}`);
  }
});

async function openGrid(page: Page): Promise<void> {
  await page.goto(`/?project=${encodeURIComponent(project)}&model=GridDrop`);
  await expandLibrary(page);
  await expect(page.getByTestId("canvas-surface")).toBeVisible();
  await page.getByRole("button", { name: "Grid view" }).click();
  await expect(page.getByRole("button", { name: "Grid view" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByTestId("library-browser")).toHaveAttribute("data-view", "grid");
}

/** The number of tiles in the first row of a category: the x positions of its first entries. */
async function columnsOf(page: Page, category: string): Promise<number> {
  const lefts = await page
    .getByTestId(`library-group-${category}`)
    .locator('[data-testid^="library-item-"]')
    .evaluateAll((items) => items.map((item) => Math.round(item.getBoundingClientRect().left)));
  return new Set(lefts).size;
}

test("drags a block from the grid onto the canvas, and the grid survives a reload", async ({ page }) => {
  await openGrid(page);
  // Three tiles per row at the default panel width, icon and name only.
  expect(await columnsOf(page, "Bond graph")).toBe(3);
  const se = page.getByTestId("library-item-Se");
  await expect(se.locator(".library-item__label")).toHaveText("Se");
  await expect(se.locator(".library-item__summary")).toHaveCount(0);

  await expect(page.getByTestId("canvas-empty")).toBeVisible();
  await se.scrollIntoViewIfNeeded();
  await se.dragTo(page.getByTestId("canvas-surface"), { targetPosition: { x: 260, y: 200 } });
  const motor = page.getByTestId("library-item-DCMotor");
  await motor.scrollIntoViewIfNeeded();
  await motor.dragTo(page.getByTestId("canvas-surface"), { targetPosition: { x: 480, y: 200 } });
  await expect(page.getByTestId("diagram-node")).toHaveCount(2);
  await expect(page.locator('[data-testid="diagram-node"][data-node-name="Se"]')).toBeVisible();
  await expect(page.locator('[data-testid="diagram-node"][data-node-name="DCMotor"]')).toBeVisible();

  await page.reload();
  await expect(page.getByTestId("library-browser")).toHaveAttribute("data-view", "grid", {
    timeout: 30_000,
  });
  await expect(page.getByRole("button", { name: "Grid view" })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "List view" }).click();
  await expect(page.getByTestId("library-browser")).toHaveAttribute("data-view", "list");
  await expect(page.getByTestId("library-item-Se").locator(".library-item__summary")).toHaveCount(1);
});

test("a narrow library panel shows fewer columns", async ({ page }) => {
  await openGrid(page);
  // Drag the column splitter to the left: the library column stops at its 200 px minimum, too
  // narrow for three tiles of at least 64 px.
  const panel = await page.getByTestId("left-panel").boundingBox();
  expect(panel).not.toBeNull();
  const x = panel!.x + panel!.width + 2;
  const y = panel!.y + panel!.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x - 150, y, { steps: 8 });
  await page.mouse.move(x - 300, y, { steps: 8 });
  await page.mouse.up();
  const width = await page
    .locator(".library-group__list--grid")
    .first()
    .evaluate((list) => list.clientWidth);
  expect(await columnsOf(page, "Bond graph"), `grid width ${width}`).toBe(2);
  const label = page.getByTestId("library-item-VoltageSource").locator(".library-item__label");
  await expect(label).toHaveCSS("text-overflow", "ellipsis");
});

for (const theme of ["dark", "light"] as const) {
  test(`the grid view is axe-clean and screenshotted (${theme})`, async ({ page }) => {
    await page.addInitScript((value) => localStorage.setItem("bgsim.theme", value), theme);
    await openGrid(page);
    // The top of the library, with the hover style on one tile.
    await page.locator(".library__groups").evaluate((groups) => groups.scrollTo(0, 0));
    await page.getByTestId("library-item-C").hover();

    const result = await new AxeBuilder({ page }).include('[data-testid="left-panel"]').analyze();
    const serious = result.violations
      .filter((violation) => violation.impact === "serious" || violation.impact === "critical")
      .map((violation) => `${violation.id}: ${violation.nodes.map((node) => node.target.join(" ")).join(", ")}`);
    expect(serious).toEqual([]);

    const directory = process.env.BGSIM_SCREENSHOT_DIR ?? tmpdir();
    mkdirSync(directory, { recursive: true });
    await page.getByTestId("left-panel").screenshot({ path: path.join(directory, `library-grid-${theme}.png`) });
  });
}
