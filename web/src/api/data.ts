/** Project data files (CSV inputs of `stdlib:sources/CsvSource`; backend `data.py`, F5.1). */

import { API_BASE } from "./client";

/** One file of the project data folder. */
export interface DataFile {
  file: string;
  bytes: number;
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

export async function listDataFiles(project: string, signal?: AbortSignal): Promise<DataFile[]> {
  const response = await fetch(base(project), { signal });
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
