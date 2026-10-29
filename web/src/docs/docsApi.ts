/** The docs endpoints of the backend (`backend/src/bgsim_server/docs.py`). */

import { API_BASE } from "../api/client";
import type { Docs } from "../contracts/docs";

export class DocsApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "DocsApiError";
  }
}

function root(project: string, model: string): string {
  const enc = encodeURIComponent;
  return `${API_BASE}/api/projects/${enc(project)}/docs/${enc(model)}`;
}

async function failure(response: Response, what: string): Promise<DocsApiError> {
  let message = `The backend answered ${response.status} while ${what}.`;
  try {
    const body = (await response.json()) as { detail?: unknown };
    const detail = body.detail;
    if (typeof detail === "string") {
      message = detail;
    } else if (typeof detail === "object" && detail !== null) {
      const text = (detail as { message?: unknown }).message;
      if (typeof text === "string") {
        message = text;
      }
    }
  } catch {
    // The body was not JSON; keep the generic message.
  }
  return new DocsApiError(message, response.status);
}

async function send(url: string, init: RequestInit, what: string): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(url, init);
  } catch {
    throw new DocsApiError(`Cannot reach the bg-sim backend while ${what}. Is it running?`, 0);
  }
  if (!response.ok) {
    throw await failure(response, what);
  }
  return response;
}

export async function fetchManifest(project: string, model: string): Promise<Docs> {
  const response = await send(root(project, model), {}, "loading the docs");
  return (await response.json()) as Docs;
}

export async function saveManifest(project: string, model: string, docs: Docs): Promise<Docs> {
  const response = await send(
    root(project, model),
    { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify(docs) },
    "saving the page tree",
  );
  return (await response.json()) as Docs;
}

export async function fetchPage(project: string, model: string, id: string): Promise<string> {
  const response = await send(`${root(project, model)}/pages/${encodeURIComponent(id)}`, {}, "loading the page");
  return response.text();
}

export async function savePage(project: string, model: string, id: string, text: string): Promise<void> {
  await send(
    `${root(project, model)}/pages/${encodeURIComponent(id)}`,
    { method: "PUT", headers: { "content-type": "text/markdown; charset=utf-8" }, body: text },
    "saving the page",
  );
}

export async function deletePage(
  project: string,
  model: string,
  id: string,
  children: "delete" | "promote" | null,
): Promise<Docs["pages"]> {
  const query = children === null ? "" : `?children=${children}`;
  const response = await send(
    `${root(project, model)}/pages/${encodeURIComponent(id)}${query}`,
    { method: "DELETE" },
    "deleting the page",
  );
  return ((await response.json()) as { pages: Docs["pages"] }).pages;
}

export interface AssetListing {
  assets: { file: string; bytes: number; used: boolean }[];
  unused: number;
}

export async function listAssets(project: string, model: string): Promise<AssetListing> {
  const response = await send(`${root(project, model)}/assets`, {}, "listing the images");
  return (await response.json()) as AssetListing;
}

export async function uploadAsset(project: string, model: string, file: File): Promise<{ file: string }> {
  const form = new FormData();
  form.append("file", file, file.name || "image");
  const response = await send(`${root(project, model)}/assets`, { method: "POST", body: form }, "adding the image");
  return (await response.json()) as { file: string };
}

export interface CopyResult {
  copied: string[];
  existing: string[];
  missing: string[];
}

export async function copyAssets(
  project: string,
  model: string,
  from: { project: string; model: string },
  files: readonly string[],
): Promise<CopyResult> {
  const response = await send(
    `${root(project, model)}/assets/copy`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ fromProject: from.project, fromModel: from.model, files }),
    },
    "copying the images",
  );
  return (await response.json()) as CopyResult;
}

export async function deleteUnusedAssets(project: string, model: string): Promise<string[]> {
  const response = await send(`${root(project, model)}/assets/unused`, { method: "DELETE" }, "cleaning up the images");
  return ((await response.json()) as { deleted: string[] }).deleted;
}
