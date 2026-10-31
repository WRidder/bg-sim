import { mkdirSync } from "node:fs";
import path from "node:path";

import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type Route } from "@playwright/test";

import type { Model, ModelNode } from "../../src/contracts/model";
import { waitForLibrary } from "./library";

/**
 * From code to a reusable block (plan 7.7):
 *
 * - fake worker: "Save to project library" of an inline node in the inspector
 *   writes library/<Name>.jl and, because the fixture catalog never publishes
 *   the block, reports that the node stays inline;
 * - fake worker with a catalog stub that publishes the project library (what
 *   the Julia worker does): saving from the Code tab re-points the node, shows
 *   the library block in the Code tab and highlights it in the library's
 *   Project category; "+ Library block" creates a block and "Place on diagram"
 *   adds it;
 * - real worker (BGSIM_E2E_REAL=1): save an inline block, then drag it from the
 *   Project category onto the diagram.
 *
 * Screenshots go to BGSIM_SCREENSHOT_DIR when it is set.
 */

const real = process.env.BGSIM_E2E_REAL === "1";
const shots = process.env.BGSIM_SCREENSHOT_DIR ?? "";

const LAG = `@block Equation begin
    @inputs u::Real
    @outputs y::Real
    @parameters begin
        tau::Real = 0.5, [unit = "s", description = "Time constant"]
    end
    @variables x::Real = 0.0
    @equations begin
        ddt(x) ~ (u - x) / tau
        y ~ x
    end
end
`;

let project = "";

function inlineNode(id: string, name: string, x: number, y: number): ModelNode {
  return {
    id,
    name,
    block: { inline: { source: LAG } },
    position: { x, y },
    rotation: 0,
    flipX: false,
    params: { tau: "0.25" },
    constants: {},
    starts: {},
    ui: { showLabel: true, color: null },
  };
}

function model(name: string, nodes: ModelNode[]): Model {
  return {
    format: "bgsim.model",
    language: "0.1.0",
    name,
    diagram: { nodes, connections: [], subsystemPorts: [], annotations: [] },
    settings: {
      t_start: 0,
      t_end: 1,
      solver: "auto",
      reltol: 1e-6,
      abstol: 1e-8,
      max_step: null,
      output: { mode: "points", points: 5000 },
      event_limit: 10000,
    },
    plots: [],
    scene: null,
    bindings: [],
  };
}

async function shot(page: Page, name: string): Promise<void> {
  if (shots.length === 0) {
    return;
  }
  mkdirSync(shots, { recursive: true });
  await page.screenshot({ path: path.join(shots, name) });
}

async function openModel(page: Page, document: Model): Promise<void> {
  project = `code2lib-${Date.now()}-${test.info().workerIndex}`;
  expect((await page.request.post("/api/projects", { data: { name: project } })).status()).toBe(201);
  expect(
    (await page.request.put(`/api/projects/${project}/models/${document.name}`, { data: document })).ok(),
  ).toBeTruthy();
  if (real) {
    // The catalog answers 503 until the Julia worker has warmed up.
    await expect
      .poll(
        async () =>
          (await page.request.get(`/api/catalog?project=${encodeURIComponent(project)}`)).status(),
        { timeout: 900_000, intervals: [5_000] },
      )
      .toBe(200);
  }
  await page.goto(`/?project=${encodeURIComponent(project)}&model=${encodeURIComponent(document.name)}`);
  await waitForLibrary(page, real ? 120_000 : 30_000);
  await expect(page.getByTestId("canvas-surface")).toBeVisible();
}

/**
 * Play the Julia worker's part for the catalog: list every file of the
 * project library as a `project:<Name>` block (the fixture catalog the fake
 * worker serves never contains them).
 */
async function publishProjectLibrary(page: Page): Promise<void> {
  await page.route(/\/api\/catalog(\?.*)?$/, async (route: Route) => {
    const response = await route.fetch();
    const catalog = (await response.json()) as { blocks: Record<string, unknown>[] };
    const base = catalog.blocks.find((block) => block.ref === "stdlib:continuous/Integrator");
    const info = (await (await page.request.get(`/api/projects/${project}`)).json()) as {
      library: { name: string }[];
    };
    for (const entry of info.library) {
      const source = await (await page.request.get(`/api/projects/${project}/library/${entry.name}`)).text();
      catalog.blocks.push({
        ...base,
        ref: `project:${entry.name}`,
        name: entry.name,
        group: "Project",
        description: `${entry.name} from the project library`,
        parameters: [],
        source,
        path: `library/${entry.name}.jl`,
      });
    }
    await route.fulfill({ response, json: catalog });
  });
}

