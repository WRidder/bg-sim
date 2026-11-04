import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { expandLibrary } from "./library";

/**
 * Sticky notes on the diagram canvas (`diagram.annotations`):
 *
 * 1. "Add note" in the canvas menu adds a note at the cursor and opens its
 *    text editor; Markdown (bold, a list) renders after a click outside;
 * 2. the note sits behind blocks; its menu recolours it; it drags;
 * 3. Delete removes it, Ctrl+Z brings it back, and it survives a reload;
 * 4. N adds a note at the pointer, Esc ends the edit;
 * 5. long text scrolls inside the note: the wheel scrolls it, not the canvas.
 *
 * Screenshots of every colour in both themes go to BGSIM_NOTE_SHOTS when set.
 */

let project = "";

test.beforeEach(async ({ page }) => {
  project = `w-sticky-notes-${Date.now()}-${test.info().workerIndex}`;
  await page.setViewportSize({ width: 1600, height: 1000 });
});

test.afterEach(async ({ request }) => {
  if (project.length > 0) {
    await request.delete(`/api/projects/${project}`);
  }
});

async function openModel(page: Page): Promise<void> {
  await page.goto(`/?project=${encodeURIComponent(project)}&model=Notes`);
  await expandLibrary(page);
  await expect(page.getByTestId("library-item-Se")).toBeVisible();
  await expect(page.getByTestId("canvas-surface")).toBeVisible();
}

async function canvasPoint(page: Page, x: number, y: number): Promise<{ x: number; y: number }> {
  const box = await page.getByTestId("canvas-surface").boundingBox();
  if (box === null) {
    throw new Error("the canvas is not visible");
  }
  return { x: box.x + x, y: box.y + y };
}

async function addNoteByMenu(page: Page, x: number, y: number): Promise<void> {
  const point = await canvasPoint(page, x, y);
  await page.mouse.click(point.x, point.y, { button: "right" });
  await expect(page.getByTestId("canvas-menu")).toBeVisible();
  await page.getByTestId("add-note").click();
}

async function waitSaved(page: Page): Promise<void> {
  await expect(page.getByTestId("save-status")).toHaveAttribute("data-state", "saved", {
    timeout: 15_000,
  });
}

const notes = (page: Page) => page.getByTestId("sticky-note");

test("add, edit, recolour, move, delete, undo and reload a note", async ({ page }) => {
  await openModel(page);
  await addNoteByMenu(page, 160, 160);
  await expect(notes(page)).toHaveCount(1);
  const editor = page.getByTestId("sticky-note-editor");
  await expect(editor).toBeFocused();
  await page.keyboard.type("**bold** start");
  await page.keyboard.press("Enter");
  await page.keyboard.press("Enter");
  await page.keyboard.type("- one");
  await page.keyboard.press("Enter");
  await page.keyboard.type("- two");

  // A click on the empty canvas ends the edit and shows the rendered Markdown.
  const empty = await canvasPoint(page, 900, 600);
  await page.mouse.click(empty.x, empty.y);
  await expect(editor).toHaveCount(0);
  const note = notes(page).first();
  await expect(note.locator("strong")).toHaveText("bold");
  await expect(note.locator("li")).toHaveText(["one", "two"]);
  await expect(note).toHaveAttribute("data-color", "yellow");

  // A block dropped onto the note sits in front of it.
  const noteBox = await note.boundingBox();
  if (noteBox === null) {
    throw new Error("the note is not visible");
  }
  const surface = await page.getByTestId("canvas-surface").boundingBox();
  if (surface === null) {
    throw new Error("the canvas is not visible");
  }
  const item = page.getByTestId("library-item-Se").first();
  await item.scrollIntoViewIfNeeded();
  await item.dragTo(page.getByTestId("canvas-surface"), {
    targetPosition: {
      x: noteBox.x - surface.x + noteBox.width / 2,
      y: noteBox.y - surface.y + noteBox.height - 30,
    },
  });
  const block = page.locator('[data-testid="diagram-node"]').first();
  await expect(block).toBeVisible();
  const blockBox = await block.boundingBox();
  if (blockBox === null) {
    throw new Error("the block is not visible");
  }
  const onTop = await page.evaluate(
    ({ x, y }) => document.elementFromPoint(x, y)?.closest(".react-flow__node")?.getAttribute("data-id") ?? null,
    { x: blockBox.x + blockBox.width / 2, y: blockBox.y + blockBox.height / 2 },
  );
  expect(onTop).not.toBeNull();
  expect(onTop?.startsWith("note:")).toBe(false);

  // The note's menu recolours it.
  await note.locator("strong").click({ button: "right" });
  await page.getByTestId("note-color-blue").click();
  await expect(note).toHaveAttribute("data-color", "blue");

  // Drag it by its text.
  const before = await note.boundingBox();
  if (before === null) {
    throw new Error("the note is not visible");
  }
  await page.mouse.move(before.x + 30, before.y + 14);
  await page.mouse.down();
  await page.mouse.move(before.x + 80, before.y + 40, { steps: 6 });
  await page.mouse.move(before.x + 130, before.y + 74, { steps: 6 });
  await page.mouse.up();
  const after = await note.boundingBox();
  expect(after?.x ?? 0).toBeGreaterThan(before.x + 60);
  expect(after?.y ?? 0).toBeGreaterThan(before.y + 30);

  // The inspector shows the selected note.
  await expect(page.getByTestId("note-inspector")).toBeVisible();
  await expect(page.getByTestId("note-inspector-color-blue")).toHaveAttribute("aria-checked", "true");

  // Delete, then undo.
  await page.keyboard.press("Delete");
  await expect(notes(page)).toHaveCount(0);
  await page.keyboard.press("Control+z");
  await expect(notes(page)).toHaveCount(1);
  await expect(notes(page).first()).toHaveAttribute("data-color", "blue");
  await expect(notes(page).first().locator("strong")).toHaveText("bold");

  // Persisted: the reload shows the same note.
  await waitSaved(page);
  await page.reload();
  // The expanded library categories persist across the reload.
  await expect(page.getByTestId("library-item-Se")).toBeVisible({ timeout: 30_000 });
  await expect(notes(page)).toHaveCount(1);
  await expect(notes(page).first()).toHaveAttribute("data-color", "blue");
  await expect(notes(page).first().locator("strong")).toHaveText("bold");
  await expect(notes(page).first().locator("li")).toHaveCount(2);
  const saved = await page.request.get(
    `/api/projects/${encodeURIComponent(project)}/models/Notes`,
  );
  const stored = (await saved.json()) as {
    diagram: { annotations?: { kind: string; text: string; color?: string }[] };
  };
  expect(stored.diagram.annotations).toHaveLength(1);
  expect(stored.diagram.annotations?.[0]).toMatchObject({
    kind: "text",
    text: "**bold** start\n\n- one\n- two",
    color: "blue",
  });
});

