/**
 * The watch *expressions* of the Debug panel (plan 7.9): expressions the user
 * wants to read at every pause. They are re-evaluated through `debug.evaluate`
 * each time the run pauses, and they are distinct from watch *breakpoints*
 * (which stop the run). Saved per model in `localStorage` next to the
 * breakpoints (every access is guarded; without storage they simply do not
 * survive a reload).
 */

import { create } from "zustand";

import type { EvaluateResult, PausedInfo } from "../../contracts/debug";
import { useDocumentStore } from "../../state/documentStore";
import { openModelKey } from "../breakpointStore";
import { subscribePaused, useDebugStore } from "../debugStore";
import { formatFrameValue } from "./frameFormat";

export interface WatchExpression {
  id: string;
  expr: string;
}

export type WatchResult =
  | { state: "value"; text: string; type: EvaluateResult["type"]; unit: string | null }
  | { state: "error"; message: string };

const STORAGE_PREFIX = "bgsim.watchexprs.";

function storageKey(modelKey: string): string {
  return `${STORAGE_PREFIX}${modelKey}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Read the stored expressions of a model; empty without storage. */
export function readWatchExpressions(modelKey: string): { items: WatchExpression[]; next: number } {
  try {
    const raw = window.localStorage.getItem(storageKey(modelKey));
    if (raw === null) {
      return { items: [], next: 1 };
    }
    const parsed: unknown = JSON.parse(raw);
    if (!isRecord(parsed) || !Array.isArray(parsed.items)) {
      return { items: [], next: 1 };
    }
    const items: WatchExpression[] = [];
    for (const entry of parsed.items) {
      if (isRecord(entry) && typeof entry.id === "string" && typeof entry.expr === "string") {
        items.push({ id: entry.id, expr: entry.expr });
      }
    }
    const highest = items.reduce((max, entry) => Math.max(max, Number(entry.id.slice(1)) || 0), 0);
    const stored = typeof parsed.next === "number" ? parsed.next : 1;
    return { items, next: Math.max(stored, highest + 1) };
  } catch {
    return { items: [], next: 1 };
  }
}

function writeWatchExpressions(modelKey: string, items: readonly WatchExpression[], next: number): void {
  try {
    window.localStorage.setItem(storageKey(modelKey), JSON.stringify({ version: 1, items, next }));
  } catch {
    /* the expressions simply will not be remembered */
  }
}

/** The instance path relative names resolve in: the paused statement's instance. */
export function evaluationContext(info: PausedInfo | null): string | null {
  const location = info?.location;
  if (location === undefined || location === null || location.scope === "watch") {
    return null;
  }
  return location.path.length > 0 ? location.path : null;
}

/** Turn an `EvaluateResult` into what the row shows. */
export function describeEvaluation(result: EvaluateResult): WatchResult {
  const failure = result.diagnostics.find((entry) => entry.severity === "error");
  if (failure !== undefined) {
    const hint = failure.hint ? ` ${failure.hint}` : "";
    return { state: "error", message: `${failure.code}: ${failure.message}${hint}` };
  }
  return {
    state: "value",
    text: formatFrameValue(result.value, result.size),
    type: result.type,
    unit: result.unit,
  };
}

export interface WatchExpressionState {
  modelKey: string | null;
  items: WatchExpression[];
  next: number;
  /** Results of the current pause by item id. */
  results: Record<string, WatchResult>;

  loadModel: (modelKey: string | null) => void;
  add: (expr: string) => string | null;
  edit: (id: string, expr: string) => void;
  remove: (id: string) => void;
  /** Evaluate every expression (or one) at the current pause. */
  evaluateAll: (only?: string) => Promise<void>;
  clearResults: () => void;
}

/** Only the newest evaluation round may publish. */
let generation = 0;

export const useWatchExpressionStore = create<WatchExpressionState>()((set, get) => {
  const commit = (items: WatchExpression[], next: number = get().next): void => {
    set({ items, next });
    const modelKey = get().modelKey;
    if (modelKey !== null) {
      writeWatchExpressions(modelKey, items, next);
    }
  };

  return {
    modelKey: null,
    items: [],
    next: 1,
    results: {},

    loadModel: (modelKey) => {
      if (modelKey === get().modelKey) {
        return;
      }
      const stored = modelKey === null ? { items: [], next: 1 } : readWatchExpressions(modelKey);
      generation += 1;
      set({ modelKey, items: stored.items, next: stored.next, results: {} });
      if (useDebugStore.getState().status === "paused") {
        void get().evaluateAll();
      }
    },

    add: (expr) => {
      const text = expr.trim();
      if (text.length === 0) {
        return null;
      }
      const id = `w${get().next}`;
      commit([...get().items, { id, expr: text }], get().next + 1);
      if (useDebugStore.getState().status === "paused") {
        void get().evaluateAll(id);
      }
      return id;
    },

    edit: (id, expr) => {
      const text = expr.trim();
      if (text.length === 0 || !get().items.some((entry) => entry.id === id)) {
        return;
      }
      commit(get().items.map((entry) => (entry.id === id ? { ...entry, expr: text } : entry)));
      const { [id]: _dropped, ...rest } = get().results;
      void _dropped;
      set({ results: rest });
      if (useDebugStore.getState().status === "paused") {
        void get().evaluateAll(id);
      }
    },

    remove: (id) => {
      commit(get().items.filter((entry) => entry.id !== id));
      const { [id]: _dropped, ...rest } = get().results;
      void _dropped;
      set({ results: rest });
    },

    evaluateAll: async (only) => {
      const debug = useDebugStore.getState();
      if (debug.status !== "paused") {
        return;
      }
      const mine = only === undefined ? ++generation : generation;
      const context = evaluationContext(debug.pausedInfo);
      const targets = get().items.filter((entry) => only === undefined || entry.id === only);
      await Promise.all(
        targets.map(async (entry) => {
          let result: WatchResult;
          try {
            result = describeEvaluation(await debug.evaluate(entry.expr, context));
          } catch (error) {
            result = {
              state: "error",
              message: error instanceof Error ? error.message : String(error),
            };
          }
          if (mine !== generation || useDebugStore.getState().status !== "paused") {
            return;
          }
          if (!get().items.some((item) => item.id === entry.id && item.expr === entry.expr)) {
            return;
          }
          set((state) => ({ results: { ...state.results, [entry.id]: result } }));
        }),
      );
    },

    clearResults: () => {
      generation += 1;
      set({ results: {} });
    },
  };
});

let wired = false;

/**
 * Re-evaluate at every pause, drop the results when the run resumes or ends, and
 * follow the open model. Idempotent; runs when this module is first imported.
 */
export function wireWatchExpressions(): void {
  if (wired) {
    return;
  }
  wired = true;
  subscribePaused(() => {
    void useWatchExpressionStore.getState().evaluateAll();
  });
  useDebugStore.subscribe((state, previous) => {
    if (previous.status === "paused" && state.status !== "paused") {
      useWatchExpressionStore.getState().clearResults();
    }
  });
  useWatchExpressionStore.getState().loadModel(openModelKey());
  useDocumentStore.subscribe((state, previous) => {
    if (state.project !== previous.project || state.modelName !== previous.modelName) {
      useWatchExpressionStore.getState().loadModel(openModelKey());
    }
  });
}

wireWatchExpressions();

/** Test hook. */
export function resetWatchExpressionStore(): void {
  generation += 1;
  useWatchExpressionStore.setState({ modelKey: null, items: [], next: 1, results: {} });
}
