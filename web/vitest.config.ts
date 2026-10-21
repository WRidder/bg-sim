import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

/**
 * Unit tests run in jsdom (the app is a browser app). `tests/contracts.test.ts`
 * uses `node:fs` and `import.meta.url`; jsdom still runs in Node, so both
 * environments share one config. `globals: false`: every test imports its own
 * helpers from `vitest` (see tests/setup.ts).
 */
export default defineConfig({
  plugins: [react()],
  test: {
    include: ["tests/**/*.test.ts", "tests/**/*.test.tsx"],
    environment: "jsdom",
    globals: false,
    setupFiles: ["tests/setup.ts"],
    css: false,
    restoreMocks: true,
    unstubEnvs: true,
    unstubGlobals: true,
  },
});
