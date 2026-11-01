/**
 * The worker state from `/api/health`, shared by the top bar's dot and the panels that need the worker
 * (the library and the model loader wait for it instead of showing its 503 as an error).
 * `WorkerStatus` polls and writes it; `known` is false until the first answer or failure.
 */

import { create } from "zustand";

import type { WorkerState } from "./health";

export interface WorkerStoreState {
  state: WorkerState;
  known: boolean;
  fake: boolean;
  detail: string;
  /** Bumped each time the worker becomes ready, so a panel can retry what failed while it was starting. */
  readyEpoch: number;
  report: (update: { state: WorkerState; fake: boolean; detail: string }) => void;
}

export const useWorkerStore = create<WorkerStoreState>()((set, get) => ({
  state: "starting",
  known: false,
  fake: false,
  detail: "Checking the bg-sim backend…",
  readyEpoch: 0,
  report: ({ state, fake, detail }) => {
    const prev = get();
    set({
      state,
      fake,
      detail,
      known: true,
      readyEpoch: state === "ready" && (prev.state !== "ready" || !prev.known) ? prev.readyEpoch + 1 : prev.readyEpoch,
    });
  },
}));

/** True while the worker has not come up yet (or is down), so a 503 means "wait", not "broken". */
export function workerNotReady(s: Pick<WorkerStoreState, "state">): boolean {
  return s.state !== "ready";
}
