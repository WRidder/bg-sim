/**
 * The Shapes category of the library: the five background shape kinds of the
 * canvas (src/editor/shapes.ts). They are not catalog blocks, so the block
 * help, completion and model tree never see them; only the library browser
 * lists them, after the junctions, and drags them with their own MIME type
 * (src/library/dnd.ts).
 */

import type { ShapeKind } from "../contracts/model";
import { SHAPE_KIND_LABELS, SHAPE_KINDS } from "../editor/shapes";

/** The one-line description of every shape entry (list view summary, tooltips). */
export const SHAPE_DESCRIPTION = "Background drawing, ignored by simulation";

export interface ShapeEntry {
  key: string;
  kind: ShapeKind;
  name: string;
}

function haystack(kind: ShapeKind): string {
  return `${SHAPE_KIND_LABELS[kind]}\n${kind}\nshape shapes\nbackground drawing`.toLowerCase();
}

/** The shape entries matching a search (all five for an empty query), in the menu order. */
export function searchShapes(query: string): ShapeEntry[] {
  const needle = query.trim().toLowerCase();
  return SHAPE_KINDS.filter((kind) => needle.length === 0 || haystack(kind).includes(needle)).map(
    (kind) => ({ key: `shape:${kind}`, kind, name: SHAPE_KIND_LABELS[kind] }),
  );
}