async function documentJson(page: Page): Promise<Model> {
  const diagram = page.getByRole("tab", { name: "Diagram", exact: true });
  if ((await diagram.getAttribute("aria-selected")) !== "true") {
    await diagram.click();
  }
  return JSON.parse((await page.getByTestId("document-json").textContent()) ?? "null") as Model;
}

function nodeNamed(document: Model, name: string): ModelNode | undefined {
  return document.diagram.nodes.find((node) => node.name === name);
}

function canvasNode(page: Page, name: string) {
  return page.locator(`[data-testid="diagram-node"][data-node-name="${name}"]`);
}

test.beforeEach(async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.emulateMedia({ reducedMotion: "reduce" });
});

test.afterEach(async ({ request }) => {
  if (project.length > 0) {
    await request.delete(`/api/projects/${project}`);
    project = "";
  }
});

test.describe("fake worker", () => {
  test.skip(real, "the real-worker pass runs the drag-from-library spec below");

  test("inspector: Save to project library writes the file and reports the unpublished block", async ({
    page,
  }) => {
    await openModel(page, model("SaveInline", [inlineNode("n1", "Lag1", 200, 160)]));
    await canvasNode(page, "Lag1").click();

    const save = page.getByTestId("inspector-save-library");
    await expect(save).toBeEnabled();
    await expect(page.getByTestId("inspector-copy-library")).toHaveCount(0);
    await save.click();

    const dialog = page.getByTestId("project-block-dialog");
    await expect(dialog).toBeVisible();
    const name = page.getByTestId("project-block-name");
    await expect(name).toBeEnabled();
    await expect(name).toHaveValue("Equation");
    await expect(name).toBeFocused();

    await name.fill("first lag");
    await expect(page.getByTestId("project-block-name-hint")).toContainText("Julia identifier");
    await expect(page.getByTestId("project-block-submit")).toBeDisabled();
    await name.fill("FirstOrderLag");
    await expect(page.getByTestId("project-block-rename-note")).toContainText("@block FirstOrderLag");
    await shot(page, "code-to-library-dialog.png");
    const axe = await new AxeBuilder({ page }).include('[data-testid="project-block-dialog"]').analyze();
    const serious = axe.violations.filter(
      (violation) => violation.impact === "serious" || violation.impact === "critical",
    );
    expect(serious.map((violation) => violation.id)).toEqual([]);
    await name.press("Enter");

    await expect(dialog).toHaveCount(0);
    await expect(page.getByTestId("inspector-copy-status")).toContainText(
      "Saved to library/FirstOrderLag.jl. The catalog does not list project:FirstOrderLag yet, so Lag1 stays an inline block",
    );
    const file = await page.request.get(`/api/projects/${project}/library/FirstOrderLag`);
    expect(file.ok()).toBeTruthy();
    expect(await file.text()).toMatch(/^@block FirstOrderLag begin/);
    const document = await documentJson(page);
    expect(nodeNamed(document, "Lag1")?.block).toEqual({ inline: { source: LAG } });

    // The name is now taken (case-insensitively, like the file system).
    await canvasNode(page, "Lag1").click();
    await page.getByTestId("inspector-save-library").click();
    await expect(page.getByTestId("project-block-name")).toHaveValue("Equation");
    await page.getByTestId("project-block-name").fill("firstorderlag");
    await expect(page.getByTestId("project-block-name-hint")).toContainText("ignore case");
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("project-block-dialog")).toHaveCount(0);
  });

  test("Code tab: saving re-points the node, opens the library block and highlights it", async ({
    page,
  }) => {
    await publishProjectLibrary(page);
    await openModel(
      page,
      model("SaveFromCode", [inlineNode("n1", "Lag1", 200, 160), inlineNode("n2", "Lag2", 520, 160)]),
    );
    await page.getByRole("tab", { name: "Code" }).click();
    await page.getByTestId("code-source-select").selectOption("inline:n1");
    await expect(page.getByTestId("code-open-source")).toContainText("inline:n1");

    await page.getByTestId("code-save-to-library").click();
    await expect(page.getByTestId("project-block-identical")).toContainText(
      "1 other inline block with the same source (Lag2)",
    );
    await page.getByTestId("project-block-identical-check").check();
    await page.getByTestId("project-block-name").fill("Lag");
    await page.getByTestId("project-block-submit").click();

    await expect(page.getByTestId("code-project-banner")).toBeVisible();
    await expect(page.getByTestId("code-open-source")).toContainText("project:Lag");
    await expect(page.locator(".cm-content")).toContainText("@block Lag begin");
    await expect(page.getByTestId("code-notice")).toContainText(
      "Lag1 (and 1 other identical inline block) now uses project:Lag",
    );
    const entry = page.getByTestId("library-item-Lag");
    await expect(page.getByTestId("library-group-Project")).toHaveAttribute("data-expanded", "true");
    await expect(entry).toHaveAttribute("data-new", "true");
    await shot(page, "code-to-library-code-tab.png");

    let document = await documentJson(page);
    expect(nodeNamed(document, "Lag1")?.block).toEqual({ ref: "project:Lag" });
    expect(nodeNamed(document, "Lag2")?.block).toEqual({ ref: "project:Lag" });
    expect(nodeNamed(document, "Lag1")?.params).toEqual({ tau: "0.25" });
    await canvasNode(page, "Lag1").click();
    await expect(page.getByTestId("inspector-ref")).toHaveText("project:Lag");
    await shot(page, "code-to-library-diagram.png");

    // One undo step brings both inline blocks back.
    await page.keyboard.press("Control+z");
    document = await documentJson(page);
    expect(nodeNamed(document, "Lag1")?.block).toEqual({ inline: { source: LAG } });
    expect(nodeNamed(document, "Lag2")?.block).toEqual({ inline: { source: LAG } });
  });

  test("Code tab: + Library block creates a block from the discrete template and places it", async ({
    page,
  }) => {
    await publishProjectLibrary(page);
    await openModel(page, model("NewBlock", []));
    await page.getByRole("tab", { name: "Code" }).click();
    await page.getByTestId("code-new-library-block").click();

    await expect(page.getByTestId("project-block-dialog")).toHaveAttribute("data-mode", "new");
    await page.getByTestId("project-block-kind-discrete").check();
    await expect(page.getByTestId("project-block-name")).toHaveValue("DiscreteCode");
    await page.getByTestId("project-block-name").fill("Accumulator");
    await shot(page, "code-to-library-new-block.png");
    await page.getByTestId("project-block-submit").click();

    await expect(page.getByTestId("code-project-banner")).toBeVisible();
    await expect(page.locator(".cm-content")).toContainText("@block Accumulator begin");
    await expect(page.locator(".cm-content")).toContainText("@discrete Ts = 0.01");
    await expect(page.getByTestId("code-notice")).toContainText(
      "Created library/Accumulator.jl. Accumulator is in the library's Project category",
    );
    await expect(page.getByTestId("library-item-Accumulator")).toHaveAttribute("data-new", "true");
    await shot(page, "code-to-library-created.png");

    await page.getByTestId("code-place-on-diagram").click();
    await expect(page.getByTestId("code-notice")).toContainText("Placed Accumulator");
    const document = await documentJson(page);
    expect(document.diagram.nodes.map((node) => node.block)).toEqual([{ ref: "project:Accumulator" }]);

    // The project block auto-saves from the Code tab.
    await page.getByRole("tab", { name: "Code" }).click();
    await page.getByTestId("code-source-select").selectOption("project:Accumulator");
    await page.locator(".cm-content").click();
    await page.keyboard.press("Control+End");
    await page.keyboard.insertText("# edited\n");
    await expect(page.getByTestId("code-save-status")).toHaveText("Saved", { timeout: 10_000 });
    const file = await page.request.get(`/api/projects/${project}/library/Accumulator`);
    expect(await file.text()).toContain("# edited");
  });
});

