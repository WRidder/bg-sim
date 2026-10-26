import {
  expect,
  test,
  type APIRequestContext,
  type Page,
} from "@playwright/test";

/**
 * W2.2 acceptance against the real worker (`BGSIM_E2E_REAL=1`):
 *
 * 1. create a copy of the `dc-motor` example through the API;
 * 2. open `iconic`, run it and record `Motor1/shaft.f` at t = 1 s;
 * 3. group Ground1, FixHousing and Damp1 (their connections become subsystem
 *    ports), save and reload: the backend accepted the document (PUT 200), the
 *    nested diagram and the edge count persist;
 * 4. enter the subsystem, see its three children, leave with Esc;
 * 5. run again: the grouped instances now live under `Subsystem1/`, but the
 *    motor is outside the group, so `Motor1/shaft.f` is unchanged.
 *
 * The fake worker is rejected exactly like the X1.1 spec: this test is
 * meaningless without Julia.
 */

test.describe.configure({ timeout: 120_000 });

let project = "";

test.beforeEach(async ({ request }) => {
  project = `w22-subsystems-${Date.now()}-${test.info().workerIndex}`;
  const created = await request.post("/api/projects", {
    data: { name: project, example: "dc-motor" },
  });
  expect(created.status(), await created.text()).toBe(201);
});

test.afterEach(async ({ request }) => {
  if (project.length > 0) {
    await request.delete(`/api/projects/${project}`);
    project = "";
  }
});

async function waitForWorker(request: APIRequestContext): Promise<void> {
  await expect
    .poll(
      async () => {
        const response = await request.get("/api/health");
        if (!response.ok()) {
          return `http ${response.status()}`;
        }
        const health = (await response.json()) as {
          worker: string;
          versions: { julia: string | null };
        };
        // `fake` is the fixture-driven worker's ping answer; the real worker
        // reports the Julia version.
        if (health.worker === "ready" && health.versions.julia === "fake") {
          return "fake worker";
        }
        return health.worker;
      },
      {
        message: "the real Julia worker becomes ready",
        timeout: 90_000,
        intervals: [200, 500, 1_000, 2_000],
      },
    )
    .toBe("ready");
}

function node(page: Page, name: string) {
  return page.locator(`[data-testid="diagram-node"][data-node-name="${name}"]`);
}

async function openIconic(page: Page): Promise<void> {
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.goto(`/?project=${encodeURIComponent(project)}&model=iconic`);
  await expect(page.getByTestId("library-item-DCMotor")).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByTestId("run-button")).toBeEnabled();
}

/** Click Run, return the run id from the POST that starts it. */
async function startRun(page: Page): Promise<string> {
  const [created] = await Promise.all([
    page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        response.url().endsWith(`/api/projects/${project}/runs`),
    ),
    page.getByTestId("run-button").click(),
  ]);
  const createdText = await created.text();
  expect(created.status(), createdText).toBe(201);
  const body = JSON.parse(createdText) as { runId?: string };
  if (typeof body.runId !== "string" || body.runId.length === 0) {
    throw new Error("the backend did not return a run id");
  }
  await expect(page.getByTestId("run-status")).toHaveAttribute("data-status", "done", {
    timeout: 90_000,
  });
  return body.runId;
}

/** The last exported sample: t = t_end for the run's 5000-point grid. */
async function shaftSpeedAtEnd(
  request: APIRequestContext,
  runId: string,
): Promise<{ t: number; value: number }> {
  const response = await request.get(
    `/api/runs/${runId}/export.csv?ids=${encodeURIComponent("Motor1/shaft.f")}`,
  );
  const text = await response.text();
  expect(response.status(), text).toBe(200);
  const lines = text.trim().split(/\r?\n/);
  expect(lines[0]?.split(",")[1]).toBe("Motor1/shaft.f");
  const last = lines[lines.length - 1]?.split(",") ?? [];
  return { t: Number(last[0]), value: Number(last[1]) };
}

async function recordShaftSpeed(
  request: APIRequestContext,
  runId: string,
): Promise<{ t: number; value: number }> {
  let sample = { t: Number.NaN, value: Number.NaN };
  await expect
    .poll(
      async () => {
        sample = await shaftSpeedAtEnd(request, runId);
        return Number.isFinite(sample.value);
      },
      { message: "the run data is on disk", timeout: 30_000 },
    )
    .toBe(true);
  expect(Math.abs(sample.t - 1)).toBeLessThan(1e-9);
  return sample;
}

