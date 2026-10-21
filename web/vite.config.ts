import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

/**
 * The backend (FastAPI/uvicorn, plan 2.1) listens on 127.0.0.1:8765.
 * In development the Vite dev server proxies `/api` and `/ws` to it; in
 * production `uv run bgsim` serves this app's `dist/` from the same origin,
 * so the client can always use relative URLs (plan 7.1).
 */
const BACKEND_ORIGIN = "http://127.0.0.1:8765";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: BACKEND_ORIGIN, changeOrigin: false },
      "/ws": { target: BACKEND_ORIGIN, ws: true, changeOrigin: false },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
    target: "es2022",
  },
});
