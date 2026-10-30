import { expect, test, type APIRequestContext, type Locator, type Page } from "@playwright/test";

/**
 * X4.1 acceptance: the M4 debugging walkthrough against the real Julia worker (plan 7.9, 9.1, 9.5).
 *
 * 1. drivetrain-kalman: a line breakpoint in `LQGController` (line 41), the Variables section shows the
 *    vector `xhat`, three statement steps move the highlighted line (42, 43, 44), continue to the end.
 * 2. bouncing-ball: break on events, pause at the first bounce (t ~ 0.4515 s), change the restitution
 *    `Ball1/e` to 0.6 live, continue, then Replay; the replay's data equals the session's, bit for bit,
 *    and differs from an unedited run.
 * 3. dc-motor: "Break when" `Motor1/i > 5` from the signal browser, the pause at t ~ 0.0105 s,
 *    "Rewind to here" at an earlier cursor time (a branch run), and Explain on the eliminated `Motor1/i`.
 *
 * Needs the real worker: `$env:BGSIM_E2E_PORT="8794"; $env:BGSIM_E2E_REAL="1"; npx playwright test tests/e2e/debug.spec.ts`.
 * Breakpoints are editor state in localStorage; every test starts with a fresh browser context.
 */

test.describe.configure({ timeout: 420_000, mode: "serial" });

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

async function createProject(request: APIRequestContext, example: string): Promise<void> {
  await waitForWorker(request);
  project = `x41-${example}-${Date.now()}-${test.info().workerIndex}`;
  const created = await request.post("/api/projects", { data: { name: project, example } });
  expect(created.status(), await created.text()).toBe(201);
}

test.afterEach(async ({ request }) => {
  if (project.length > 0) {
    await request.delete(`/api/projects/${project}`);
    project = "";
  }
});

const STATUS = (page: Page) => page.getByTestId("run-status");

async function open(page: Page, model: string): Promise<void> {
  await page.setViewportSize({ width: 1700, height: 1000 });
  await page.goto(`/?project=${encodeURIComponent(project)}&model=${model}`);
  await expect(page.getByTestId("run-button")).toBeEnabled({ timeout: 60_000 });
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
  expect(view.getUint32(0, true)).toBe(1);
  return { t: new Float64Array(bytes.buffer, 8, n), y: new Float64Array(bytes.buffer, 8 + 8 * n, n) };
}

async function clickGutter(page: Page, text: string): Promise<void> {
  const line = page.locator(".cm-line", { hasText: text }).first();
  await line.scrollIntoViewIfNeeded();
  const lineBox = await line.boundingBox();
  const gutterBox = await page.locator(".cm-bp-gutter").boundingBox();
  expect(lineBox).not.toBeNull();
  expect(gutterBox).not.toBeNull();
  if (lineBox === null || gutterBox === null) return;
  await page.mouse.click(gutterBox.x + gutterBox.width / 2, lineBox.y + 9);
}

async function signalMenu(page: Page, signalId: string, item: "break-when" | "explain-signal"): Promise<void> {
  await page.getByRole("tab", { name: "Signals" }).click();
  const row = page.locator(`[data-testid="signal-item"][data-signal-id="${signalId}"]`);
  await expect(row).toHaveCount(1);
  await row.click({ button: "right" });
  await expect(page.getByTestId("signal-menu")).toBeVisible();
  await page.getByTestId("signal-menu").getByTestId(item).click();
}

function pauseSeconds(text: string | null): number {
  const match = /Paused at t = ([0-9.eE+-]+) s/.exec(text ?? "");
  expect(match, `a pause status, got ${JSON.stringify(text)}`).not.toBeNull();
  return Number(match?.[1]);
}

async function hoverPlot(page: Page, fraction: number): Promise<number> {
  const over = page.locator('[data-testid="plot-chart"] .u-over').first();
  await expect(over).toBeVisible();
  const box = await over.boundingBox();
  if (box === null) throw new Error("the plot has no measurable area");
  await page.mouse.move(box.x + box.width * fraction, box.y + box.height * 0.5, { steps: 4 });
  const read = async () => {
    const text = (await page.getByTestId("plot-inspect-time").textContent()) ?? "";
    return Number.parseFloat(/=\s*([0-9.eE+-]+)/.exec(text)?.[1] ?? "");
  };
  await expect.poll(read).toBeGreaterThan(0);
  return read();
}

