/**
 * Opening projects, shared by the Open dialog and the start page: navigate to
 * the session route after saving the open document, create a project, and
 * import an example as a copy (samples are read-only templates, so importing
 * always goes through `POST /api/projects {name, example}`).
 */

import { useDocumentStore } from "../state/documentStore";
import { createProject, ProjectApiError, type ProjectModelEntry } from "../state/modelApi";
import { saveCurrentModel } from "../state/persistence";

export const NAME_PATTERN = /^[A-Za-z0-9_.-]+$/;

export function nameIssue(value: string, kind: "project" | "model"): string | null {
  const name = value.trim();
  if (name.length === 0) {
    return `Enter a ${kind} name.`;
  }
  if (!NAME_PATTERN.test(name) || name.startsWith(".") || name.endsWith(".")) {
    return "Use letters, digits, '_', '-' or '.' (no leading or trailing dot).";
  }
  return null;
}

export function modelNames(entries: readonly ProjectModelEntry[]): string[] {
  return entries.filter((entry) => entry.inProject).map((entry) => entry.name);
}

export function firstModel(
  entries: readonly ProjectModelEntry[],
  preferred = "iconic",
): string | null {
  const names = modelNames(entries);
  if (names.includes(preferred)) {
    return preferred;
  }
  return names[0] ?? entries[0]?.name ?? null;
}

/** A free project name for an imported sample: `dc-motor`, then `dc-motor-2`, … */
export function uniqueProjectName(base: string, taken: ReadonlySet<string>): string {
  if (!taken.has(base)) {
    return base;
  }
  for (let index = 2; index < 10_000; index += 1) {
    const candidate = `${base}-${index}`;
    if (!taken.has(candidate)) {
      return candidate;
    }
  }
  return `${base}-${Date.now()}`;
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/** The one place the app leaves the page; tests replace `assign` (jsdom cannot navigate). */
export const navigation = {
  assign: (url: string): void => window.location.assign(url),
};

export type OpenResult = { ok: true } | { ok: false; error: string };

/**
 * Save the open document (if dirty), then navigate to `?project=&model=`. The
 * page reloads, so a successful call never returns control to a live UI.
 */
export async function openSession(project: string, model: string): Promise<OpenResult> {
  const state = useDocumentStore.getState();
  if (state.project !== null && state.revision !== state.savedRevision) {
    const saved = await saveCurrentModel();
    if (!saved) {
      return {
        ok: false,
        error: "The current model could not be saved; fix the save error and try again.",
      };
    }
  }
  const url = new URL(window.location.href);
  url.searchParams.set("project", project);
  url.searchParams.set("model", model);
  navigation.assign(url.toString());
  return { ok: true };
}

export class SampleImportError extends Error {
  constructor(
    message: string,
    /** The project list changed under the import (HTTP 409): reload it and retry. */
    readonly conflict: boolean,
    /** The imported project when the sample has no models to open. */
    readonly project: string | null = null,
  ) {
    super(message);
    this.name = "SampleImportError";
  }
}

/**
 * Import `sample` as a new project (never writing to the sample) and open its
 * first model. Throws `SampleImportError`; resolves with the open result.
 */
export async function importSample(
  sample: string,
  existingProjects: ReadonlySet<string>,
): Promise<OpenResult> {
  try {
    const target = uniqueProjectName(sample, existingProjects);
    const opened = await createProject(target, sample);
    const model = firstModel(opened.models);
    if (model === null) {
      throw new SampleImportError(`The sample “${sample}” has no models.`, false, opened.name);
    }
    return await openSession(opened.name, model);
  } catch (cause) {
    if (cause instanceof SampleImportError) {
      throw cause;
    }
    if (cause instanceof ProjectApiError && cause.status === 409) {
      throw new SampleImportError("The project list changed while importing; try again.", true);
    }
    throw new SampleImportError(errorMessage(cause), false);
  }
}
