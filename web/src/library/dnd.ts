/**
 * The typed HTML5 drag payload used by the library -> canvas drag (plan 7.2).
 *
 * A private MIME type carries JSON; `text/plain` carries the catalog ref as a
 * fallback for a browser that drops custom types. Junction drags carry their
 * `0`/`1` kind.
 */

import type { CatalogBlock } from "../contracts/catalog";
import type { JunctionType } from "../contracts/model";

export const BLOCK_DRAG_MIME = "application/x-bgsim-block";

export type LibraryDragPayload =
  | { kind: "block"; ref: string }
  | { kind: "junction"; junction: JunctionType };

function isJunction(value: unknown): value is JunctionType {
  return value === "0" || value === "1";
}

/** Parse a payload string; null for anything malformed. */
export function parseDragPayload(raw: string | null | undefined): LibraryDragPayload | null {
  if (raw === null || raw === undefined || raw.trim().length === 0) {
    return null;
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw) as unknown;
  } catch {
    return null;
  }
  if (typeof parsed !== "object" || parsed === null) {
    return null;
  }
  const record = parsed as Record<string, unknown>;
  if (record.kind === "block" && typeof record.ref === "string" && record.ref.trim().length > 0) {
    return { kind: "block", ref: record.ref };
  }
  if (record.kind === "junction" && isJunction(record.junction)) {
    return { kind: "junction", junction: record.junction };
  }
  return null;
}

export function payloadForBlock(block: CatalogBlock): LibraryDragPayload {
  return { kind: "block", ref: block.ref };
}

/**
 * Read the payload from a drag event. The private MIME type wins; plain text is
 * accepted only as a catalog ref (which keeps a text-only drag honest).
 */
export function readDragPayload(dataTransfer: {
  getData: (format: string) => string;
}): LibraryDragPayload | null {
  const typed = parseDragPayload(dataTransfer.getData(BLOCK_DRAG_MIME));
  if (typed !== null) {
    return typed;
  }
  const plain = dataTransfer.getData("text/plain").trim();
  if (plain.includes(":")) {
    return { kind: "block", ref: plain };
  }
  return null;
}

/** Fill a real DataTransfer for a drag start. */
export function writeDragPayload(dataTransfer: DataTransfer, payload: LibraryDragPayload): void {
  dataTransfer.setData(BLOCK_DRAG_MIME, JSON.stringify(payload));
  dataTransfer.setData(
    "text/plain",
    payload.kind === "block" ? payload.ref : `junction:${payload.junction}`,
  );
  dataTransfer.effectAllowed = "copy";
}
