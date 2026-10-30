/**
 * The run endpoints of plan 3.7 used by the editor:
 *
 *     POST   /api/projects/{p}/runs        { model } -> { runId }
 *     GET    /api/runs/{id}                the manifest
 *     GET    /api/runs/{id}/data?ids=&t0=&t1=&px=   binary columns
 *     DELETE /api/runs/{id}                cancel
 *     WS     /ws/runs/{id}                 phases, progress, done, tails
 *
 * Every non-2xx answer carries the backend's `detail` when it has one, so a
 * failed start points at the model problem rather than at the transport.
 */

import { API_BASE } from "../api/client";
import type { DebugStartOptions } from "../contracts/debug";
import type { Model } from "../contracts/model";
import type { RunManifest } from "../contracts/run-manifest";
import type { SeriesWindow } from "./runCache";
import { parseRunData, RunDataError, type RunDataFrame } from "./runData";

/** A failed run request with the HTTP status and the backend's detail. */
export class RunApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.name = "RunApiError";
    this.status = status;
    this.detail = detail;
  }
}

interface ErrorBody {
  detail?: unknown;
  message?: unknown;
}

function detailText(body: unknown): string | null {
  if (typeof body === "string" && body.trim().length > 0) {
    return body;
  }
  if (typeof body !== "object" || body === null) {
    return null;
  }
  const record = body as ErrorBody;
  if (typeof record.detail === "string" && record.detail.trim().length > 0) {
    return record.detail;
  }
  if (typeof record.detail === "object" && record.detail !== null) {
    const detail = record.detail as { message?: unknown };
    if (typeof detail.message === "string" && detail.message.trim().length > 0) {
      return detail.message;
    }
  }
  if (typeof record.message === "string" && record.message.trim().length > 0) {
    return record.message;
  }
  return null;
}

async function failure(response: Response, action: string): Promise<RunApiError> {
  let body: unknown = null;
  try {
    const text = await response.text();
    if (text.length > 0) {
      try {
        body = JSON.parse(text) as unknown;
      } catch {
        body = text;
      }
    }
  } catch {
    body = null;
  }
  const detail = detailText(body);
  return new RunApiError(
    detail ?? `${action} failed: the backend answered ${response.status}.`,
    response.status,
    body,
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

const RUN_STATUSES = new Set(["running", "paused", "done", "failed", "cancelled"]);

/** A narrow boundary check; a malformed manifest must not crash the plot UI. */
function isRunManifest(value: unknown): value is RunManifest {
  if (!isRecord(value)) {
    return false;
  }
  if (
    typeof value.id !== "string" ||
    typeof value.model !== "string" ||
    typeof value.status !== "string" ||
    !RUN_STATUSES.has(value.status) ||
    !Array.isArray(value.signals) ||
    !isRecord(value.time) ||
    !isRecord(value.settings)
  ) {
    return false;
  }
  return value.signals.every(
    (signal) =>
      isRecord(signal) &&
      typeof signal.id === "string" &&
      typeof signal.path === "string" &&
      typeof signal.kind === "string" &&
      typeof signal.type === "string",
  );
}

function projectRunsPath(project: string): string {
  return `/api/projects/${encodeURIComponent(project)}/runs`;
}

/** Start a run with the model **document** (the backend compiles it). */
export async function createRun(
  project: string,
  model: Model,
  signal?: AbortSignal,
  debug?: DebugStartOptions,
): Promise<string> {
  const url = `${API_BASE}${projectRunsPath(project)}`;
  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: {
        accept: "application/json",
        "content-type": "application/json",
      },
      body: JSON.stringify(debug === undefined ? { model } : { model, debug }),
      signal,
    });
  } catch (cause) {
    if (signal?.aborted) {
      throw cause;
    }
    throw new RunApiError(
      `Cannot reach the bg-sim backend at ${url}. Is it running?`,
      0,
      cause,
    );
  }
  if (!response.ok) {
    throw await failure(response, "Starting the run");
  }
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new RunApiError(
      "The backend accepted the run but did not return a run id.",
      response.status,
    );
  }
  if (!isRecord(body) || typeof body.runId !== "string" || body.runId.length === 0) {
    throw new RunApiError(
      "The backend accepted the run but did not return a run id.",
      response.status,
      body,
    );
  }
  return body.runId;
}

