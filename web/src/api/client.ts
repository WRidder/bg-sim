/**
 * The typed HTTP client for the backend API (plan 3.7).
 *
 * The base URL comes from `VITE_API_BASE` and defaults to "" — a relative URL
 * — so the same code works behind the Vite dev proxy and behind the backend
 * that serves `web/dist` (plan 2.1).
 */

import { isWorkerState, type HealthResponse } from "./health";

const RAW_BASE: string = import.meta.env.VITE_API_BASE ?? "";

/** Backend base URL without a trailing slash; "" means same origin. */
export const API_BASE: string = RAW_BASE.replace(/\/+$/, "");

/** A failed request: a transport error (status 0) or a non-2xx answer. */
export class ApiError extends Error {
  readonly status: number;
  readonly url: string;

  constructor(message: string, options: { status: number; url: string; cause?: unknown }) {
    super(message, { cause: options.cause });
    this.name = "ApiError";
    this.status = options.status;
    this.url = options.url;
  }
}

export interface RequestOptions {
  /** Aborts the request; an abort is re-thrown unchanged, not wrapped. */
  signal?: AbortSignal;
}

function isAbort(error: unknown, signal: AbortSignal | undefined): boolean {
  if (signal?.aborted) {
    return true;
  }
  return error instanceof DOMException && error.name === "AbortError";
}

/** Fetches `path` and parses the JSON body, reporting failures as ApiError. */
export async function requestJson<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const url = `${API_BASE}${path}`;
  let response: Response;
  try {
    response = await fetch(url, {
      headers: { accept: "application/json" },
      signal: options.signal,
    });
  } catch (cause) {
    if (isAbort(cause, options.signal)) {
      throw cause;
    }
    throw new ApiError(`Cannot reach the bg-sim backend at ${url}. Is it running?`, {
      status: 0,
      url,
      cause,
    });
  }

  if (!response.ok) {
    throw new ApiError(`The bg-sim backend answered ${response.status} for ${path}.`, {
      status: response.status,
      url,
    });
  }

  try {
    return (await response.json()) as T;
  } catch (cause) {
    throw new ApiError(`The bg-sim backend answered ${path} with invalid JSON.`, {
      status: response.status,
      url,
      cause,
    });
  }
}

/** `GET /api/health` (plan 3.7), validated at the boundary. */
export async function getHealth(options: RequestOptions = {}): Promise<HealthResponse> {
  const payload = await requestJson<Partial<HealthResponse>>("/api/health", options);
  if (!isWorkerState(payload.worker)) {
    throw new ApiError(
      `The backend reported an unknown worker state (${JSON.stringify(payload.worker ?? null)}).`,
      { status: 200, url: `${API_BASE}/api/health` },
    );
  }
  const health: HealthResponse = {
    backend: typeof payload.backend === "string" ? payload.backend : "unknown",
    worker: payload.worker,
    versions: payload.versions ?? {},
  };
  return health;
}
