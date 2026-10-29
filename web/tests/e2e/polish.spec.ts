import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/**
 * W5.4 acceptance (plan 7.8), fake worker: the start page with the example gallery, the keyboard
 * shortcuts and their overlay, the block help dialog, dialog focus handling, and Esc cancelling a
 * Ctrl-drag connection.
 *
 * Run with `$env:BGSIM_E2E_PORT="8778"; npx playwright test tests/e2e/polish.spec.ts`.
 */

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "../../..");

let project = "";
let imported = "";

test.beforeEach(async ({ page }) => {
  project = `w54-polish-${Date.now()}-${test.info().workerIndex}`;
  imported = "";
  await page.setViewportSize({ width: 1600, height: 1000 });
});

test.afterEach(async ({ request }) => {
  for (const name of [project, imported]) {
    if (name.length > 0) await request.delete(`/api/projects/${name}`);
  }
});

async function storeRlc(request: APIRequestContext): Promise<void> {
  expect((await request.post("/api/projects", { data: { name: project } })).status()).toBe(201);
  const model = JSON.parse(
    readFileSync(path.join(repoRoot, "contracts", "fixtures", "model", "valid", "model.rlc.iconic.json"), "utf8"),
  ) as Record<string, unknown>;
  expect((await request.put(`/api/projects/${project}/models/Rlc`, { data: model })).status()).toBe(200);
}

async function openEditor(page: Page): Promise<void> {
  await page.goto(`/?project=${project}&model=Rlc`);
  await expect(page.getByTestId("diagram-node").first()).toBeVisible({ timeout: 30_000 });
}

test("the start page lists a card per example, imports a sample and lists the project as recent", async ({
  page,
  request,
}) => {
  // A tooling directory such as __pycache__ is listed by the backend but is not an example.
  const examples = ((await (await request.get("/api/examples")).json()) as { examples: string[] }).examples.filter(
    (name) => !name.startsWith("_") && !name.startsWith("."),
  );
  expect(examples.length).toBeGreaterThan(3);

  await page.goto("/");
  const start = page.getByTestId("start-page");
  await expect(start).toHaveAttribute("data-state", "ready", { timeout: 30_000 });
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  // The editor is not mounted behind the start page.
  await expect(page.getByTestId("left-panel")).toHaveCount(0);

  for (const name of examples) {
    const card = page.getByTestId(`example-card-${name}`);
    await expect(card).toBeVisible();
    // Every card has a thumbnail or the neutral placeholder, never a broken image.
    const thumb = card.getByTestId(`example-thumbnail-${name}`);
    if ((await thumb.count()) > 0) {
      await thumb.scrollIntoViewIfNeeded();
      await expect
        .poll(() => thumb.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0))
        .toBe(true);
    } else {
      await expect(card.getByTestId(`example-placeholder-${name}`)).toHaveCount(1);
    }
    await expect(card.getByRole("button", { name: /^Open sample/ })).toBeEnabled();
  }

  const before = readFileSync(
    path.join(repoRoot, "examples", "dc-motor", "models", "iconic.bgmodel.json"),
    "utf8",
  );
  await page.getByTestId("example-open-dc-motor").click();
  await expect(page).toHaveURL(/project=dc-motor/);
  imported = new URL(page.url()).searchParams.get("project") ?? "";
  await expect(page.getByTestId("diagram-node")).toHaveCount(7, { timeout: 30_000 });
  // The sample itself never changes.
  expect(
    readFileSync(path.join(repoRoot, "examples", "dc-motor", "models", "iconic.bgmodel.json"), "utf8"),
  ).toBe(before);

  // Back on the start page the import is a recent project.
  await page.goto("/");
  await expect(page.getByTestId(`recent-project-${imported}`)).toBeVisible({ timeout: 30_000 });
});

test("a new project is created from the start page", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("start-page")).toHaveAttribute("data-state", "ready", { timeout: 30_000 });
  await page.getByTestId("start-new-project-name").fill(project);
  await page.getByTestId("start-create-project").click();
  await expect(page).toHaveURL(new RegExp(`project=${project}`));
  await expect(page.getByTestId("library-browser")).toBeVisible({ timeout: 30_000 });
});