test("drivetrain-kalman: line breakpoint, xhat, three statement steps, continue to the end", async ({
  page,
  request,
}) => {
  await createProject(request, "drivetrain-kalman");
  await open(page, "drivetrain-kalman");

  await page.getByRole("tab", { name: "Code" }).click();
  const select = page.getByTestId("code-source-select");
  await expect(select.locator('option[value="project:LQGController"]')).toHaveCount(1);
  await select.selectOption("project:LQGController");
  await expect(page.locator(".cm-content")).toContainText("measurement update");
  await clickGutter(page, "measurement update");
  await expect(page.locator('[data-testid="bp-marker"][data-line="41"]')).toHaveCount(1);

  await page.getByTestId("debug-button").click();
  await expect(STATUS(page)).toHaveAttribute("data-status", "paused", { timeout: 180_000 });
  await expect(STATUS(page)).toContainText("LQGController line 41 (LQG)");
  const paused = page.locator(".cm-line.cm-paused-line");
  await expect(paused).toHaveCount(1);
  await expect(paused).toContainText("measurement update");
  await expect(page.locator('[data-testid="bp-marker"][data-line="41"]')).toHaveAttribute(
    "data-state",
    "verified",
  );
  console.warn(`X4.1 test 1 pause: ${await STATUS(page).textContent()}`);

  // xhat in the Variables section: a non-empty numeric vector.
  await page.getByRole("tab", { name: "Debug" }).click();
  await expect(page.getByTestId("debug-panel")).toBeVisible();
  const xhat = page.locator('[data-testid^="var-"][data-testid$="-xhat"]').first();
  await expect(xhat).toBeVisible({ timeout: 20_000 });
  const summary = (await xhat.textContent()) ?? "";
  expect(summary).toMatch(/xhat/);
  expect(summary).toMatch(/\d/);
  await xhat.locator("summary").click();
  const elements = xhat.locator(".debug-var__elements .debug-var__value");
  expect(await elements.count()).toBeGreaterThanOrEqual(2);
  for (const text of await elements.allTextContents()) {
    expect(text).toMatch(/\d/);
  }

  // Three statements (F10): the highlighted line moves each time.
  await page.getByRole("tab", { name: "Code" }).click();
  const expected: [number, string][] = [
    [42, "integral of the load-speed error"],
    [43, "Kff * w_ref"],
    [45, "u = clamp(v, -umax, umax)"],
  ];
  for (const [line, text] of expected) {
    await page.keyboard.press("F10");
    await expect(STATUS(page)).toContainText(`LQGController line ${line} (LQG)`, { timeout: 30_000 });
    await expect(paused).toHaveCount(1);
    await expect(paused).toContainText(text);
  }

  // Remove the breakpoint and run to the end.
  const put = page.waitForResponse((r) => r.url().includes("/breakpoints") && r.request().method() === "PUT");
  await clickGutter(page, "measurement update");
  await put;
  await page.waitForTimeout(300);
  await page.keyboard.press("F5");
  await expect(STATUS(page)).toHaveAttribute("data-status", "done", { timeout: 180_000 });
  await expect(paused).toHaveCount(0);
});

