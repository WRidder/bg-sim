import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

/**
 * W5.6 acceptance: the model Docs tab. Create a model's docs, add a page and a child page,
 * write inline and display math, paste an image (synthetic clipboard event), copy it and paste it
 * into a second model, switch View/Edit/Split, reload, check axe and follow a `block:` link.
 * Fake worker; the docs feature needs no Julia.
 *
 * Run with `$env:BGSIM_E2E_PORT="8783"; npx playwright test tests/e2e/docs.spec.ts`.
 */

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "../../..");

let project = "";

test.beforeEach(async ({ page, request }) => {
  await page.setViewportSize({ width: 1600, height: 1000 });
  project = `w56-docs-${Date.now()}-${test.info().workerIndex}`;
  expect((await request.post("/api/projects", { data: { name: project } })).status()).toBe(201);
  const model = readFileSync(
    path.join(repoRoot, "contracts", "fixtures", "model", "valid", "model.dcmotor.bondgraph.json"),
    "utf8",
  );
  for (const name of ["Alpha", "Beta"]) {
    const stored = await request.put(`/api/projects/${project}/models/${name}`, {
      data: JSON.parse(model),
    });
    expect(stored.status()).toBe(200);
  }
});

test.afterEach(async ({ request }) => {
  if (project.length > 0) {
    await request.delete(`/api/projects/${project}`);
  }
});

async function openDocs(page: Page, model: string): Promise<void> {
  await page.goto(`/?project=${encodeURIComponent(project)}&model=${model}`);
  await expect(page.getByTestId("library-item-DCMotor")).toBeVisible({ timeout: 30_000 });
  await page.getByRole("tab", { name: "Docs" }).click();
  await expect(page.getByTestId("docs-tab")).toHaveAttribute("data-status", "ready");
}

/** Type into the Markdown editor, replacing what is there. */
async function write(page: Page, text: string): Promise<void> {
  await page.locator(".cm-content").click();
  await page.keyboard.press("Control+a");
  await page.keyboard.insertText(text);
}

/** Paste a generated PNG as a synthetic clipboard event on the editor. */
async function pasteImage(page: Page, fill: string): Promise<void> {
  await page.evaluate(async (color) => {
    const canvas = document.createElement("canvas");
    canvas.width = 40;
    canvas.height = 30;
    const context = canvas.getContext("2d");
    if (context === null) throw new Error("no 2d context");
    context.fillStyle = color;
    context.fillRect(0, 0, 40, 30);
    const blob = await new Promise<Blob>((resolve) => canvas.toBlob((b) => resolve(b as Blob), "image/png"));
    const data = new DataTransfer();
    data.items.add(new File([blob], "screenshot.png", { type: "image/png" }));
    const target = document.querySelector(".cm-content");
    if (target === null) throw new Error("no editor");
    target.dispatchEvent(new ClipboardEvent("paste", { clipboardData: data, bubbles: true, cancelable: true }));
  }, fill);
}

async function imagesLoaded(page: Page, count: number): Promise<void> {
  await expect
    .poll(
      () =>
        page.locator('[data-testid="docs-preview"] img').evaluateAll(
          (images) => images.filter((i) => (i as HTMLImageElement).naturalWidth > 0).length,
        ),
      { timeout: 15_000 },
    )
    .toBe(count);
}

async function axeViolations(page: Page): Promise<string[]> {
  const result = await new AxeBuilder({ page }).analyze();
  return result.violations.map(
    (v) => `${v.id} (${v.impact}): ${v.help}; ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`,
  );
}

test("a model without docs shows an empty tree and creates the first page", async ({ page }) => {
  await openDocs(page, "Alpha");
  await expect(page.getByTestId("docs-empty")).toBeVisible();
  await page.getByTestId("docs-create-first").click();
  await expect(page.getByRole("treeitem", { name: /Overview/ })).toBeVisible();
  await expect(page.getByTestId("docs-tree-item-overview")).toHaveAttribute("aria-selected", "true");
});

