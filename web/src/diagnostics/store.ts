/**
 * The diagnostics state of the editor (plan 7.3): the latest `model.check`
 * result, the check lifecycle, the badge counts and the navigation requests
 * that the panel and the canvas share.
 *
 * The store is deliberately flat. `domains`, `causality` and `unitFactors` are
 * kept exactly as the worker sent them (connection id -> value) so the canvas
 * decorator can apply them without knowing anything about the check pipeline.
 * `causality` stays empty until J2.4; reading it is always safe.
 */

import { create } from "zustand";

import type { WorkerState } from "../api/health";
import type { Diagnostic, DiagnosticSeverity } from "../contracts/diagnostic";
import type {
  CausalityStroke,
  DomainName,
  ModelCheckResult,
  ModelCheckStats,
  RunSignal,
} from "../contracts/worker-rpc";

/** What the panel shows about the last check. */
export type DiagnosticsStatus = "idle" | "waiting" | "checking" | "ok" | "error";

export interface DiagnosticsCounts {
  error: number;
  warning: number;
  info: number;
}

/** A request to select and pan to a node; `nonce` makes repeats observable. */
export interface FocusRequest {
  nodeId: string;
  nonce: number;
}

/** A request to reveal a source range (the code tab consumes it when it lands). */
export interface SourceFocus {
  ref: string;
  line: number;
  col: number;
  nonce: number;
}

export interface DiagnosticsState {
  status: DiagnosticsStatus;
  diagnostics: Diagnostic[];
  /** Scene diagnostics of the 3D viewer (E305, E306); shown with, counted with, but never replaced by a model check. */
  viewerDiagnostics: Diagnostic[];
  /** Connection id -> adopted domain (plan 3.6). */
  domains: Record<string, DomainName>;
  /** Connection id -> causal stroke; empty until J2.4. */
  causality: Record<string, CausalityStroke>;
  /** Connection id -> unit conversion factor. */
  unitFactors: Record<string, number>;
  /** Connection id -> instance-qualified reference frame (D-MB5). */
  frames: Record<string, string>;
  signals: RunSignal[];
  stats: ModelCheckStats | null;
  /** The document revision the shown result belongs to, or null. */
  checkedRevision: number | null;
  /** The last transport/protocol failure, when the check did not answer. */
  error: string | null;
  workerState: WorkerState | null;
  counts: DiagnosticsCounts;
  focus: FocusRequest | null;
  sourceFocus: SourceFocus | null;

  beginCheck: () => void;
  beginWaiting: () => void;
  applyResult: (result: ModelCheckResult, revision: number) => void;
  setCheckError: (message: string, diagnostics?: readonly Diagnostic[]) => void;
  setWorkerState: (state: WorkerState) => void;
  setViewerDiagnostics: (diagnostics: readonly Diagnostic[]) => void;
  requestFocus: (nodeId: string) => void;
  requestSourceFocus: (source: { ref: string; line: number; col: number }) => void;
  clearResults: () => void;
}

export const EMPTY_COUNTS: DiagnosticsCounts = { error: 0, warning: 0, info: 0 };

/** Count the severities the panel and the dock badges show. */
export function countDiagnostics(diagnostics: readonly Diagnostic[]): DiagnosticsCounts {
  const counts: DiagnosticsCounts = { ...EMPTY_COUNTS };
  for (const diagnostic of diagnostics) {
    switch (diagnostic.severity) {
      case "error":
        counts.error += 1;
        break;
      case "warning":
        counts.warning += 1;
        break;
      case "info":
        counts.info += 1;
        break;
      default:
        break;
    }
  }
  return counts;
}

/** The severities in the order the panel and the plan use them. */
export const SEVERITIES: readonly DiagnosticSeverity[] = ["error", "warning", "info"];

function initialState(): Omit<DiagnosticsState, keyof DiagnosticsActions> {
  return {
    status: "idle",
    diagnostics: [],
    viewerDiagnostics: [],
    domains: {},
    causality: {},
    unitFactors: {},
    frames: {},
    signals: [],
    stats: null,
    checkedRevision: null,
    error: null,
    workerState: null,
    counts: { ...EMPTY_COUNTS },
    focus: null,
    sourceFocus: null,
  };
}

type DiagnosticsActions = Pick<
  DiagnosticsState,
  | "beginCheck"
  | "beginWaiting"
  | "applyResult"
  | "setCheckError"
  | "setWorkerState"
  | "setViewerDiagnostics"
  | "requestFocus"
  | "requestSourceFocus"
  | "clearResults"
>;

export const useDiagnosticsStore = create<DiagnosticsState>()((set, get) => ({
  ...initialState(),

  beginCheck: () => set({ status: "checking", error: null }),

  beginWaiting: () => set({ status: "waiting" }),

  applyResult: (result, revision) =>
    set({
      status: "ok",
      diagnostics: result.diagnostics,
      domains: result.domains as Record<string, DomainName>,
      // J2.4 fills this in; an absent map must not break the panel or canvas.
      causality: result.causality ?? {},
      unitFactors: result.unitFactors ?? {},
      frames: result.frames ?? {},
      signals: result.signals ?? [],
      stats: result.stats ?? null,
      checkedRevision: revision,
      error: null,
      counts: countDiagnostics([...result.diagnostics, ...get().viewerDiagnostics]),
    }),

  setCheckError: (message, diagnostics = []) =>
    set({
      status: "error",
      error: message,
      diagnostics: [...diagnostics],
      counts: countDiagnostics([...diagnostics, ...get().viewerDiagnostics]),
    }),

  setWorkerState: (workerState) => set({ workerState }),

  setViewerDiagnostics: (viewerDiagnostics) =>
    set((state) => ({
      viewerDiagnostics: [...viewerDiagnostics],
      counts: countDiagnostics([...state.diagnostics, ...viewerDiagnostics]),
    })),

  requestFocus: (nodeId) =>
    set((state) => ({
      focus: { nodeId, nonce: (state.focus?.nonce ?? 0) + 1 },
    })),

  requestSourceFocus: (source) =>
    set((state) => ({
      sourceFocus: {
        ref: source.ref,
        line: source.line,
        col: source.col,
        nonce: (state.sourceFocus?.nonce ?? 0) + 1,
      },
    })),

  clearResults: () =>
    set((state) => ({
      ...initialState(),
      workerState: state.workerState,
      // the 3D view owns these: a model switch clears them when its scene reloads
      viewerDiagnostics: state.viewerDiagnostics,
      counts: countDiagnostics(state.viewerDiagnostics),
    })),
}));

/** Reset every field; used by tests and when a different document opens. */
export function resetDiagnosticsStore(): void {
  useDiagnosticsStore.setState(initialState());
}

export const selectCounts = (state: DiagnosticsState): DiagnosticsCounts => state.counts;
