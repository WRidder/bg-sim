/**
 * The breakpoint store (plan 3.8, decision D26).
 *
 * Breakpoints are editor state, saved per model in `localStorage` and never in
 * the model document (so they do not change the model hash or the compile
 * cache). Every storage access is wrapped in try/catch: the store works the
 * same without storage, the breakpoints then simply do not survive a reload.
 *
 * The store is generic over the five kinds of the contract. W4.1 creates `line`
 * breakpoints from the gutter; W4.2 adds `watch`, `event` and `exception`
 * through `add` and the same enable/disable actions. Ids are stable (`bp<n>`)
 * and never reused inside a model, so a status the server reported for an id
 * cannot be mistaken for a later breakpoint.
 */

import { create } from "zustand";

import type {
  Breakpoint,
  EventBreakpoint,
  ExceptionBreakpoint,
  LineBreakpoint,
  TimeBreakpoint,
  WatchBreakpoint,
} from "../contracts/debug";
import { useDocumentStore } from "../state/documentStore";

/** A breakpoint before the store gave it an id. */
export type NewBreakpoint =
  | Omit<LineBreakpoint, "id">
  | Omit<WatchBreakpoint, "id">
  | Omit<TimeBreakpoint, "id">
  | Omit<EventBreakpoint, "id">
  | Omit<ExceptionBreakpoint, "id">;

const STORAGE_PREFIX = "bgsim.breakpoints.";
const STORAGE_VERSION = 1;

type ReadStorage = Pick<Storage, "getItem">;
type WriteStorage = Pick<Storage, "setItem">;

/** The storage key of a model: `bgsim.breakpoints.<project>/<model>`. */
export function breakpointStorageKey(modelKey: string): string {
  return `${STORAGE_PREFIX}${modelKey}`;
}

export interface StoredBreakpoints {
  breakpoints: Breakpoint[];
  /** The next id number; ids are never reused inside a model. */
  next: number;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isBreakpoint(value: unknown): value is Breakpoint {
  if (!isRecord(value) || typeof value.id !== "string" || typeof value.enabled !== "boolean") {
    return false;
  }
  switch (value.kind) {
    case "line": {
      const line = value.line;
      return (
        isRecord(line) &&
        typeof line.ref === "string" &&
        typeof line.line === "number" &&
        Number.isInteger(line.line) &&
        line.line >= 1 &&
        (line.path === null || typeof line.path === "string")
      );
    }
    case "watch":
      return isRecord(value.watch) && typeof value.watch.expr === "string";
    case "time":
      return isRecord(value.time) && typeof value.time.t === "number";
    case "event":
      return isRecord(value.event);
    case "exception":
      return isRecord(value.exception) && Array.isArray(value.exception.on);
    default:
      return false;
  }
}

function idNumber(id: string): number {
  const match = /^bp(\d+)$/.exec(id);
  return match === null ? 0 : Number(match[1]);
}

/**
 * Read the stored breakpoints of a model. Null when nothing usable is stored
 * or when storage is unavailable (absent, blocked or throwing).
 */
export function readBreakpoints(
  modelKey: string,
  storage?: ReadStorage,
): StoredBreakpoints | null {
  try {
    const raw = (storage ?? localStorage).getItem(breakpointStorageKey(modelKey));
    if (raw === null) {
      return null;
    }
    const parsed: unknown = JSON.parse(raw);
    if (!isRecord(parsed) || !Array.isArray(parsed.breakpoints)) {
      return null;
    }
    const seen = new Set<string>();
    const breakpoints: Breakpoint[] = [];
    for (const entry of parsed.breakpoints) {
      if (isBreakpoint(entry) && !seen.has(entry.id)) {
        seen.add(entry.id);
        breakpoints.push(entry);
      }
    }
    const highest = breakpoints.reduce((max, entry) => Math.max(max, idNumber(entry.id)), 0);
    const stored = typeof parsed.next === "number" && Number.isInteger(parsed.next) ? parsed.next : 1;
    return { breakpoints, next: Math.max(stored, highest + 1) };
  } catch {
    return null;
  }
}

/** Store the breakpoints of a model; a storage failure is ignored. */
export function writeBreakpoints(
  modelKey: string,
  value: StoredBreakpoints,
  storage?: WriteStorage,
): void {
  try {
    (storage ?? localStorage).setItem(
      breakpointStorageKey(modelKey),
      JSON.stringify({ version: STORAGE_VERSION, ...value }),
    );
  } catch {
    /* the breakpoints simply will not be remembered */
  }
}

export interface BreakpointStoreState {
  /** `<project>/<model>`, or null before a model is open. */
  modelKey: string | null;
  breakpoints: Breakpoint[];
  next: number;

