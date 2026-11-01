/**
 * What a run is doing right now, in words for the top bar and the 3D view.
 *
 * The worker reports the phases of the run contract (`parse`, `flatten`, `causality`, `mtkcompile`, `init`,
 * `simulate`, `write`); a large model can spend a minute in `mtkcompile` or `init` before the first sample,
 * so the indicators name the stage and count the seconds instead of showing a progress bar that does not move.
 */

import { useEffect, useState } from "react";

import type { RunUiStatus } from "../plot/runStore";

/** The stages shown to the user. `prepare` covers parse, flatten and causality (they run inside `run.start`). */
export type RunStage = "prepare" | "compile" | "init" | "simulate" | "write" | "cancel";

/** The stages before the first sample, in order (the 3D view lists them while it waits). */
export const PRE_SIM_STAGES: readonly { readonly stage: RunStage; readonly label: string }[] = [
  { stage: "prepare", label: "Check and flatten the model" },
  { stage: "compile", label: "Compile the equations" },
  { stage: "init", label: "Find the initial state" },
  { stage: "simulate", label: "Simulate" },
];

const STAGE_OF_PHASE: Record<string, RunStage> = {
  parse: "prepare",
  flatten: "prepare",
  causality: "prepare",
  mtkcompile: "compile",
  init: "init",
  simulate: "simulate",
  write: "write",
  cancelling: "cancel",
};

const STAGE_LABEL: Record<RunStage, string> = {
  prepare: "Preparing",
  compile: "Compiling",
  init: "Initializing",
  simulate: "Simulating",
  write: "Writing results",
  cancel: "Stopping",
};

export interface RunActivity {
  /** A run is starting or running (not paused in the debugger). */
  readonly busy: boolean;
  /** The stage, or null when no run is active. */
  readonly stage: RunStage | null;
  /** "Compiling", "Simulating", … */
  readonly label: string;
  /** Busy and no sample yet: the stages before `simulate`, and `simulate` until the first sample (the solver's
   *  first step compiles its code, which takes a while on a large model). */
  readonly preparing: boolean;
}

export function runStage(status: RunUiStatus, phase: string | null): RunStage | null {
  if (status !== "starting" && status !== "running") return null;
  if (phase === null) return "prepare";
  return STAGE_OF_PHASE[phase] ?? (status === "starting" ? "prepare" : "simulate");
}

export function describeRunActivity(
  status: RunUiStatus,
  phase: string | null,
  debugPaused: boolean,
  hasSamples = true,
): RunActivity {
  const stage = debugPaused ? null : runStage(status, phase);
  if (stage === null) return { busy: false, stage: null, label: "", preparing: false };
  const firstStep = stage === "simulate" && !hasSamples;
  return {
    busy: true,
    stage,
    label: firstStep ? "Starting the solver" : STAGE_LABEL[stage],
    preparing: stage === "prepare" || stage === "compile" || stage === "init" || firstStep,
  };
}

/** The run has taken a step past the initial row (the live view and plots start to move). */
export function hasSamples(progress: { rows: number } | null): boolean {
  return progress !== null && progress.rows > 1;
}

/** `4 s`, then a clock: `1:05`, `1:02:05` (short enough for the top bar). */
export function formatElapsed(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  const ss = String(s % 60).padStart(2, "0");
  if (m < 60) return `${m}:${ss}`;
  return `${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")}:${ss}`;
}

/** Milliseconds since `since`, re-rendered every half second while `active`. */
export function useElapsed(since: number | null, active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(timer);
  }, [active, since]);
  return since === null ? 0 : Math.max(0, now - since);
}
