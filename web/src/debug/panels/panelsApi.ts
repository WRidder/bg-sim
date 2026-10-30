/**
 * The two HTTP calls of the Debug panels (plan 3.8):
 *
 *     POST /api/runs/{id}/replay               -> { runId }   (a normal run that applies the edits)
 *     POST /api/check/explain?project=<name>   { model, signal } -> ExplainResult   (needs no run)
 *
 * Failures carry the backend's `detail` so the panel can say what to do next.
 */

import { API_BASE } from "../../api/client";
import type { ExplainResult } from "../../contracts/debug";
import type { Model } from "../../contracts/model";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function detailOf(body: unknown): string | null {
  if (!isRecord(body)) {
    return null;
  }
  const detail = body.detail;
  if (typeof detail === "string" && detail.length > 0) {
    return detail;
  }
  if (isRecord(detail) && typeof detail.message === "string") {
    return detail.message;
  }
  return typeof body.message === "string" && body.message.length > 0 ? body.message : null;
}

async function postJson(path: string, payload: unknown, action: string): Promise<unknown> {
  const url = `${API_BASE}${path}`;
  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { accept: "application/json", "content-type": "application/json" },
      body: JSON.stringify(payload),
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
    throw new Error(detailOf(body) ?? `${action} failed: the backend answered ${response.status}.`);
  }
  return body;
}

/** `POST /api/runs/{id}/replay`: the id of the new run. */
export async function postReplay(runId: string): Promise<string> {
  const body = await postJson(`/api/runs/${encodeURIComponent(runId)}/replay`, {}, "The replay");
  if (!isRecord(body) || typeof body.runId !== "string" || body.runId.length === 0) {
    throw new Error("The backend accepted the replay but did not return a run id.");
  }
  return body.runId;
}

/** `POST /api/check/explain`. */
export async function postExplain(
  project: string | null,
  model: Model,
  signal: string,
): Promise<ExplainResult> {
  const query = project !== null && project.length > 0 ? `?project=${encodeURIComponent(project)}` : "";
  const body = await postJson(`/api/check/explain${query}`, { model, signal }, "Explaining the signal");
  if (!isRecord(body) || typeof body.kind !== "string" || !Array.isArray(body.equations)) {
    throw new Error("The backend answered the explanation in an unexpected shape.");
  }
  return body as unknown as ExplainResult;
}
