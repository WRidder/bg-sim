import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import type { Model, ModelConnection, ModelNode } from "../../src/contracts/model";

/**
 * W1.3 acceptance (plan 7.3): with the fake worker's 28-diagnostic fixture
 * loaded, every diagnostic item navigates to its node, the canvas shows the
 * node/edge markers, filtering and grouping work, and the live check loop
 * applies `domains`, `unitFactors` and `causality` when the worker reports them.
 *
 * The fixture points at editor ids `n2` ... `n31`, so the test writes a model
 * with exactly those ids before opening it. Each test uses its own project and
 * deletes it afterwards.
 */

let project = "";
let serial = 0;

test.beforeEach(async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 1000 });
});

test.afterEach(async ({ request }) => {
  if (project.length > 0) {
    await request.delete(`/api/projects/${project}`);
    project = "";
  }
});

const FIXTURE_NODES: ReadonlyArray<readonly [string, string, number, number]> = [
  ["n2", "Graph1", 80, 40],
  ["n3", "Motor1", 320, 40],
  ["n4", "Sensor1", 560, 40],
  ["n6", "Se2", 800, 40],
  ["n7", "Filter1", 1040, 40],
  ["n8", "Ball", 1280, 40],
  ["n9", "LUT1", 80, 220],
  ["n10", "Filter1b", 320, 220],
  ["n12", "PI1", 560, 220],
  ["n14", "Sum1", 800, 220],
  ["n16", "I2", 1040, 220],
  ["n21", "Compare1", 1280, 220],
  ["n22", "Gear1", 80, 400],
  ["n31", "Counter1", 2600, 400],
  // The M3 diagnostic entries E007 (frame mismatch), E108/E109 (inertia/mass).
  ["n41", "Load1", 560, 400],
  ["n51", "Body1", 800, 400],
];

/** Connection ids the fixture names in `connection` (E102, E105, E106, W201, W202, W205). */
const FIXTURE_CONNECTIONS: ReadonlyArray<readonly [string, string, string]> = [
  ["c9", "n22", "n3"],
  ["c14", "n6", "n2"],
  ["c17", "n16", "n14"],
  ["c18", "n7", "n9"],
  ["c20", "n2", "n7"],
  ["c22", "n31", "n21"],
];

function node(id: string, name: string, x: number, y: number, ref = "stdlib:bondgraph/R"): ModelNode {
  return {
    id,
    name,
    block: { ref },
    position: { x, y },
    rotation: 0,
    flipX: false,
    params: {},
    constants: {},
    starts: {},
    ui: { showLabel: true, color: null },
  };
}

function connection(id: string, from: string, to: string, kind: "bond" | "signal", fromPort: string, toPort: string): ModelConnection {
  return {
    id,
    kind,
    from: { node: from, port: fromPort },
    to: { node: to, port: toPort },
    route: [],
    label: null,
  };
}

