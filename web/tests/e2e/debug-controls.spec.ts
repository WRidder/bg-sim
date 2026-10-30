import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

/**
 * W4.1 acceptance (plan 7.9) against the fake worker's debug runs
 * (`backend/src/bgsim_server/fake_debug.py`):
 *
 * - open the drivetrain-kalman example and the `LQGController` source;
 * - set a gutter breakpoint on a statement line and on line 37 (`@discrete`, which
 *   is not a statement: E401, so the marker stays hollow with the message);
 * - start debugging, pause at the line (status text, highlighted line, tab title);
 * - step three statements (the highlight moves each time), remove the breakpoints
 *   and continue until the run is `done`.
 *
 * The fake worker serves the fixture catalog, which has no project blocks, so the
 * catalog answer is extended with `project:LQGController` (source read from the
 * example) for the Code tab. The fake finds the same source in the project's
 * library directory to verify the breakpoints.
 */

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const LQG_SOURCE = readFileSync(
  path.join(repoRoot, "examples", "drivetrain-kalman", "library", "LQGController.jl"),
  "utf8",
);

let project = "";

test.beforeEach(async ({ page, request }) => {
  project = `w41-debug-${Date.now()}-${test.info().workerIndex}`;
  const created = await request.post("/api/projects", {
    data: { name: project, example: "drivetrain-kalman" },
  });
  expect(created.status(), await created.text()).toBe(201);
  await page.setViewportSize({ width: 1700, height: 1000 });
  await page.route(/\/api\/catalog(\?|$)/, async (route) => {
    const response = await route.fetch();
    const catalog = (await response.json()) as { blocks: Record<string, unknown>[] };
    const template = catalog.blocks.find((block) => block.ref === "stdlib:continuous/PIController");
    if (template === undefined) {
      throw new Error("the fixture catalog has no PIController to clone");
    }
    catalog.blocks.push({
      ...template,
      ref: "project:LQGController",
      name: "LQGController",
      group: "Project",
      path: "library/LQGController.jl",
      source: LQG_SOURCE,
    });
    await route.fulfill({ response, json: catalog });
  });
});

test.afterEach(async ({ request }) => {
  if (project.length > 0) {
    await request.delete(`/api/projects/${project}`);
    project = "";
  }
});

async function openLqgSource(page: Page): Promise<void> {
  await page.goto(`/?project=${encodeURIComponent(project)}&model=drivetrain-kalman`);
  await expect(page.getByTestId("run-button")).toBeEnabled({ timeout: 30_000 });
  await page.getByRole("tab", { name: "Code" }).click();
  const select = page.getByTestId("code-source-select");
  await expect(select.locator('option[value="project:LQGController"]')).toHaveCount(1);
  await select.selectOption("project:LQGController");
  await expect(page.locator(".cm-content")).toContainText("@discrete");
}

/** Click the breakpoint gutter next to the editor line that contains `text`. */
async function clickGutter(
  page: Page,
  text: string,
  options: { button?: "left" | "right" } = {},
): Promise<void> {
  const line = page.locator(".cm-line", { hasText: text }).first();
  await line.scrollIntoViewIfNeeded();
  const lineBox = await line.boundingBox();
  const gutterBox = await page.locator(".cm-bp-gutter").boundingBox();
  expect(lineBox).not.toBeNull();
  expect(gutterBox).not.toBeNull();
  if (lineBox === null || gutterBox === null) {
    return;
  }
  await page.mouse.click(gutterBox.x + gutterBox.width / 2, lineBox.y + 9, {
    button: options.button ?? "left",
  });
}

function marker(page: Page, line: number) {
  return page.locator(`[data-testid="bp-marker"][data-line="${line}"]`);
}

function pausedLine(page: Page) {
  return page.locator(".cm-line.cm-paused-line");
}

const STATUS = (page: Page) => page.getByTestId("run-status");