test("N adds a note at the pointer; Esc ends the edit; one edit is one undo step", async ({ page }) => {
  await openModel(page);
  const point = await canvasPoint(page, 400, 300);
  await page.mouse.move(point.x, point.y);
  await page.keyboard.press("n");
  await expect(notes(page)).toHaveCount(1);
  const box = await notes(page).first().boundingBox();
  expect(Math.abs((box?.x ?? 0) - point.x)).toBeLessThan(30);
  expect(Math.abs((box?.y ?? 0) - point.y)).toBeLessThan(30);
  const editor = page.getByTestId("sticky-note-editor");
  await expect(editor).toBeFocused();
  await page.keyboard.type("first words");
  await page.keyboard.press("Escape");
  await expect(editor).toHaveCount(0);
  await expect(notes(page).first()).toContainText("first words");

  // A second session (double-click) is a second undo step; R and Del type text.
  // The double-click edits the note and does not zoom the canvas.
  const viewport = page.locator(".react-flow__viewport");
  const zoomBefore = await viewport.getAttribute("style");
  await notes(page).first().dblclick();
  expect(await viewport.getAttribute("style")).toBe(zoomBefore);
  await expect(editor).toBeFocused();
  await page.keyboard.press("End");
  await page.keyboard.type(" R Del");
  await page.keyboard.press("Escape");
  await expect(notes(page).first()).toContainText("first words R Del");
  await page.getByTestId("undo").click();
  await expect(notes(page).first()).toContainText("first words");
  await expect(notes(page).first()).not.toContainText("R Del");
  await page.getByTestId("undo").click();
  await expect(notes(page).first()).not.toContainText("first words");
  await page.getByTestId("undo").click();
  await expect(notes(page)).toHaveCount(0);
});