test.describe("real worker", () => {
  test.skip(!real, "needs the Julia worker (BGSIM_E2E_REAL=1)");
  test.setTimeout(1_200_000);

  test("save an inline block to the library and drag it from the Project category", async ({ page }) => {
    await openModel(page, model("RealSave", [inlineNode("n1", "Lag1", 200, 160)]));
    await canvasNode(page, "Lag1").click();
    await page.getByTestId("inspector-save-library").click();
    await page.getByTestId("project-block-name").fill("FirstOrderLag");
    await page.getByTestId("project-block-submit").click();

    await expect(page.getByTestId("inspector-copy-status")).toContainText(
      "Lag1 now uses project:FirstOrderLag",
      { timeout: 120_000 },
    );
    await expect(page.getByTestId("inspector-ref")).toHaveText("project:FirstOrderLag");
    const entry = page.getByTestId("library-item-FirstOrderLag");
    await expect(page.getByTestId("library-group-Project")).toHaveAttribute("data-expanded", "true");
    await expect(entry).toBeVisible();
    await shot(page, "code-to-library-real-library.png");

    await entry.scrollIntoViewIfNeeded();
    await entry.dragTo(page.getByTestId("canvas-surface"), { targetPosition: { x: 620, y: 300 } });
    await expect(canvasNode(page, "FirstOrderLag")).toBeVisible();
    // The library block's ports come from the worker's interface.
    const document = await documentJson(page);
    const dropped = nodeNamed(document, "FirstOrderLag");
    expect(dropped?.block).toEqual({ ref: "project:FirstOrderLag" });
    expect(nodeNamed(document, "Lag1")?.params).toEqual({ tau: "0.25" });
    await shot(page, "code-to-library-real-dragged.png");
  });
});
