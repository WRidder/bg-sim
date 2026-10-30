import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/**
 * X5.10 acceptance (UI side): the documentation of the example models shows up in the Docs tab.
 * Two examples are copied through `POST /api/projects {name, example}`, their model is opened and
 * the Docs tab must render the page tree, the KaTeX math and the images of the first page, and the
 * model-aware `block:` links must resolve (no broken link). The content itself (links, assets,
 * every math span) is verified by the docs check of `examples/run_checks.py`.
 *
 * Fake worker; the Docs tab needs no Julia.
 * Run with `$env:BGSIM_E2E_PORT="8785"; npx playwright test tests/e2e/example-docs.spec.ts`.
 */

interface Case {
  example: string;
  model: string;
  pages: string[];
}

const CASES: Case[] = [
  { example: "bouncing-ball", model: "bouncing-ball", pages: ["overview", "model", "results"] },
  { example: "dc-motor", model: "iconic", pages: ["overview", "physics", "results"] },
];

const projects: string[] = [];

test.afterEach(async ({ request }: { request: APIRequestContext }) => {
  for (const name of projects.splice(0)) {
    await request.delete(`/api/projects/${name}`);
  }
});

async function openDocs(page: Page, request: APIRequestContext, entry: Case): Promise<void> {
  const name = `x510-${entry.example}-${Date.now()}-${test.info().workerIndex}`;
  const created = await request.post("/api/projects", { data: { name, example: entry.example } });
  expect(created.status(), await created.text()).toBe(201);
  projects.push(name);
  await page.goto(`/?project=${encodeURIComponent(name)}&model=${encodeURIComponent(entry.model)}`);
  await expect(page.getByTestId("canvas-surface")).toBeVisible({ timeout: 30_000 });
  await page.getByRole("tab", { name: "Docs" }).click();
  await expect(page.getByTestId("docs-tab")).toHaveAttribute("data-status", "ready");
}

async function imagesLoaded(page: Page): Promise<number> {
  return page
    .locator('[data-testid="docs-preview"] img')
    .evaluateAll((images) => images.filter((image) => (image as HTMLImageElement).naturalWidth > 0).length);
}

for (const entry of CASES) {
  test(`the docs of ${entry.example}/${entry.model} render with tree, math and images`, async ({ page, request }) => {
    await page.setViewportSize({ width: 1600, height: 1000 });
    await openDocs(page, request, entry);

    // The page tree lists every page of the model, the first one is a root.
    for (const id of entry.pages) {
      await expect(page.getByTestId(`docs-tree-item-${id}`)).toBeVisible();
    }
    await expect(page.getByTestId("docs-empty")).toHaveCount(0);

    // The overview page: math rendered by KaTeX, at least one image that decoded.
    await page.getByTestId("docs-tree-item-overview").click();
    const preview = page.getByTestId("docs-preview");
    await expect(preview).toBeVisible();
    await expect(preview.locator(".katex").first()).toBeVisible({ timeout: 15_000 });
    expect(await preview.locator(".katex").count()).toBeGreaterThan(0);
    await expect.poll(() => imagesLoaded(page), { timeout: 15_000 }).toBeGreaterThan(0);

    // Model-aware links resolve: no broken link or broken image on the page.
    await expect(preview.getByTestId("docs-broken-link")).toHaveCount(0);
    await expect(preview.getByTestId("docs-broken-image")).toHaveCount(0);
    await expect(preview.locator('a[data-link-kind="block"]').first()).toBeVisible();

    // A second page of the tree opens and renders math as well.
    const second = entry.pages[1] ?? "";
    await page.getByTestId(`docs-tree-item-${second}`).click();
    await expect(page.getByTestId(`docs-tree-item-${second}`)).toHaveAttribute("aria-selected", "true");
    await expect(preview.locator(".katex").first()).toBeVisible({ timeout: 15_000 });
    await expect(preview.getByTestId("docs-broken-link")).toHaveCount(0);
  });
}
