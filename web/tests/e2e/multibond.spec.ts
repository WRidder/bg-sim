import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import type { Model } from "../../src/contracts/model";

/**
 * W-MB1 acceptance (plan 7.1/7.2/7.4): a Planar multibond is drawn as two
 * parallel strokes with one half arrow per stroke and **one** causal bar across
 * the bundle, its group carries `data-multibond-strokes="2"`, and the
 * `model.check` frame appears as a `frame: <name>` pill only on hover or
 * selection.
 *
 * The model is two inline blocks with `Power{Planar}` ports. The fake worker
 * does not parse block source, so this spec plays it for the two endpoints,
 * exactly like `code.spec.ts` does for the inline interface: `block.check`
 * declares the Planar ports, `model.check` adopts the domain (`c1`), the
 * instance-qualified frame (`Arm1/body`) and the `to` causal stroke. This is a
 * fake-worker fixture by design (DEC-6); it is not in the real-worker pass.
 */

let project = "";
let serial = 0;

const GROUND = `@block GroundPlanar begin
    @ports p::Power{Planar}, [frame = "world"]
    @equations p.f ~ [0.0, 0.0, 0.0]
    @causality p => (:flow_out, :fixed)
end
`;

const BODY = `@block BodyPlanar begin
    @ports p::Power{Planar}, [frame = "arm"]
    @parameters begin
        m::Real = 1.2, [unit = "kg", min = 0]
        J::Real = 0.04, [unit = "kg*m^2", min = 0]
    end
    @variables P::Vec{3} = [0.0, 0.0, 0.0], [state = :prefer]
    @equations begin
        p.f[1] ~ P[1] / J
        p.f[2] ~ P[2] / m
        p.f[3] ~ P[3] / m
        for k in 1:3
            ddt(P[k]) ~ p.e[k]
        end
    end
    @causality p => :flow_out
end
`;

const PLANAR_MODEL: Model = {
  format: "bgsim.model",
  language: "0.1.0",
  name: "Multibond2D",
  diagram: {
    nodes: [
      {
        id: "n1",
        name: "Ground",
        block: { inline: { source: GROUND } },
        position: { x: 120, y: 220 },
        rotation: 0,
        flipX: false,
        params: {},
        constants: {},
        starts: {},
        ui: { showLabel: true, color: null },
      },
      {
        id: "n2",
        name: "Arm1",
        block: { inline: { source: BODY } },
        position: { x: 560, y: 220 },
        rotation: 0,
        flipX: false,
        params: {},
        constants: {},
        starts: {},
        ui: { showLabel: true, color: null },
      },
    ],
    connections: [
      {
        id: "c1",
        kind: "bond",
        from: { node: "n1", port: "p" },
        to: { node: "n2", port: "p" },
        route: [],
        label: null,
      },
    ],
    subsystemPorts: [],
    annotations: [],
  },
  settings: {
    t_start: 0,
    t_end: 1,
    solver: "auto",
    reltol: 1e-6,
    abstol: 1e-8,
    max_step: null,
    output: { mode: "points", points: 1000 },
    event_limit: 10000,
  },
  plots: [],
  scene: null,
  bindings: [],
};

const SPATIAL_GROUND = `@block GroundSpatial begin
    @ports p::Power{Spatial}, [frame = "world"]
    @equations p.f ~ [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    @causality p => (:flow_out, :fixed)
end
`;

const SPATIAL_BODY = `@block BodySpatial begin
    @ports p::Power{Spatial}, [frame = "body"]
    @parameters begin
        m::Real = 1.2, [unit = "kg", min = 0]
        J::Real = 0.04, [unit = "kg*m^2", min = 0]
    end
    @variables P::Vec{6} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [state = :prefer]
    @equations begin
        for k in 1:3
            p.f[k] ~ P[k] / J
            p.f[k + 3] ~ P[k + 3] / m
        end
        for k in 1:6
            ddt(P[k]) ~ p.e[k]
        end
    end
    @causality p => :flow_out
end
`;

