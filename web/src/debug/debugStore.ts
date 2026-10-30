/**
 * The debug session store (plan 3.8, 7.9).
 *
 * One store owns the active debug run: its id, `status` (`idle | running |
 * paused | done`), the current `PausedInfo`, the breakpoint statuses the server
 * reported, and the API calls. It does not open a socket: `runStore` owns the
 * single run WebSocket and forwards `debug.paused`, `debug.resumed` and
 * `run.done` through `subscribeRunEvents`, which this module subscribes to.
 *
 * Later panels build on it (W4.2: variables, watches, breakpoints list, edits;
 * W4.3: pause-aware plots, live inspector, rewind): read `pausedInfo`, `runId`
 * and `status`, call `evaluate` / `values`, and react to a pause with
 * `subscribePaused` or the `pauseCount` counter.
 */

import { create } from "zustand";

import type {
  Breakpoint,
  BreakpointStatus,
  EvaluateResult,
  PausedInfo,
  StepGranularity,
  ValuesResult,
} from "../contracts/debug";
import { subscribeRunEvents, useRunStore, type RunEvent } from "../plot/runStore";
import { useBreakpointStore } from "./breakpointStore";
import {
  getValues,
  postDebugCommand,
  postEvaluate,
  putBreakpoints,
  type DebugCommand,
} from "./debugApi";

export type DebugStatus = "idle" | "running" | "paused" | "done";

export interface StartDebugOptions {
  /** Pause before the first statement (F10 and F11 on an idle run bar do this). */
  pauseOnEntry?: boolean;
}

export interface DebugStoreState {
  /** The active debug run, or null. */
  runId: string | null;
  status: DebugStatus;
  /** The `debug.paused` notification while paused, else null. */
  pausedInfo: PausedInfo | null;
  /** Incremented at every pause; a cheap selector for "paused". */
  pauseCount: number;
  /** Server statuses of the breakpoints by id (`verified`, diagnostics). */
  statuses: Record<string, BreakpointStatus>;
  /** The last failed debug call, or null. */
  error: string | null;

  startDebug: (options?: StartDebugOptions) => Promise<void>;
  continueRun: () => Promise<void>;
  pause: () => Promise<void>;
  step: (granularity: StepGranularity) => Promise<void>;
  runTo: (t: number) => Promise<void>;
  /** Stop the run (cancel; works while paused). */
  stop: () => Promise<void>;
  /** Send the current breakpoints to the active run and store their statuses. */
  syncBreakpoints: () => Promise<void>;
  /** `debug.evaluate` at the current pause. */
  evaluate: (expr: string, context?: string | null) => Promise<EvaluateResult>;
  /** `debug.values` of signal ids at the current pause. */
  values: (ids: readonly string[]) => Promise<ValuesResult>;
  clearError: () => void;

