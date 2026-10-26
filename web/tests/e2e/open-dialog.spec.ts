import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

import { expect, test } from "@playwright/test";

/**
 * The Open dialog: switch projects/models, start a new project or model, and
 * import a sample as a copy. Samples are read-only templates under
 * `examples/`; importing one must never write to the sample tree.
 */

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const DC_MOTOR_SAMPLE = path.join(
  repoRoot,
  "examples",
  "dc-motor",
  "models",
  "iconic.bgmodel.json",
);

let project = "";
let importedProject = "";

test.beforeEach(async ({ page }) => {
  project = `w-open-${Date.now()}-${test.info().workerIndex}`;
  importedProject = "";
  await page.setViewportSize({ width: 1600, height: 1000 });
});

test.afterEach(async ({ request }) => {
  for (const name of [project, importedProject]) {
    if (name.length > 0) {
      await request.delete(`/api/projects/${name}`);
    }
  }
});

test("opens an existing project and model from the dialog", async ({ page, request }) => {
  expect((await request.post("/api/projects", { data: { name: project } })).status()).toBe(201);
  const model = JSON.parse(
    readFileSync(
      path.join(repoRoot, "contracts", "fixtures", "model", "valid", "model.rlc.iconic.json"),
      "utf8",
    ),
  ) as Record<string, unknown>;
  const stored = await request.put(`/api/projects/${project}/models/Alpha`, { data: model });
  expect(stored.status()).toBe(200);

  await page.goto("/");
  await expect(page.getByTestId("open-project")).toBeVisible({ timeout: 30_000 });
  await page.getByTestId("open-project").click();
  await expect(page.getByTestId("open-dialog")).toBeVisible();
  await expect(page.getByTestId("open-project-list")).toBeVisible();
  await page.getByTestId(`project-option-${project}`).click();
  await page.getByTestId("model-option-Alpha").click();

  await expect(page).toHaveURL(new RegExp(`project=${project}`));
  await expect(page).toHaveURL(/model=Alpha/);
  await expect(page.getByTestId("diagram-node")).toHaveCount(6, { timeout: 30_000 });
});

test("creates a new project and a new model", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("open-project")).toBeVisible({ timeout: 30_000 });

  await page.getByTestId("open-project").click();
  await expect(page.getByTestId("new-project-name")).toBeVisible();
  await page.getByTestId("new-project-name").fill(project);
  await page.getByTestId("create-project").click();

  await expect(page).toHaveURL(new RegExp(`project=${project}`));
  await expect(page).toHaveURL(/model=Model1/);

  await page.getByTestId("open-project").click();
  await page.getByTestId("new-model-name").fill("Second");
  await page.getByTestId("create-model").click();
  await expect(page).toHaveURL(/model=Second/);
});

test("imports a sample as a copy and never writes to the sample", async ({ page, request }) => {
  const sampleBefore = readFileSync(DC_MOTOR_SAMPLE, "utf8");
  await page.goto("/");
  await expect(page.getByTestId("open-project")).toBeVisible({ timeout: 30_000 });

  await page.getByTestId("open-project").click();
  await expect(page.getByTestId("sample-option-dc-motor")).toBeVisible();
  await expect(page.getByTestId("sample-option-drivetrain")).toBeVisible();
  const sample = page.getByTestId("sample-option-dc-motor");
  await expect(sample).toBeVisible();
  await sample.click();

  await expect(page).toHaveURL(/project=dc-motor/);
  await expect(page).toHaveURL(/model=iconic/);
  const imported = new URL(page.url()).searchParams.get("project") ?? "";
  importedProject = imported;
  expect(imported).toMatch(/^dc-motor(-\d+)?$/);
  await expect(page.getByTestId("diagram-node")).toHaveCount(7, { timeout: 30_000 });

  // The sample in the repository is untouched.
  expect(readFileSync(DC_MOTOR_SAMPLE, "utf8")).toBe(sampleBefore);

  // The opened project is a copy in the projects root, not the sample tree.
  const opened = (await (await request.get(`/api/projects/${imported}`)).json()) as {
    path: string;
  };
  expect(opened.path).not.toContain(`${path.sep}examples${path.sep}`);
  expect(opened.path).toContain(imported);
});
