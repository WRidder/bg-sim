import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

/**
 * The user manual: the help icon at the top right opens a full-screen modal, on the start page
 * and in a project; F1 opens it in the editor; the page list and the page: links navigate inside
 * the dialog; Escape closes it and focus returns to the icon. Axe-clean (serious and up) in both
 * themes. Screenshots go to BGSIM_SCREENSHOT_DIR when it is set.
 */

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "../../..");
const shots = process.env.BGSIM_SCREENSHOT_DIR ?? "";
let project = "";

test.beforeEach(async ({ page }) => {
  project = `w-user-manual-${Date.now()}-${test.info().workerIndex}`;
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.emulateMedia({ reducedMotion: "reduce" });
});

test.afterEach(async ({ request }) => {
  if (project.length > 0) await request.delete(`/api/projects/${project}`);
});

async function violations(page: Page): Promise<string[]> {
  const result = await new AxeBuilder({ page }).analyze();
  return result.violations
    .filter((violation) => violation.impact === "serious" || violation.impact === "critical")
    .map(
      (violation) =>
        `${violation.id} (${violation.impact}): ${violation.help}\n` +
        violation.nodes
          .slice(0, 4)
          .map((node) => `    ${node.target.join(" ")}  ${node.failureSummary?.split("\n")[1] ?? ""}`)
          .join("\n"),
    );
}

for (const theme of ["light", "dark"] as const) {
  test(`the user manual opens from the header, navigates and is axe-clean (${theme})`, async ({ page, request }) => {
    test.setTimeout(120_000);
    // A fresh browser context per test: no remembered manual page yet.
    await page.addInitScript((value) => localStorage.setItem("bgsim.theme", value), theme);

    // Start page: the icon is at the top right of the header.
    await page.goto("/");
    await expect(page.getByTestId("start-page")).toBeVisible({ timeout: 30_000 });
    const icon = page.getByRole("button", { name: "User manual" });
    await expect(icon).toHaveAttribute("title", "User manual (F1)");
    const iconBox = await icon.boundingBox();
    expect(iconBox).not.toBeNull();
    expect((iconBox?.x ?? 0) + (iconBox?.width ?? 0)).toBeGreaterThan(1440 - 60);

    await icon.click();
    const dialog = page.getByRole("dialog", { name: "User manual" });
    await expect(dialog).toBeVisible();
    const content = dialog.getByTestId("manual-page");
    await expect(content).toHaveAttribute("data-page", "getting-started");
    await expect(content.getByRole("heading", { level: 1 })).toHaveText("Getting started");
    // Full screen: the dialog covers nearly the whole viewport.
    const box = await dialog.boundingBox();
    expect(box?.width ?? 0).toBeGreaterThan(1440 - 40);
    expect(box?.height ?? 0).toBeGreaterThan(900 - 40);
    expect.soft(await violations(page), "axe violations on the manual").toEqual([]);
    if (shots.length > 0) {
      await page.screenshot({ path: `${shots}/user-manual-${theme}.png` });
    }

    // The page list navigates; a page: link inside the page navigates too.
    await dialog.getByRole("button", { name: "Export (C / FMU)" }).click();
    await expect(content).toHaveAttribute("data-page", "export");
    await expect(content.getByRole("table").first()).toBeVisible();
    await content.getByRole("link", { name: "background task" }).click();
    await expect(content).toHaveAttribute("data-page", "background-tasks");
    await expect(content).toBeFocused();
    expect.soft(await violations(page), "axe violations on a manual page with tables").toEqual([]);
    await dialog.getByRole("button", { name: "Export (C / FMU)" }).click();
    await expect(content).toHaveAttribute("data-page", "export");
    if (shots.length > 0) {
      await page.screenshot({ path: `${shots}/user-manual-export-${theme}.png` });
    }

    // Search narrows the page list.
    await dialog.getByRole("searchbox", { name: "Search the manual" }).fill("breakpoint");
    await expect(dialog.getByRole("button", { name: "Debugging" })).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Dashboard" })).toHaveCount(0);
    expect.soft(await violations(page), "axe violations with a filtered page list").toEqual([]);

    // Escape closes and returns the focus to the icon.
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(icon).toBeFocused();

    // In a project, F1 without a selected block opens the manual at the last page.
    expect((await request.post("/api/projects", { data: { name: project } })).status()).toBe(201);
    const model = JSON.parse(
      readFileSync(path.join(repoRoot, "contracts", "fixtures", "model", "valid", "model.rlc.iconic.json"), "utf8"),
    ) as Record<string, unknown>;
    expect((await request.put(`/api/projects/${project}/models/Arm`, { data: model })).status()).toBe(200);
    await page.goto(`/?project=${project}&model=Arm`);
    await expect(page.getByTestId("run-button")).toBeEnabled({ timeout: 30_000 });
    await page.getByTestId("diagram-node").first().waitFor();
    await page.locator("body").press("F1");
    await expect(dialog).toBeVisible();
    await expect(content).toHaveAttribute("data-page", "export");
    expect.soft(await violations(page), "axe violations on the manual in the editor").toEqual([]);
    await dialog.getByRole("button", { name: "Close the user manual" }).click();
    await expect(dialog).toBeHidden();
    await expect(icon).toBeVisible();
  });
}
