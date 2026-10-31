/**
 * The export endpoints (plan/EXPORT_PLAN.md P-EX1):
 *
 *     POST   /api/projects/{p}/models/{m}/export   ExportRequest -> { exportId }
 *     GET    /api/exports?project={p}[&model={m}]  ExportJob[] (newest first)
 *     GET    /api/exports/{id}                     ExportJob (status, report, fmu)
 *     DELETE /api/exports/{id}                     cancel
 *     GET    /api/exports/{id}/fmu                 the FMU file
 *
 * A non-2xx answer becomes an `ExportApiError` with the backend's `detail`, so the dialog
 * can say what went wrong instead of failing.
 */

import { API_BASE } from "../api/client";
import type { ExportJob } from "../contracts/export-job";
import type { ExportRequest } from "../contracts/export-request";

export class ExportApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ExportApiError";
    this.status = status;
  }
}

function detailOf(body: unknown): string | null {
  if (typeof body !== "object" || body === null) {
    return null;
  }
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    // FastAPI's request validation errors: [{ loc, msg }, ...]
    return detail
      .map((entry: { loc?: unknown[]; msg?: unknown }) =>
        [Array.isArray(entry.loc) ? entry.loc.join(".") : "", String(entry.msg ?? "")]
          .filter((part) => part.length > 0)
          .join(": "),
      )
      .join("; ");
  }
  return null;
}

async function call<T>(path: string, init: RequestInit, action: string): Promise<T> {
  const url = `${API_BASE}${path}`;
  let response: Response;
  try {
    response = await fetch(url, { ...init, headers: { accept: "application/json", ...init.headers } });
  } catch (cause) {
    if (init.signal?.aborted) {
      throw cause;
    }
    throw new ExportApiError(`Cannot reach the bg-sim backend at ${url}. Is it running?`, 0);
  }
  if (!response.ok) {
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      body = null;
    }
    throw new ExportApiError(
      detailOf(body) ?? `${action} failed: the backend answered ${response.status}.`,
      response.status,
    );
  }
  return (await response.json()) as T;
}

/** Start an export of the model **document** (unsaved edits included). */
export async function startExport(
  project: string,
  model: string,
  request: ExportRequest,
  signal?: AbortSignal,
): Promise<string> {
  const path = `/api/projects/${encodeURIComponent(project)}/models/${model
    .split("/")
    .map(encodeURIComponent)
    .join("/")}/export`;
  const body = await call<{ exportId?: unknown }>(
    path,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(request),
      signal,
    },
    "Starting the export",
  );
  if (typeof body.exportId !== "string") {
    throw new ExportApiError("The backend answered the export without an exportId.", 502);
  }
  return body.exportId;
}

export function getExport(exportId: string, signal?: AbortSignal): Promise<ExportJob> {
  return call<ExportJob>(
    `/api/exports/${encodeURIComponent(exportId)}`,
    { signal },
    "Reading the export status",
  );
}

/** The project's jobs (optionally one model's), newest first. */
export async function listExports(
  project: string,
  model?: string,
  signal?: AbortSignal,
): Promise<ExportJob[]> {
  const params = new URLSearchParams({ project });
  if (model !== undefined) {
    params.set("model", model);
  }
  const body = await call<unknown>(`/api/exports?${params.toString()}`, { signal }, "Listing the exports");
  return Array.isArray(body) ? (body as ExportJob[]) : [];
}

export async function cancelExport(exportId: string): Promise<boolean> {
  const body = await call<{ ok?: unknown }>(
    `/api/exports/${encodeURIComponent(exportId)}`,
    { method: "DELETE" },
    "Cancelling the export",
  );
  return body.ok === true;
}

/** The download URL of a finished export's FMU. */
export function fmuUrl(exportId: string): string {
  return `${API_BASE}/api/exports/${encodeURIComponent(exportId)}/fmu`;
}

/** A job that will not change any more. */
export function isFinished(job: Pick<ExportJob, "status">): boolean {
  return job.status !== "queued" && job.status !== "running";
}
