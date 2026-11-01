import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

import { expect, test } from "@playwright/test";

/**
 * The Open dialog (start page), the project overview (model picker) and the
 * model menu of the top bar: open a project or model, start a new project or
 * model, and import a sample as a copy. Samples are read-only templates under
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

  // A new model starts from the project overview (the project name in the top bar).
  await expect(page.getByTestId("canvas-surface")).toBeVisible({ timeout: 30_000 });
  await page.getByTestId("project-crumb").click();
  await expect(page.getByTestId("model-picker")).toHaveAttribute("data-state", "ready", { timeout: 30_000 });
  await expect(page).not.toHaveURL(/model=/);
  await page.getByTestId("picker-new-model-name").fill("Second");
  await page.getByTestId("picker-create-model").click();
  await expect(page).toHaveURL(/model=Second/);
});

test("a project opens on its overview; the model menu lists only its models", async ({ page, request }) => {
  expect((await request.post("/api/projects", { data: { name: project } })).status()).toBe(201);
  const model = JSON.parse(
    readFileSync(
      path.join(repoRoot, "contracts", "fixtures", "model", "valid", "model.rlc.iconic.json"),
      "utf8",
    ),
  ) as Record<string, unknown>;
  for (const name of ["Alpha", "Beta"]) {
    const document = { ...model, name, $comment: `Plan 9.9 (X1.1): the ${name} circuit. More text.` };
    expect((await request.put(`/api/projects/${project}/models/${name}`, { data: document })).status()).toBe(200);
  }

  // The Open dialog's project overview button and the picker cards.
  await page.goto("/");
  await expect(page.getByTestId("start-page")).toHaveAttribute("data-state", "ready", { timeout: 30_000 });
  await page.keyboard.press("Control+o");
  await expect(page.getByTestId("open-dialog")).toBeVisible();
  await page.getByTestId(`project-option-${project}`).click();
  await page.getByTestId("open-project-page").click();
  await expect(page).toHaveURL(new RegExp(`project=${project}$`));
  const picker = page.getByTestId("model-picker");
  await expect(picker).toHaveAttribute("data-state", "ready", { timeout: 30_000 });
  const alpha = page.getByTestId("model-card-Alpha");
  await expect(alpha).toContainText("The Alpha circuit.");
  await expect(alpha).not.toContainText("Plan 9.9");
  await expect(alpha.getByTestId("model-miniature-Alpha")).toBeVisible();

  // Keyboard: Tab reaches the cards and Enter opens one.
  await alpha.focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/model=Alpha/);
  await expect(page.getByTestId("diagram-node")).toHaveCount(6, { timeout: 30_000 });

  // The model menu: this project's models only, the open one marked; Escape closes it.
  await page.getByTestId("open-project").click();
  const menu = page.getByTestId("model-menu");
  await expect(menu).toHaveAttribute("data-state", "ready");
  await expect(menu.getByTestId("model-option-Alpha")).toHaveAttribute("aria-current", "page");
  await expect(menu.getByTestId("model-option-Alpha")).toBeFocused();
  await expect(menu.getByTestId("model-option-Beta")).toBeVisible();
  await expect(page.getByTestId("open-project-list")).toHaveCount(0);
  await page.keyboard.press("Escape");
  await expect(menu).toBeHidden();
  await expect(page.getByTestId("open-project")).toBeFocused();

  await page.keyboard.press("Control+o");
  await menu.getByTestId("model-option-Beta").click();
  await expect(page).toHaveURL(/model=Beta/);
  await expect(page.getByTestId("top-bar")).toContainText("Beta");

  // Another project goes through the start page.
  await page.getByTestId("open-project").click();
  await page.getByTestId("model-menu-home").click();
  await expect(page.getByTestId("start-page")).toBeVisible({ timeout: 30_000 });
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
  const imported = new URL(page.url()).searchParams.get("project") ?? "";
  importedProject = imported;
  expect(imported).toMatch(/^dc-motor(-\d+)?$/);
  // The copy opens on its project overview: a card per model, with the docs picture.
  await expect(page.getByTestId("model-picker")).toHaveAttribute("data-state", "ready", { timeout: 30_000 });
  for (const name of ["iconic", "bondgraph", "speed-control"]) {
    await expect(page.getByTestId(`model-card-${name}`)).toBeVisible();
  }
  const thumb = page.getByTestId("model-thumbnail-iconic");
  await expect
    .poll(() => thumb.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0))
    .toBe(true);
  await page.getByTestId("model-card-iconic").click();
  await expect(page).toHaveURL(/model=iconic/);
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