const SPATIAL_MODEL: Model = {
  ...PLANAR_MODEL,
  name: "Multibond3D",
  diagram: {
    nodes: [
      {
        id: "n1",
        name: "World",
        block: { inline: { source: SPATIAL_GROUND } },
        position: { x: 120, y: 220 },
        rotation: 0,
        flipX: false,
        params: {},
        constants: {},
        starts: {},
        ui: { showLabel: true, color: null },
      },
      {
        id: "n2",
        name: "Body",
        block: { inline: { source: SPATIAL_BODY } },
        position: { x: 560, y: 220 },
        rotation: 0,
        flipX: false,
        params: {},
        constants: {},
        starts: {},
        ui: { showLabel: true, color: null },
      },
    ],
    connections: [
      {
        id: "c1",
        kind: "bond",
        from: { node: "n1", port: "p" },
        to: { node: "n2", port: "p" },
        route: [],
        label: null,
      },
    ],
    subsystemPorts: [],
    annotations: [],
  },
};

async function createProject(request: APIRequestContext, document: Model): Promise<string> {
  serial += 1;
  const name = `wmb1e2e-${Date.now()}-${test.info().workerIndex}-${serial}`;
  const created = await request.post("/api/projects", { data: { name } });
  expect(created.ok()).toBeTruthy();
  const stored = await request.put(`/api/projects/${name}/models/${document.name}`, {
    data: document,
  });
  expect(stored.ok()).toBeTruthy();
  return name;
}

/** Play the worker for the two inline Planar blocks (their interfaces are derived). */
async function stubBlockCheck(page: Page): Promise<void> {
  await page.route(/\/api\/check\/block$/, async (route) => {
    const body = route.request().postDataJSON() as { source?: unknown };
    const source = typeof body.source === "string" ? body.source : "";
    const ground = source.includes("GroundPlanar");
    const frame = ground ? "world" : "arm";
    await route.fulfill({
      json: {
        diagnostics: [],
        interface: {
          constants: [],
          parameters: [],
          inputs: [],
          outputs: [],
          ports: [{ name: "p", domain: "Planar", size: [3], frame }],
          variables: [],
          causality: [{ ports: ["p"], kind: "preferred", value: "flow_out" }],
          dimension: 2,
        },
      },
    });
  });
}

/** Adopt the Planar domain, the frame and the causal stroke for the one bond. */
async function stubModelCheck(page: Page): Promise<void> {
  await page.route(/\/api\/check\/model(\?.*)?$/, async (route) => {
    await route.fulfill({
      json: {
        diagnostics: [],
        domains: { c1: "Planar" },
        causality: { c1: { strokeAt: "to" } },
        frames: { c1: "Arm1/body" },
        multibond: { c1: 2 },
        unitFactors: {},
        signals: [],
        stats: { states: 3, equations: 3 },
      },
    });
  });
}

/** Play the worker for the two inline Spatial blocks (their interfaces are derived). */
async function stubSpatialBlockCheck(page: Page): Promise<void> {
  await page.route(/\/api\/check\/block$/, async (route) => {
    const body = route.request().postDataJSON() as { source?: unknown };
    const source = typeof body.source === "string" ? body.source : "";
    const ground = source.includes("GroundSpatial");
    const frame = ground ? "world" : "body";
    await route.fulfill({
      json: {
        diagnostics: [],
        interface: {
          constants: [],
          parameters: [],
          inputs: [],
          outputs: [],
          ports: [{ name: "p", domain: "Spatial", size: [6], frame }],
          variables: [],
          causality: [{ ports: ["p"], kind: "preferred", value: "flow_out" }],
          dimension: 3,
        },
      },
    });
  });
}

/** Adopt the Spatial domain, the frame and the causal stroke for the one bond. */
async function stubSpatialModelCheck(page: Page): Promise<void> {
  await page.route(/\/api\/check\/model(\?.*)?$/, async (route) => {
    await route.fulfill({
      json: {
        diagnostics: [],
        domains: { c1: "Spatial" },
        causality: { c1: { strokeAt: "to" } },
        frames: { c1: "World/body" },
        multibond: { c1: 3 },
        unitFactors: {},
        signals: [],
        stats: { states: 6, equations: 6 },
      },
    });
  });
}