test("bouncing-ball: event pause, live e = 0.6, continue, Replay equals the session", async ({
  page,
  request,
}) => {
  await createProject(request, "bouncing-ball");
  await open(page, "bouncing-ball");

  // The unedited reference run (e = 0.8).
  await page.keyboard.press("Control+Enter");
  await expect(STATUS(page)).toHaveAttribute("data-status", "done", { timeout: 180_000 });
  const baseline = await runId(page);
  const base = await series(request, baseline, "Ball1/h");

  await page.getByRole("tab", { name: "Debug" }).click();
  await page.getByTestId("break-on-events").check();
  await page.getByTestId("debug-button").click();
  await expect(STATUS(page)).toHaveAttribute("data-status", "paused", { timeout: 60_000 });
  const tPause = pauseSeconds(await STATUS(page).textContent());
  console.warn(`X4.1 test 2 event pause: ${await STATUS(page).textContent()}`);
  expect(Math.abs(tPause - 0.4515)).toBeLessThan(0.002);

  // Live edit: Ball1/e = 0.6.
  // The pause opened the Code tab at the event line; go back to the diagram to select the instance.
  await page.getByRole("tab", { name: "Diagram", exact: true }).click();
  await page.locator('[data-testid="diagram-node"][data-node-name="Ball1"]').click();
  await expect(page.getByTestId("inspector-live-banner")).toBeVisible();
  const e = page.getByTestId("inspector-param-e");
  await expect(e).toHaveAttribute("data-live", "true");
  await e.fill("0.6");
  await e.press("Enter");
  await page.getByRole("tab", { name: "Debug" }).click();
  const rows = page.getByTestId("edit-row");
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toContainText("Ball1/e = 0.6");

  // Stop breaking on every bounce, then run to the end.
  await page.getByTestId("break-on-events").uncheck();
  await page.waitForTimeout(500);
  await page.getByTestId("debug-continue").click();
  await expect(STATUS(page)).toHaveAttribute("data-status", "done", { timeout: 120_000 });
  const session = await runId(page);
  expect(session).not.toBe(baseline);
  const sess = await series(request, session, "Ball1/h");

  // The edit applies after the first bounce: the second rebound apex is 0.2304 m (e = 0.6), not 0.4096 m (0.8).
  const apex = (data: { t: Float64Array; y: Float64Array }) => {
    let top = -Infinity;
    for (let i = 0; i < data.t.length; i += 1) {
      const t = data.t[i] ?? 0;
      if (t > 1.2 && t < 1.8) top = Math.max(top, data.y[i] ?? 0);
    }
    return top;
  };
  const apexBase = apex(base);
  const apexSession = apex(sess);
  console.warn(`X4.1 test 2 second apex: unedited ${apexBase.toFixed(4)} m, session ${apexSession.toFixed(4)} m`);
  expect(Math.abs(apexBase - 0.4096)).toBeLessThan(0.02);
  expect(Math.abs(apexSession - 0.2304)).toBeLessThan(0.02);

  // Replay: a new run with the edit applied; its data equals the session's.
  await page.getByRole("tab", { name: "Debug" }).click();
  const replay = page.getByTestId("edits-replay");
  await expect(replay).toBeEnabled({ timeout: 20_000 });
  await replay.click();
  await expect.poll(() => runId(page), { timeout: 60_000 }).not.toBe(session);
  await page.getByRole("tab", { name: "Debug" }).click();
  await expect(STATUS(page)).toHaveAttribute("data-status", "done", { timeout: 120_000 });
  const replayId = await runId(page);
  expect(replayId).not.toBe(baseline);
  const rep = await series(request, replayId, "Ball1/h");
  expect(rep.t.length).toBe(sess.t.length);
  let differing = 0;
  for (let i = 0; i < rep.t.length; i += 1) {
    if (rep.t[i] !== sess.t[i] || rep.y[i] !== sess.y[i]) differing += 1;
  }
  console.warn(`X4.1 test 2 replay vs session: ${rep.t.length} samples, ${differing} differing`);
  expect(differing).toBe(0);
});

