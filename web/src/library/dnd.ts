/**
 * The typed HTML5 drag payload used by the library -> canvas drag (plan 7.2).
 *
 * A private MIME type carries JSON; `text/plain` carries the catalog ref as a
 * fallback for a browser that drops custom types. Junction drags carry their
 * `0`/`1` kind.
 *
 * A background shape from the library's Shapes category travels under its own
 * MIME type (`SHAPE_DRAG_MIME`), so a drop can never mistake it for a block:
 * the canvas adds a shape (`diagram.shapes`), not a catalog block.
 */

import type { CatalogBlock } from "../contracts/catalog";
import type { JunctionType, ShapeKind } from "../contracts/model";
import { SHAPE_KINDS } from "../editor/shapes";

export const BLOCK_DRAG_MIME = "application/x-bgsim-block";
export const SHAPE_DRAG_MIME = "application/x-bgsim-shape";

export type LibraryDragPayload =
  | { kind: "block"; ref: string }
  | { kind: "junction"; junction: JunctionType }
  | { kind: "shape"; shape: ShapeKind };

function isJunction(value: unknown): value is JunctionType {
  return value === "0" || value === "1";
}

function isShapeKind(value: unknown): value is ShapeKind {
  return typeof value === "string" && (SHAPE_KINDS as readonly string[]).includes(value);
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
  if (record.kind === "shape" && isShapeKind(record.shape)) {
    return { kind: "shape", shape: record.shape };
  }
  return null;
}

export function payloadForBlock(block: CatalogBlock): LibraryDragPayload {
  return { kind: "block", ref: block.ref };
}

export function payloadForShape(shape: ShapeKind): LibraryDragPayload {
  return { kind: "shape", shape };
}

/**
 * Read the payload from a drag event. The shape MIME type wins, then the block
 * MIME type; plain text is accepted only as a catalog ref (which keeps a
 * text-only drag honest), never as a shape.
 */
export function readDragPayload(dataTransfer: {
  getData: (format: string) => string;
}): LibraryDragPayload | null {
  const shape = parseDragPayload(dataTransfer.getData(SHAPE_DRAG_MIME));
  if (shape !== null && shape.kind === "shape") {
    return shape;
  }
  const typed = parseDragPayload(dataTransfer.getData(BLOCK_DRAG_MIME));
  if (typed !== null && typed.kind !== "shape") {
    return typed;
  }
  const plain = dataTransfer.getData("text/plain").trim();
  if (plain.includes(":") && !plain.startsWith("shape:")) {
    return { kind: "block", ref: plain };
  }
  return null;
}

/** Fill a real DataTransfer for a drag start. */
export function writeDragPayload(dataTransfer: DataTransfer, payload: LibraryDragPayload): void {
  if (payload.kind === "shape") {
    dataTransfer.setData(SHAPE_DRAG_MIME, JSON.stringify(payload));
    dataTransfer.setData("text/plain", `shape:${payload.shape}`);
  } else {
    dataTransfer.setData(BLOCK_DRAG_MIME, JSON.stringify(payload));
    dataTransfer.setData(
      "text/plain",
      payload.kind === "block" ? payload.ref : `junction:${payload.junction}`,
    );
  }
  dataTransfer.effectAllowed = "copy";
}