  // Reducers fed by the run WebSocket (exported so tests and W4.2 can drive them).
  begin: (runId: string) => void;
  applyPaused: (info: PausedInfo) => void;
  applyResumed: (runId: string) => void;
  applyDone: (runId: string) => void;
  reset: () => void;
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

const pausedListeners = new Set<(info: PausedInfo) => void>();

/** Call `listener` at every pause; returns the unsubscribe. */
export function subscribePaused(listener: (info: PausedInfo) => void): () => void {
  pausedListeners.add(listener);
  return () => {
    pausedListeners.delete(listener);
  };
}

/** Only the newest breakpoint PUT may publish its statuses. */
let syncSequence = 0;

export const useDebugStore = create<DebugStoreState>()((set, get) => {
  /** Run a command on the active run; a refusal becomes `error`. */
  const command = async (
    name: DebugCommand,
    body: Record<string, unknown> = {},
  ): Promise<void> => {
    const runId = get().runId;
    if (runId === null) {
      return;
    }
    try {
      await postDebugCommand(runId, name, body);
      if (get().error !== null) {
        set({ error: null });
      }
    } catch (error) {
      set({ error: messageOf(error) });
    }
  };

  return {
    runId: null,
    status: "idle",
    pausedInfo: null,
    pauseCount: 0,
    statuses: {},
    error: null,

    startDebug: async (options = {}) => {
      const { status } = get();
      if (status === "running" || status === "paused") {
        return;
      }
      const breakpoints = useBreakpointStore.getState().breakpoints;
      await useRunStore.getState().startRun({
        debug: { breakpoints, pauseOnEntry: options.pauseOnEntry === true },
      });
    },

    continueRun: () => command("continue"),
    pause: () => command("pause"),
    step: (granularity) => command("step", { granularity }),
    runTo: (t) => command("runTo", { t }),

    stop: async () => {
      const runId = get().runId;
      if (runId === null) {
        return;
      }
      await useRunStore.getState().stopRun();
    },

    syncBreakpoints: async () => {
      const runId = get().runId;
      if (runId === null || (get().status !== "running" && get().status !== "paused")) {
        return;
      }
      syncSequence += 1;
      const sequence = syncSequence;
      try {
        const result = await putBreakpoints(runId, useBreakpointStore.getState().breakpoints);
        if (sequence !== syncSequence || get().runId !== runId) {
          return;
        }
        const statuses: Record<string, BreakpointStatus> = {};
        for (const entry of result) {
          statuses[entry.id] = entry;
        }
        set({ statuses });
      } catch (error) {
        if (sequence === syncSequence && get().runId === runId) {
          set({ error: messageOf(error) });
        }
      }
    },

    evaluate: async (expr, context = null) => {
      const runId = get().runId;
      if (runId === null) {
        throw new Error("There is no debug run to evaluate in. Start debugging first.");
      }
      return postEvaluate(runId, expr, context);
    },

    values: async (ids) => {
      const runId = get().runId;
      if (runId === null) {
        throw new Error("There is no debug run to read values from. Start debugging first.");
      }
      return getValues(runId, ids);
    },

    clearError: () => set({ error: null }),

    begin: (runId) => {
      syncSequence += 1;
      set({
        runId,
        status: "running",
        pausedInfo: null,
        statuses: {},
        error: null,
      });
    },

    applyPaused: (info) => {
      const { runId, status } = get();
      if (runId === null || info.runId !== runId || status === "done") {
        return;
      }
      set((state) => ({
        status: "paused",
        pausedInfo: info,
        pauseCount: state.pauseCount + 1,
      }));
      for (const listener of [...pausedListeners]) {
        listener(info);
      }
    },

    applyResumed: (runId) => {
      if (get().runId !== runId || get().status === "done") {
        return;
      }
      set({ status: "running", pausedInfo: null });
    },

    applyDone: (runId) => {
      if (get().runId !== runId) {
        return;
      }
      set({ status: "done", pausedInfo: null });
    },

    reset: () => {
      syncSequence += 1;
      set({ runId: null, status: "idle", pausedInfo: null, statuses: {}, error: null });
    },
  };
});

function isPausedInfo(value: Record<string, unknown>): value is Record<string, unknown> & PausedInfo {
  return (
    typeof value.runId === "string" &&
    typeof value.t === "number" &&
    typeof value.reason === "string" &&
    (value.location === null || isRecord(value.location))
  );
}

/** Route a run event into the reducers. */
export function handleRunEvent(event: RunEvent): void {
  const store = useDebugStore.getState();
  switch (event.type) {
    case "reset":
      store.reset();
      break;
    case "started":
      if (event.debug) {
        store.begin(event.runId);
        void useDebugStore.getState().syncBreakpoints();
      } else {
        store.reset();
      }
      break;
    case "message": {
      const { method, params } = event;
      if (method === "debug.paused") {
        if (isPausedInfo(params)) {
          store.applyPaused({ ...params, diagnostics: params.diagnostics ?? [] });
        }
      } else if (method === "debug.resumed" && typeof params.runId === "string") {
        store.applyResumed(params.runId);
      } else if (method === "run.done" && typeof params.runId === "string") {
        store.applyDone(params.runId);
      }
      break;
    }
  }
}

/** True while a debug run is active (running or paused). */
export function isDebugging(state: Pick<DebugStoreState, "status">): boolean {
  return state.status === "running" || state.status === "paused";
}

let wired = false;

/**
 * Subscribe the store to the run events and to the breakpoint store (a change
 * during a debug run is sent as `PUT /breakpoints`). Idempotent; runs when this
 * module is first imported.
 */
export function wireDebugStore(): void {
  if (wired) {
    return;
  }
  wired = true;
  subscribeRunEvents(handleRunEvent);
  let previous: readonly Breakpoint[] = useBreakpointStore.getState().breakpoints;
  useBreakpointStore.subscribe((state) => {
    if (state.breakpoints === previous) {
      return;
    }
    previous = state.breakpoints;
    if (isDebugging(useDebugStore.getState())) {
      void useDebugStore.getState().syncBreakpoints();
    }
  });
}

wireDebugStore();


/** Test hook. */
export function resetDebugStore(): void {
  useDebugStore.getState().reset();
  useDebugStore.setState({ pauseCount: 0 });
}

