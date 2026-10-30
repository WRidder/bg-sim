import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

/**
 * Canvas selection regressions, fake worker:
 *
 * 1. inside a subsystem a click on an element shows it in the inspector, and
 *    an edit there lands on the nested node;
 * 2. a box selection leaves no rectangle behind after mouse up, and the
 *    selected nodes still drag as one;
 * 3. a click selects on the first try: with a 1-3 px pointer jitter, right
 *    after a box selection and after Ctrl-clicks.
 *
 * Run with `$env:BGSIM_E2E_PORT="8793"; npx playwright test tests/e2e/selection.spec.ts`.
 */

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "../../..");

let project = "";

test.beforeEach(async ({ page }) => {
  project = `selection-${Date.now()}-${test.info().workerIndex}`;
  await page.setViewportSize({ width: 1600, height: 1000 });
  expect((await page.request.post("/api/projects", { data: { name: project } })).status()).toBe(
    201,
  );
  const model: unknown = JSON.parse(
    readFileSync(
      path.join(repoRoot, "examples", "rlc-dual", "models", "rlc-dual.bgmodel.json"),
      "utf8",
    ),
  );
  expect(
    (await page.request.put(`/api/projects/${project}/models/Dual`, { data: model })).status(),
  ).toBe(200);
});

test.afterEach(async ({ request }) => {
  await request.delete(`/api/projects/${project}`);
});

function node(page: Page, name: string) {
  return page.locator(`[data-testid="diagram-node"][data-node-name="${name}"]`);
}

interface StoredNode {
  id: string;
  name: string;
  params?: Record<string, string>;
  position: { x: number; y: number };
  block: { subsystem?: { diagram: { nodes: StoredNode[] } } };
}

async function readDocument(page: Page): Promise<{ diagram: { nodes: StoredNode[] } }> {
  const text = await page.getByTestId("document-json").textContent();
  return JSON.parse(text ?? "null") as { diagram: { nodes: StoredNode[] } };
}

async function openDual(page: Page): Promise<void> {
  await page.goto(`/?project=${project}&model=Dual`);
  await expect(page.getByTestId("diagram-node")).toHaveCount(2, { timeout: 30_000 });
}

async function enterIconic(page: Page): Promise<void> {
  await node(page, "Iconic").click({ position: { x: 8, y: 8 } });
  await expect(node(page, "Iconic")).toHaveClass(/is-selected/);
  await node(page, "Iconic").dblclick({ position: { x: 8, y: 8 } });
  await expect(page.getByTestId("breadcrumb-1")).toHaveAttribute(
    "data-breadcrumb-name",
    "Iconic",
  );
  await expect(page.getByTestId("diagram-node")).toHaveCount(6);
}

/** The centre of a node's header, where a click hits the node and no port. */
async function headerPoint(page: Page, name: string): Promise<{ x: number; y: number }> {
  const box = await node(page, name).boundingBox();
  if (box === null) {
    throw new Error(`${name} is not visible`);
  }
  return { x: box.x + box.width / 2, y: box.y + 10 };
}

/** A press and release with the pointer moved by `jitter` px in between. */
async function jitterClick(
  page: Page,
  name: string,
  jitter: number,
  modifiers: ("Control" | "Shift")[] = [],
): Promise<void> {
  const { x, y } = await headerPoint(page, name);
  for (const key of modifiers) {
    await page.keyboard.down(key);
  }
  await page.mouse.move(x, y);
  await page.mouse.down();
  if (jitter > 0) {
    await page.mouse.move(x + jitter, y);
  }
  await page.mouse.up();
  for (const key of modifiers) {
    await page.keyboard.up(key);
  }
}

/** A click on empty canvas, well below the Step1 source. */
async function clickEmpty(page: Page): Promise<void> {
  const box = await node(page, "Step1").boundingBox();
  if (box === null) {
    throw new Error("Step1 is not visible");
  }
  await page.mouse.click(box.x + 10, box.y + box.height + 160);
}

/**
 * A left drag on empty canvas from below-left of R1 up into the middle of L1:
 * the rectangle touches R1 and L1 and nothing else. It stays clear of the
 * canvas edges, where xyflow auto-pans during a selection.
 */