function model(name: string, nodes: ModelNode[], connections: ModelConnection[]): Model {
  return {
    format: "bgsim.model",
    language: "0.1.0",
    name,
    diagram: { nodes, connections, subsystemPorts: [], annotations: [] },
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

function fixtureModel(): Model {
  const nodes = FIXTURE_NODES.map(([id, name, x, y]) => node(id, name, x, y));
  const connections = FIXTURE_CONNECTIONS.map(([id, from, to]) =>
    connection(id, from, to, "bond", "p", "p"),
  );
  return model("DiagnosticsFixture", nodes, connections);
}

function signalModel(): Model {
  return model(
    "DiagnosticsSignals",
    [
      node("n1", "Command", 80, 80, "stdlib:sources/Constant"),
      node("n2", "Gain1", 360, 80, "stdlib:continuous/Gain"),
      node("n3", "R1", 80, 360),
      node("n4", "R2", 360, 360),
    ],
    [
      connection("c1", "n3", "n4", "bond", "p", "p"),
      connection("c2", "n1", "n2", "signal", "y", "u"),
    ],
  );
}

async function createProject(request: APIRequestContext, document: Model): Promise<string> {
  serial += 1;
  const name = `w13e2e-${Date.now()}-${test.info().workerIndex}-${serial}`;
  const created = await request.post("/api/projects", { data: { name } });
  expect(created.ok()).toBeTruthy();
  const stored = await request.put(`/api/projects/${name}/models/${document.name}`, {
    data: document,
  });
  expect(stored.ok()).toBeTruthy();
  return name;
}

async function openModel(page: Page, document: Model): Promise<void> {
  project = await createProject(page.request, document);
  await page.goto(`/?project=${encodeURIComponent(project)}&model=${encodeURIComponent(document.name)}`);
  await expect(page.getByTestId("library-item-DCMotor")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("canvas-surface")).toBeVisible();
  await page.getByRole("tab", { name: /^Diagnostics/ }).click();
  await expect(page.getByTestId("diagnostic-item-0")).toBeVisible({ timeout: 30_000 });
}

function nodeCard(page: Page, nodeId: string) {
  return page.locator(`[data-testid="diagram-node"][data-node-id="${nodeId}"]`);
}

async function expectInsideCanvas(page: Page, nodeId: string): Promise<void> {
  const canvas = await page.getByTestId("canvas-surface").boundingBox();
  const box = await nodeCard(page, nodeId).boundingBox();
  expect(canvas).not.toBeNull();
  expect(box).not.toBeNull();
  if (canvas === null || box === null) {
    return;
  }
  expect(box.x).toBeGreaterThanOrEqual(canvas.x - 1);
  expect(box.y).toBeGreaterThanOrEqual(canvas.y - 1);
  expect(box.x + box.width).toBeLessThanOrEqual(canvas.x + canvas.width + 1);
  expect(box.y + box.height).toBeLessThanOrEqual(canvas.y + canvas.height + 1);
}

test("navigates every fixture diagnostic to its node and marks the canvas", async ({ page }) => {
  await openModel(page, fixtureModel());

  const rows = page.locator('[data-testid^="diagnostic-item-"]');
  // 33 items: the M2 sample plus the M4 debugger codes E401, E402 and W401 (C4.0).
  await expect(rows).toHaveCount(33);
  await expect(page.getByTestId("diagnostics-count-error")).toContainText("26");
  await expect(page.getByTestId("diagnostics-count-warning")).toContainText("7");

  // Grouping by instance path: 24 groups (E401 adds `Ctrl`), Ctrl/PI1 holds four diagnostics.
  await expect(page.locator('[data-testid="diagnostics-group"]')).toHaveCount(24);
  const controller = page.locator('[data-testid="diagnostics-group"][data-path="Ctrl/PI1"]');
  await expect(controller.locator('[data-testid^="diagnostic-item-"]')).toHaveCount(4);
  await expect(controller).toContainText("E001");

  // Filter by severity: hiding errors leaves the seven warnings.
  await page.getByTestId("diagnostics-filter-error").click();
  await expect(rows).toHaveCount(7);
  await page.getByTestId("diagnostics-filter-warning").click();
  await expect(page.getByTestId("diagnostics-filter-empty")).toBeVisible();
  await page.getByTestId("diagnostics-show-all").click();
  await expect(rows).toHaveCount(33);

  // Canvas markers: Motor1 carries E103 and E900, and c9 carries E102.
  const motor = nodeCard(page, "n3");
  await expect(motor).toHaveAttribute("data-diagnostic-severity", "error");
  await expect(motor).toHaveAttribute("data-diagnostic-count", "2");
  await expect(motor).toHaveAttribute("data-diagnostic-messages", /E103/);
  await expect(motor).toHaveAttribute("title", /E900/);
  await expect(page.locator('[data-testid="edge-c9"]')).toHaveAttribute(
    "data-diagnostic-severity",
    "error",
  );

  // n31 starts far outside the viewport; clicking E105 must select it and pan.
  const canvasBefore = await page.getByTestId("canvas-surface").boundingBox();
  const farBefore = await nodeCard(page, "n31").boundingBox();
  expect(canvasBefore).not.toBeNull();
  expect(farBefore).not.toBeNull();
  if (canvasBefore !== null && farBefore !== null) {
    expect(farBefore.x).toBeGreaterThan(canvasBefore.x + canvasBefore.width);
  }

  const farRow = page.getByTestId("diagnostic-item-12");
  await farRow.scrollIntoViewIfNeeded();
  await farRow.click();
  await expect(nodeCard(page, "n31")).toHaveClass(/is-selected/);
  await expect(page.getByTestId("canvas-surface")).toHaveAttribute("data-focused-node", "n31");
  await expectInsideCanvas(page, "n31");

  // Every item with a node navigates; W401 (no node id) navigates by its instance path, E401
  // (no node at its path) to its source range; the binding diagnostics have no target.
  const count = await rows.count();
  for (let index = 0; index < count; index += 1) {
    const row = rows.nth(index);
    await row.scrollIntoViewIfNeeded();
    const nodeId = await row.getAttribute("data-node");
    const target = await row.getAttribute("data-target");
    if (nodeId !== null && nodeId.length > 0) {
      await row.click();
      const node = nodeCard(page, nodeId);
      await expect(node).toHaveClass(/is-selected/);
      await expectInsideCanvas(page, nodeId);
    } else if (target === "node") {
      expect(await row.getAttribute("data-code")).toBe("W401");
      await row.click();
      await expect(nodeCard(page, "n7")).toHaveClass(/is-selected/);
      await expectInsideCanvas(page, "n7");
    } else if (target === "source") {
      expect(await row.getAttribute("data-code")).toBe("E401");
      await row.click();
      await expect(page.getByTestId("diagnostics-source-focus")).toContainText(
        "project:LQGController",
      );
    } else {
      await row.click();
      expect(target).toBe("none");
    }
  }

  // A source-level diagnostic announces its range for the code tab as well.
  await page.getByTestId("diagnostic-item-0").click();
  await expect(page.getByTestId("diagnostics-source-focus")).toBeVisible();
  await expect(page.getByTestId("diagnostics-source-focus")).toContainText("inline:n7");
});

test("applies domains, unit factors, edge markers and causal strokes from model.check", async ({
  page,
}) => {
  let checks = 0;
  await page.route(/\/api\/check\/model(?:\?.*)?$/, async (route) => {
    checks += 1;
    await route.fulfill({
      json: {
        diagnostics: [
          {
            code: "E901",
            severity: "error",
            message: "solver failed at t = 0.412 s",
            hint: "the largest state was Command/y",
            path: "Command",
            block: "stdlib:sources/Constant",
            scope: null,
            source: null,
            node: "n1",
            connection: null,
          },
          {
            code: "W201",
            severity: "warning",
            message: "R1 is in derivative causality",
            hint: null,
            path: "R1",
            block: "stdlib:bondgraph/R",
            scope: null,
            source: null,
            node: null,
            connection: "c1",
          },
        ],
        domains: { c1: "Electrical" },
        causality: { c1: { strokeAt: "to" } },
        unitFactors: { c2: 0.001 },
        signals: [],
        stats: { states: 1, equations: 1 },
      },
    });
  });

  await openModel(page, signalModel());
  expect(checks).toBeGreaterThanOrEqual(1);

  // Domain colouring overrides the Generic client-side analysis on the bond.
  const bond = page.locator('[data-testid="edge-c1"]');
  await expect(bond).toHaveAttribute("data-domain", "Electrical");
  await expect(bond).toHaveAttribute("data-bgsim-base-domain", "Generic");
  await expect(bond.locator(".react-flow__edge-path")).toHaveAttribute(
    "style",
    /--domain-electrical/,
  );

  // The unit conversion badge sits on the signal wire, inside the canvas.
  const factor = page.getByTestId("unit-badge-c2");
  await expect(factor).toBeVisible();
  await expect(factor).toHaveText("×0.001");
  const canvasBox = await page.getByTestId("canvas-surface").boundingBox();
  const factorBox = await factor.boundingBox();
  expect(canvasBox).not.toBeNull();
  expect(factorBox).not.toBeNull();
  if (canvasBox !== null && factorBox !== null) {
    expect(factorBox.x).toBeGreaterThanOrEqual(canvasBox.x);
    expect(factorBox.y).toBeGreaterThanOrEqual(canvasBox.y);
    expect(factorBox.x + factorBox.width).toBeLessThanOrEqual(canvasBox.x + canvasBox.width);
    expect(factorBox.y + factorBox.height).toBeLessThanOrEqual(canvasBox.y + canvasBox.height);
  }

  // Connection diagnostics badge the edge; node diagnostics outline the node.
  await expect(page.getByTestId("edge-diagnostic-c1")).toBeVisible();
  await expect(page.getByTestId("edge-diagnostic-c1")).toHaveText("1");
  const command = nodeCard(page, "n1");
  await expect(command).toHaveAttribute("data-diagnostic-severity", "error");
  await expect(command).toHaveAttribute("data-diagnostic-count", "1");

  // Causality is rendered when it is non-empty (J2.4 supplies it for real).
  await expect(page.locator('[data-testid="causal-stroke-c1"]')).toHaveCount(1);
});
