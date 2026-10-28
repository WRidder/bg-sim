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
// The X1.1 acceptance spec needs the real Julia worker; the other UI specs use
// the fixture-driven fake worker (plan 2.3). Lane x runs both passes.
const realWorker = process.env.BGSIM_E2E_REAL === "1";

export default defineConfig({
  testDir: "tests",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
      // Only the browser end-to-end specs; tests/*.test.ts belong to Vitest.
      testMatch: /e2e[\\/].*\.spec\.ts/,
      // tests/perf holds the plan 7.5 budgets; it runs as its own project so
      // `npx playwright test tests/perf` selects exactly those files.
      // The real-worker acceptance specs are skipped in the fake-worker pass.
      testIgnore: realWorker
        ? [/perf[\\/]/, /multibond\.spec\.ts/]
        : [/perf[\\/]/, /multibond-pendulum\.spec\.ts/, /dcmotor\.spec\.ts/, /subsystems\.spec\.ts/, /rlc-dual\.spec\.ts/, /domain-visual\.spec\.ts/, /inverted-pendulum-cart\.spec\.ts/, /drivetrain-kalman\.spec\.ts/, /quarter-car\.spec\.ts/, /industrial-servo\.spec\.ts/, /hydraulic-servo\.spec\.ts/, /speed-control\.spec\.ts/],
    },
    {
      name: "perf",
      use: { ...devices["Desktop Chrome"] },
      testMatch: /perf[\\/].*\.spec\.ts/,
      // A frame-rate measurement must not compete with a second worker.
      fullyParallel: false,
      workers: 1,
    },
  ],
  webServer: {
    command: "uv run bgsim",
    cwd: repoRoot,
    env: process.env.BGSIM_E2E_REAL === "1" ? {} : { BGSIM_FAKE_WORKER: "1" },
    url: `${BASE_URL}/api/health`,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
  },
});
