/**
 * Project data files (backend `data.py`, F5.1): CSV inputs of `stdlib:sources/CsvSource` and
 * reduced-model files (`*.modal.json`) of `stdlib:spatial/ModalBody3D`.
 */

import { API_BASE } from "./client";

/** `csv` for a CSV table, `modal` for a reduced-model file (`bgsim.modal-body`). */
export type DataFileKind = "csv" | "modal";

/** One file of the project data folder. */
export interface DataFile {
  file: string;
  bytes: number;
  /** Sent by the backend since the reduced-model files; absent from older answers (CSV). */
  kind?: DataFileKind;
}

/** The kind of a data file by its name, or null when it is not one. */
export function dataFileKind(file: string): DataFileKind | null {
  const lower = file.toLowerCase();
  if (lower.endsWith(".modal.json") && lower.length > ".modal.json".length) return "modal";
  if (lower.endsWith(".csv") && lower.length > ".csv".length) return "csv";
  return null;
}

/** A column of a CSV header; `unit` is the text of an optional `name [unit]`. */
export interface CsvColumn {
  name: string;
  unit: string;
}

/** `GET /api/projects/{p}/data/{file}/preview`. */
export interface CsvPreview {
  project: string;
  file: string;
  path: string;
  bytes: number;
  rows: number;
  columns: CsvColumn[];
  head: (number | string)[][];
  delimiter: string;
}

/** The backend refused a data request; `message` says what to do. */
export class DataApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "DataApiError";
  }
}

function base(project: string): string {
  return `${API_BASE}/api/projects/${encodeURIComponent(project)}/data`;
}

async function failure(response: Response, what: string): Promise<DataApiError> {
  let detail: string;
  try {
    const body = (await response.json()) as { detail?: unknown };
    const raw = body.detail;
    detail =
      typeof raw === "string"
        ? raw
        : typeof raw === "object" && raw !== null && "message" in raw
          ? String((raw as { message: unknown }).message)
          : JSON.stringify(raw ?? "");
  } catch {
    detail = response.statusText;
  }
  return new DataApiError(`${what}: ${detail}`, response.status);
}

/**
 * `GET /api/projects/{p}/data[?kind=…]`: the CSV files (no `kind`, the backend default), the
 * reduced-model files (`modal`) or every data file (`all`).
 */
export async function listDataFiles(
  project: string,
  signal?: AbortSignal,
  kind?: DataFileKind | "all",
): Promise<DataFile[]> {
  const query = kind === undefined ? "" : `?kind=${kind}`;
  const response = await fetch(`${base(project)}${query}`, { signal });
  if (!response.ok) throw await failure(response, "cannot list the data files of the project");
  return (await response.json()) as DataFile[];
}

export async function fetchCsvPreview(
  project: string,
  file: string,
  rows = 8,
  signal?: AbortSignal,
): Promise<CsvPreview> {
  const response = await fetch(
    `${base(project)}/${encodeURIComponent(file)}/preview?rows=${rows}`,
    { signal },
  );
  if (!response.ok) throw await failure(response, `cannot read ${file}`);
  return (await response.json()) as CsvPreview;
}

/**
 * `GET /api/projects/{p}/data/{file}`: the text of a CSV or reduced-model file, or null when the
 * project has no such file.
 */
export async function fetchDataText(
  project: string,
  file: string,
  signal?: AbortSignal,
): Promise<string | null> {
  const response = await fetch(`${base(project)}/${encodeURIComponent(file)}`, { signal });
  if (response.status === 404) return null;
  if (!response.ok) throw await failure(response, `cannot read ${file}`);
  return response.text();
}

/**
 * `PUT /api/projects/{p}/data/{file}`: create or replace a data file with `text` (a CSV table,
 * or the JSON of a reduced model for a `.modal.json` name).
 */
export async function writeDataText(project: string, file: string, text: string): Promise<void> {
  const contentType =
    dataFileKind(file) === "modal" ? "application/json; charset=utf-8" : "text/csv; charset=utf-8";
  const response = await fetch(`${base(project)}/${encodeURIComponent(file)}`, {
    method: "PUT",
    headers: { "content-type": contentType },
    body: text,
  });
  if (!response.ok) throw await failure(response, `cannot write ${file}`);
}

/** `POST /api/projects/{p}/data` (multipart, field `file`); returns the stored name. */
export async function uploadDataFile(
  project: string,
  file: File,
): Promise<{ file: string; path: string }> {
  const form = new FormData();
  form.append("file", file, file.name);
  const response = await fetch(base(project), { method: "POST", body: form });
  if (!response.ok) throw await failure(response, `cannot upload ${file.name}`);
  return (await response.json()) as { file: string; path: string };
}
