/**
 * Library helpers shared by the end-to-end specs. The library categories start collapsed, so a
 * spec waits for the category headers to know the catalog has loaded, and opens every category
 * (through the quick settings, as a user would) before it drags blocks from the library.
 */

import { expect, type Page } from "@playwright/test";

/** Wait until the library lists its categories, i.e. the catalog has loaded. */
export async function waitForLibrary(page: Page, timeout = 30_000): Promise<void> {
  await expect(page.locator('[data-testid^="library-group-toggle-"]').first()).toBeVisible({
    timeout,
  });
}

/** Open every library category with the cog's "Expand all", then close the popover. */
export async function expandLibrary(page: Page, timeout = 30_000): Promise<void> {
  await waitForLibrary(page, timeout);
  await page.getByRole("button", { name: "Library settings" }).click();
  await page.getByTestId("library-settings-expand-all").click();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("library-settings-popover")).toHaveCount(0);
}
