import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/**
 * W5.5 acceptance: the 3D View detaches into a same-origin popup that stays in step with the main
 * window (run, bindings, plot cursor, playback time), docks again, and playback of a finished run
 * survives a failing stream socket by loading the run over HTTP.
 *
 * Run with `$env:BGSIM_E2E_PORT="8780"; npx playwright test tests/e2e/viewer-popout.spec.ts`
 * (add `--project=chromium` or `--browser=firefox` as needed).
 */

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "../../..");
const sceneFixture = readFileSync(path.join(here, "..", "fixtures", "scenes", "chain.sdf"), "utf8");

let project = "";

test.beforeEach(async ({ page }) => {
  project = `w55-${Date.now()}-${test.info().workerIndex}`;
  await page.setViewportSize({ width: 1600, height: 1000 });
});

test.afterEach(async ({ request }) => {
  if (project.length > 0) await request.delete(`/api/projects/${project}`);
});

async function store(request: APIRequestContext): Promise<void> {
  expect((await request.post("/api/projects", { data: { name: project } })).status()).toBe(201);
  const model = JSON.parse(
    readFileSync(path.join(repoRoot, "contracts", "fixtures", "model", "valid", "model.rlc.iconic.json"), "utf8"),
  ) as Record<string, unknown>;
  model["scene"] = { file: "scenes/chain.sdf" };
  model["bindings"] = [{ target: "joint:j1", property: "position", signal: "Synthetic/counter", gain: 0.1 }];
  expect((await request.put(`/api/projects/${project}/models/Arm`, { data: model })).status()).toBe(200);
  const put = await request.put(`/api/projects/${project}/scenes/chain.sdf`, {
    data: sceneFixture,
    headers: { "content-type": "application/xml" },
  });
  expect(put.status()).toBe(200);
}

async function openAndRun(page: Page): Promise<void> {
  await page.goto(`/?project=${project}&model=Arm`);
  await expect(page.getByTestId("run-button")).toBeEnabled({ timeout: 30_000 });
  await page.keyboard.press("Control+Enter");
  await expect(page.getByTestId("run-status")).toHaveAttribute("data-status", "done", { timeout: 30_000 });
}

async function plotCounter(page: Page): Promise<void> {
  await page.getByRole("tab", { name: "Signals" }).click();
  await page.locator('[data-signal-id="Synthetic/counter"]').dblclick();
  await page.getByRole("tab", { name: "Plots" }).click();
  await expect(page.locator('[data-testid="plot-chart"] .u-over').first()).toBeVisible();
}

async function inspectTime(page: Page): Promise<number> {
  const text = (await page.getByTestId("plot-inspect-time").textContent()) ?? "";
  return Number.parseFloat(/=\s*([0-9.eE+-]+)/.exec(text)?.[1] ?? "");
}

async function hoverPlot(page: Page, fraction: number): Promise<number> {
  const over = page.locator('[data-testid="plot-chart"] .u-over').first();
  const box = await over.boundingBox();
  if (box === null) throw new Error("the plot has no measurable area");
  await page.mouse.move(box.x + box.width * fraction, box.y + box.height * 0.5, { steps: 4 });
  await expect.poll(async () => inspectTime(page)).toBeGreaterThan(0);
  return inspectTime(page);
}

async function applied(page: Page): Promise<number | undefined> {
  const raw = await page.getByTestId("playback-bar").getAttribute("data-applied");
  return (JSON.parse(raw ?? "{}") as Record<string, number>)["joint:j1"];
}

async function barTime(page: Page): Promise<number> {
  return Number(await page.getByTestId("playback-bar").getAttribute("data-time"));
}