/** The screen point at the middle of the bond's centre path. */
async function edgePoint(page: Page, id: string): Promise<{ x: number; y: number } | null> {
  return page.evaluate((edgeId) => {
    const path = document.querySelector<SVGPathElement>(
      `[data-testid="edge-${edgeId}"] .react-flow__edge-path`,
    );
    if (path === null) {
      return null;
    }
    const matrix = path.getScreenCTM();
    if (matrix === null) {
      return null;
    }
    const middle = path.getPointAtLength(path.getTotalLength() / 2);
    const screen = middle.matrixTransform(matrix);
    return { x: screen.x, y: screen.y };
  }, id);
}

test.beforeEach(async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 1000 });
});

test.afterEach(async ({ request }) => {
  if (project.length > 0) {
    await request.delete(`/api/projects/${project}`);
    project = "";
  }
});

test("a Planar out bond is a two-stroke bundle with one causal bar and a frame pill", async ({
  page,
}) => {
  await stubBlockCheck(page);
  await stubModelCheck(page);
  project = await createProject(page.request, PLANAR_MODEL);
  await page.goto(
    `/?project=${encodeURIComponent(project)}&model=${encodeURIComponent(PLANAR_MODEL.name)}`,
  );
  await expect(page.getByTestId("canvas-surface")).toBeVisible({ timeout: 30_000 });

  const edge = page.getByTestId("edge-c1");
  await expect(edge).toBeVisible({ timeout: 30_000 });
  await expect(edge).toHaveAttribute("data-multibond-strokes", "2");
  await expect(edge).toHaveAttribute(
    "aria-label",
    "Planar multibond, 3 components, 2 strokes",
  );

  // Two stroke paths at the two offsets, and exactly one bar across them.
  const strokes = edge.locator(".editor-edge__multibond-stroke");
  await expect(strokes).toHaveCount(2);
  expect(await strokes.nth(0).getAttribute("data-offset")).toBe("-2.1");
  expect(await strokes.nth(1).getAttribute("data-offset")).toBe("2.1");
  expect(await strokes.nth(0).getAttribute("d")).not.toBe(
    await strokes.nth(1).getAttribute("d"),
  );

  const bar = page.getByTestId("causal-stroke-c1");
  await expect(bar).toHaveCount(1);
  await expect(bar).toHaveAttribute("data-stroke-at", "to");
  const span = await bar.evaluate((line) => {
    const x1 = Number(line.getAttribute("x1"));
    const y1 = Number(line.getAttribute("y1"));
    const x2 = Number(line.getAttribute("x2"));
    const y2 = Number(line.getAttribute("y2"));
    return Math.hypot(x2 - x1, y2 - y1);
  });
  // 2 * (bundleHalf + 3) with bundleHalf = gap/2 + strokeWidth/2 = 2.85.
  expect(span).toBeCloseTo(11.7, 6);

  // The port stays one logical point with two ticks (plan 7.2).
  const port = page.getByTestId("port-n1-p");
  await expect(port).toHaveAttribute("data-glyph", "multibond");
  await expect(port).toHaveAttribute("data-strokes", "2");

  // The legend key is keyboard reachable and names the stroke count in text.
  const legendKey = page.getByTestId("legend-multibond2d");
  await expect(legendKey).toContainText("2D multibond (2 strokes)");
  await legendKey.focus();
  await expect(legendKey).toBeFocused();
  await page.evaluate(() => {
    if (document.activeElement instanceof HTMLElement) {
      document.activeElement.blur();
    }
  });

  // The frame pill is hidden until the bond is hovered.
  const pill = page.getByTestId("frame-badge-c1");
  await expect(pill).toHaveCount(0);
  const point = await edgePoint(page, "c1");
  expect(point).not.toBeNull();
  await page.mouse.move(Math.round(point!.x), Math.round(point!.y));
  await expect(pill).toBeVisible({ timeout: 10_000 });
  await expect(pill).toHaveText("frame: Arm1/body");
  await expect(pill).toHaveAttribute("data-frame", "Arm1/body");
  await page.mouse.move(4, 4);
  await expect(pill).toHaveCount(0);

  // Stable screenshot of the bundle with no hover affordance in it.
  const canvas = page.getByTestId("canvas-surface");
  await expect(canvas).toHaveScreenshot("multibond-2d.png", {
    maxDiffPixels: 400,
    animations: "disabled",
    caret: "hide",
  });
});

