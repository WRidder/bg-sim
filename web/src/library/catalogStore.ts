/**
 * The catalog of the open project (plan 3.2, 7.2 library browser).
 *
 * The session loader fills this store; components only read it. Keeping the
 * built `CatalogIndex` next to the raw catalog means the canvas and the
 * library share one lookup structure.
 */

import { create } from "zustand";

import type { Catalog } from "../contracts/catalog";
import { buildCatalogIndex, type CatalogIndex } from "./catalogIndex";

export type CatalogStatus = "idle" | "loading" | "ready" | "error";

export interface CatalogState {
  catalog: Catalog | null;
  index: CatalogIndex | null;
  status: CatalogStatus;
  error: string | null;
  setLoading: () => void;
  setCatalog: (catalog: Catalog) => void;
  setError: (message: string) => void;
  reset: () => void;
}

export const useCatalogStore = create<CatalogState>()((set) => ({
  catalog: null,
  index: null,
  status: "idle",
  error: null,
  setLoading: () => set({ status: "loading", error: null }),
  setCatalog: (catalog) =>
    set({ catalog, index: buildCatalogIndex(catalog), status: "ready", error: null }),
  setError: (message) => set({ status: "error", error: message }),
  reset: () => set({ catalog: null, index: null, status: "idle", error: null }),
}));

export function resetCatalogStore(): void {
  useCatalogStore.setState({ catalog: null, index: null, status: "idle", error: null });
}
