import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/**
 * The `examples/debug-tour` walkthrough (its Docs tab, page "Walkthrough") against the real Julia worker.
 *
 * The example ships a planted bug: the cart controller `Ctrl` (project:CartPID) has anti-windup off
 * (`aw = 0`), so after the 1 m step at 0.5 s the integrator winds up while the drive is saturated, the
 * cart overshoots and the `@events` limit switch `Limit` trips at t = 1.0937 s. The spec follows the
 * documented steps:
 *
 * 1. Break on Events, Debug: the pause at the trip, on `LimitSwitch` line 24; a watch expression.
 * 2. A line breakpoint on `CartPID` line 30 with the condition `abs(u) > umax`: the pause at t = 0.5 s,
 *    the locals and held outputs, two statement steps (line 31, then line 26 of the next tick).
 * 3. Rewind to here at about 0.45 s (a branch run, paused), the live edit `Ctrl/aw = 1`, Continue: no
 *    event pause, the cart never reaches the switch.
 * 4. Replay equals the session bit for bit; Save parameters to model.
 *
 * Needs the real worker: `$env:BGSIM_E2E_PORT="8794"; $env:BGSIM_E2E_REAL="1"; npx playwright test tests/e2e/debug-tour.spec.ts`.
 */

test.describe.configure({ timeout: 420_000 });

let project = "";

async function waitForWorker(request: APIRequestContext): Promise<void> {
  await expect
    .poll(
      async () => {
        const response = await request.get("/api/health");
        return response.ok() ? ((await response.json()) as { worker: string }).worker : `http ${response.status()}`;
      },
      { message: "the worker becomes ready", timeout: 180_000 },
    )
    .toBe("ready");
}

test.afterEach(async ({ request }) => {
  if (project.length > 0) {
    await request.delete(`/api/projects/${project}`);
    project = "";
  }
});

const STATUS = (page: Page) => page.getByTestId("run-status");

function pauseSeconds(text: string | null): number {
  const match = /Paused at t = ([0-9.eE+-]+) s/.exec(text ?? "");
  expect(match, `a pause status, got ${JSON.stringify(text)}`).not.toBeNull();
  return Number(match?.[1]);
}

async function runId(page: Page): Promise<string> {
  await page.getByRole("tab", { name: "Plots" }).click();
  const id = (await page.getByTestId("plot-run-status").getAttribute("title")) ?? "";
  expect(id).toMatch(/\S/);
  return id;
}

/** The raw (px = 0) series of one signal: `u32 n_signals | u32 n | time | values`. */
async function series(
  request: APIRequestContext,
  id: string,
  signal: string,
): Promise<{ t: Float64Array; y: Float64Array }> {
  const response = await request.get(`/api/runs/${id}/data?ids=${encodeURIComponent(signal)}&px=0`);
  expect(response.status()).toBe(200);
  const body = await response.body();
  const bytes = new Uint8Array(body.byteLength);
  bytes.set(body);
  const view = new DataView(bytes.buffer);
  const n = view.getUint32(4, true);
  return { t: new Float64Array(bytes.buffer, 8, n), y: new Float64Array(bytes.buffer, 8 + 8 * n, n) };
}

const maxOf = (values: Float64Array) => values.reduce((top, value) => Math.max(top, value), -Infinity);

async function clickGutter(page: Page, text: string, button: "left" | "right" = "left"): Promise<void> {
  const line = page.locator(".cm-line", { hasText: text }).first();
  await line.scrollIntoViewIfNeeded();
  const lineBox = await line.boundingBox();
  const gutterBox = await page.locator(".cm-bp-gutter").boundingBox();
  if (lineBox === null || gutterBox === null) throw new Error("the code editor has no measurable gutter");
  await page.mouse.click(gutterBox.x + gutterBox.width / 2, lineBox.y + 9, { button });
}

/** Hover the first plot at the time closest to `target` (the x range is not known up front). */
async function hoverPlotAt(page: Page, target: number): Promise<{ t: number; x: number; y: number }> {
  const over = page.locator('[data-testid="plot-chart"] .u-over').first();
  await expect(over).toBeVisible();
  const box = await over.boundingBox();
  if (box === null) throw new Error("the plot has no measurable area");
  const read = async () => {
    const text = (await page.getByTestId("plot-inspect-time").textContent()) ?? "";
    return Number.parseFloat(/=\s*([0-9.eE+-]+)/.exec(text)?.[1] ?? "");
  };
  let fraction = 0.5;
  let t = Number.NaN;
  for (let attempt = 0; attempt < 4; attempt += 1) {
    await page.mouse.move(box.x + box.width * fraction, box.y + box.height * 0.5, { steps: 4 });
    await expect.poll(read).toBeGreaterThan(0);
    t = await read();
    if (Math.abs(t - target) < 0.02) break;
    fraction = Math.min(0.95, Math.max(0.02, (fraction * target) / t));
  }
  return { t, x: box.width * fraction, y: box.height * 0.5 };
}

