import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import type { Model, ModelNode } from "../../src/contracts/model";

/**
 * W2.1 acceptance (plan 7.7): create an inline Equation node in the Code tab,
 * type an equation with `=` (E001), see the squiggle with the hint, fix it,
 * and watch the canvas node gain the ports of the corrected source.
 *
 * `block.check` in this repository's fake worker currently answers
 * `{diagnostics: [], interface: null}`; the real Julia worker is the
 * authority. The contract stub below therefore plays the worker for this one
 * endpoint: E001 while the source has `=` in `@equations`, and an interface
 * with an extra input `w` once it is fixed. Every other call still goes to the
 * running backend.
 */

let project = "";
let serial = 0;

const BROKEN = `@block Equation begin
    @inputs u::Real
    @outputs y::Real
    @equations y = u
end
`;

const FIXED = `@block Equation begin
    @inputs u::Real, w::Real
    @outputs y::Real
    @equations y ~ u + w
end
`;

function emptyModel(name: string): Model {
  return {
    format: "bgsim.model",
    language: "0.1.0",
    name,
    diagram: { nodes: [], connections: [], subsystemPorts: [], annotations: [] },
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

async function createProject(request: APIRequestContext, document: Model): Promise<string> {
  serial += 1;
  const name = `w21e2e-${Date.now()}-${test.info().workerIndex}-${serial}`;
  const created = await request.post("/api/projects", { data: { name } });
  expect(created.ok()).toBeTruthy();
  const stored = await request.put(`/api/projects/${name}/models/${document.name}`, {
    data: document,
  });
  expect(stored.ok()).toBeTruthy();
  return name;
}

function nodeById(document: Model, nodeId: string): ModelNode | undefined {
  return document.diagram.nodes.find((node) => node.id === nodeId);
}

function equalsRange(source: string): { line: number; col: number; endLine: number; endCol: number } {
  const lines = source.split("\n");
  const lineIndex = lines.findIndex((line) => line.includes("="));
  const line = lines[lineIndex] ?? "";
  const index = line.indexOf("=");
  return {
    line: lineIndex + 1,
    col: index + 1,
    endLine: lineIndex + 1,
    endCol: index + 2,
  };
}

async function stubBlockCheck(page: Page): Promise<void> {
  await page.route(/\/api\/check\/block$/, async (route) => {
    const body = route.request().postDataJSON() as { source?: unknown; ref?: unknown };
    const source = typeof body.source === "string" ? body.source : "";
    const ref = typeof body.ref === "string" ? body.ref : "inline:unknown";
    if (/(^|\n)\s*@equations[^\n]*=/.test(source)) {
      const range = equalsRange(source);
      await route.fulfill({
        json: {
          diagnostics: [
            {
              code: "E001",
              severity: "error",
              message: "`=` is not allowed in @equations",
              hint: "use `~` for equations",
              path: null,
              block: ref,
              scope: "@equations",
              source: {
                kind: "inline",
                ref,
                range,
              },
              node: null,
              connection: null,
            },
          ],
          interface: null,
        },
      });
      return;
    }
    await route.fulfill({
      json: {
        diagnostics: [],
        interface: {
          constants: [],
          parameters: [],
          inputs: [
            { name: "u", type: "Real", size: [], unit: null },
            { name: "w", type: "Real", size: [], unit: null },
          ],
          outputs: [{ name: "y", type: "Real", size: [], unit: null }],
          ports: [],
          variables: [],
          causality: [],
        },
      },
    });
  });
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

test("E001 squiggle with its hint, then the canvas node gains the new port", async ({ page }) => {
  await stubBlockCheck(page);
  const document = emptyModel("CodeEntry");
  project = await createProject(page.request, document);
  await page.goto(`/?project=${encodeURIComponent(project)}&model=${encodeURIComponent(document.name)}`);
  await expect(page.getByTestId("library-item-DCMotor")).toBeVisible({ timeout: 30_000 });

  // Open the Code tab and create an inline Equation node.
  await page.getByRole("tab", { name: "Code" }).click();
  await expect(page.getByTestId("code-empty")).toBeVisible();
  await page.getByTestId("code-empty-new-equation").click();

  const editor = page.getByTestId("code-editor");
  await expect(editor).toBeVisible();
  await expect(editor).toHaveAttribute("data-read-only", "false");
  const nodeId = await page.getByTestId("code-tab").getAttribute("data-node-id");
  expect(nodeId).toBeTruthy();
  if (nodeId === null) {
    return;
  }
  await expect(page.getByTestId(`code-open-source`)).toContainText(`inline:${nodeId}`);
  await expect(page.locator(".cm-content")).toContainText("@block Equation");

  // Type the version with `=` in @equations.
  await page.locator(".cm-content").click();
  await page.keyboard.press("Control+a");
  await page.keyboard.insertText(BROKEN);

  // The linter runs 300 ms after the change; the range and the hint must be
  // visible both in the editor and in the diagnostics list.
  const squiggle = page.locator(".cm-lintRange-error").first();
  await expect(squiggle).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId("code-diagnostic-0")).toHaveAttribute("data-code", "E001");
  await expect(page.getByTestId("code-diagnostic-0")).toContainText("use `~` for equations");

  await squiggle.hover();
  const tooltip = page.locator(".cm-tooltip-lint");
  await expect(tooltip).toBeVisible({ timeout: 5_000 });
  await expect(tooltip).toContainText("E001");
  await expect(tooltip).toContainText("use `~` for equations");
  await expect(tooltip.getByText("Use ~ for equations")).toBeVisible();

  // Fix it with the port added.
  await page.locator(".cm-content").click();
  await page.keyboard.press("Control+a");
  await page.keyboard.insertText(FIXED);
  await expect(page.getByTestId("code-diagnostic-0")).toHaveCount(0, { timeout: 10_000 });
  await expect(page.getByTestId("code-no-diagnostics")).toBeVisible({ timeout: 10_000 });
  await expect(page.locator(".cm-lintRange-error")).toHaveCount(0);

  // The source was written through the document store.
  await page.getByRole("tab", { name: "Diagram" }).click();
  const node = page.locator(`[data-testid="diagram-node"][data-node-id="${nodeId}"]`);
  await expect(node).toBeVisible();
  await expect(page.getByTestId(`port-${nodeId}-u`)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId(`port-${nodeId}-w`)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId(`port-${nodeId}-y`)).toBeVisible({ timeout: 10_000 });

  const snapshot = JSON.parse((await page.getByTestId("document-json").textContent()) ?? "null") as Model;
  const inline = nodeById(snapshot, nodeId);
  expect(inline !== undefined && "inline" in inline.block ? inline.block.inline.source : "").toBe(FIXED);
});

test("a stdlib source is read-only and copies into an editable project block", async ({ page }) => {
  await stubBlockCheck(page);
  const document = emptyModel("CopyEntry");
  project = await createProject(page.request, document);
  await page.goto(`/?project=${encodeURIComponent(project)}&model=${encodeURIComponent(document.name)}`);
  await expect(page.getByTestId("library-item-DCMotor")).toBeVisible({ timeout: 30_000 });

  await page.getByRole("tab", { name: "Code" }).click();
  await page.getByTestId("code-source-select").selectOption("stdlib:bondgraph/C");

  await expect(page.getByTestId("code-readonly-banner")).toBeVisible();
  await expect(page.getByTestId("code-editor")).toHaveAttribute("data-read-only", "true");
  await expect(page.locator(".cm-content")).toContainText("@block C begin");
  await expect(page.locator(".cm-content")).toHaveAttribute("contenteditable", "false");

  await page.getByTestId("code-copy-to-library").click();
  await expect(page.getByTestId("code-project-banner")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId("code-editor")).toHaveAttribute("data-read-only", "false");
  await expect(page.locator(".cm-content")).toContainText("@block CCopy begin");
  await expect(page.getByTestId("code-notice")).toContainText("Copied to library/CCopy.jl");
});