async function boxSelectR1L1(page: Page, steps = 12): Promise<void> {
  const r1 = await node(page, "R1").boundingBox();
  const l1 = await node(page, "L1").boundingBox();
  if (r1 === null || l1 === null) {
    throw new Error("the blocks are not visible");
  }
  await page.mouse.move(r1.x - 20, r1.y + r1.height + 30);
  await page.mouse.down();
  await page.mouse.move(l1.x + l1.width / 2, l1.y + l1.height / 2, { steps });
  await page.mouse.up();
}

test("inside a subsystem a click shows the element in the inspector and edits it there", async ({
  page,
}) => {
  await openDual(page);
  await enterIconic(page);

  await node(page, "R1").click({ position: { x: 20, y: 10 } });
  await expect(node(page, "R1")).toHaveClass(/is-selected/);
  await expect(page.getByTestId("inspector-node")).toBeVisible();
  await expect(page.getByTestId("inspector-name")).toHaveValue("R1");
  const r = page.getByTestId("inspector-param-R");
  await expect(r).toHaveValue("10.0");
  await r.fill("22.0");
  await r.press("Enter");
  await expect(r).toHaveValue("22.0");

  const doc = await readDocument(page);
  const iconic = doc.diagram.nodes.find((entry) => entry.id === "iconic");
  const nested = iconic?.block.subsystem?.diagram.nodes.find((entry) => entry.id === "i3");
  expect(nested?.params?.R).toBe("22.0");
  // The other subsystem's R1 is untouched.
  const bondgraph = doc.diagram.nodes.find((entry) => entry.id === "bondgraph");
  const other = bondgraph?.block.subsystem?.diagram.nodes.find((entry) => entry.id === "b3");
  expect(other?.params?.r).toBe("10.0");

  // Two selected nested elements give the multiple-selection summary.
  await node(page, "C1").click({ position: { x: 20, y: 10 }, modifiers: ["Control"] });
  await expect(page.getByTestId("inspector-multi")).toBeVisible();
  await expect(page.getByTestId("inspector-multi-R1")).toBeVisible();
  await expect(page.getByTestId("inspector-multi-C1")).toBeVisible();

  // A nested connection shows the connection inspector.
  await clickEmpty(page);
  const mid = await page
    .locator('[data-testid="rf__edge-ic3"] path.react-flow__edge-interaction')
    .evaluate((element) => {
      const path = element as SVGPathElement;
      const point = path.getPointAtLength(path.getTotalLength() / 2);
      const matrix = path.getScreenCTM();
      if (matrix === null) {
        throw new Error("the bond has no screen transform");
      }
      const screen = point.matrixTransform(matrix);
      return { x: screen.x, y: screen.y };
    });
  await page.mouse.click(mid.x, mid.y);
  await expect(page.getByTestId("inspector-connection-summary-ic3")).toBeVisible();
});

test("a box selection leaves no rectangle after mouse up and drags as one", async ({ page }) => {
  await openDual(page);
  await enterIconic(page);

  await boxSelectR1L1(page);
  await expect(node(page, "R1")).toHaveClass(/is-selected/);
  await expect(node(page, "L1")).toHaveClass(/is-selected/);
  await expect(node(page, "C1")).not.toHaveClass(/is-selected/);
  await expect(page.getByTestId("inspector-multi")).toBeVisible();
  // Neither the drawn rectangle nor xyflow's persistent selection box stays.
  await expect(page.locator(".react-flow__selection")).toHaveCount(0);
  await expect(page.locator(".react-flow__nodesselection-rect")).toHaveCount(0);

  // Dragging one of the selected nodes moves both.
  const before = await readDocument(page);
  const start = await headerPoint(page, "R1");
  await page.mouse.move(start.x, start.y);
  await page.mouse.down();
  await page.mouse.move(start.x + 60, start.y + 40, { steps: 6 });
  await page.mouse.up();
  const after = await readDocument(page);
  const nested = (doc: typeof before, id: string) =>
    doc.diagram.nodes
      .find((entry) => entry.id === "iconic")
      ?.block.subsystem?.diagram.nodes.find((entry) => entry.id === id);
  const moved = (id: string) => {
    const a = nested(after, id)?.position;
    const b = nested(before, id)?.position;
    return a !== undefined && b !== undefined && (a.x !== b.x || a.y !== b.y);
  };
  expect(moved("i3")).toBe(true);
  expect(moved("i4")).toBe(true);
  expect(moved("i5")).toBe(false);
  await expect(page.getByTestId("inspector-multi")).toBeVisible();
});