test("dc-motor: Break when Motor1/i > 5, Rewind to here, Explain on the eliminated current", async ({
  page,
  request,
}) => {
  await createProject(request, "dc-motor");
  await open(page, "iconic");

  await page.keyboard.press("Control+Enter");
  await expect(STATUS(page)).toHaveAttribute("data-status", "done", { timeout: 180_000 });
  await page.getByRole("tab", { name: "Signals" }).click();
  await page.locator('[data-testid="signal-item"][data-signal-id="Motor1/i"]').dblclick();

  // Break when Motor1/i > 5.
  await signalMenu(page, "Motor1/i", "break-when");
  await expect(page.getByTestId("break-when-dialog")).toBeVisible();
  await page.getByTestId("break-when-comparison").selectOption(">");
  await page.getByTestId("break-when-value").fill("5");
  await page.getByTestId("break-when-add").click();
  await expect(page.getByTestId("break-when-dialog")).toHaveCount(0);

  await page.getByTestId("debug-button").click();
  await expect(STATUS(page)).toHaveAttribute("data-status", "paused", { timeout: 120_000 });
  const tPause = pauseSeconds(await STATUS(page).textContent());
  console.warn(`X4.1 test 3 watch pause: ${await STATUS(page).textContent()}`);
  expect(tPause).toBeGreaterThan(0.0104);
  expect(tPause).toBeLessThan(0.0112);

  await page.getByRole("tab", { name: "Debug" }).click();
  const row = page.getByTestId("breakpoint-row").first();
  await expect(row).toHaveAttribute("data-kind", "watch");
  await expect(row).toHaveAttribute("data-verified", "true");
  const current = page.locator(
    '[data-testid="var-signal"][data-signal-id="Motor1/i"] [data-testid="var-signal-value"]',
  );
  await expect(current).toHaveText(/^5(\.\d*)?$/, { timeout: 20_000 });

  // Rewind to here at an earlier cursor time (about 0.005 s).
  await page.getByRole("tab", { name: "Plots" }).click();
  const parent = await runId(page);
  const over: Locator = page.locator('[data-testid="plot-chart"] .u-over').first();
  await expect(over).toBeVisible();
  const box = await over.boundingBox();
  if (box === null) throw new Error("the plot has no measurable area");
  const t = await hoverPlot(page, 0.45);
  expect(t).toBeGreaterThan(0.003);
  expect(t).toBeLessThan(tPause);
  await over.click({ button: "right", position: { x: box.width * 0.45, y: 60 } });
  const item = page.getByTestId("plot-rewind");
  await expect(item).toBeEnabled();
  await item.click();

  await expect(STATUS(page)).toHaveAttribute("data-status", "paused", { timeout: 120_000 });
  await expect(STATUS(page)).toContainText("time breakpoint");
  const branchTime = pauseSeconds(await STATUS(page).textContent());
  console.warn(`X4.1 test 3 rewind: cursor ${t}, ${await STATUS(page).textContent()}`);
  expect(Math.abs(branchTime - t)).toBeLessThan(0.0005);
  const branch = await runId(page);
  expect(branch).not.toBe(parent);
  const manifest = (await (await request.get(`/api/runs/${branch}`)).json()) as {
    parentRun?: string;
    branchAt?: number;
    status: string;
  };
  expect(manifest.parentRun).toBe(parent);
  expect(Math.abs((manifest.branchAt ?? 0) - t)).toBeLessThan(0.0005);
  expect(manifest.status).toBe("paused");

  // Explain the eliminated signal: an alias or observed variable, an expression, a source origin.
  await signalMenu(page, "Motor1/i", "explain-signal");
  await expect(page.getByTestId("explain-popover")).toBeVisible();
  await expect(page.getByTestId("explain-kind")).toHaveText(/alias|observed/i);
  // `mtkcompile` eliminated Motor1/i: it is an alias of a state, and following the link explains that state.
  await expect(page.getByTestId("explain-kind")).toHaveText("Alias");
  const alias = page.getByTestId("explain-alias");
  await expect(alias).toHaveText(/\S/);
  const target = (await alias.textContent()) ?? "";
  await alias.click();
  await expect(page.getByTestId("explain-popover")).toContainText(target);
  await expect(page.getByTestId("explain-origin").first()).toBeVisible({ timeout: 20_000 });
  console.warn(
    `X4.1 test 3 explain: Motor1/i is an alias of ${target}; its kind ${await page.getByTestId("explain-kind").textContent()}`,
  );
  await page.getByTestId("explain-close").click();

  await page.keyboard.press("Shift+F5");
  await expect(STATUS(page)).toHaveAttribute("data-status", "cancelled", { timeout: 60_000 });
});
