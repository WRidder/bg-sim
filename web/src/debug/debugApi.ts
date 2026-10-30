/**
 * The debug HTTP endpoints of plan 3.8 (backend `debug.py`):
 *
 *     PUT  /api/runs/{id}/breakpoints        full set -> { breakpoints: BreakpointStatus[] }
 *     POST /api/runs/{id}/debug/{command}    pause | continue | step | runTo | setParameter | setState
 *     POST /api/runs/{id}/evaluate           { expr, context } -> EvaluateResult
 *     GET  /api/runs/{id}/values?ids=a,b     -> ValuesResult
 *
 * A worker refusal (for example "run is not paused") is a 409 whose `detail`
 * carries the message; it surfaces as a `DebugApiError`.
 */

import { API_BASE } from "../api/client";
import type {
  Breakpoint,
  BreakpointStatus,
  EvaluateResult,
  ValuesResult,
} from "../contracts/debug";

export type DebugCommand = "pause" | "continue" | "step" | "runTo" | "setParameter" | "setState";

export class DebugApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "DebugApiError";
    this.status = status;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function detailOf(body: unknown): string | null {
  if (!isRecord(body)) {
    return typeof body === "string" && body.length > 0 ? body : null;
  }
  const detail = body.detail;
  if (typeof detail === "string" && detail.length > 0) {
    return detail;
  }
  if (isRecord(detail) && typeof detail.message === "string") {
    return detail.message;
  }
  if (typeof body.message === "string" && body.message.length > 0) {
    return body.message;
  }
  return null;
}

async function request(
  path: string,
  init: RequestInit,
  action: string,
  signal?: AbortSignal,
): Promise<unknown> {
  const url = `${API_BASE}${path}`;
  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      headers: { accept: "application/json", ...(init.headers ?? {}) },
      signal,
    });
  } catch (cause) {
    if (signal?.aborted) {
      throw cause;
    }
    throw new DebugApiError(`Cannot reach the bg-sim backend at ${url}. Is it running?`, 0);
  }
  let body: unknown;
  try {
    const text = await response.text();
    body = text.length === 0 ? null : (JSON.parse(text) as unknown);
  } catch {
    body = null;
  }
  if (!response.ok) {
    throw new DebugApiError(
      detailOf(body) ?? `${action} failed: the backend answered ${response.status}.`,
      response.status,
    );
  }
  return body;
}

function runPath(runId: string, rest: string): string {
  return `/api/runs/${encodeURIComponent(runId)}${rest}`;
}

const JSON_HEADERS = { "content-type": "application/json" };

/** `PUT /api/runs/{id}/breakpoints`: replace the full set; the status of every breakpoint. */
export async function putBreakpoints(
  runId: string,
  breakpoints: readonly Breakpoint[],
  signal?: AbortSignal,
): Promise<BreakpointStatus[]> {
  const body = await request(
    runPath(runId, "/breakpoints"),
    { method: "PUT", headers: JSON_HEADERS, body: JSON.stringify({ breakpoints }) },
    "Setting the breakpoints",
    signal,
  );
  if (!isRecord(body) || !Array.isArray(body.breakpoints)) {
    throw new DebugApiError("The backend answered the breakpoints without a status list.", 200);
  }
  return body.breakpoints as BreakpointStatus[];
}

/** `POST /api/runs/{id}/debug/{command}`. */
export async function postDebugCommand(
  runId: string,
  command: DebugCommand,
  body: Record<string, unknown> = {},
  signal?: AbortSignal,
): Promise<unknown> {
  return request(
    runPath(runId, `/debug/${command}`),
    { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(body) },
    `The debug command ${command}`,
    signal,
  );
}

/** `POST /api/runs/{id}/evaluate`: evaluate a watch expression at the pause. */
export async function postEvaluate(
  runId: string,
  expr: string,
  context: string | null,
  signal?: AbortSignal,
): Promise<EvaluateResult> {
  const body = await request(
    runPath(runId, "/evaluate"),
    { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ expr, context }) },
    "Evaluating the expression",
    signal,
  );
  return body as EvaluateResult;
}

/** `GET /api/runs/{id}/values?ids=`: the values of signals at the pause. */
export async function getValues(
  runId: string,
  ids: readonly string[],
  signal?: AbortSignal,
): Promise<ValuesResult> {
  const query = new URLSearchParams({ ids: ids.join(",") });
  const body = await request(
    runPath(runId, `/values?${query.toString()}`),
    { method: "GET" },
    "Reading the values",
    signal,
  );
  return body as ValuesResult;
}
