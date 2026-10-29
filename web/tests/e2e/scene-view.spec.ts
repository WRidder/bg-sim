import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type APIRequestContext } from "@playwright/test";

/**
 * W5.2 acceptance (plan 7.6): a model whose `scene` names an SDF file shows that scene in the
 * 3D View, lists its links, joints and visuals as a tree, and reports unsupported SDF elements
 * (E306) in the Diagnostics tab. Fake worker; the scene is stored through `PUT /scenes/{file}`.
 *
 * Run with `$env:BGSIM_E2E_PORT="8775"; npx playwright test tests/e2e/scene-view.spec.ts`.
 */

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "../../..");
const sceneFixture = (name: string): string => readFileSync(path.join(here, "..", "fixtures", "scenes", name), "utf8");

let project = "";

test.beforeEach(async ({ page }) => {
  project = `w52-${Date.now()}-${test.info().workerIndex}`;
  await page.setViewportSize({ width: 1600, height: 1000 });
});

test.afterEach(async ({ request }) => {
  if (project.length > 0) await request.delete(`/api/projects/${project}`);
});

async function store(request: APIRequestContext, scene: string | null, sdf?: string): Promise<void> {
  expect((await request.post("/api/projects", { data: { name: project } })).status()).toBe(201);
  const model = JSON.parse(
    readFileSync(path.join(repoRoot, "contracts", "fixtures", "model", "valid", "model.rlc.iconic.json"), "utf8"),
  ) as Record<string, unknown>;
  if (scene !== null) model["scene"] = { file: `scenes/${scene}` };
  expect((await request.put(`/api/projects/${project}/models/Arm`, { data: model })).status()).toBe(200);
  if (scene !== null && sdf !== undefined) {
    const put = await request.put(`/api/projects/${project}/scenes/${scene}`, {
      data: sdf,
      headers: { "content-type": "application/xml" },
    });
    expect(put.status()).toBe(200);
  }
}

test("shows the scene of the open model with its tree, and selecting a row outlines it", async ({ page, request }) => {
  await store(request, "chain.sdf", sceneFixture("chain.sdf"));
  await page.goto(`/?project=${project}&model=Arm`);
  await page.getByRole("tab", { name: "3D View" }).click();

  const view = page.getByTestId("scene-view");
  await expect(view).toHaveAttribute("data-state", "loaded", { timeout: 30_000 });
  await expect(page.getByTestId("viewer")).toHaveAttribute("data-state", "idle", { timeout: 30_000 });

  for (const ref of ["model:chain", "link:base", "link:l1", "link:l2", "joint:j1", "joint:j2", "visual:l2_visual"]) {
    await expect(page.getByTestId(`scene-tree-row-${ref}`)).toBeVisible();
  }
  await expect(page.getByTestId("scene-tree-row-joint:j1")).toHaveAttribute("data-kind", "joint");

  const row = page.getByTestId("scene-tree-row-link:l1");
  await row.click();
  await expect(row).toHaveAttribute("aria-pressed", "true");
  await row.click();
  await expect(row).toHaveAttribute("aria-pressed", "false");

  await page.getByRole("tab", { name: /^Diagnostics/ }).click();
  await expect(page.getByTestId("diagnostics-panel")).toBeVisible();
  // the fake worker answers model.check with the shared sample (which names scenes/arm.sdf); this scene reports nothing
  await expect(page.getByTestId("diagnostics-panel")).not.toContainText("scenes/chain.sdf");
});

test("lists E306 in the Diagnostics tab when the scene uses an unsupported joint", async ({ page, request }) => {
  const sdf = `<?xml version="1.0"?>
<sdf version="1.7"><model name="m">
  <link name="a"><visual name="v"><geometry><box><size>1 1 1</size></box></geometry></visual></link>
  <link name="b"/>
  <joint name="wrist" type="ball"><parent>a</parent><child>b</child></joint>
</model></sdf>`;
  await store(request, "ball.sdf", sdf);
  await page.goto(`/?project=${project}&model=Arm`);
  await page.getByRole("tab", { name: "3D View" }).click();
  await expect(page.getByTestId("scene-view")).toHaveAttribute("data-state", "loaded", { timeout: 30_000 });

  await page.getByRole("tab", { name: /^Diagnostics/ }).click();
  await expect(page.getByTestId("diagnostics-panel")).toContainText("unsupported SDF element skipped", { timeout: 30_000 });
  await expect(page.getByTestId("diagnostics-panel")).toContainText("wrist");
});

test("explains how to add a scene when the model has none, and reports a missing scene file as E305", async ({ page, request }) => {
  await store(request, null);
  await page.goto(`/?project=${project}&model=Arm`);
  await page.getByRole("tab", { name: "3D View" }).click();
  await expect(page.getByTestId("scene-view")).toHaveAttribute("data-state", "none", { timeout: 30_000 });
  await expect(page.getByText(/scenes\/ folder/)).toBeVisible();

  const missing = `${project}-missing`;
  expect((await request.post("/api/projects", { data: { name: missing } })).status()).toBe(201);
  try {
    const model = JSON.parse(
      readFileSync(path.join(repoRoot, "contracts", "fixtures", "model", "valid", "model.rlc.iconic.json"), "utf8"),
    ) as Record<string, unknown>;
    model["scene"] = { file: "scenes/gone.sdf" };
    expect((await request.put(`/api/projects/${missing}/models/Arm`, { data: model })).status()).toBe(200);
    await page.goto(`/?project=${missing}&model=Arm`);
    await page.getByRole("tab", { name: "3D View" }).click();
    await expect(page.getByTestId("scene-view")).toHaveAttribute("data-state", "error", { timeout: 30_000 });
    await page.getByRole("tab", { name: /^Diagnostics/ }).click();
    await expect(page.getByTestId("diagnostics-panel")).toContainText("scene file could not be loaded or parsed");
  } finally {
    await request.delete(`/api/projects/${missing}`);
  }
});