test("pages, math, images, modes, reload, a second model, axe and block links", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await openDocs(page, "Alpha");

  // First page, then a child page that is renamed with the toolbar.
  await page.getByTestId("docs-create-first").click();
  await page.getByTestId("docs-new-child").click();
  await expect(page.getByTestId("docs-tree-item-new-page")).toHaveAttribute("aria-level", "2");
  await page.getByTestId("docs-rename").click();
  await page.getByLabel("Page title").fill("Plant model");
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("docs-tree-item-new-page")).toContainText("Plant model");

  // Overview: Edit mode with inline and display math, a block link, a broken link and a table.
  await page.getByTestId("docs-tree-item-overview").click();
  await page.getByTestId("docs-mode-edit").click();
  await write(
    page,
    [
      "# Overview",
      "",
      "The energy is $E = m c^2$ and the integral is",
      "",
      "$$\\int_0^1 x\\,dx = \\tfrac12$$",
      "",
      "See [the motor](page:new-page), [Se1](block:Se1) and [gone](page:ghost).",
      "",
      "| a | b |",
      "|---|---|",
      "| 1 | 2 |",
      "",
    ].join("\n"),
  );
  await expect(page.getByTestId("docs-save-status")).toHaveAttribute("data-state", "dirty");
  await expect(page.getByTestId("docs-tree-item-overview")).toHaveAttribute("data-dirty", "true");

  // Split shows the live preview next to the editor.
  await page.getByTestId("docs-mode-split").click();
  await expect(page.locator(".cm-content")).toBeVisible();
  await expect(page.getByTestId("docs-preview").locator(".katex")).toHaveCount(2);
  await expect(page.getByTestId("docs-preview").locator(".katex-display")).toHaveCount(1);
  await expect(page.getByTestId("docs-preview").locator("table")).toHaveCount(1);
  await expect(page.getByTestId("docs-broken-link")).toHaveAttribute("title", /no page "ghost"/);

  // Ctrl+S saves; Ctrl+E toggles View and Edit.
  await page.keyboard.press("Control+s");
  await expect(page.getByTestId("docs-save-status")).toHaveAttribute("data-state", "saved");
  await page.getByTestId("docs-mode-view").click();
  await expect(page.locator(".cm-content")).toHaveCount(0);
  await page.getByTestId("docs-preview").focus();
  await page.keyboard.press("Control+e");
  await expect(page.getByTestId("docs-body")).toHaveAttribute("data-mode", "edit");
  await page.keyboard.press("Control+e");
  await expect(page.getByTestId("docs-body")).toHaveAttribute("data-mode", "view");

  // Paste an image in the editor: uploaded to assets/, inserted at the cursor, shown in the preview.
  await page.getByTestId("docs-mode-split").click();
  await page.locator(".cm-content").click();
  await page.keyboard.press("Control+End");
  const uploads = page.waitForResponse(
    (r) => r.url().includes("/docs/Alpha/assets") && r.request().method() === "POST",
  );
  await pasteImage(page, "#d22");
  expect((await uploads).status()).toBe(201);
  await expect(page.locator(".cm-content")).toContainText("![](assets/");
  await imagesLoaded(page, 1);
  // The same image pasted again is stored once (content hash) and shown twice.
  await pasteImage(page, "#d22");
  await imagesLoaded(page, 2);
  const listing = await page.request.get(`/api/projects/${project}/docs/Alpha/assets`);
  expect(((await listing.json()) as { assets: unknown[] }).assets).toHaveLength(1);
  await page.keyboard.press("Control+s");
  await expect(page.getByTestId("docs-save-status")).toHaveAttribute("data-state", "saved");

  // Copy the rendered image: image/png and its Markdown go on the clipboard.
  await page.getByTestId("docs-preview").locator(".docs-image").first().hover();
  await page.getByRole("button", { name: "Copy image" }).first().click();
  await expect(page.getByTestId("docs-notice")).toContainText("Image copied");
  const types = await page.evaluate(async () => {
    const items = await navigator.clipboard.read();
    return items.flatMap((item) => [...item.types]);
  });
  expect(types).toContain("image/png");
  expect(types).toContain("text/plain");

  // Second model: paste the copied picture into a page of Beta.
  await openDocs(page, "Beta");
  await page.getByTestId("docs-create-first").click();
  await page.getByTestId("docs-mode-split").click();
  await page.locator(".cm-content").click();
  await page.keyboard.press("Control+v");
  await expect(page.locator(".cm-content")).toContainText("![](assets/");
  await imagesLoaded(page, 1);
  await page.keyboard.press("Control+s");
  await expect(page.getByTestId("docs-save-status")).toHaveAttribute("data-state", "saved");
  const betaAssets = await page.request.get(`/api/projects/${project}/docs/Beta/assets`);
  expect(((await betaAssets.json()) as { assets: unknown[] }).assets).toHaveLength(1);

  // Reload Alpha: tree, text and image are persisted next to the model file.
  await openDocs(page, "Alpha");
  await expect(page.getByTestId("docs-tree-item-overview")).toBeVisible();
  await expect(page.getByTestId("docs-tree-item-new-page")).toContainText("Plant model");
  await page.getByTestId("docs-mode-view").click();
  await expect(page.getByTestId("docs-preview").locator(".katex")).toHaveCount(2);
  await imagesLoaded(page, 2);

  // Axe: no violation on the Docs tab (view and split).
  expect(await axeViolations(page)).toEqual([]);
  await page.getByTestId("docs-mode-split").click();
  await expect(page.locator(".cm-content")).toBeVisible();
  expect(await axeViolations(page)).toEqual([]);
  await page.evaluate(() => document.documentElement.setAttribute("data-theme", "dark"));
  expect(await axeViolations(page)).toEqual([]);
  await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));

  // A block link switches to the Diagram tab and selects the node.
  await page.getByTestId("docs-mode-view").click();
  await page.getByRole("link", { name: "Se1" }).click();
  await expect(page.getByRole("tab", { name: "Diagram" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByTestId("tree-node-Se1")).toHaveAttribute("aria-current", "true");
});

