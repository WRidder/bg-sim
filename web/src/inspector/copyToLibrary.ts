/**
 * "Copy to project library" (plan 7.4): fork a library block into
 * `library/<Name>.jl`, then re-point the instance when the refreshed catalog
 * exposes the project block.
 *
 * The write uses the project-library PUT of plan 3.7:
 *
 *     PUT /api/projects/{project}/library/{block}   text/plain source
 *
 * The catalog is re-read afterwards because the worker is the only authority
 * on which project blocks exist and what their interface is. The fake worker
 * serves a fixed fixture catalog, so it never publishes the fork; the caller
 * reports that instead of re-pointing to a block the editor cannot resolve.
 */

import { API_BASE } from "../api/client";
import type { Catalog, CatalogBlock } from "../contracts/catalog";
import { fetchCatalog } from "../library/catalogClient";
import { uniqueName } from "../state/ids";

export interface CopyOutcome {
  /** The new project block name (also the file stem). */
  name: string;
  /** Display path, e.g. `library/DCMotorCopy.jl`. */
  file: string;
  /** The rewritten source that was written. */
  source: string;
  /** `project:<name>` when the refreshed catalog contains it, else null. */
  ref: string | null;
  /** The refreshed catalog, or null when re-reading it failed after the write. */
  catalog: Catalog | null;
  /** Why the catalog could not be re-read; the library file still exists. */
  catalogError: string | null;
}

interface ProjectInfo {
  libraryNames: string[];
  libraryDir: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Rewrite the `@block <oldName>` declaration to the new project block name. */
export function forkedSource(block: CatalogBlock, name: string): string {
  const pattern = new RegExp(`^([ \\t]*@block[ \\t]+)${escapeRegExp(block.name)}\\b`, "m");
  if (!pattern.test(block.source)) {
    throw new Error(
      `The source of ${block.name} has no @block ${block.name} declaration to rename.`,
    );
  }
  return block.source.replace(pattern, (_match, prefix: string) => `${prefix}${name}`);
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

async function loadProjectInfo(project: string): Promise<ProjectInfo> {
  const url = `${API_BASE}/api/projects/${encodeURIComponent(project)}`;
  let response: Response;
  try {
    response = await fetch(url, { headers: { accept: "application/json" } });
  } catch (cause) {
    throw new Error(`Cannot reach the bg-sim backend at ${url}. Is it running?`, { cause });
  }
  const text = await response.text();
  if (!response.ok) {
    throw new Error(
      `The project "${project}" could not be read: ${detailFrom(text, response.status)}`,
    );
  }
  let body: unknown;
  try {
    body = JSON.parse(text) as unknown;
  } catch {
    body = null;
  }
  const libraryNames: string[] = [];
  const library = isRecord(body) && Array.isArray(body.library) ? body.library : [];
  for (const entry of library) {
    if (isRecord(entry) && typeof entry.name === "string") {
      libraryNames.push(entry.name);
    }
  }
  const projectDocument = isRecord(body) && isRecord(body.project) ? body.project : null;
  const libraryDir =
    projectDocument !== null && typeof projectDocument.libraryDir === "string"
      ? projectDocument.libraryDir
      : "library";
  return { libraryNames, libraryDir };
}

/**
 * Fork `block` into the project library. The returned `ref` is non-null only
 * when the refreshed catalog already contains `project:<name>`.
 */
export async function copyBlockToProjectLibrary(
  project: string,
  block: CatalogBlock,
): Promise<CopyOutcome> {
  const info = await loadProjectInfo(project);
  const name = uniqueName(`${block.name}Copy`, info.libraryNames);
  const source = forkedSource(block, name);
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
  const text = await response.text();
  if (!response.ok) {
    throw new Error(`The block could not be copied: ${detailFrom(text, response.status)}`);
  }
  const ref = `project:${name}`;
  let catalog: Catalog | null = null;
  let catalogError: string | null = null;
  try {
    catalog = await fetchCatalog(project);
  } catch (error) {
    catalogError = error instanceof Error ? error.message : String(error);
  }
  return {
    name,
    file: `${info.libraryDir}/${name}.jl`,
    source,
    ref: catalog !== null && catalog.blocks.some((entry) => entry.ref === ref) ? ref : null,
    catalog,
    catalogError,
  };
}
