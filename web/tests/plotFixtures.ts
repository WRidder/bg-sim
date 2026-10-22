/** Shared plot fixtures for the W1.4 unit tests. */

import type {
  RunManifest,
  RunSignal,
  RunSignalKind,
  ValueType,
} from "../src/contracts/run-manifest";

export function runSignal(
  id: string,
  options: {
    unit?: string | null;
    kind?: RunSignalKind;
    type?: ValueType;
    path?: string;
  } = {},
): RunSignal {
  return {
    id,
    unit: options.unit ?? null,
    kind: options.kind ?? "state",
    path: options.path ?? (id.includes("/") ? id.slice(0, id.lastIndexOf("/")) : ""),
    type: options.type ?? "Real",
  };
}

export function runManifest(
  signals: RunSignal[],
  overrides: Partial<RunManifest> = {},
): RunManifest {
  return {
    id: "run-test",
    model: "Model1",
    modelHash: "0".repeat(64),
    created: "2026-01-01T00:00:00Z",
    status: "done",
    settings: {
      t_start: 0,
      t_end: 1,
      solver: "auto",
      reltol: 1e-6,
      abstol: 1e-8,
      max_step: null,
      output: { mode: "points", points: 1001 },
      event_limit: 10000,
    },
    stats: {
      compile_s: 0.1,
      sim_s: 0.5,
      steps: 1000,
      events: 0,
      states: 2,
      equations: 5,
    },
    signals,
    time: { n: 1001, t0: 0, t1: 1 },
    diagnostics: [],
    layout: "columnar-f64-v1",
    ...overrides,
  };
}
