/**
 * The assistant's REST calls (plan/ASSISTANT_PLAN.md); the event stream is opened by the store.
 * A refused call throws `AssistantApiError` with the backend's sentence.
 */

import { API_BASE } from "../api/client";
import type {
  AssistantAnswers,
  AssistantMessageRequest,
  AssistantProfileList,
  AssistantSessionInfo,
} from "../contracts/assistant";
import type { Model } from "../contracts/model";

export class AssistantApiError extends Error {
  readonly status: number;
  readonly code: string | null;

  constructor(message: string, status: number, code: string | null) {
    super(message);
    this.name = "AssistantApiError";
    this.status = status;
    this.code = code;
  }
}

export interface ApplyResult {
  applied: string[];
  backup: string | null;
  /** The open model as the draft has it: the editor takes it, so it stays one undo step. */
  openModel?: Model;
}

async function call<T>(method: "GET" | "POST" | "DELETE", path: string, body?: unknown): Promise<T> {
  const url = `${API_BASE}/api${path}`;
  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers: { accept: "application/json", ...(body === undefined ? {} : { "content-type": "application/json" }) },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
  } catch {
    throw new AssistantApiError(`Cannot reach the bg-sim backend at ${url}. Is it running?`, 0, null);
  }
  const data = (await response.json().catch(() => null)) as { message?: string; detail?: unknown; code?: string } | null;
  if (!response.ok) {
    const message = data?.message ?? (typeof data?.detail === "string" ? data.detail : null);
    throw new AssistantApiError(message ?? `The assistant answered ${response.status}.`, response.status, data?.code ?? null);
  }
  return data as T;
}

export function eventsUrl(session: string, after: number): string {
  return `${API_BASE}/api/assistant/${encodeURIComponent(session)}/events?after=${after}`;
}

export function fetchProfiles(refresh = false): Promise<AssistantProfileList> {
  return call("GET", `/assistant/profiles${refresh ? "?refresh=true" : ""}`);
}

/** The chat of a project, or of the home screen (`null`). */
export async function findSession(project: string | null): Promise<AssistantSessionInfo | null> {
  const query = project === null ? "" : `?project=${encodeURIComponent(project)}`;
  const found = await call<{ session: AssistantSessionInfo | null }>("GET", `/assistant/sessions${query}`);
  return found.session;
}

export function startSession(project: string | null, body: AssistantMessageRequest): Promise<AssistantSessionInfo> {
  const path = project === null ? "/assistant" : `/projects/${encodeURIComponent(project)}/assistant`;
  return call("POST", path, body);
}

export function sendMessage(session: string, body: AssistantMessageRequest): Promise<AssistantSessionInfo> {
  return call("POST", `/assistant/${encodeURIComponent(session)}/messages`, body);
}

export function sendAnswers(session: string, body: AssistantAnswers): Promise<AssistantSessionInfo> {
  return call("POST", `/assistant/${encodeURIComponent(session)}/answers`, body);
}

export function cancelRun(session: string): Promise<unknown> {
  return call("POST", `/assistant/${encodeURIComponent(session)}/cancel`);
}

export function discardDraft(session: string): Promise<AssistantSessionInfo> {
  return call("POST", `/assistant/${encodeURIComponent(session)}/discard`);
}

export function applyDraft(session: string, openModel: string | null): Promise<ApplyResult> {
  return call("POST", `/assistant/${encodeURIComponent(session)}/apply`, { openModel });
}

export function closeSession(session: string): Promise<unknown> {
  return call("DELETE", `/assistant/${encodeURIComponent(session)}`);
}

export function fetchSession(session: string): Promise<AssistantSessionInfo> {
  return call("GET", `/assistant/${encodeURIComponent(session)}`);
}
