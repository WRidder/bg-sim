/**
 * Sticky notes on the diagram canvas: the model's `diagram.annotations`
 * (kind `text`), one list per diagram level. A note is editor state only;
 * compile, simulation and export ignore it.
 *
 * On the canvas a note is a virtual xyflow node `note:<annotation id>`, like
 * the `terminal:<port>` nodes of a subsystem boundary, so it selects, drags,
 * box-selects, copies and deletes with the blocks. The prefix keeps a note id
 * from clashing with a node id in the selection.
 */

import type { AnnotationColor, ModelAnnotation } from "../contracts/model";

export const NOTE_PREFIX = "note:";

/** The colours of the contract, in the order the menus offer them; absent is yellow. */
export const NOTE_COLORS: readonly AnnotationColor[] = ["yellow", "blue", "green", "pink", "grey"];
export const DEFAULT_NOTE_COLOR: AnnotationColor = "yellow";

export const NOTE_COLOR_LABELS: Record<AnnotationColor, string> = {
  yellow: "Yellow",
  blue: "Blue",
  green: "Green",
  pink: "Pink",
  grey: "Grey",
};

/** A new note's size (flow units); square, like a paper sticky note. */
export const NOTE_DEFAULT_SIZE = { w: 200, h: 200 } as const;
/** The smallest note the resize handles allow. */
export const NOTE_MIN_SIZE = { w: 80, h: 60 } as const;

/**
 * Notes sit behind blocks and wires: a negative z-index puts them below the
 * edges (z 0) and the nodes (z 0). It stays negative when selected, which
 * xyflow elevates by 1000.
 */
export const NOTE_Z_INDEX = -2000;

export function noteFlowId(annotationId: string): string {
  return `${NOTE_PREFIX}${annotationId}`;
}

/** The annotation id of a `note:<id>` canvas id, else null. */
export function noteIdOf(flowId: string): string | null {
  return flowId.startsWith(NOTE_PREFIX) ? flowId.slice(NOTE_PREFIX.length) : null;
}

export function isNoteId(flowId: string | null | undefined): boolean {
  return typeof flowId === "string" && flowId.startsWith(NOTE_PREFIX);
}

export function noteColor(annotation: Pick<ModelAnnotation, "color">): AnnotationColor {
  return annotation.color ?? DEFAULT_NOTE_COLOR;
}

/** The annotation ids among canvas selection ids. */
export function selectedNoteIds(ids: readonly string[]): string[] {
  const result: string[] = [];
  for (const id of ids) {
    const note = noteIdOf(id);
    if (note !== null) {
      result.push(note);
    }
  }
  return result;
}