test("a selected note resizes from its corner in one undo step", async ({ page }) => {
  await openModel(page);
  await addNoteByMenu(page, 200, 200);
  await page.keyboard.press("Escape");
  const note = notes(page).first();
  await note.click({ position: { x: 40, y: 40 } });
  await expect(note).toHaveClass(/is-selected/);
  const before = await note.boundingBox();
  const handle = note.locator(".react-flow__resize-control.handle.bottom.right");
  const box = await handle.boundingBox();
  if (before === null || box === null) {
    throw new Error("the note or its handle is not visible");
  }
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + 40, box.y + 30, { steps: 5 });
  await page.mouse.move(box.x + 90, box.y + 60, { steps: 5 });
  await page.mouse.up();
  // xyflow sizes the node's wrapper at once and the note from its measured size one
  // ResizeObserver tick later, before the paint, so these reads retry instead of racing it.
  const width = async () => (await note.boundingBox())?.width ?? 0;
  const height = async () => (await note.boundingBox())?.height ?? 0;
  await expect.poll(width).toBeGreaterThan(before.width + 60);
  await expect.poll(height).toBeGreaterThan(before.height + 40);
  const after = await note.boundingBox();
  expect(Math.abs((after?.x ?? 0) - before.x)).toBeLessThan(2);
  await page.getByTestId("undo").click();
  await expect.poll(async () => Math.abs((await width()) - before.width)).toBeLessThan(2);
  await expect.poll(async () => Math.abs((await height()) - before.height)).toBeLessThan(2);
  // One step: the next undo takes back the note itself, not more of the resize.
  await page.getByTestId("undo").click();
  await expect(notes(page)).toHaveCount(0);
});

test("the wheel scrolls a long note instead of zooming the canvas", async ({ page }) => {
  await openModel(page);
  await addNoteByMenu(page, 200, 200);
  const editor = page.getByTestId("sticky-note-editor");
  await editor.fill(Array.from({ length: 40 }, (_, i) => `- line ${i + 1}`).join("\n"));
  await page.keyboard.press("Escape");
  const content = notes(page).first().getByTestId("sticky-note-content");
  await expect(content).toHaveAttribute("data-scrollable", "true");
  const viewport = page.locator(".react-flow__viewport");
  const before = await viewport.getAttribute("style");
  const box = await content.boundingBox();
  if (box === null) {
    throw new Error("the note is not visible");
  }
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.wheel(0, 300);
  await expect.poll(() => content.evaluate((element) => element.scrollTop)).toBeGreaterThan(50);
  expect(await viewport.getAttribute("style")).toBe(before);
});

test("note colours in both themes", async ({ page }) => {
  const shots = process.env.BGSIM_NOTE_SHOTS;
  await openModel(page);
  const texts = [
    "# Yellow note\n**Bold**, *italic* and `code`.\n\n- a list\n- of items",
    "## Blue\nThe motor current is $i = u / R$.",
    "### Green\n1. first\n2. second",
    "Pink: see [the docs](page:overview).",
    "Grey note\n\n> a quote",
  ];
  const colours = ["yellow", "blue", "green", "pink", "grey"] as const;
  for (const [index, colour] of colours.entries()) {
    await addNoteByMenu(page, 16 + index * 180, 90);
    await page.getByTestId("sticky-note-editor").fill(texts[index] ?? "");
    await page.keyboard.press("Escape");
    const note = notes(page).nth(index);
    if (colour !== "yellow") {
      await note.click({ button: "right", position: { x: 40, y: 40 } });
      await page.getByTestId(`note-color-${colour}`).click();
    }
    await expect(note).toHaveAttribute("data-color", colour);
  }
  // Headings render as bold text, not as headings.
  await expect(notes(page).locator("h1, h2, h3")).toHaveCount(0);
  await expect(notes(page).first().locator(".note-markdown__heading strong")).toHaveText("Yellow note");
  // A block in front of a note.
  const item = page.getByTestId("library-item-Se").first();
  await item.dragTo(page.getByTestId("canvas-surface"), { targetPosition: { x: 820, y: 200 } });
  const empty = await canvasPoint(page, 600, 600);
  await page.mouse.click(empty.x, empty.y);
  // The blue note selected: its outline and resize handles.
  await notes(page).nth(1).click({ position: { x: 60, y: 120 } });
  await expect(notes(page).nth(1)).toHaveClass(/is-selected/);

  for (const theme of ["dark", "light"] as const) {
    await page.evaluate((value) => document.documentElement.setAttribute("data-theme", value), theme);
    const surface = await page.getByTestId("canvas-surface").boundingBox();
    if (shots !== undefined && surface !== null) {
      await page.screenshot({
        path: `${shots}/sticky-${theme}.png`,
        clip: { x: surface.x, y: surface.y, width: Math.min(surface.width, 1220), height: 420 },
      });
    }
    // Text contrast: the note text differs clearly from the card in this theme.
    const colours = await notes(page).first().evaluate((element) => {
      const style = getComputedStyle(element);
      const paper = element.querySelector(".sticky-note__paper");
      return { text: style.color, bg: paper === null ? "" : getComputedStyle(paper).backgroundColor };
    });
    expect(colours.text).not.toBe(colours.bg);
    // axe: the note text meets the contrast ratio on every card, in this theme.
    const result = await new AxeBuilder({ page }).include('[data-testid="sticky-note"]').analyze();
    expect(result.violations.map((violation) => violation.id)).toEqual([]);
  }
});