test("debug-tour: event pause, conditional line breakpoint, steps, Rewind to here, live fix, Replay", async ({
  page,
  request,
}) => {
  await waitForWorker(request);
  project = `debug-tour-${Date.now()}-${test.info().workerIndex}`;
  const created = await request.post("/api/projects", { data: { name: project, example: "debug-tour" } });
  expect(created.status(), await created.text()).toBe(201);
  await page.setViewportSize({ width: 1700, height: 1000 });
  await page.goto(`/?project=${encodeURIComponent(project)}&model=debug-tour`);
  await expect(page.getByTestId("run-button")).toBeEnabled({ timeout: 60_000 });
  // The Scope probe on the canvas (a model-document probe) opens its plot window.
  await expect(page.locator('[data-testid^="probe-window-"]')).toHaveCount(1);

  // 1. Break on Events, Debug: the pause at the limit switch.
  await page.getByRole("tab", { name: "Debug" }).click();
  await page.getByTestId("break-on-events").check();
  await page.getByTestId("debug-button").click();
  await expect(STATUS(page)).toHaveAttribute("data-status", "paused", { timeout: 180_000 });
  const tTrip = pauseSeconds(await STATUS(page).textContent());
  console.warn(`debug-tour event pause: ${await STATUS(page).textContent()}`);
  expect(Math.abs(tTrip - 1.0937)).toBeLessThan(0.001);
  await expect(page.locator(".cm-line.cm-paused-line")).toContainText("x > x_limit");

  await page.getByRole("tab", { name: "Debug" }).click();
  await page.getByTestId("watch-expression-input").fill('s"Ctrl/z"');
  await page.getByTestId("watch-expression-add").click();
  const watch = page.locator('[data-testid="watch-expression-row"][data-expr=\'s"Ctrl/z"\']');
  await expect(watch.getByTestId("watch-expression-value")).toHaveText(/^0\.27/, { timeout: 20_000 });

  await page.getByTestId("debug-continue").click();
  await expect(STATUS(page)).toHaveAttribute("data-status", "done", { timeout: 120_000 });

  // Rewind to here (step 3) needs a plot in the Plots tab.
  await page.getByRole("tab", { name: "Signals" }).click();
  await page.locator('[data-testid="signal-item"][data-signal-id="Pos/y"]').dblclick();
  await page.getByRole("tab", { name: "Plots" }).click();
  await expect(page.locator('[data-testid="plot-chart"] .u-over').first()).toBeVisible();

  // 2. A conditional line breakpoint in the controller: the first saturated tick.
  await page.getByRole("tab", { name: "Code" }).click();
  await page.getByTestId("code-source-select").selectOption("project:CartPID");
  await expect(page.locator(".cm-content")).toContainText("the drive saturates");
  await clickGutter(page, "the drive saturates");
  const marker = page.locator('[data-testid="bp-marker"][data-line="30"]');
  await expect(marker).toHaveCount(1);
  await clickGutter(page, "the drive saturates", "right");
  await expect(page.getByTestId("bp-popover")).toBeVisible();
  await page.getByTestId("bp-condition").fill("abs(u) > umax");
  await page.getByTestId("bp-apply").click();
  await expect(page.getByTestId("bp-popover")).toHaveCount(0);

  await page.getByTestId("debug-button").click();
  await expect(STATUS(page)).toHaveAttribute("data-status", "paused", { timeout: 120_000 });
  await expect(STATUS(page)).toContainText("Paused at t = 0.5000 s: CartPID line 30 (Ctrl)");
  await expect(marker).toHaveAttribute("data-state", "verified");
  const paused = page.locator(".cm-line.cm-paused-line");
  await expect(paused).toContainText("F = clamp(u, -umax, umax)");

  await page.getByRole("tab", { name: "Debug" }).click();
  await expect(page.getByTestId("var-locals-err-value")).toHaveText(/^1(\.0*)?$/, { timeout: 20_000 });
  await expect(page.getByTestId("var-held-u-value")).toHaveText(/^40\.8/);
  await expect(page.getByTestId("var-held-z-value")).toHaveText(/^0\.01/);

  // Two statement steps: the anti-windup `if` is false, so the next stop is line 26 of the next tick.
  await page.getByRole("tab", { name: "Code" }).click();
  await page.keyboard.press("F10");
  await expect(STATUS(page)).toContainText("CartPID line 31 (Ctrl)", { timeout: 30_000 });
  await expect(paused).toContainText("if aw > 0.5");
  await page.keyboard.press("F10");
  await expect(STATUS(page)).toContainText("Paused at t = 0.5100 s: CartPID line 26 (Ctrl)", { timeout: 30_000 });

  // Remove the line breakpoint (keep Break on Events).
  const put = page.waitForResponse((r) => r.url().includes("/breakpoints") && r.request().method() === "PUT");
  await clickGutter(page, "the drive saturates");
  await put;
  await expect(marker).toHaveCount(0);

  // 3. Rewind to here, before the step.
  await page.getByRole("tab", { name: "Plots" }).click();
  const parent = await runId(page);
  const spot = await hoverPlotAt(page, 0.45);
  expect(spot.t).toBeGreaterThan(0.3);
  expect(spot.t).toBeLessThan(0.5);
  await page
    .locator('[data-testid="plot-chart"] .u-over')
    .first()
    .click({ button: "right", position: { x: spot.x, y: spot.y } });
  await expect(page.getByTestId("plot-rewind")).toBeEnabled();
  await page.getByTestId("plot-rewind").click();
  await expect(STATUS(page)).toHaveAttribute("data-status", "paused", { timeout: 120_000 });
  await expect(STATUS(page)).toContainText("time breakpoint");
  const branchAt = pauseSeconds(await STATUS(page).textContent());
  console.warn(`debug-tour rewind: cursor ${spot.t}, ${await STATUS(page).textContent()}`);
  expect(Math.abs(branchAt - spot.t)).toBeLessThan(0.005);
  const session = await runId(page);
  expect(session).not.toBe(parent);

  // The live fix: Ctrl/aw = 1.
  await page.getByRole("tab", { name: "Diagram", exact: true }).click();
  await page.locator('[data-testid="diagram-node"][data-node-name="Ctrl"]').click();
  await expect(page.getByTestId("inspector-live-banner")).toBeVisible();
  const aw = page.getByTestId("inspector-param-aw");
  await expect(aw).toHaveAttribute("data-live", "true");
  await aw.fill("1");
  await aw.press("Enter");
  await page.getByRole("tab", { name: "Debug" }).click();
  await expect(page.getByTestId("edit-row")).toHaveCount(1);
  await expect(page.getByTestId("edit-row").first()).toContainText("Ctrl/aw = 1");

  // Continue: Break on Events is still on, but the switch never trips any more.
  await page.getByTestId("debug-continue").click();
  await expect(STATUS(page)).toHaveAttribute("data-status", "done", { timeout: 120_000 });
  const fixed = await series(request, session, "Pos/y");
  const tripped = await series(request, session, "Limit/tripped");
  console.warn(`debug-tour fixed session: peak ${maxOf(fixed.y).toFixed(4)} m, tripped ${maxOf(tripped.y)}`);
  expect(maxOf(fixed.y)).toBeLessThan(1.1);
  expect(maxOf(fixed.y)).toBeGreaterThan(1.0);
  expect(maxOf(tripped.y)).toBe(0);
  expect(Math.abs((fixed.y[fixed.y.length - 1] ?? 0) - 1)).toBeLessThan(0.01);

  // 4. Replay equals the session (the edit was made at a time pause); then save the parameter.
  await page.getByRole("tab", { name: "Debug" }).click();
  const replay = page.getByTestId("edits-replay");
  await expect(replay).toBeEnabled({ timeout: 20_000 });
  await replay.click();
  await expect.poll(() => runId(page), { timeout: 60_000 }).not.toBe(session);
  await expect(STATUS(page)).toHaveAttribute("data-status", "done", { timeout: 120_000 });
  const replayed = await series(request, await runId(page), "Pos/y");
  expect(replayed.t.length).toBe(fixed.t.length);
  let differing = 0;
  for (let i = 0; i < fixed.t.length; i += 1) {
    if (replayed.t[i] !== fixed.t[i] || replayed.y[i] !== fixed.y[i]) differing += 1;
  }
  console.warn(`debug-tour replay vs session: ${fixed.t.length} samples, ${differing} differing`);
  expect(differing).toBe(0);

  await page.getByRole("tab", { name: "Debug" }).click();
  await page.getByTestId("edits-save").click();
  await expect(page.getByTestId("edits-message")).toContainText("Saved 1 parameter");
});