test("sets a breakpoint, debugs, pauses at the line, steps 3 statements and runs to the end", async ({
  page,
}) => {
  await openLqgSource(page);

  // Line 41 is a statement (measurement update); line 37 is the @discrete header.
  await clickGutter(page, "measurement update");
  await clickGutter(page, "@discrete");
  await expect(marker(page, 41)).toHaveAttribute("data-state", "unverified");
  await expect(marker(page, 37)).toHaveAttribute("data-state", "unverified");

  await page.getByTestId("debug-button").click();

  // The pause: status text, the highlighted line, the tab title and the filled marker.
  await expect(STATUS(page)).toContainText("Paused at t = 0.0000 s: LQGController line 41 (LQG)", {
    timeout: 20_000,
  });
  await expect(STATUS(page)).toHaveAttribute("data-status", "paused");
  await expect(pausedLine(page)).toHaveCount(1);
  await expect(pausedLine(page)).toContainText("measurement update");
  await expect(page.getByRole("tab", { name: /Code · paused in LQG/ })).toBeVisible();
  await expect(marker(page, 41)).toHaveAttribute("data-state", "verified");

  // Line 37 is not a statement: hollow with the E401 message in its tooltip.
  await expect(marker(page, 37)).toHaveAttribute("data-state", "unverified");
  await expect(marker(page, 37)).toHaveAttribute("title", /E401/);
  await expect(marker(page, 37)).toHaveAttribute("title", /watch breakpoint/);

  // The controls: Continue and the steps are on while paused.
  await expect(page.getByTestId("debug-continue")).toBeEnabled();
  await expect(page.getByTestId("debug-pause")).toBeDisabled();
  await expect(page.getByTestId("debug-step-statement")).toHaveAttribute("title", "Step statement (F10)");

  // Step three statements (F10): the highlight moves each time.
  const expected: [number, string][] = [
    [42, "integral of the load-speed error"],
    [43, "Kff * w_ref"],
    [44, "for j in 1:nu"],
  ];
  for (const [line, text] of expected) {
    await page.keyboard.press("F10");
    await expect(STATUS(page)).toContainText(`LQGController line ${line} (LQG)`);
    await expect(pausedLine(page)).toHaveCount(1);
    await expect(pausedLine(page)).toContainText(text);
  }

  // Remove both breakpoints; the full (empty) set goes to the run. Then continue to the end.
  const put = page.waitForResponse(
    (response) => response.url().includes("/breakpoints") && response.request().method() === "PUT",
  );
  await clickGutter(page, "measurement update");
  await clickGutter(page, "@discrete");
  await put;
  await expect(page.locator('[data-testid="bp-marker"][data-state="verified"]')).toHaveCount(0);
  await expect(page.locator('[data-testid="bp-marker"][data-state="unverified"]')).toHaveCount(0);
  await page.waitForTimeout(300);

  await page.keyboard.press("F5");
  await expect(STATUS(page)).toHaveAttribute("data-status", "done", { timeout: 30_000 });
  await expect(page.getByTestId("debug-controls")).toHaveCount(0);
  await expect(pausedLine(page)).toHaveCount(0);
  await expect(page.getByRole("tab", { name: "Code", exact: true })).toBeVisible();
});

test("starts with F5, edits the hit count and the condition, persists across a reload, and stops", async ({
  page,
}) => {
  await openLqgSource(page);

  // F9 toggles on the caret line.
  await page.locator(".cm-line", { hasText: "measurement update" }).first().click();
  await page.keyboard.press("F9");
  await expect(marker(page, 41)).toHaveCount(1);

  // Right-click: a condition and a hit count.
  await clickGutter(page, "measurement update", { button: "right" });
  const popover = page.getByTestId("bp-popover");
  await expect(popover).toBeVisible();
  await page.getByTestId("bp-condition").fill("k >= 2");
  await page.getByTestId("bp-hit-count").fill("2");
  await page.getByTestId("bp-apply").click();
  await expect(popover).toHaveCount(0);
  await expect(marker(page, 41)).toHaveText("?");

  // The breakpoint survives a reload (localStorage, never the model).
  await page.reload();
  await expect(page.getByTestId("run-button")).toBeEnabled({ timeout: 30_000 });
  await page.getByRole("tab", { name: "Code" }).click();
  await page.getByTestId("code-source-select").selectOption("project:LQGController");
  await expect(marker(page, 41)).toHaveCount(1);
  await expect(marker(page, 41)).toHaveAttribute("title", /when k >= 2, hit 2/);

  // F5 starts the debug run; the 2nd hit with k >= 2 is tick 3.
  await page.keyboard.press("F5");
  await expect(STATUS(page)).toContainText("Paused at t = 0.0300 s: LQGController line 41 (LQG)", {
    timeout: 20_000,
  });
  await expect(marker(page, 41)).toHaveAttribute("data-state", "verified");

  // Shift+F5 stops the paused run.
  await page.keyboard.press("Shift+F5");
  await expect(STATUS(page)).toHaveAttribute("data-status", "cancelled", { timeout: 20_000 });
  await expect(page.getByTestId("debug-controls")).toHaveCount(0);
  await expect(pausedLine(page)).toHaveCount(0);
});
