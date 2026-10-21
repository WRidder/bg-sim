import { fileURLToPath } from "node:url";

import { defineConfig, devices } from "@playwright/test";

/**
 * The end-to-end tests run against the real backend on 127.0.0.1:8765
 * (plan 2.1): `uv run bgsim` starts FastAPI and, with BGSIM_FAKE_WORKER=1,
 * answers from the contract fixtures. `npm run e2e` builds `dist/` first so
 * the backend can serve the app itself.
 */
const repoRoot = fileURLToPath(new URL("..", import.meta.url));
const BASE_URL = "http://127.0.0.1:8765";

export default defineConfig({
  testDir: "tests/e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "uv run bgsim",
    cwd: repoRoot,
    env: process.env.BGSIM_E2E_REAL === "1" ? {} : { BGSIM_FAKE_WORKER: "1" },
    url: `${BASE_URL}/api/health`,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
  },
});