  /** Switch to the breakpoints of another model (reads storage). */
  loadModel: (modelKey: string | null) => void;
  /** Add a breakpoint; returns its new id. */
  add: (breakpoint: NewBreakpoint) => string;
  remove: (id: string) => void;
  clear: () => void;
  setEnabled: (id: string, enabled: boolean) => void;
  /** Line and watch breakpoints; blank text clears the condition. */
  setCondition: (id: string, condition: string | null) => void;
  /** Line and watch breakpoints; a value below 1 clears the hit count. */
  setHitCount: (id: string, hitCount: number | null) => void;
  /** Move a line breakpoint (the editor text shifted). */
  moveLine: (id: string, line: number) => void;
  /** Gutter toggle: removes the line breakpoint at the place, or creates one. Returns the new id or null. */
  toggleLine: (ref: string, line: number, path?: string | null) => string | null;
}

function lineBreakpointsAt(
  breakpoints: readonly Breakpoint[],
  ref: string,
  line: number,
): LineBreakpoint[] {
  return breakpoints.filter(
    (entry): entry is LineBreakpoint =>
      entry.kind === "line" && entry.line.ref === ref && entry.line.line === line,
  );
}

export const useBreakpointStore = create<BreakpointStoreState>()((set, get) => {
  /** Apply a change to the list and save it. */
  const commit = (breakpoints: Breakpoint[], next: number = get().next): void => {
    set({ breakpoints, next });
    const modelKey = get().modelKey;
    if (modelKey !== null) {
      writeBreakpoints(modelKey, { breakpoints, next });
    }
  };

  const update = (id: string, change: (entry: Breakpoint) => Breakpoint): void => {
    const current = get().breakpoints;
    if (!current.some((entry) => entry.id === id)) {
      return;
    }
    commit(current.map((entry) => (entry.id === id ? change(entry) : entry)));
  };

  return {
    modelKey: null,
    breakpoints: [],
    next: 1,

    loadModel: (modelKey) => {
      if (modelKey === get().modelKey) {
        return;
      }
      const stored = modelKey === null ? null : readBreakpoints(modelKey);
      set({
        modelKey,
        breakpoints: stored?.breakpoints ?? [],
        next: stored?.next ?? 1,
      });
    },

    add: (breakpoint) => {
      const id = `bp${get().next}`;
      commit([...get().breakpoints, { ...breakpoint, id } as Breakpoint], get().next + 1);
      return id;
    },

    remove: (id) => {
      const current = get().breakpoints;
      if (current.some((entry) => entry.id === id)) {
        commit(current.filter((entry) => entry.id !== id));
      }
    },

    clear: () => {
      if (get().breakpoints.length > 0) {
        commit([]);
      }
    },

    setEnabled: (id, enabled) => update(id, (entry) => ({ ...entry, enabled })),

    setCondition: (id, condition) =>
      update(id, (entry) => {
        if (entry.kind !== "line") {
          return entry;
        }
        const text = condition === null ? "" : condition.trim();
        return { ...entry, condition: text.length === 0 ? null : text };
      }),

    setHitCount: (id, hitCount) =>
      update(id, (entry) => {
        if (entry.kind !== "line" && entry.kind !== "watch") {
          return entry;
        }
        const valid = hitCount !== null && Number.isFinite(hitCount) && hitCount >= 1;
        return { ...entry, hitCount: valid ? Math.trunc(hitCount) : null };
      }),

    moveLine: (id, line) =>
      update(id, (entry) =>
        entry.kind === "line" && line >= 1 && entry.line.line !== line
          ? { ...entry, line: { ...entry.line, line } }
          : entry,
      ),

    toggleLine: (ref, line, path = null) => {
      const existing = lineBreakpointsAt(get().breakpoints, ref, line);
      if (existing.length > 0) {
        const doomed = new Set(existing.map((entry) => entry.id));
        commit(get().breakpoints.filter((entry) => !doomed.has(entry.id)));
        return null;
      }
      return get().add({
        enabled: true,
        kind: "line",
        line: { ref, line, path },
        condition: null,
        hitCount: null,
      });
    },
  };
});

/** The line breakpoints of one source, in line order. */
export function lineBreakpointsOf(
  breakpoints: readonly Breakpoint[],
  ref: string,
): LineBreakpoint[] {
  return breakpoints
    .filter((entry): entry is LineBreakpoint => entry.kind === "line" && entry.line.ref === ref)
    .sort((a, b) => a.line.line - b.line.line);
}

/** Test hook: forget everything (storage is left alone). */
export function resetBreakpointStore(): void {
  useBreakpointStore.setState({ modelKey: null, breakpoints: [], next: 1 });
}

/** The key of the open model, or null. */
export function openModelKey(): string | null {
  const { project, modelName } = useDocumentStore.getState();
  return project !== null && modelName !== null ? `${project}/${modelName}` : null;
}

let bound = false;

/**
 * Follow the open model: whenever the project or model name changes, load that
 * model's breakpoints. Idempotent; called once by the debug controls.
 */
export function bindBreakpointsToDocument(): void {
  if (bound) {
    return;
  }
  bound = true;
  useBreakpointStore.getState().loadModel(openModelKey());
  useDocumentStore.subscribe((state, previous) => {
    if (state.project !== previous.project || state.modelName !== previous.modelName) {
      useBreakpointStore.getState().loadModel(openModelKey());
    }
  });
}
