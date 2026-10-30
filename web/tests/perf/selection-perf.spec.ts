/**
 * Canvas selection cost on a large diagram (fake worker): the panda example's
 * 81-node model. Two numbers:
 *
 *  1. a box selection dragged across the whole diagram: the longest frame and
 *     the long-task time while the rectangle moves;
 *  2. a click on a node: the time from the click to the node showing as
 *     selected and to the inspector naming it.
 *
 * The results are printed and attached to the report; the budgets are loose
 * on purpose (a shared CI machine), they catch a regression to a full diagram
 * rebuild per pointer move.
 *
 * Run with `npx playwright test tests/perf/selection-perf.spec.ts` from `web/`.
 */

import { expect, test, type Page } from "@playwright/test";

test.describe.configure({ timeout: 120_000 });

const MAX_FRAME_MS = 100;
const CLICK_BUDGET_MS = 150;

let project = "";

test.beforeEach(async ({ page }) => {
  project = `selection-perf-${Date.now()}-${test.info().workerIndex}`;
  await page.setViewportSize({ width: 1600, height: 1000 });
  const created = await page.request.post("/api/projects", {
    data: { name: project, example: "panda-3d" },
  });
  expect(created.status(), await created.text()).toBe(201);
});

test.afterEach(async ({ request }) => {
  if (project.length > 0) {
    await request.delete(`/api/projects/${project}`);
  }
});

async function openPanda(page: Page): Promise<number> {
  await page.goto(`/?project=${encodeURIComponent(project)}&model=panda-free`);
  const nodes = page.getByTestId("diagram-node");
  await expect(nodes.first()).toBeVisible({ timeout: 30_000 });
  await page.getByTestId("fit-view").click();
  await page.waitForTimeout(400);
  return nodes.count();
}

interface FrameStats {
  frames: number;
  maxFrameMs: number;
  meanFrameMs: number;
  longTaskMs: number;
}

async function startRecording(page: Page): Promise<void> {
  await page.evaluate(() => {
    const state = { frames: [] as number[], longTask: 0, running: true };
    (window as unknown as { __selectionPerf: typeof state }).__selectionPerf = state;
    const observer = new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        state.longTask += entry.duration;
      }
    });
    observer.observe({ type: "longtask", buffered: false });
    const tick = (time: number) => {
      state.frames.push(time);
      if (state.running) {
        requestAnimationFrame(tick);
      } else {
        observer.disconnect();
      }
    };
    requestAnimationFrame(tick);
  });
}

async function stopRecording(page: Page): Promise<FrameStats> {
  return page.evaluate(async () => {
    const state = (
      window as unknown as {
        __selectionPerf: { frames: number[]; longTask: number; running: boolean };
      }
    ).__selectionPerf;
    await new Promise((resolve) => requestAnimationFrame(() => resolve(null)));
    state.running = false;
    const gaps = state.frames.slice(1).map((time, index) => time - (state.frames[index] ?? time));
    return {
      frames: state.frames.length,
      maxFrameMs: Math.max(0, ...gaps),
      meanFrameMs: gaps.reduce((sum, gap) => sum + gap, 0) / Math.max(1, gaps.length),
      longTaskMs: state.longTask,
    };
  });
}

test("a box selection over 80 nodes stays responsive; a click selects quickly", async ({
  page,
}, testInfo) => {
  const count = await openPanda(page);
  expect(count).toBeGreaterThan(60);
  const pane = await page.locator(".react-flow__pane").boundingBox();
  if (pane === null) {
    throw new Error("the pane is not visible");
  }

  // 1. A box from the top-left corner across the diagram and back.
  const from = { x: pane.x + 4, y: pane.y + 4 };
  await page.mouse.move(from.x, from.y);
  await startRecording(page);
  const started = Date.now();
  await page.mouse.down();
  for (let step = 1; step <= 60; step += 1) {
    const f = step <= 40 ? step / 40 : 1 - (step - 40) / 40;
    await page.mouse.move(from.x + f * (pane.width - 12), from.y + f * (pane.height - 12));
  }
  await page.mouse.up();
  const dragMs = Date.now() - started;
  const box = await stopRecording(page);
  const selected = await page.locator('[data-testid="diagram-node"].is-selected').count();
  expect(selected).toBeGreaterThan(10);
  await expect(page.locator(".react-flow__selection")).toHaveCount(0);

  // 2. Clicks on a few nodes: click to the selected class and to the inspector.
  await page.locator(".react-flow__pane").click({ position: { x: 4, y: pane.height - 4 } });
  const clicks: { selectedMs: number; inspectorMs: number }[] = [];
  const names = await page
    .locator('[data-testid="diagram-node"]')
    .evaluateAll((elements) =>
      elements.slice(0, 40).map((element) => element.getAttribute("data-node-name") ?? ""),
    );
  for (const name of names.filter((_, index) => index % 8 === 3)) {
    const target = page.locator(`[data-testid="diagram-node"][data-node-name="${name}"]`);
    const point = await target.boundingBox();
    if (point === null) {
      continue;
    }
    await page.evaluate((nodeName) => {
      const element = document.querySelector(
        `[data-testid="diagram-node"][data-node-name="${nodeName}"]`,
      );
      const result = { start: 0, selected: 0, inspector: 0 };
      (window as unknown as { __click: typeof result }).__click = result;
      window.addEventListener("pointerdown", () => (result.start = performance.now()), {
        capture: true,
        once: true,
      });
      const check = () => {
        const now = performance.now();
        if (result.selected === 0 && element?.classList.contains("is-selected") === true) {
          result.selected = now;
        }
        const field = document.querySelector<HTMLInputElement>('[data-testid="inspector-name"]');
        if (result.inspector === 0 && field?.value === nodeName) {
          result.inspector = now;
        }
      };
      const observer = new MutationObserver(check);
      observer.observe(document.body, { subtree: true, attributes: true, childList: true });
      setTimeout(() => observer.disconnect(), 3_000);
    }, name);
    await page.mouse.click(point.x + point.width / 2, point.y + Math.min(8, point.height / 2));
    await expect(page.getByTestId("inspector-name")).toHaveValue(name);
    const timing = await page.evaluate(() => {
      const result = (window as unknown as { __click: { start: number; selected: number; inspector: number } })
        .__click;
      return {
        selectedMs: result.selected - result.start,
        inspectorMs: result.inspector - result.start,
      };
    });
    clicks.push(timing);
  }

  const report = {
    nodes: count,
    boxSelected: selected,
    box: { ...box, dragMs },
    clicks,
  };
  console.warn(`[perf] canvas selection: ${JSON.stringify(report)}`);
  await testInfo.attach("selection-perf.json", {
    body: JSON.stringify(report, null, 2),
    contentType: "application/json",
  });
  expect(box.maxFrameMs).toBeLessThan(MAX_FRAME_MS);
  for (const click of clicks) {
    expect(click.inspectorMs).toBeLessThan(CLICK_BUDGET_MS);
  }
});