test("copying Markdown with images between models brings the images along", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await openDocs(page, "Alpha");
  await page.getByTestId("docs-create-first").click();
  await page.getByTestId("docs-mode-split").click();
  await page.locator(".cm-content").click();
  await pasteImage(page, "#28c");
  await imagesLoaded(page, 1);
  await page.keyboard.press("Control+s");
  await expect(page.getByTestId("docs-save-status")).toHaveAttribute("data-state", "saved");

  // Copy the Markdown text (not the picture) of the page.
  await page.locator(".cm-content").click();
  await page.keyboard.press("Control+a");
  await page.keyboard.press("Control+c");

  await openDocs(page, "Beta");
  await page.getByTestId("docs-create-first").click();
  await page.getByTestId("docs-mode-split").click();
  const copied = page.waitForResponse((r) => r.url().includes("/docs/Beta/assets/copy"));
  await page.locator(".cm-content").click();
  await page.keyboard.press("Control+v");
  expect((await copied).status()).toBe(200);
  await imagesLoaded(page, 1);
});

test("unused images stay on disk while editing, are counted, and Clean up removes them", async ({ page }) => {
  await openDocs(page, "Alpha");
  await page.getByTestId("docs-create-first").click();
  await page.getByTestId("docs-mode-edit").click();
  await page.locator(".cm-content").click();
  await pasteImage(page, "#4a4");
  await expect(page.locator(".cm-content")).toContainText("![](assets/");
  await page.keyboard.press("Control+s");
  await expect(page.getByTestId("docs-save-status")).toHaveAttribute("data-state", "saved");

  // Remove the reference: the file stays (undo must keep working) and is reported as unused.
  await write(page, "no picture any more");
  await page.keyboard.press("Control+s");
  await expect(page.getByTestId("docs-unused-count")).toHaveText("1 unused image");
  const before = await page.request.get(`/api/projects/${project}/docs/Alpha/assets`);
  expect(((await before.json()) as { assets: unknown[] }).assets).toHaveLength(1);

  await page.getByTestId("docs-cleanup").click();
  await expect(page.getByTestId("docs-notice")).toContainText("Removed 1 unused image");
  await expect(page.getByTestId("docs-unused")).toHaveCount(0);
  const after = await page.request.get(`/api/projects/${project}/docs/Alpha/assets`);
  expect(((await after.json()) as { assets: unknown[] }).assets).toHaveLength(0);
});

