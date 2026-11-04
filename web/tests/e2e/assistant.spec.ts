import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

/**
 * The assistant's chat on the fake worker and a scripted `claude` (backend/tests/fake_claude.py):
 * a tag in the message picks what it does. The tool surface, the draft and the runners have their
 * own tests in backend/tests; this one is the browser's half: real KaTeX and Mermaid, the question
 * form, the selection chips, Apply as one undo step, and the home-screen chat.
 */

test.describe.configure({ timeout: 90_000 });

let project = "";

test.beforeEach(async ({ request, page }) => {
  project = `w-assistant-${Date.now()}-${test.info().workerIndex}`;
  const created = await request.post("/api/projects", {
    data: { name: project, example: "hydraulic-servo" },
  });
  expect(created.status(), await created.text()).toBe(201);
  await page.setViewportSize({ width: 1600, height: 1000 });
});

test.afterEach(async ({ request }) => {
  const found = await request.get(`/api/assistant/sessions?project=${project}`);
  const session = ((await found.json()) as { session: { session: string } | null }).session;
  if (session !== null) {
    await request.delete(`/api/assistant/${session.session}`);
  }
  await request.delete(`/api/projects/${project}`);
});

async function openChat(page: Page): Promise<void> {
  await page.goto(`/?project=${project}&model=hydraulic-servo`);
  await expect(page.getByTestId("diagram-node").first()).toBeVisible({ timeout: 30_000 });
  await page.getByTestId("assistant-toggle").click();
  await expect(page.getByTestId("assistant-panel")).toBeVisible();
}

async function say(page: Page, text: string): Promise<void> {
  await page.getByTestId("assistant-input").fill(text);
  await page.getByTestId("assistant-send").click();
  await expect(page.getByTestId("assistant-user").last()).toContainText(text);
}

test("an answer shows its math, table and Mermaid diagram", async ({ page }) => {
  await openChat(page);
  await say(page, "#math the time constant");
  const answer = page.getByTestId("assistant-text").last();
  await expect(answer.locator(".katex").first()).toBeVisible();
  await expect(answer.locator(".katex-display")).toBeVisible();
  await expect(answer.locator("table")).toContainText("42 rad/s");
  // Real mermaid in a real browser: the fence becomes an SVG with the labels in it.
  await expect(answer.getByTestId("mermaid-diagram").locator("svg")).toBeVisible({ timeout: 20_000 });
  await expect(answer.getByTestId("mermaid-diagram")).toContainText("Motor");
  await expect(page.getByTestId("assistant-working")).toBeHidden();

  const results = await new AxeBuilder({ page }).include('[data-testid="assistant-panel"]').analyze();
  expect(results.violations.map((violation) => violation.id)).toEqual([]);
});

test("a question is answered with radio buttons and checkboxes", async ({ page }) => {
  await openChat(page);
  await say(page, "#ask scope first");
  const card = page.getByTestId("question-card");
  await expect(card).toBeVisible();
  await card.getByRole("radio", { name: /Viscous/ }).check();
  await card.getByRole("checkbox", { name: "Speed" }).check();
  await card.getByRole("checkbox", { name: "Power" }).check();
  await page.getByTestId("question-send").click();

  await expect(card).toHaveAttribute("data-answered", "true");
  await expect(page.getByTestId("assistant-user").last()).toContainText("Viscous (`viscous`)");
  await expect(page.getByTestId("assistant-text").last()).toContainText("You said:");
});

test("a change is a proposal until applied, and Apply is one undo step", async ({ page }) => {
  await openChat(page);
  const nodes = page.getByTestId("diagram-node");
  const before = await nodes.count();

  await say(page, "#ok add a damper");
  await expect(page.getByTestId("assistant-proposal")).toContainText("model hydraulic-servo");
  await expect(page.getByTestId("assistant-working")).toBeHidden();
  expect(await nodes.count()).toBe(before); // the canvas is still the saved model

  await page.getByTestId("assistant-apply").click();
  await expect(page.getByTestId("assistant-notice")).toContainText("Applied 1 file");
  await expect(nodes).toHaveCount(before + 1);
  await expect(page.getByTestId("assistant-proposal")).toBeHidden();

  await page.getByTestId("diagram-node").first().click();
  await page.keyboard.press("Control+z");
  await expect(nodes).toHaveCount(before);
});

