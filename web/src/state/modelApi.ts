/**
 * The model/project calls of plan 3.7 used by the editor:
 *
 *     GET  /api/projects/{p}
 *     POST /api/projects                      { name }
 *     GET  /api/projects/{p}/models/{m}       the model document
 *     PUT  /api/projects/{p}/models/{m}       validate + store, returns the document
 *
 * `{m}` is the model name (the file is `models/<m>.bgmodel.json`; the backend
 * also accepts the file name). Requests go through the same base URL as the
 * rest of the client (src/api/client.ts), so the Vite proxy and the production
 * backend both work unchanged.
 */

import { API_BASE } from "../api/client";
import type { Model } from "../contracts/model";

export class ProjectApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.name = "ProjectApiError";
    this.status = status;
    this.detail = detail;
  }
}

interface ApiAnswer {
  status: number;
  body: unknown;
  text: string;
}

function detailMessage(body: unknown, status: number): string {
  if (typeof body === "string" && body.trim().length > 0) {
    return body;
  }
  if (typeof body === "object" && body !== null) {
    const record = body as Record<string, unknown>;
    if (typeof record.detail === "string") {
      return record.detail;
    }
    if (typeof record.detail === "object" && record.detail !== null) {
      const detail = record.detail as Record<string, unknown>;
      if (typeof detail.message === "string") {
        return detail.message;
      }
    }
    if (typeof record.message === "string") {
      return record.message;
    }
  }
  return `The bg-sim backend answered ${status}.`;
}

async function call(
  path: string,
  init: { method: string; body?: unknown; signal?: AbortSignal } = { method: "GET" },
): Promise<ApiAnswer> {
  const url = `${API_BASE}${path}`;
  const headers: Record<string, string> = { accept: "application/json" };
  if (init.body !== undefined) {
    headers["content-type"] = "application/json";
  }
  let response: Response;
  try {
    response = await fetch(url, {
      method: init.method,
      headers,
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
      signal: init.signal,
    });
  } catch (cause) {
    if (init.signal?.aborted) {
      throw cause;
    }
    throw new ProjectApiError(
      `Cannot reach the bg-sim backend at ${url}. Is it running?`,
      0,
      cause,
    );
  }
  const text = await response.text();
  let body: unknown = null;
  if (text.length > 0) {
    try {
      body = JSON.parse(text) as unknown;
    } catch {
      body = text;
    }
  }
  return { status: response.status, body, text };
}

function projectPath(project: string): string {
  return `/api/projects/${encodeURIComponent(project)}`;
}