test("an image over the size limit is refused with a diagnostic", async ({ page }) => {
  await openDocs(page, "Alpha");
  await page.getByTestId("docs-create-first").click();
  await page.getByTestId("docs-mode-edit").click();
  await page.locator(".cm-content").click();
  await page.evaluate(() => {
    const data = new DataTransfer();
    data.items.add(new File([new Uint8Array(11 * 1024 * 1024)], "huge.png", { type: "image/png" }));
    document
      .querySelector(".cm-content")
      ?.dispatchEvent(new ClipboardEvent("paste", { clipboardData: data, bubbles: true, cancelable: true }));
  });
  await expect(page.getByTestId("docs-problem")).toContainText("the limit is 10 MB");
  await expect(page.locator(".cm-content")).not.toContainText("![](assets/");
});

test("tree: keyboard reorder, delete with children, and unsaved changes block leaving", async ({ page }) => {
  await openDocs(page, "Alpha");
  await page.getByTestId("docs-create-first").click();
  await page.getByTestId("docs-new-page").click();
  await page.getByTestId("docs-new-page").click();
  const ids = async (): Promise<string[]> =>
    page.getByRole("treeitem").evaluateAll((items) => items.map((i) => i.getAttribute("data-page-id") ?? ""));
  expect(await ids()).toEqual(["overview", "new-page", "new-page-2"]);

  // Alt+Up moves the focused page up; Alt+Right indents it under its previous sibling.
  await page.getByTestId("docs-tree-item-new-page-2").focus();
  await page.keyboard.press("Alt+ArrowUp");
  await expect.poll(ids).toEqual(["overview", "new-page-2", "new-page"]);
  await page.keyboard.press("Alt+ArrowRight");
  await expect(page.getByTestId("docs-tree-item-new-page-2")).toHaveAttribute("aria-level", "2");
  await expect(page.getByTestId("docs-tree-item-new-page")).toHaveAttribute("aria-level", "1");

  // The order survives a reload.
  await openDocs(page, "Alpha");
  await expect.poll(ids).toEqual(["overview", "new-page-2", "new-page"]);

  // Deleting a page with children asks what to do with them.
  await page.getByTestId("docs-tree-item-overview").click();
  await page.getByTestId("docs-delete").click();
  await expect(page.getByTestId("docs-delete-dialog")).toContainText("1 sub-page");
  await page.getByTestId("docs-delete-promote").click();
  await expect.poll(ids).toEqual(["new-page-2", "new-page"]);
  await expect(page.getByTestId("docs-tree-item-new-page-2")).toHaveAttribute("aria-level", "1");

  // Leaving the Docs tab with unsaved edits asks; Cancel keeps the page open.
  await page.getByTestId("docs-tree-item-new-page").click();
  await page.getByTestId("docs-mode-edit").click();
  await write(page, "unsaved words");
  page.once("dialog", (dialog) => void dialog.dismiss());
  await page.getByRole("tab", { name: "Diagram" }).click();
  await expect(page.getByRole("tab", { name: "Docs" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByTestId("docs-save-status")).toHaveAttribute("data-state", "dirty");
  page.once("dialog", (dialog) => void dialog.accept());
  await page.getByRole("tab", { name: "Diagram" }).click();
  await expect(page.getByRole("tab", { name: "Diagram" })).toHaveAttribute("aria-selected", "true");
  const saved = await page.request.get(`/api/projects/${project}/docs/Alpha/pages/new-page`);
  expect(await saved.text()).toBe("unsaved words");
});