test("discarding drops the draft and leaves the model alone", async ({ page }) => {
  await openChat(page);
  const nodes = page.getByTestId("diagram-node");
  const before = await nodes.count();
  await say(page, "#ok add a damper");
  await expect(page.getByTestId("assistant-proposal")).toBeVisible();
  await expect(page.getByTestId("assistant-working")).toBeHidden();
  await page.getByTestId("assistant-discard").click();
  await expect(page.getByTestId("assistant-proposal")).toBeHidden();
  expect(await nodes.count()).toBe(before);
});

test("figures and code cells are drawn in the chat", async ({ page }) => {
  await openChat(page);
  await say(page, "#figure run it");
  await expect(page.getByTestId("figure-plot").getByRole("img")).toBeVisible();
  await expect(page.getByTestId("figure-diagram").getByRole("img")).toBeVisible();

  await say(page, "#cell a spectrum");
  await expect(page.getByTestId("code-card")).toContainText("Spectrum");
  await expect(page.getByTestId("code-card")).toContainText("length(t) =");
  await expect(page.getByTestId("figure-table").first()).toBeVisible();
});

test("a debug run of the assistant pauses in the editor's debugger", async ({ page }) => {
  await openChat(page);
  await say(page, "#debug why is it off");
  await expect(page.getByTestId("assistant-panel")).toContainText("Debugging");
  await expect(page.getByTestId("assistant-panel")).toContainText("Paused at t = 0");
  await expect(page.getByTestId("debug-controls")).toBeVisible();
  await expect(page.locator('[data-status="paused"]').first()).toBeVisible();
});

test("the selection goes along with a message, once", async ({ page }) => {
  await openChat(page);
  await page.getByTestId("diagram-node").first().click();
  const chip = page.getByTestId("selection-chip-diagram");
  await expect(chip).toBeVisible();

  await say(page, "#math what is this?");
  await expect(page.getByTestId("assistant-user").last().getByTestId("selection-chip-diagram")).toBeVisible();
  await expect(page.locator(".assistant-composer").getByTestId("selection-chip-diagram")).toBeHidden();
});

test("the chat comes back after a reload, with its proposal", async ({ page }) => {
  await openChat(page);
  await say(page, "#ok add a damper");
  await expect(page.getByTestId("assistant-proposal")).toBeVisible();
  await expect(page.getByTestId("assistant-working")).toBeHidden();
  await page.reload();
  await expect(page.getByTestId("assistant-panel")).toBeVisible();
  await expect(page.getByTestId("assistant-user").first()).toContainText("add a damper");
  await expect(page.getByTestId("assistant-proposal")).toBeVisible();
});

test("the home screen's chat creates a project, and opening it finds the chat", async ({ page, request }) => {
  const name = `w-home-${Date.now()}-${test.info().workerIndex}`;
  await page.goto("/");
  await page.getByTestId("assistant-toggle").click();
  await say(page, `#home ${name}`);
  const created = page.getByTestId("assistant-project-created");
  await expect(created).toContainText(name);
  await expect(page.getByTestId("assistant-proposal")).toContainText("model first");

  await created.getByRole("button", { name: "Open project" }).click();
  await expect(page).toHaveURL(new RegExp(`project=${name}`));
  await expect(page.getByTestId("assistant-user").first()).toContainText(name);
  await expect(page.getByTestId("assistant-apply")).toBeEnabled();

  const found = await request.get(`/api/assistant/sessions?project=${name}`);
  const session = ((await found.json()) as { session: { session: string } }).session;
  await request.delete(`/api/assistant/${session.session}`);
  await request.delete(`/api/projects/${name}`);
});
