import { mkdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

/**
 * Subsystem images (plan 3.3 `ui.image`), fake worker: a large PNG chosen as a file is
 * compressed below 512 KB, a PNG pasted with Ctrl+V on the selected subsystem replaces it,
 * SVG markup pasted with the Paste button lands on the second subsystem, the fit toggles,
 * and everything survives the autosave and a reload. The screenshot shows a PNG (contain)
 * and an SVG (stretch); BGSIM_SCREENSHOT_DIR moves it out of test-results/.
 *
 * Run with `$env:BGSIM_E2E_PORT="8778"; npx playwright test tests/e2e/node-image.spec.ts`.
 */

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "../../..");

// Square on purpose: stretched into the wide card body, the circle becomes an ellipse.
const SVG = [
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40">',
  '<rect x="1" y="1" width="38" height="38" rx="4" fill="#10b981"/>',
  '<circle cx="20" cy="20" r="13" fill="none" stroke="#fff" stroke-width="3"/>',
  "</svg>",
].join("");

let project = "";

test.beforeEach(async ({ page, context }) => {
  project = `node-image-${Date.now()}-${test.info().workerIndex}`;
  await page.setViewportSize({ width: 1600, height: 1000 });
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
});

test.afterEach(async ({ request }) => {
  await request.delete(`/api/projects/${project}`);
});

interface StoredImage {
  mime: string;
  data: string;
  fit: string;
}

async function storedImages(page: Page): Promise<(StoredImage | undefined)[]> {
  const response = await page.request.get(`/api/projects/${project}/models/Dual`);
  expect(response.ok()).toBe(true);
  const model = (await response.json()) as {
    diagram: { nodes: { ui?: { image?: StoredImage } }[] };
  };
  return model.diagram.nodes.map((node) => node.ui?.image);
}

/** A noisy 1600x1200 PNG of several MB, made by the browser's own encoder. */
async function largePng(page: Page): Promise<Buffer> {
  const base64 = await page.evaluate(async () => {
    const canvas = document.createElement("canvas");
    canvas.width = 1600;
    canvas.height = 1200;
    const context = canvas.getContext("2d");
    if (context === null) throw new Error("no 2d context");
    const pixels = context.createImageData(1600, 1200);
    let seed = 12345;
    for (let index = 0; index < pixels.data.length; index += 4) {
      seed = (seed * 1103515245 + 12345) & 0x7fffffff;
      const x = (index / 4) % 1600;
      pixels.data[index] = (x / 1600) * 255;
      pixels.data[index + 1] = seed & 0xff;
      pixels.data[index + 2] = (seed >> 8) & 0xff;
      pixels.data[index + 3] = 255;
    }
    context.putImageData(pixels, 0, 0);
    const blob = await new Promise<Blob>((resolve) => canvas.toBlob((b) => resolve(b as Blob), "image/png"));
    const bytes = new Uint8Array(await blob.arrayBuffer());
    let binary = "";
    for (let start = 0; start < bytes.length; start += 0x8000) {
      binary += String.fromCharCode(...bytes.subarray(start, start + 0x8000));
    }
    return btoa(binary);
  });
  return Buffer.from(base64, "base64");
}

async function selectNode(page: Page, id: string): Promise<void> {
  await page.locator(`[data-testid="diagram-node"][data-node-id="${id}"] .block-node__header`).click();
  await expect(page.getByTestId("inspector-image")).toBeVisible();
}

