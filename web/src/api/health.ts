/**
 * The health payload of `GET /api/health` (plan 3.7).
 *
 * `contracts/schemas/` has no health schema (M0.2 shipped eight schemas and
 * none of them is the HTTP envelope), so this interface is the local source of
 * truth for the client and must stay in step with the backend's app.py:
 *
 *     { backend, worker: "starting" | "warming" | "ready" | "crashed", versions }
 */

export type WorkerState = "starting" | "warming" | "ready" | "crashed";

export const WORKER_STATES: readonly WorkerState[] = ["starting", "warming", "ready", "crashed"];

export interface HealthResponse {
  /** Backend version, e.g. "0.1.0". */
  backend: string;
  /** Lifecycle state of the Julia worker. */
  worker: WorkerState;
  /** Version stamps: bgsim, julia, python and anything else the backend adds. */
  versions: Record<string, string | number | boolean>;
}

export function isWorkerState(value: unknown): value is WorkerState {
  return typeof value === "string" && (WORKER_STATES as readonly string[]).includes(value);
}

/**
 * True when the backend answers from fixtures instead of a Julia worker
 * (BGSIM_FAKE_WORKER=1, plan 2.3). The backend reports the fake through its
 * `versions` payload; accept either a key or a value that says "fake" so the
 * indicator keeps working if the backend names it differently.
 */
export function isFakeWorker(health: Pick<HealthResponse, "backend" | "versions">): boolean {
  if (/fake/i.test(health.backend)) {
    return true;
  }
  const versions = health.versions ?? {};
  return Object.entries(versions).some(([key, value]) => {
    if (/fake/i.test(key)) {
      return value !== false && value !== 0 && value !== "";
    }
    return typeof value === "string" && /fake/i.test(value);
  });
}

/** A one-line description of the backend and its version stamps, for tooltips. */
export function describeHealth(health: HealthResponse): string {
  const versions = Object.entries(health.versions ?? {})
    .map(([name, value]) => `${name} ${value}`)
    .join(", ");
  return versions.length > 0 ? `backend ${health.backend} · ${versions}` : `backend ${health.backend}`;
}
