/**
 * `GET /api/catalog` (plan 3.7), validated at the boundary.
 */

import { requestJson } from "../api/client";
import type { Catalog } from "../contracts/catalog";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** A catalog the editor can use: a language stamp, blocks, junctions, domains. */
export function isCatalog(value: unknown): value is Catalog {
  if (!isRecord(value)) {
    return false;
  }
  return (
    typeof value.language === "string" &&
    Array.isArray(value.blocks) &&
    Array.isArray(value.junctions) &&
    Array.isArray(value.domains)
  );
}

export async function fetchCatalog(
  project: string | null,
  signal?: AbortSignal,
): Promise<Catalog> {
  const query = project === null ? "" : `?project=${encodeURIComponent(project)}`;
  const payload = await requestJson<unknown>(`/api/catalog${query}`, { signal });
  if (!isCatalog(payload)) {
    throw new Error("The backend returned a catalog that does not match the contract.");
  }
  return payload;
}
