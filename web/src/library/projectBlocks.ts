/**
 * The project library (plan 3.3, 3.7, 7.4): `library/<Name>.jl` files of the
 * open project, written with
 *
 *     GET /api/projects/{project}                   the library file list
 *     PUT /api/projects/{project}/library/{block}   text/plain source
 *
 * and published by re-reading the catalog, because the worker is the only
 * authority on which project blocks exist and what their interface is. Every
 * way a block gets into the project library goes through here: "Copy to
 * project library" (inspector/copyToLibrary.ts), "Save to project library"
 * of an inline block and "+ Library block" in the Code tab
 * (code/inlineToLibrary.ts).
 *
 * The fake worker serves a fixed fixture catalog, so it never publishes a new
 * project block; `ref` is then null and the caller reports that instead of
 * re-pointing an instance to a block the editor cannot resolve.
 */

import { API_BASE } from "../api/client";
import type { Catalog } from "../contracts/catalog";
import { fetchCatalog } from "./catalogClient";

export interface ProjectLibraryInfo {
  /** The block names (file stems) already in `library/`. */
  libraryNames: string[];
  /** The project's library folder, `library` by default. */
  libraryDir: string;
}

export interface PublishOutcome {
  /** The project block name (also the file stem). */
  name: string;
  /** Display path, e.g. `library/DCMotorCopy.jl`. */
  file: string;
  /** The source that was written. */
  source: string;
  /** `project:<name>` when the refreshed catalog contains it, else null. */
  ref: string | null;
  /** The refreshed catalog, or null when re-reading it failed after the write. */
  catalog: Catalog | null;
  /** Why the catalog could not be re-read; the library file still exists. */
  catalogError: string | null;
}

/**
 * Julia's reserved words: a block named after one would not parse, and the
 * backend only checks the identifier shape.
 */
const JULIA_KEYWORDS = new Set([
  "baremodule",
  "begin",
  "break",
  "catch",
  "const",
  "continue",
  "do",
  "else",
  "elseif",
  "end",
  "export",
  "false",
  "finally",
  "for",
  "function",
  "global",
  "if",
  "import",
  "let",
  "local",
  "macro",
  "module",
  "quote",
  "return",
  "struct",
  "true",
  "try",
  "using",
  "while",
]);

/** File names Windows refuses (the backend rejects them too). */
const WINDOWS_RESERVED = /^(con|prn|aux|nul|com[0-9]|lpt[0-9])$/i;

const IDENTIFIER = /^[A-Za-z_][A-Za-z0-9_]*$/;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** A short user-facing detail from an error answer of the backend. */
export function detailFrom(text: string, status: number): string {
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

/**
 * Why `name` cannot be a new project block, or null when it can. The file
 * name is the block name (plan 3.3), and Windows file names ignore case, so a
 * name that differs from an existing block only in case is taken too.
 */
export function blockNameProblem(name: string, taken: Iterable<string>): string | null {
  const trimmed = name.trim();
  if (trimmed.length === 0) {
    return "Enter a block name.";
  }
  if (!IDENTIFIER.test(trimmed)) {
    return "Use a Julia identifier: a letter or “_”, then letters, digits or “_”.";
  }
  if (JULIA_KEYWORDS.has(trimmed)) {
    return `“${trimmed}” is a Julia keyword.`;
  }
  if (WINDOWS_RESERVED.test(trimmed)) {
    return `“${trimmed}” is a reserved file name on Windows.`;
  }
  const lower = trimmed.toLowerCase();
  for (const existing of taken) {
    if (existing.toLowerCase() === lower) {
      return existing === trimmed
        ? `The project library already has a block called ${existing}.`
        : `The project library already has ${existing}; block file names ignore case.`;
    }
  }
  return null;
}

/**
 * `base` when it is free in the project library (ignoring case), else the
 * first free `base2`, `base3`, ...
 */
export function freeBlockName(base: string, taken: Iterable<string>): string {
  const lower = new Set([...taken].map((name) => name.toLowerCase()));
  if (!lower.has(base.toLowerCase())) {
    return base;
  }
  const match = /^(.*?)(\d+)$/.exec(base);
  const stem = match?.[1] && match[1].length > 0 ? match[1] : base;
  let value = match ? Number(match[2]) + 1 : 2;
  while (lower.has(`${stem}${value}`.toLowerCase())) {
    value += 1;
  }
  return `${stem}${value}`;
}

/**
 * Rename the first `@block <Name>` declaration to `name` (a library file must
 * declare the block named like the file). With `from`, only a declaration of
 * that name matches. Throws when the source has no such declaration.
 */
export function renameBlockDeclaration(source: string, name: string, from?: string): string {
  const declared = from === undefined ? "[A-Za-z_][A-Za-z0-9_]*" : escapeRegExp(from);
  const pattern = new RegExp(`^([ \\t]*@block[ \\t]+)${declared}\\b`, "m");
  if (!pattern.test(source)) {
    throw new Error(
      from === undefined
        ? "The source has no @block <Name> declaration to name the library block."
        : `The source of ${from} has no @block ${from} declaration to rename.`,
    );
  }
  return source.replace(pattern, (_match, prefix: string) => `${prefix}${name}`);
}

/** The project's library file names and folder; throws with a user-facing message. */
export async function loadProjectLibraryInfo(project: string): Promise<ProjectLibraryInfo> {
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
 * Write `source` to `library/<name>.jl`; throws with a user-facing message
 * that starts with `failure` ("The block could not be saved" by default).
 */
export async function writeProjectLibrary(
  project: string,
  name: string,
  source: string,
  failure = "The block could not be saved",
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
    throw new Error(`${failure}: ${detailFrom(text, response.status)}`);
  }
}

/**
 * Write a new project block and re-read the catalog. A failed write throws; a
 * failed catalog read does not (the file exists), it is reported in
 * `catalogError`.
 */
export async function publishProjectBlock(
  project: string,
  name: string,
  source: string,
  options: { libraryDir?: string; failure?: string } = {},
): Promise<PublishOutcome> {
  await writeProjectLibrary(project, name, source, options.failure);
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
    file: `${options.libraryDir ?? "library"}/${name}.jl`,
    source,
    ref: catalog !== null && catalog.blocks.some((entry) => entry.ref === ref) ? ref : null,
    catalog,
    catalogError,
  };
}

/**
 * The source of `library/<name>.jl` of `project`, or null when the project has no
 * such block (404); throws with a user-facing message on any other failure.
 */
export async function readProjectLibrarySource(project: string, name: string): Promise<string | null> {
  const url = `${API_BASE}/api/projects/${encodeURIComponent(project)}/library/${encodeURIComponent(name)}`;
  let response: Response;
  try {
    response = await fetch(url, { headers: { accept: "text/plain" } });
  } catch (cause) {
    throw new Error(`Cannot reach the bg-sim backend at ${url}. Is it running?`, { cause });
  }
  const text = await response.text();
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error(`The library block ${name} could not be read: ${detailFrom(text, response.status)}`);
  }
  return text;
}
