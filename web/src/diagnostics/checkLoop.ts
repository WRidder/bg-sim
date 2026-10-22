/**
 * The debounced `model.check` loop of plan 7.3: every document mutation
 * schedules a check 400 ms later; rapid edits coalesce into one request, and a
 * response that belongs to a superseded request is discarded by sequence
 * number.
 *
 * The loop is a plain object, not a React hook, so the coalescing and stale
 * response rules are unit-tested with fake timers instead of a rendered app.
 */

import type { Model } from "../contracts/model";
import type { ModelCheckResult } from "../contracts/worker-rpc";

/** How long after the last edit the check runs (plan 7.3). */
export const CHECK_DEBOUNCE_MS = 400;

export type CheckLoopStatus = "waiting" | "checking" | "idle";

export interface CheckLoopOptions {
  check: (model: Model, signal: AbortSignal) => Promise<ModelCheckResult>;
  onResult: (result: ModelCheckResult, revision: number) => void;
  onError: (error: unknown, revision: number) => void;
  onStatus?: (status: CheckLoopStatus) => void;
  debounceMs?: number;
}

export interface CheckLoop {
  /** Mark `model` as the newest document, replacing any pending schedule. */
  schedule: (model: Model, revision: number) => void;
  /** Checks do not fire until the worker is ready. */
  setReady: (ready: boolean) => void;
  /** Forget the pending document and abort an in-flight request. */
  cancel: () => void;
  dispose: () => void;
  /** The revision waiting for the debounce timer, for tests and diagnostics. */
  pendingRevision: () => number | null;
}

function isAbort(error: unknown, signal: AbortSignal): boolean {
  if (signal.aborted) {
    return true;
  }
  return (
    typeof error === "object" &&
    error !== null &&
    "name" in error &&
    (error as { name?: unknown }).name === "AbortError"
  );
}

export function createCheckLoop(options: CheckLoopOptions): CheckLoop {
  const debounceMs = options.debounceMs ?? CHECK_DEBOUNCE_MS;
  let ready = false;
  let disposed = false;
  let pending: { model: Model; revision: number } | null = null;
  /**
   * Incremented by every schedule. A request records the value it was fired
   * under; a newer edit makes every older response stale immediately, even
   * before the new debounce timer fires.
   */
  let generation = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let controller: AbortController | null = null;

  const clearTimer = (): void => {
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
  };

  const arm = (): void => {
    clearTimer();
    if (!ready) {
      options.onStatus?.("waiting");
      return;
    }
    if (pending === null) {
      return;
    }
    timer = setTimeout(fire, debounceMs);
  };

  const fire = (): void => {
    timer = null;
    if (disposed || pending === null) {
      return;
    }
    const request = generation;
    const { model, revision } = pending;
    pending = null;
    controller?.abort();
    const local = new AbortController();
    controller = local;
    options.onStatus?.("checking");

    void options.check(model, local.signal).then(
      (result) => {
        if (disposed || request !== generation) {
          return;
        }
        controller = null;
        options.onResult(result, revision);
      },
      (error: unknown) => {
        if (disposed || request !== generation || isAbort(error, local.signal)) {
          return;
        }
        controller = null;
        options.onError(error, revision);
      },
    );
  };

  return {
    schedule: (model, revision) => {
      if (disposed) {
        return;
      }
      generation += 1;
      pending = { model, revision };
      // The previous request can no longer win; abort it so a slow worker does
      // not spend time on an answer the editor will throw away.
      controller?.abort();
      controller = null;
      arm();
    },

    setReady: (next) => {
      if (disposed || next === ready) {
        return;
      }
      ready = next;
      if (ready) {
        arm();
      } else {
        clearTimer();
        options.onStatus?.("waiting");
      }
    },

    cancel: () => {
      clearTimer();
      pending = null;
      generation += 1;
      controller?.abort();
      controller = null;
      if (!disposed) {
        options.onStatus?.("idle");
      }
    },

    dispose: () => {
      disposed = true;
      clearTimer();
      pending = null;
      controller?.abort();
      controller = null;
    },

    pendingRevision: () => pending?.revision ?? null,
  };
}
