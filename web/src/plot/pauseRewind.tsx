/**
 * "Rewind to here" (plan 5.13, 7.9): the plot context menu item that branches the run at the cursor time.
 *
 *     POST /api/runs/{id}/branch  { t }  ->  { runId }
 *
 * The new run is a debug run that replays the parent (with its edits made before `t`) and pauses at `t` with
 * reason `time`. It is followed like any debug run: the run bar, the plots and the debug store adopt it, so
 * Continue and Step work on it. A paused parent is stopped first (its manifest is read by the branch call
 * before that, and the parent's data stays on disk).
 */

import { useEffect, useRef } from "react";

import { API_BASE } from "../api/client";
import type { RunManifest } from "../contracts/run-manifest";
import { useBreakpointStore } from "../debug/breakpointStore";
import { useDebugStore, type DebugStatus } from "../debug/debugStore";
import { useRunStore, type RunUiStatus } from "./runStore";

export interface RewindContext {
  runId: string | null;
  runStatus: RunUiStatus;
  manifest: RunManifest | null;
  debugStatus: DebugStatus;
  debugRunId: string | null;
  /** The pause time of the parent while it is paused, else null. */
  pauseTime: number | null;
}

export interface RewindAvailability {
  enabled: boolean;
  /** Why the item is disabled (a tooltip), or null. */
  reason: string | null;
}

const TIME_EPS = 1e-12;

function disabled(reason: string): RewindAvailability {
  return { enabled: false, reason };
}

/**
 * Whether "Rewind to here" works at cursor time `t`: a paused debug run or a finished run that has a
 * manifest, and `t` before the parent's current time.
 */
export function rewindAvailability(context: RewindContext, t: number | null): RewindAvailability {
  const { runId, runStatus, manifest, debugStatus, debugRunId, pauseTime } = context;
  if (runId === null || manifest === null || manifest.id !== runId) {
    return disabled("Run the model first; Rewind to here branches a run at the cursor time.");
  }
  if (t === null || !Number.isFinite(t)) {
    return disabled("Move the cursor over the plot to the time to rewind to, then right-click.");
  }
  const pausedHere = debugStatus === "paused" && debugRunId === runId && pauseTime !== null;
  const finished = runStatus === "done" || runStatus === "failed" || runStatus === "cancelled";
  if (!pausedHere && !finished) {
    return disabled("Pause the debug run (or wait until the run has finished) before rewinding.");
  }
  const current = pausedHere ? pauseTime : manifest.time.t1;
  if (t < manifest.time.t0 - TIME_EPS) {
    return disabled(`The run starts at t = ${manifest.time.t0} s; choose a later time.`);
  }
  if (!(t < current - TIME_EPS)) {
    return disabled(
      `Rewind needs a time before the run's current time (t = ${current.toFixed(4)} s); move the cursor earlier.`,
    );
  }
  return { enabled: true, reason: null };
}

/** The context of the stores right now. */
export function currentRewindContext(): RewindContext {
  const run = useRunStore.getState();
  const debug = useDebugStore.getState();
  return {
    runId: run.runId,
    runStatus: run.status,
    manifest: run.manifest,
    debugStatus: debug.status,
    debugRunId: debug.runId,
    pauseTime: debug.status === "paused" ? (debug.pausedInfo?.t ?? null) : null,
  };
}

function detailOf(body: unknown): string | null {
  if (typeof body !== "object" || body === null) {
    return null;
  }
  const detail = (body as Record<string, unknown>).detail;
  if (typeof detail === "string" && detail.length > 0) {
    return detail;
  }
  if (typeof detail === "object" && detail !== null) {
    const message = (detail as Record<string, unknown>).message;
    return typeof message === "string" ? message : null;
  }
  return null;
}