/** Exactly `names` carry the selected class, and the inspector agrees. */
async function expectSelected(page: Page, names: readonly string[]): Promise<void> {
  await expect(page.locator('[data-testid="diagram-node"].is-selected')).toHaveCount(names.length);
  for (const name of names) {
    await expect(node(page, name)).toHaveClass(/is-selected/);
  }
  if (names.length === 1) {
    await expect(page.getByTestId("inspector-name")).toHaveValue(names[0] ?? "");
  } else if (names.length > 1) {
    for (const name of names) {
      await expect(page.getByTestId(`inspector-multi-${name}`)).toBeVisible();
    }
    await expect(page.locator('[data-testid^="inspector-multi-"]')).toHaveCount(names.length);
  }
}

test("a click selects on the first try with 0-3 px of pointer jitter", async ({ page }) => {
  await openDual(page);
  await enterIconic(page);
  const targets = ["R1", "L1", "C1", "V1", "Step1", "R1", "C1", "L1"];
  for (const [index, name] of targets.entries()) {
    await jitterClick(page, name, index % 4);
    await expectSelected(page, [name]);
  }
});

test("a click right after a box selection selects that node", async ({ page }) => {
  await openDual(page);
  await enterIconic(page);

  // A node inside the box.
  await boxSelectR1L1(page);
  await expectSelected(page, ["R1", "L1"]);
  await jitterClick(page, "L1", 0);
  await expectSelected(page, ["L1"]);

  // A node outside the box, with a little jitter.
  await boxSelectR1L1(page);
  await expectSelected(page, ["R1", "L1"]);
  await jitterClick(page, "C1", 1);
  await expectSelected(page, ["C1"]);

  // Ctrl-click after a box adds to it.
  await boxSelectR1L1(page);
  await expectSelected(page, ["R1", "L1"]);
  await jitterClick(page, "V1", 0, ["Control"]);
  await expectSelected(page, ["R1", "L1", "V1"]);

  // An empty box clears.
  const step1 = await node(page, "Step1").boundingBox();
  if (step1 === null) {
    throw new Error("Step1 is not visible");
  }
  await page.mouse.move(step1.x + 10, step1.y + step1.height + 160);
  await page.mouse.down();
  await page.mouse.move(step1.x + 90, step1.y + step1.height + 200, { steps: 6 });
  await page.mouse.up();
  await expectSelected(page, []);
  await expect(page.getByTestId("inspector-multi")).toHaveCount(0);
  await jitterClick(page, "Step1", 2);
  await expectSelected(page, ["Step1"]);
});

test("Ctrl-clicks add and remove; the next plain click selects one node", async ({ page }) => {
  await openDual(page);
  await enterIconic(page);
  await jitterClick(page, "R1", 0);
  await expectSelected(page, ["R1"]);
  await jitterClick(page, "L1", 0, ["Control"]);
  await expectSelected(page, ["R1", "L1"]);
  await jitterClick(page, "C1", 1, ["Control"]);
  await expectSelected(page, ["R1", "L1", "C1"]);
  await jitterClick(page, "L1", 0, ["Control"]);
  await expectSelected(page, ["R1", "C1"]);
  await jitterClick(page, "V1", 0);
  await expectSelected(page, ["V1"]);
  await jitterClick(page, "Step1", 0, ["Control"]);
  await expectSelected(page, ["V1", "Step1"]);
  await jitterClick(page, "Step1", 2);
  await expectSelected(page, ["Step1"]);
  await clickEmpty(page);
  await expectSelected(page, []);
  await jitterClick(page, "C1", 1);
  await expectSelected(page, ["C1"]);
});