/** `GET /api/runs/{id}`. */
export async function fetchRunManifest(
  runId: string,
  signal?: AbortSignal,
): Promise<RunManifest> {
  const url = `${API_BASE}/api/runs/${encodeURIComponent(runId)}`;
  let response: Response;
  try {
    response = await fetch(url, { headers: { accept: "application/json" }, signal });
  } catch (cause) {
    if (signal?.aborted) {
      throw cause;
    }
    throw new RunApiError(
      `Cannot reach the bg-sim backend at ${url}. Is it running?`,
      0,
      cause,
    );
  }
  if (!response.ok) {
    throw await failure(response, "Reading the run manifest");
  }
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new RunApiError(
      "The run manifest is not valid JSON. Reload the run.",
      response.status,
    );
  }
  if (!isRunManifest(body)) {
    throw new RunApiError(
      "The run manifest does not follow the run-manifest contract. " +
        "The backend and the web app are probably different versions.",
      response.status,
      body,
    );
  }
  return body;
}

/** `DELETE /api/runs/{id}`; true when the worker accepted the cancellation. */
export async function cancelRun(
  runId: string,
  signal?: AbortSignal,
): Promise<boolean> {
  const url = `${API_BASE}/api/runs/${encodeURIComponent(runId)}`;
  let response: Response;
  try {
    response = await fetch(url, { method: "DELETE", signal });
  } catch (cause) {
    if (signal?.aborted) {
      throw cause;
    }
    throw new RunApiError(
      `Cannot reach the bg-sim backend at ${url}. Is it running?`,
      0,
      cause,
    );
  }
  if (!response.ok) {
    throw await failure(response, "Stopping the run");
  }
  try {
    const body = (await response.json()) as unknown;
    return isRecord(body) && body.ok === true;
  } catch {
    return false;
  }
}

/**
 * The `/data` URL. `ids` are sent in display order; the answer's columns keep
 * that order. A null window means "show all" and requests raw data (`px=0`,
 * plan 7.5), so the first paint never hides spikes behind decimation.
 */
export function runDataUrl(
  runId: string,
  ids: readonly string[],
  window: SeriesWindow | null,
  px: number,
): string {
  const params = new URLSearchParams();
  if (ids.length > 0) {
    params.set("ids", ids.join(","));
  }
  if (window !== null) {
    params.set("t0", String(window.t0));
    params.set("t1", String(window.t1));
  }
  params.set("px", String(Math.max(0, Math.round(px))));
  return `${API_BASE}/api/runs/${encodeURIComponent(runId)}/data?${params.toString()}`;
}

/** Fetch and decode one `/data` answer. */
export async function fetchRunData(
  runId: string,
  ids: readonly string[],
  window: SeriesWindow | null,
  px: number,
  signal?: AbortSignal,
): Promise<RunDataFrame> {
  const url = runDataUrl(runId, ids, window, px);
  let response: Response;
  try {
    response = await fetch(url, {
      headers: { accept: "application/octet-stream" },
      signal,
    });
  } catch (cause) {
    if (signal?.aborted) {
      throw cause;
    }
    throw new RunApiError(
      `Cannot reach the bg-sim backend at ${url}. Is it running?`,
      0,
      cause,
    );
  }
  if (!response.ok) {
    throw await failure(response, "Reading the run data");
  }
  const buffer = await response.arrayBuffer();
  try {
    return parseRunData(buffer);
  } catch (error) {
    if (error instanceof RunDataError) {
      throw new RunApiError(error.message, response.status);
    }
    throw error;
  }
}

/** The CSV download URL, with the plotted signals or (when empty) every signal. */
export function runExportUrl(runId: string, ids: readonly string[]): string {
  const params = new URLSearchParams();
  if (ids.length > 0) {
    params.set("ids", ids.join(","));
  }
  const query = params.toString();
  return `${API_BASE}/api/runs/${encodeURIComponent(runId)}/export.csv${
    query.length > 0 ? `?${query}` : ""
  }`;
}

/**
 * The run WebSocket URL. The backend aliases the socket at `/ws/runs/{id}`
 * as well as `/api/ws/runs/{id}`; the alias is also the path the Vite dev
 * server proxies with `ws: true`.
 */
export function runSocketUrl(runId: string): string {
  const base =
    API_BASE.length > 0
      ? API_BASE
      : typeof window === "undefined"
        ? "http://127.0.0.1:8765"
        : window.location.origin;
  const url = new URL(
    `${base}/ws/runs/${encodeURIComponent(runId)}`,
    typeof window === "undefined" ? "http://127.0.0.1:8765" : window.location.href,
  );
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}