/** `POST /api/runs/{id}/branch`: the id of the branch run. */
export async function postBranch(runId: string, t: number): Promise<string> {
  const url = `${API_BASE}/api/runs/${encodeURIComponent(runId)}/branch`;
  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { accept: "application/json", "content-type": "application/json" },
      body: JSON.stringify({ t }),
    });
  } catch {
    throw new Error(`Cannot reach the bg-sim backend at ${url}. Is it running?`);
  }
  let body: unknown;
  try {
    const text = await response.text();
    body = text.length === 0 ? null : (JSON.parse(text) as unknown);
  } catch {
    body = null;
  }
  if (!response.ok) {
    throw new Error(detailOf(body) ?? `Rewind failed: the backend answered ${response.status}.`);
  }
  const id = (body as Record<string, unknown> | null)?.runId;
  if (typeof id !== "string" || id.length === 0) {
    throw new Error("The backend accepted the branch but did not return a run id.");
  }
  return id;
}

/** Resolve when the run store leaves `running` (a stopped parent), or after `timeoutMs`. */
function untilSettled(timeoutMs: number): Promise<void> {
  return new Promise((resolve) => {
    if (useRunStore.getState().status !== "running") {
      resolve();
      return;
    }
    const timer = setTimeout(done, timeoutMs);
    const unsubscribe = useRunStore.subscribe((state) => {
      if (state.status !== "running") {
        done();
      }
    });
    function done(): void {
      clearTimeout(timer);
      unsubscribe();
      resolve();
    }
  });
}

/**
 * Branch the shown run at `t` and follow the new run as a debug run. Throws a readable message when the
 * branch is refused.
 */
export async function rewindToHere(t: number): Promise<string> {
  const run = useRunStore.getState();
  const parent = run.runId;
  if (parent === null) {
    throw new Error("Run the model first; Rewind to here branches a run at the cursor time.");
  }
  const branchId = await postBranch(parent, t);
  if (useRunStore.getState().status === "running") {
    await run.stopRun();
    await untilSettled(10_000);
  }
  await useRunStore.getState().startRun({
    followRunId: branchId,
    debug: { breakpoints: useBreakpointStore.getState().breakpoints, pauseOnEntry: false },
  });
  return branchId;
}

export interface RewindMenuProps {
  /** Pointer position (viewport px). */
  x: number;
  y: number;
  /** The plot cursor time the menu was opened at. */
  time: number | null;
  onClose: () => void;
}

/** The plot context menu: "Rewind to here". Escape and a click elsewhere close it. */
export function RewindMenu({ x, y, time, onClose }: RewindMenuProps) {
  const root = useRef<HTMLDivElement>(null);
  const availability = rewindAvailability(currentRewindContext(), time);

  useEffect(() => {
    root.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
    const onPointer = (event: PointerEvent): void => {
      if (!(event.target instanceof Node) || !root.current?.contains(event.target)) {
        onClose();
      }
    };
    window.addEventListener("pointerdown", onPointer, true);
    return () => window.removeEventListener("pointerdown", onPointer, true);
  }, [onClose]);

  return (
    <div
      ref={root}
      className="editor-menu plot-menu"
      role="menu"
      aria-label="Plot actions"
      data-testid="plot-menu"
      style={{ position: "fixed", left: x, top: y, zIndex: 70 }}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.preventDefault();
          event.stopPropagation();
          onClose();
        }
      }}
    >
      <button
        type="button"
        role="menuitem"
        data-testid="plot-rewind"
        disabled={!availability.enabled}
        title={
          availability.reason ??
          `Branch the run at t = ${time?.toFixed(4) ?? ""} s: a new debug run that replays up to here and pauses`
        }
        onClick={() => {
          onClose();
          if (time === null) {
            return;
          }
          rewindToHere(time).catch((error: unknown) => {
            useRunStore
              .getState()
              .setNotice(error instanceof Error ? error.message : String(error));
          });
        }}
      >
        {time === null ? "Rewind to here" : `Rewind to here (t = ${time.toFixed(4)} s)`}
      </button>
    </div>
  );
}
