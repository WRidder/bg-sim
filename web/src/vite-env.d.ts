/// <reference types="vite/client" />

/**
 * Environment variables Vite exposes to the app (plan 7.1). `VITE_API_BASE`
 * is empty by default: the dev server proxies `/api` to the backend and the
 * backend-served production build is same-origin.
 */
interface ImportMetaEnv {
  readonly VITE_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