test("groups three elements into Subsystem1 and the run result is unchanged", async ({
  page,
  request,
}) => {
  await waitForWorker(request);
  await openIconic(page);

  const beforeRun = await startRun(page);
  const before = await recordShaftSpeed(request, beforeRun);
  expect(Number.isFinite(before.value)).toBe(true);

  // Select the three auxiliary elements (Ctrl-click adds to the selection).
  await node(page, "Ground1").click();
  await node(page, "FixHousing").click({ modifiers: ["Control"] });
  await node(page, "Damp1").click({ modifiers: ["Control"] });
  await expect(node(page, "Ground1")).toHaveClass(/is-selected/);
  await expect(node(page, "FixHousing")).toHaveClass(/is-selected/);
  await expect(node(page, "Damp1")).toHaveClass(/is-selected/);
  const create = page.getByTestId("create-subsystem");
  await expect(create).toBeEnabled();

  const saved = page.waitForResponse(
    (response) =>
      response.request().method() === "PUT" &&
      response.url().includes(`/api/projects/${project}/models/iconic`),
  );
  await create.click();
  const savedResponse = await saved;
  expect(savedResponse.status(), await savedResponse.text()).toBe(200);
  await expect(page.getByTestId("save-status")).toHaveText("Saved", {
    timeout: 20_000,
  });

  await expect(node(page, "Subsystem1")).toBeVisible();
  await expect(page.getByTestId("diagram-node")).toHaveCount(5);
  await expect(page.locator(".react-flow__edge")).toHaveCount(7);

  // The exposed faces are ordinary power ports on the canvas.
  const subsystemPorts = page.locator(
    '[data-testid="diagram-node"][data-node-name="Subsystem1"] [data-port]',
  );
  await expect(subsystemPorts).toHaveCount(5);
  await expect(
    page.locator(
      '[data-testid="diagram-node"][data-node-name="Subsystem1"] [data-port="Ground1_p"]',
    ),
  ).toHaveAttribute("data-kind", "power");
  await expect(
    page.locator(
      '[data-testid="diagram-node"][data-node-name="Subsystem1"] [data-port="Damp1_a"]',
    ),
  ).toHaveAttribute("data-domain", "Rotation");

  const document = JSON.parse(
    (await page.getByTestId("document-json").textContent()) ?? "null",
  ) as {
    diagram: {
      nodes: {
        id: string;
        name: string;
        block: {
          subsystem?: {
            ports: { name: string; kind: string }[];
            diagram: { nodes: { name: string }[]; connections: unknown[] };
          };
        };
      }[];
      connections: unknown[];
    };
  };
  const subsystem = document.diagram.nodes.find((entry) => entry.name === "Subsystem1");
  if (subsystem === undefined || subsystem.block.subsystem === undefined) {
    throw new Error("the document has no Subsystem1 node");
  }
  const grouped = subsystem.block.subsystem;
  // c3, c4, c5, c6 and c7 cross the boundary; all five become power ports.
  expect(grouped.ports).toHaveLength(5);
  expect(grouped.ports.every((port) => port.kind === "power")).toBe(true);
  expect(grouped.diagram.nodes.map((entry) => entry.name).sort()).toEqual([
    "Damp1",
    "FixHousing",
    "Ground1",
  ]);
  expect(grouped.diagram.connections).toHaveLength(0);
  expect(document.diagram.connections).toHaveLength(7);

  // The document survives a reload.
  await page.reload();
  await expect(page.getByTestId("canvas-surface")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("diagram-node")).toHaveCount(5);
  await expect(page.locator(".react-flow__edge")).toHaveCount(7);
  await expect(node(page, "Subsystem1")).toBeVisible();

  // Double-click enters the nested diagram; the breadcrumb names it and Esc
  // leaves (plan 7.5/7.8). Select first: Playwright's zero-delay double-click
  // races the re-render that the first click's selection causes. The header
  // offset avoids a diagnostics badge over a connection midpoint.
  await node(page, "Subsystem1").click();
  await expect(node(page, "Subsystem1")).toHaveClass(/is-selected/);
  await node(page, "Subsystem1").dblclick({ position: { x: 8, y: 8 } });
  await expect(page.getByTestId("subsystem-breadcrumbs")).toBeVisible();
  await expect(page.getByTestId("breadcrumb-1")).toHaveAttribute(
    "data-breadcrumb-name",
    "Subsystem1",
  );
  await expect(page.getByTestId("diagram-node")).toHaveCount(3);
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("diagram-node")).toHaveCount(5);

  // The same signal at t = 1 s: the motor is outside the group.
  const afterRun = await startRun(page);
  const after = await recordShaftSpeed(request, afterRun);
  expect(Number.isFinite(after.value)).toBe(true);
  expect(Math.abs(after.value - before.value)).toBeLessThan(1e-9);
});