test("? opens the shortcuts overlay, Esc closes it and focus returns", async ({ page, request }) => {
  await storeRlc(request);
  await openEditor(page);

  await page.getByTestId("library-search").focus();
  await page.keyboard.press("Escape");
  await page.getByTestId("diagram-node").first().click();
  await page.keyboard.press("?");
  const overlay = page.getByTestId("shortcuts-overlay");
  await expect(overlay).toBeVisible();
  await expect(overlay).toContainText("Ctrl");
  await expect(overlay).toContainText("Run the model");

  // Tab never leaves the dialog.
  for (let press = 0; press < 4; press += 1) {
    await page.keyboard.press("Tab");
    await expect.poll(() => overlay.evaluate((el) => el.contains(document.activeElement))).toBe(true);
  }
  await page.keyboard.press("Escape");
  await expect(overlay).toBeHidden();
});

test("/ focuses the library search, and a / typed in a field stays text", async ({ page, request }) => {
  await storeRlc(request);
  await openEditor(page);

  await page.locator(".react-flow__pane").click({ position: { x: 600, y: 400 } });
  await page.keyboard.press("/");
  await expect(page.getByTestId("library-search")).toBeFocused();
  await page.keyboard.type("a/b");
  await expect(page.getByTestId("library-search")).toHaveValue("a/b");
});

test("Ctrl+O opens the Open dialog, traps focus and returns it to the project button", async ({ page, request }) => {
  await storeRlc(request);
  await openEditor(page);

  await page.getByTestId("open-project").focus();
  await page.keyboard.press("Control+o");
  const dialog = page.getByTestId("open-dialog");
  await expect(dialog).toBeVisible();
  for (let press = 0; press < 12; press += 1) {
    await page.keyboard.press("Tab");
    await expect.poll(() => dialog.evaluate((el) => el.contains(document.activeElement))).toBe(true);
  }
  await page.keyboard.press("Shift+Tab");
  await expect.poll(() => dialog.evaluate((el) => el.contains(document.activeElement))).toBe(true);
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(page.getByTestId("open-project")).toBeFocused();
});

test("block help shows description, ports with units and parameters for the selected block", async ({
  page,
  request,
}) => {
  await storeRlc(request);
  await openEditor(page);

  await page.locator('[data-testid="diagram-node"][data-node-name="R1"]').click();
  await page.getByTestId("block-help-button").first().click();
  const help = page.getByTestId("block-help");
  await expect(help).toBeVisible();
  await expect(help.getByRole("heading", { level: 2 })).toHaveText("Resistor");
  await expect(help.getByTestId("block-help-ports")).toContainText("Electrical");
  await expect(help.getByTestId("block-help-params")).toContainText("Default");
  await page.keyboard.press("Escape");
  await expect(help).toBeHidden();

  // F1 does the same for the selected block.
  await page.getByTestId("diagram-node").first().click();
  await page.keyboard.press("F1");
  await expect(page.getByTestId("block-help")).toBeVisible();
});

test("Esc cancels a Ctrl-drag connection", async ({ page, request }) => {
  await storeRlc(request);
  await openEditor(page);
  const edgesBefore = await page.locator('[data-testid^="edge-"]').count();

  const nodes = page.getByTestId("diagram-node");
  const sourceBox = await nodes.nth(0).boundingBox();
  const targetBox = await nodes.nth(2).boundingBox();
  if (sourceBox === null || targetBox === null) throw new Error("the nodes are not visible");

  await page.keyboard.down("Control");
  await page.mouse.move(sourceBox.x + sourceBox.width / 2, sourceBox.y + sourceBox.height / 2);
  await page.mouse.down();
  await page.mouse.move(sourceBox.x + sourceBox.width / 2 + 24, sourceBox.y + 40, { steps: 4 });
  await expect(page.getByTestId("quick-connect-line")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("quick-connect-line")).toHaveCount(0);
  await page.mouse.move(targetBox.x + targetBox.width / 2, targetBox.y + targetBox.height / 2, { steps: 8 });
  await page.mouse.up();
  await page.keyboard.up("Control");

  await expect(page.locator('[data-testid^="edge-"]')).toHaveCount(edgesBefore);
});
