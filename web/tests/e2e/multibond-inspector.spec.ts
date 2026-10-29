import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import type { Model } from "../../src/contracts/model";

/**
 * W-MB3 acceptance: the frame inspector and the per-component units.
 *
 * Two inline multibond models (one Planar, one Spatial) exercise the whole
 * path: the worker-reported instance-qualified frame on a selected bond, the
 * port frame on a selected block, and the component unit arrays/multibond
 * signal ids instead of one port-level unit. The fake worker is played for
 * `block.check`/`model.check` because inline sources are not in the catalog
 * (DEC-6), exactly as the W-MB1 `multibond` spec does.
 */

let project = "";
let serial = 0;

const PLANAR_GROUND = `@block GroundPlanar begin
    @ports p::Power{Planar}, [frame = "arm"]
    @equations p.f ~ [0.0, 0.0, 0.0]
    @causality p => (:flow_out, :fixed)
end
`;

const PLANAR_BODY = `@block ArmPlanar begin
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

const SPATIAL_GROUND = `@block WorldSpatial begin
    @ports p::Power{Spatial}, [frame = "body"]
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

function model(
  name: string,
  groundSource: string,
  bodySource: string,
  groundName: string,
  bodyName: string,
): Model {
  const node = (id: string, label: string, source: string, x: number) => ({
    id,
    name: label,
    block: { inline: { source } },
    position: { x, y: 220 },
    rotation: 0,
    flipX: false,
    params: {},
    constants: {},
    starts: {},
    ui: { showLabel: true, color: null },
  });
  return {
    format: "bgsim.model",
    language: "0.1.0",
    name,
    diagram: {
      nodes: [
        node("n1", groundName, groundSource, 120),
        node("n2", bodyName, bodySource, 560),
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
}

const PLANAR_MODEL = model(
  "MultibondInspector2D",
  PLANAR_GROUND,
  PLANAR_BODY,
  "Ground",
  "Arm1",
);
const SPATIAL_MODEL = model(
  "MultibondInspector3D",
  SPATIAL_GROUND,
  SPATIAL_BODY,
  "World",
  "Body",
);

type FrameCase = {
  document: Model;
  domain: "Planar" | "Spatial";
  size: 3 | 6;
  frame: string;
  qualified: string;
  ground: string;
  body: string;
  effort: string;
  flow: string;
};

const PLANAR_CASE: FrameCase = {
  document: PLANAR_MODEL,
  domain: "Planar",
  size: 3,
  frame: "arm",
  qualified: "Arm1/arm",
  ground: "Ground",
  body: "Arm1",
  effort: "[N*m, N, N]",
  flow: "[rad/s, m/s, m/s]",
};

const SPATIAL_CASE: FrameCase = {
  document: SPATIAL_MODEL,
  domain: "Spatial",
  size: 6,
  frame: "body",
  qualified: "Body/body",
  ground: "World",
  body: "Body",
  effort: "[N*m, N*m, N*m, N, N, N]",
  flow: "[rad/s, rad/s, rad/s, m/s, m/s, m/s]",
};

async function createProject(request: APIRequestContext, document: Model): Promise<string> {
  serial += 1;
  const name = `wmb3e2e-${Date.now()}-${test.info().workerIndex}-${serial}`;
  const created = await request.post("/api/projects", { data: { name } });
  expect(created.ok()).toBeTruthy();
  const stored = await request.put(`/api/projects/${name}/models/${document.name}`, {
    data: document,
  });
  expect(stored.ok()).toBeTruthy();
  return name;
}

async function stubWorker(page: Page, frameCase: FrameCase): Promise<void> {
  await page.route(/\/api\/check\/block$/, async (route) => {
    await route.fulfill({
      json: {
        diagnostics: [],
        interface: {
          constants: [],
          parameters: [],
          inputs: [],
          outputs: [],
          ports: [
            {
              name: "p",
              domain: frameCase.domain,
              size: [frameCase.size],
              frame: frameCase.frame,
            },
          ],
          variables: [],
          causality: [{ ports: ["p"], kind: "preferred", value: "flow_out" }],
          dimension: frameCase.size === 3 ? 2 : 3,
        },
      },
    });
  });
  await page.route(/\/api\/check\/model(\?.*)?$/, async (route) => {
    await route.fulfill({
      json: {
        diagnostics: [],
        domains: { c1: frameCase.domain },
        causality: { c1: { strokeAt: "to" } },
        frames: { c1: frameCase.qualified },
        multibond: { c1: frameCase.size === 3 ? 2 : 3 },
        unitFactors: {},
        signals: [],
        stats: { states: frameCase.size, equations: frameCase.size },
      },
    });
  });
}

async function edgePoint(page: Page, id: string): Promise<{ x: number; y: number }> {
  // The edge path is replaced when the inline interface or model check reroutes
  // the bond, so poll until a live path exists.
  let point: { x: number; y: number } | null = null;
  await expect
    .poll(async () => {
      point = await measureEdge(page, id);
      return point !== null;
    }, { timeout: 10_000 })
    .toBe(true);
  if (point === null) {
    throw new Error(`the bond ${id} has no path`);
  }
  return point;
}

async function measureEdge(page: Page, id: string): Promise<{ x: number; y: number } | null> {
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

for (const frameCase of [PLANAR_CASE, SPATIAL_CASE]) {
  test(`the inspector shows the ${frameCase.domain} bond frame and component units`, async ({
    page,
  }) => {
    await stubWorker(page, frameCase);
    project = await createProject(page.request, frameCase.document);
    await page.goto(
      `/?project=${encodeURIComponent(project)}&model=${encodeURIComponent(frameCase.document.name)}`,
    );
    await expect(page.getByTestId("canvas-surface")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("edge-c1")).toBeVisible({ timeout: 30_000 });
    // Wait for the inline interface and the model check: both can move the
    // nodes and reroute the bond, so clicking earlier can miss.
    await expect(page.getByTestId("port-n2-p")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("edge-c1")).toHaveAttribute(
      "data-multibond-strokes",
      frameCase.size === 3 ? "2" : "3",
    );

    // Hover first: the frame pill proves the edge hit area is live and stable.
    let point = await edgePoint(page, "c1");
    await page.mouse.move(Math.round(point.x), Math.round(point.y));
    await expect(page.getByTestId("frame-badge-c1")).toBeVisible({ timeout: 10_000 });

    // Select the bond: the inspector shows the worker's qualified frame, both
    // port frames and what the bond does to them.
    point = await edgePoint(page, "c1");
    await page.mouse.click(Math.round(point.x), Math.round(point.y));
    await expect(page.getByTestId("inspector-connections")).toBeVisible({ timeout: 10_000 });

    const frame = page.getByTestId("inspector-connection-frame-c1");
    await expect(frame).toContainText(frameCase.qualified);
    await expect(frame).toHaveAttribute("data-frame", frameCase.qualified);
    await expect(page.getByTestId("inspector-connection-end-c1-from")).toContainText(
      `${frameCase.ground}/${frameCase.frame}`,
    );
    await expect(page.getByTestId("inspector-connection-end-c1-to")).toContainText(
      frameCase.qualified,
    );
    const explanation = page.getByTestId("inspector-frame-explanation-c1");
    await expect(explanation).toContainText("The model check accepts this bond (no E007)");
    await expect(page.getByTestId("inspector-connection-domain-c1")).toContainText(
      `${frameCase.domain} · ${frameCase.size} components · ${frameCase.size === 3 ? 2 : 3} strokes`,
    );

    // Select the body block: the port frame is qualified for the instance and
    // the effort/flow units are per component, not one port-level unit.
    await page
      .locator(`[data-testid="diagram-node"][data-node-name="${frameCase.body}"]`)
      .click();
    await expect(page.getByTestId("inspector-node")).toBeVisible();

    const portFrame = page.getByTestId("inspector-port-p-frame");
    await expect(portFrame).toContainText(frameCase.frame);
    await expect(portFrame).toContainText(frameCase.qualified);

    const units = page.getByTestId("inspector-port-p-units");
    await expect(units).toContainText(frameCase.effort);
    await expect(units).toContainText(frameCase.flow);
    await expect(
      page.getByTestId(`inspector-signal-${frameCase.body}/p.e[1]`),
    ).toContainText("N*m");
    await expect(
      page.getByTestId(`inspector-signal-${frameCase.body}/p.f[1]`),
    ).toContainText("rad/s");
    // The scalar port-level signal ids are gone for this port.
    await expect(page.getByTestId(`inspector-signal-${frameCase.body}/p.e`)).toHaveCount(0);
  });
}