test("a Spatial out bond is a three-stroke bundle with one causal bar and three port ticks", async ({
  page,
}) => {
  await stubSpatialBlockCheck(page);
  await stubSpatialModelCheck(page);
  project = await createProject(page.request, SPATIAL_MODEL);
  await page.goto(
    `/?project=${encodeURIComponent(project)}&model=${encodeURIComponent(SPATIAL_MODEL.name)}`,
  );
  await expect(page.getByTestId("canvas-surface")).toBeVisible({ timeout: 30_000 });

  const edge = page.getByTestId("edge-c1");
  await expect(edge).toBeVisible({ timeout: 30_000 });
  await expect(edge).toHaveAttribute("data-multibond-strokes", "3");
  await expect(edge).toHaveAttribute(
    "aria-label",
    "Spatial multibond, 6 components, 3 strokes",
  );

  // Three distinct stroke paths at the full-gap offsets, one causal bar.
  const strokes = edge.locator(".editor-edge__multibond-stroke");
  await expect(strokes).toHaveCount(3);
  expect(await strokes.nth(0).getAttribute("data-offset")).toBe("-4.2");
  expect(await strokes.nth(1).getAttribute("data-offset")).toBe("0");
  expect(await strokes.nth(2).getAttribute("data-offset")).toBe("4.2");
  expect(await strokes.nth(0).getAttribute("d")).not.toBe(
    await strokes.nth(2).getAttribute("d"),
  );
  expect(await strokes.nth(0).getAttribute("stroke")).toBe("var(--domain-spatial)");
  await expect(edge.locator(".editor-edge__multibond-arrow")).toHaveCount(3);

  const bar = page.getByTestId("causal-stroke-c1");
  await expect(bar).toHaveCount(1);
  await expect(bar).toHaveAttribute("data-stroke-at", "to");
  const span = await bar.evaluate((line) => {
    const x1 = Number(line.getAttribute("x1"));
    const y1 = Number(line.getAttribute("y1"));
    const x2 = Number(line.getAttribute("x2"));
    const y2 = Number(line.getAttribute("y2"));
    return Math.hypot(x2 - x1, y2 - y1);
  });
  // 2 * (bundleHalf + 3) with bundleHalf = gap + strokeWidth/2 = 4.95.
  expect(span).toBeCloseTo(15.9, 6);

  // The port stays one logical point with three ticks (plan 7.2).
  const port = page.getByTestId("port-n1-p");
  await expect(port).toHaveAttribute("data-glyph", "multibond");
  await expect(port).toHaveAttribute("data-strokes", "3");
  await expect(port.locator(".port-glyph__tick")).toHaveCount(3);

  // The 3D legend key is keyboard reachable and names the stroke count in text.
  const legendKey = page.getByTestId("legend-multibond3d");
  await expect(legendKey).toContainText("3D multibond (3 strokes)");
  await legendKey.focus();
  await expect(legendKey).toBeFocused();
  await page.evaluate(() => {
    if (document.activeElement instanceof HTMLElement) {
      document.activeElement.blur();
    }
  });

  // Stable screenshot of the three-stroke bundle, no hover affordance in it.
  const canvas = page.getByTestId("canvas-surface");
  await expect(canvas).toHaveScreenshot("multibond-3d.png", {
    maxDiffPixels: 400,
    animations: "disabled",
    caret: "hide",
  });
});
