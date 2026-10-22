/**
 * The React integration of the diagnostics pipeline (plan 7.3):
 *
 * * polls `/api/health` and pauses checking while the worker is
 *   `starting`/`warming`/`crashed` (the panel shows a quiet status instead);
 * * subscribes to the document store and feeds the debounced check loop;
 * * starts the canvas decorator, which is independent of which dock tab is
 *   open (the badge counts and the canvas markers must always be live);
 * * maps a failed check to a panel error and a 503 to `waiting`.
 *
 * `useDiagnosticBadges` is what `BottomDock` calls: one hook keeps the runtime
 * mounted and returns the live counts.
 */

import { useEffect } from "react";

import { ApiError, getHealth } from "../api/client";
import type { WorkerState } from "../api/health";
import { useDocumentStore } from "../state/documentStore";
import { startCanvasDiagnostics } from "./canvasMarkers";
import { CHECK_DEBOUNCE_MS, createCheckLoop, type CheckLoopStatus } from "./checkLoop";
import { checkModel, ModelCheckError } from "./modelCheckClient";
import { useDiagnosticsStore, type DiagnosticsCounts } from "./store";

export const HEALTH_POLL_MS = 1000;

export interface DiagnosticsRuntimeOptions {
  debounceMs?: number;
  healthPollMs?: number;
}

function modelKey(project: string | null, modelName: string | null): string | null {
  return project === null || modelName === null ? null : `${project}/${modelName}`;
}

function describeFailure(error: unknown): string {
  if (error instanceof ModelCheckError) {
    return error.message;
  }
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

/** Start the live check loop, health poll and canvas decorator. */
export function useDiagnosticsRuntime(options: DiagnosticsRuntimeOptions = {}): void {
  const debounceMs = options.debounceMs ?? CHECK_DEBOUNCE_MS;
  const healthPollMs = options.healthPollMs ?? HEALTH_POLL_MS;

  useEffect(() => {
    let stopped = false;
    let healthTimer: ReturnType<typeof setTimeout> | null = null;
    let openKey: string | null = null;

    const loop = createCheckLoop({
      debounceMs,
      check: (model, signal) =>
        checkModel(model, {
          signal,
          project: useDocumentStore.getState().project,
        }),
      onResult: (result, revision) => {
        useDiagnosticsStore.getState().applyResult(result, revision);
      },
      onError: (error, _revision) => {
        const state = useDiagnosticsStore.getState();
        if (error instanceof ModelCheckError) {
          // A 503 means the worker is restarting: keep the panel quiet and let
          // the health poll resume checking when it is ready again.
          if (error.status === 503) {
            state.beginWaiting();
            loop.setReady(false);
            return;
          }
          state.setCheckError(error.message, error.diagnostics);
          return;
        }
        if (error instanceof ApiError && error.status === 503) {
          state.beginWaiting();
          loop.setReady(false);
          return;
        }
        state.setCheckError(describeFailure(error));
      },
      onStatus: (status: CheckLoopStatus) => {
        const state = useDiagnosticsStore.getState();
        if (status === "checking") {
          state.beginCheck();
        } else if (status === "waiting") {
          state.beginWaiting();
        }
      },
    });

    const onWorkerState = (worker: WorkerState): void => {
      useDiagnosticsStore.getState().setWorkerState(worker);
      loop.setReady(worker === "ready");
    };

    const pollHealth = async (): Promise<void> => {
      try {
        const health = await getHealth();
        if (stopped) {
          return;
        }
        onWorkerState(health.worker);
      } catch {
        if (stopped) {
          return;
        }
        onWorkerState("crashed");
      } finally {
        if (!stopped) {
          healthTimer = setTimeout(() => void pollHealth(), healthPollMs);
        }
      }
    };

    const syncDocument = (): void => {
      const { doc, revision, status, project, modelName } = useDocumentStore.getState();
      const key = modelKey(project, modelName);
      if (key !== openKey) {
        openKey = key;
        useDiagnosticsStore.getState().clearResults();
      }
      if (status === "ready" && doc !== null) {
        loop.schedule(doc, revision);
      } else {
        loop.cancel();
      }
    };

    const unsubscribeDocument = useDocumentStore.subscribe((state, previous) => {
      if (
        state.doc !== previous.doc ||
        state.revision !== previous.revision ||
        state.status !== previous.status ||
        state.project !== previous.project ||
        state.modelName !== previous.modelName
      ) {
        syncDocument();
      }
    });

    const stopCanvas = startCanvasDiagnostics();

    void pollHealth();
    syncDocument();

    return () => {
      stopped = true;
      if (healthTimer !== null) {
        clearTimeout(healthTimer);
      }
      unsubscribeDocument();
      loop.dispose();
      stopCanvas();
    };
  }, [debounceMs, healthPollMs]);
}

/**
 * Live badge counts and the mounted runtime. `BottomDock` calls this once;
 * the returned object only changes when a check result changes.
 */
export function useDiagnosticBadges(): DiagnosticsCounts {
  useDiagnosticsRuntime();
  return useDiagnosticsStore((state) => state.counts);
}