test("the 3D view detaches into a popup that follows the plot cursor, and docks again", async ({ page, request }) => {
  await store(request);
  await openAndRun(page);
  await plotCounter(page);

  await page.getByRole("tab", { name: "3D View" }).click();
  await expect(page.getByTestId("scene-view")).toHaveAttribute("data-state", "loaded", { timeout: 30_000 });
  const popupPromise = page.waitForEvent("popup");
  await page.getByTestId("detach-viewer").click();
  const popup = await popupPromise;

  // the popup shows the scene, the tree and the playback bar; the dock shows a placeholder
  await expect(popup.getByTestId("scene-view")).toHaveAttribute("data-state", "loaded", { timeout: 30_000 });
  await expect(popup.getByTestId("playback-bar")).toHaveAttribute("data-mode", "playback", { timeout: 30_000 });
  await expect(popup.getByTestId("scene-tree")).toBeVisible();
  await expect(page.getByTestId("viewer-detached")).toBeVisible();
  await expect(page.getByTestId("viewer")).toHaveCount(0);

  // the popup is styled (theme tokens apply) and its canvas is a real, sized WebGL canvas
  const canvasBox = await popup.getByTestId("viewer-canvas").boundingBox();
  expect(canvasBox?.width ?? 0).toBeGreaterThan(200);
  expect(canvasBox?.height ?? 0).toBeGreaterThan(200);
  expect(await popup.evaluate(() => getComputedStyle(document.body).backgroundColor)).not.toBe("rgba(0, 0, 0, 0)");

  // scrubbing the plot cursor in the main window moves the popup
  await page.getByRole("tab", { name: "Plots" }).click();
  const t1 = await hoverPlot(page, 0.55);
  await expect.poll(() => barTime(popup)).toBeCloseTo(t1, 2);
  await expect.poll(() => applied(popup)).toBeCloseTo(Math.floor(t1 / 0.1 + 1e-9) * 0.1, 6);
  const t2 = await hoverPlot(page, 0.95);
  expect(t2).toBeGreaterThan(t1);
  await expect.poll(() => applied(popup)).toBeCloseTo(Math.floor(t2 / 0.1 + 1e-9) * 0.1, 6);

  // and the popup's slider moves the plot cursor of the main window
  await popup.getByTestId("playback-time").fill("0.25");
  await expect.poll(() => inspectTime(page)).toBeCloseTo(0.25, 2);

  // Space toggles playback while the popup's stage has focus
  await popup.getByTestId("playback-rewind").click();
  await popup.getByTestId("playback-speed").selectOption("0.25");
  await popup.getByTestId("scene-stage").focus();
  await popup.keyboard.press("Space");
  await expect(popup.getByTestId("playback-bar")).toHaveAttribute("data-playing", "true");
  await expect.poll(() => barTime(popup)).toBeGreaterThan(0.03);
  await popup.keyboard.press("Space");
  await expect(popup.getByTestId("playback-bar")).toHaveAttribute("data-playing", "false");

  // stationary, the popup redraws at most 2 fps (plan 7.5)
  const frames = async (): Promise<number> => Number(await popup.getByTestId("viewer").getAttribute("data-frames"));
  await popup.waitForTimeout(500);
  const f0 = await frames();
  await popup.waitForTimeout(3000);
  expect((await frames()) - f0).toBeLessThanOrEqual(6);

  // Dock restores the tab (and closes the popup)
  // the click closes the page, which Firefox reports as a failed click: deliver it from a timer instead
  await popup.getByTestId("dock-viewer-button").evaluate((el) => {
    setTimeout(() => { (el as HTMLElement).click(); }, 0);
  });
  await expect.poll(async () => popup.isClosed()).toBe(true);
  await page.getByRole("tab", { name: "3D View" }).click();
  await expect(page.getByTestId("viewer-detached")).toHaveCount(0);
  await expect(page.getByTestId("scene-view")).toHaveAttribute("data-state", "loaded", { timeout: 30_000 });
  await expect(page.getByTestId("playback-bar")).toHaveAttribute("data-mode", "playback", { timeout: 30_000 });
});

test("closing the popup docks the 3D view again", async ({ page, request }) => {
  await store(request);
  await openAndRun(page);
  await page.getByRole("tab", { name: "3D View" }).click();
  await expect(page.getByTestId("scene-view")).toHaveAttribute("data-state", "loaded", { timeout: 30_000 });
  const popupPromise = page.waitForEvent("popup");
  await page.getByTestId("detach-viewer").click();
  const popup = await popupPromise;
  await expect(popup.getByTestId("scene-view")).toHaveAttribute("data-state", "loaded", { timeout: 30_000 });
  await expect(page.getByTestId("viewer-detached")).toBeVisible();
  await popup.close();
  await expect(page.getByTestId("viewer-detached")).toHaveCount(0);
  await expect(page.getByTestId("scene-view")).toHaveAttribute("data-state", "loaded", { timeout: 30_000 });
  await expect(page.getByTestId("playback-bar")).toHaveAttribute("data-mode", "playback", { timeout: 30_000 });
});

test("a dropped stream socket falls back to HTTP and the run still plays", async ({ page, request }) => {
  await store(request);
  // every /ws/stream/ socket fails the way a blocked or reset WebSocket does in some browsers: error, then close 1006
  await page.addInitScript(() => {
    const Native = window.WebSocket;
    class Failing extends EventTarget {
      binaryType = "blob";
      readyState = 0;
      onopen: ((e: Event) => void) | null = null;
      onmessage: ((e: MessageEvent) => void) | null = null;
      onerror: ((e: Event) => void) | null = null;
      onclose: ((e: CloseEvent) => void) | null = null;
      constructor() {
        super();
        setTimeout(() => {
          this.readyState = 3;
          this.onerror?.(new Event("error"));
          this.onclose?.(new CloseEvent("close", { code: 1006, reason: "", wasClean: false }));
        }, 20);
      }
      close(): void {
        this.readyState = 3;
      }
      send(): void {
        /* closed */
      }
    }
    const Patched = function (this: unknown, url: string | URL, protocols?: string | string[]) {
      return String(url).includes("/ws/stream/") ? new Failing() : new Native(url, protocols);
    } as unknown as typeof WebSocket;
    Object.assign(Patched, { CONNECTING: 0, OPEN: 1, CLOSING: 2, CLOSED: 3 });
    Patched.prototype = Native.prototype;
    window.WebSocket = Patched;
  });
  await openAndRun(page);
  await page.getByRole("tab", { name: "3D View" }).click();
  await expect(page.getByTestId("scene-view")).toHaveAttribute("data-state", "loaded", { timeout: 30_000 });
  const bar = page.getByTestId("playback-bar");
  await expect(bar).toHaveAttribute("data-mode", "playback", { timeout: 30_000 });
  await expect(page.getByTestId("playback-fallback-note")).toContainText(/dropped \(1006\).*over HTTP/);
  await expect(page.getByTestId("playback-note")).toHaveCount(0);
  const end = await page.getByTestId("playback-readout").textContent();
  expect(Number.parseFloat(/\/\s*([0-9.]+)/.exec(end ?? "")?.[1] ?? "0")).toBeGreaterThan(0);

  // the loaded run drives the scene
  await page.getByTestId("playback-time").fill("0.55");
  await expect.poll(() => applied(page)).toBeCloseTo(0.5, 6);
});