test("set a subsystem image from a file, Ctrl+V and the Paste button; fit, save and reload", async ({
  page,
}) => {
  expect((await page.request.post("/api/projects", { data: { name: project } })).status()).toBe(201);
  const model = JSON.parse(
    readFileSync(path.join(repoRoot, "examples", "rlc-dual", "models", "rlc-dual.bgmodel.json"), "utf8"),
  ) as { diagram: { nodes: { position: { x: number; y: number } }[] } };
  // Side by side, so one screenshot shows both cards.
  model.diagram.nodes[0]!.position = { x: 80, y: 120 };
  model.diagram.nodes[1]!.position = { x: 320, y: 120 };
  expect((await page.request.put(`/api/projects/${project}/models/Dual`, { data: model })).status()).toBe(200);

  await page.goto(`/?project=${project}&model=Dual`);
  await expect(page.getByTestId("diagram-node")).toHaveCount(2, { timeout: 30_000 });
  await expect(page.getByTestId("node-image-iconic")).toHaveCount(0);

  // 1. A large PNG from the file input is compressed below 512 KB, aspect ratio kept.
  await selectNode(page, "iconic");
  const png = await largePng(page);
  expect(png.length).toBeGreaterThan(2 * 1024 * 1024);
  await page.getByTestId("inspector-image-input").setInputFiles({
    name: "noise.png",
    mimeType: "image/png",
    buffer: png,
  });
  const status = page.getByTestId("inspector-image-status");
  await expect(status).toHaveText(/^Compressed from [\d.]+ MB to \d+ KB, \d+×\d+ (PNG|WebP|JPEG)\.$/, {
    timeout: 20_000,
  });
  const [, width, height] = /, (\d+)×(\d+) /.exec((await status.textContent()) ?? "") ?? [];
  expect(Number(width) / Number(height)).toBeCloseTo(4 / 3, 2);
  await expect(page.getByTestId("node-image-iconic")).toHaveAttribute("data-fit", "contain");
  await expect(page.getByTestId("save-status")).toHaveText("Saved", { timeout: 20_000 });
  const compressed = (await storedImages(page))[0];
  expect(compressed?.fit).toBe("contain");
  expect(Buffer.from(compressed?.data ?? "", "base64").length).toBeLessThanOrEqual(512 * 1024);

  // 2. Ctrl+V on the selected subsystem (focus on the canvas) takes a PNG from the clipboard.
  await page.evaluate(async () => {
    const canvas = document.createElement("canvas");
    canvas.width = 160;
    canvas.height = 80;
    const context = canvas.getContext("2d");
    if (context === null) throw new Error("no 2d context");
    context.fillStyle = "#2563eb";
    context.fillRect(0, 0, 80, 80);
    context.fillStyle = "#f59e0b";
    context.fillRect(80, 0, 80, 80);
    context.fillStyle = "#ffffff";
    context.font = "bold 28px sans-serif";
    context.fillText("PNG", 52, 52);
    const blob = await new Promise<Blob>((resolve) => canvas.toBlob((b) => resolve(b as Blob), "image/png"));
    await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
  });
  await page.locator('[data-testid="diagram-node"][data-node-id="iconic"] .block-node__header').click();
  await page.keyboard.press("Control+V");
  await expect(page.getByTestId("node-image-iconic")).toHaveAttribute("data-mime", "image/png");
  await expect(status).toHaveText("Image set.");
  await expect(page.getByTestId("diagram-node")).toHaveCount(2);

  // 3. The Paste button reads SVG markup copied as text onto the second subsystem.
  await selectNode(page, "bondgraph");
  await page.evaluate((svg) => navigator.clipboard.writeText(svg), SVG);
  await page.getByTestId("inspector-image-paste").click();
  await expect(page.getByTestId("node-image-bondgraph")).toHaveAttribute("data-mime", "image/svg+xml");
  await expect(page.getByTestId("inspector-image-preview")).toHaveAttribute("data-fit", "contain");

  // 4. Fit: stretch, then undo and redo it like any other edit.
  await page.getByTestId("inspector-image-fit").selectOption("stretch");
  await expect(page.getByTestId("node-image-bondgraph")).toHaveAttribute("data-fit", "stretch");
  await page.getByTestId("undo").click();
  await expect(page.getByTestId("node-image-bondgraph")).toHaveAttribute("data-fit", "contain");
  await page.getByTestId("redo").click();
  await expect(page.getByTestId("node-image-bondgraph")).toHaveAttribute("data-fit", "stretch");
  // The Image section with an image is axe-clean.
  const axe = await new AxeBuilder({ page }).include('[data-testid="inspector-image"]').analyze();
  expect(axe.violations.map((violation) => `${violation.id}: ${violation.help}`)).toEqual([]);
  // The SVG is an <img>, never inline markup.
  expect(
    await page.locator('[data-node-id="bondgraph"] .block-node__body--image svg').count(),
  ).toBe(0);

  await expect(page.getByTestId("save-status")).toHaveText("Saved", { timeout: 20_000 });
  const saved = await storedImages(page);
  expect(saved.map((image) => [image?.mime, image?.fit])).toEqual([
    ["image/png", "contain"],
    ["image/svg+xml", "stretch"],
  ]);
  expect(Buffer.from(saved[1]?.data ?? "", "base64").toString("utf8")).toBe(SVG);

  // 5. Reload: both images come back from disk and draw.
  await page.reload();
  await expect(page.getByTestId("diagram-node")).toHaveCount(2, { timeout: 30_000 });
  for (const [id, mime, fit] of [
    ["iconic", "image/png", "contain"],
    ["bondgraph", "image/svg+xml", "stretch"],
  ] as const) {
    const image = page.getByTestId(`node-image-${id}`);
    await expect(image).toHaveAttribute("data-mime", mime);
    await expect(image).toHaveAttribute("data-fit", fit);
    await expect.poll(() => image.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true);
  }
  const contain = await page.getByTestId("node-image-iconic").evaluate((img) => getComputedStyle(img).objectFit);
  const stretch = await page.getByTestId("node-image-bondgraph").evaluate((img) => getComputedStyle(img).objectFit);
  expect([contain, stretch]).toEqual(["contain", "fill"]);

  // Screenshot of both cards: the PNG letterboxed (contain) and the SVG stretched.
  const first = await page.locator('[data-node-id="iconic"]').boundingBox();
  const second = await page.locator('[data-node-id="bondgraph"]').boundingBox();
  expect(first).not.toBeNull();
  expect(second).not.toBeNull();
  const x = Math.min(first!.x, second!.x) - 40;
  const y = Math.min(first!.y, second!.y) - 30;
  const right = Math.max(first!.x + first!.width, second!.x + second!.width) + 40;
  const bottom = Math.max(first!.y + first!.height, second!.y + second!.height) + 30;
  const directory = process.env.BGSIM_SCREENSHOT_DIR ?? path.join(here, "..", "..", "test-results");
  mkdirSync(directory, { recursive: true });
  await page.screenshot({
    path: path.join(directory, "subsystem-images.png"),
    clip: { x, y, width: right - x, height: bottom - y },
  });
  await selectNode(page, "bondgraph");
  await page.getByTestId("inspector-image").screenshot({ path: path.join(directory, "inspector-image.png") });

  // Ctrl+V on a selected subsystem with no image on the clipboard is still the node paste.
  await page.evaluate(() => navigator.clipboard.writeText("not an image"));
  await page.locator('[data-testid="diagram-node"][data-node-id="iconic"] .block-node__header').click();
  await page.keyboard.press("Control+C");
  await page.keyboard.press("Control+V");
  await expect(page.getByTestId("diagram-node")).toHaveCount(3);
  await page.getByTestId("undo").click();
  await expect(page.getByTestId("diagram-node")).toHaveCount(2);

  // Remove takes the image away and the card shows its icon again.
  await selectNode(page, "iconic");
  await page.getByTestId("inspector-image-remove").click();
  await expect(page.getByTestId("node-image-iconic")).toHaveCount(0);
});