function modelPath(project: string, model: string): string {
  return `${projectPath(project)}/models/${encodeURIComponent(model)}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** A document the editor can open; the backend validates the full schema. */
export function isModelDocument(value: unknown): value is Model {
  if (!isRecord(value) || value.format !== "bgsim.model") {
    return false;
  }
  if (typeof value.name !== "string" || typeof value.language !== "string") {
    return false;
  }
  if (!isRecord(value.diagram)) {
    return false;
  }
  return (
    Array.isArray(value.diagram.nodes) &&
    Array.isArray(value.diagram.connections) &&
    isRecord(value.settings)
  );
}

/**
 * Ensure the project exists, creating an empty one when the backend answers
 * 404. A concurrent creation (409) is treated as success.
 */
export async function ensureProject(project: string, signal?: AbortSignal): Promise<void> {
  const answer = await call(projectPath(project), { method: "GET", signal });
  if (answer.status === 200) {
    return;
  }
  if (answer.status !== 404) {
    throw new ProjectApiError(detailMessage(answer.body, answer.status), answer.status, answer.body);
  }
  const created = await call(`/api/projects`, {
    method: "POST",
    body: { name: project },
    signal,
  });
  if (created.status === 201 || created.status === 200 || created.status === 409) {
    return;
  }
  throw new ProjectApiError(
    detailMessage(created.body, created.status),
    created.status,
    created.body,
  );
}

/** The model document, or null when the project has no such model yet. */
export async function getModel(
  project: string,
  model: string,
  signal?: AbortSignal,
): Promise<Model | null> {
  const answer = await call(modelPath(project, model), { method: "GET", signal });
  if (answer.status === 404) {
    return null;
  }
  if (answer.status !== 200) {
    throw new ProjectApiError(detailMessage(answer.body, answer.status), answer.status, answer.body);
  }
  if (!isModelDocument(answer.body)) {
    throw new ProjectApiError(
      `The model ${project}/${model} does not match the model contract.`,
      answer.status,
      answer.body,
    );
  }
  return answer.body;
}

/** Validate, store and return the document (the backend normalises defaults). */
export async function putModel(
  project: string,
  model: string,
  document: Model,
  signal?: AbortSignal,
): Promise<Model> {
  const answer = await call(modelPath(project, model), {
    method: "PUT",
    body: document,
    signal,
  });
  if (answer.status < 200 || answer.status >= 300) {
    throw new ProjectApiError(detailMessage(answer.body, answer.status), answer.status, answer.body);
  }
  return isModelDocument(answer.body) ? answer.body : document;
}

// --------------------------------------------------------------- project browser

/** One row of `GET /api/projects` (plan 3.7). */
export interface ProjectSummary {
  name: string;
  path: string;
  language: string | null;
  /** The model names in the project file's tab order. */
  models: string[];
  modified: string | null;
  valid: boolean;
  error: string | null;
}

/** One model entry of the `GET /api/projects/{p}` payload. */
export interface ProjectModelEntry {
  name: string;
  modified: string | null;
  inProject: boolean;
}

/** The open-project payload (`GET /projects/{p}` and `POST /projects`). */
export interface OpenedProject {
  name: string;
  path: string;
  models: ProjectModelEntry[];
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((entry): entry is string => typeof entry === "string")
    : [];
}

function openedProject(body: unknown): OpenedProject {
  if (!isRecord(body) || typeof body.name !== "string") {
    throw new ProjectApiError("The backend returned an invalid project payload.", 0, body);
  }
  const models = Array.isArray(body.models)
    ? body.models.filter(isRecord).flatMap((entry) => {
        if (typeof entry.name !== "string") {
          return [];
        }
        return [
          {
            name: entry.name,
            modified: typeof entry.modified === "string" ? entry.modified : null,
            inProject: entry.inProject === true,
          },
        ];
      })
    : [];
  return {
    name: body.name,
    path: typeof body.path === "string" ? body.path : "",
    models,
  };
}

/** Every project below the backend's projects root. */
export async function listProjects(signal?: AbortSignal): Promise<ProjectSummary[]> {
  const answer = await call("/api/projects", { method: "GET", signal });
  if (answer.status !== 200) {
    throw new ProjectApiError(detailMessage(answer.body, answer.status), answer.status, answer.body);
  }
  const entries = isRecord(answer.body) ? answer.body.projects : undefined;
  if (!Array.isArray(entries)) {
    throw new ProjectApiError("The backend returned an invalid project list.", 0, answer.body);
  }
  return entries.filter(isRecord).flatMap((entry) => {
    if (typeof entry.name !== "string" || entry.name.length === 0) {
      return [];
    }
    return [
      {
        name: entry.name,
        path: typeof entry.path === "string" ? entry.path : "",
        language: typeof entry.language === "string" ? entry.language : null,
        models: stringList(entry.models),
        modified: typeof entry.modified === "string" ? entry.modified : null,
        valid: entry.valid === true,
        error: typeof entry.error === "string" ? entry.error : null,
      },
    ];
  });
}

/** The examples the backend can copy into a new project. */
export async function listExamples(signal?: AbortSignal): Promise<string[]> {
  const answer = await call("/api/examples", { method: "GET", signal });
  if (answer.status !== 200) {
    throw new ProjectApiError(detailMessage(answer.body, answer.status), answer.status, answer.body);
  }
  return stringList(isRecord(answer.body) ? answer.body.examples : undefined);
}

/** Create an empty project, or copy one from `examples/<example>`. */
export async function createProject(
  name: string,
  example?: string,
  signal?: AbortSignal,
): Promise<OpenedProject> {
  const answer = await call("/api/projects", {
    method: "POST",
    body: example === undefined ? { name } : { name, example },
    signal,
  });
  if (answer.status !== 201 && answer.status !== 200) {
    throw new ProjectApiError(detailMessage(answer.body, answer.status), answer.status, answer.body);
  }
  return openedProject(answer.body);
}

/** The project file plus its model and library listings. */
export async function openProject(name: string, signal?: AbortSignal): Promise<OpenedProject> {
  const answer = await call(projectPath(name), { method: "GET", signal });
  if (answer.status !== 200) {
    throw new ProjectApiError(detailMessage(answer.body, answer.status), answer.status, answer.body);
  }
  return openedProject(answer.body);
}
