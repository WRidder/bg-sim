/**
 * Writing a project library block (plan 3.7):
 *
 *     PUT /api/projects/{project}/library/{block}   text/plain source
 *
 * This is the save path behind the editable project-block source. The copy
 * action already has its own write in `inspector/copyToLibrary.ts`; this
 * module is only for subsequent edits of the same file.
 */

import { API_BASE } from "../api/client";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function detailFrom(text: string, status: number): string {
  const trimmed = text.trim();
  if (trimmed.length === 0) {
    return `The backend answered ${status}.`;
  }
  try {
    const body = JSON.parse(trimmed) as unknown;
    if (isRecord(body) && typeof body.detail === "string") {
      return body.detail;
    }
  } catch {
    // The body is not JSON; the text itself is the detail.
  }
  return trimmed.length > 400 ? `${trimmed.slice(0, 400)}…` : trimmed;
}

/** Write `source` to `library/<name>.jl`; throws with a user-facing message. */
export async function writeProjectLibrary(
  project: string,
  name: string,
  source: string,
): Promise<void> {
  const url = `${API_BASE}/api/projects/${encodeURIComponent(project)}/library/${encodeURIComponent(name)}`;
  let response: Response;
  try {
    response = await fetch(url, {
      method: "PUT",
      headers: { accept: "application/json", "content-type": "text/plain; charset=utf-8" },
      body: source,
    });
  } catch (cause) {
    throw new Error(`Cannot reach the bg-sim backend at ${url}. Is it running?`, { cause });
  }
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`The block could not be saved: ${detailFrom(text, response.status)}`);
  }
}
