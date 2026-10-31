/**
 * Canvas menu items for sticky notes: "Add note" on the empty canvas, and
 * edit / colour / delete on a note. The canvas owns the menu; these are its
 * rows.
 */

import type { AnnotationColor } from "../contracts/model";
import { useDocumentStore } from "../state/documentStore";
import { GRID_SIZE } from "./geometry";
import { useNoteEditStore } from "./noteEditing";
import {
  NOTE_COLOR_LABELS,
  NOTE_COLORS,
  noteColor,
  noteIdOf,
  selectedNoteIds,
} from "./notes";
import { activeDiagram } from "./subsystemPath";
import "./nodes/note.css";

/**
 * Add a note with its top-left corner at `point` (flow coordinates; on the
 * grid when snapping) and open its editor. Returns the canvas id or null.
 */
export function addNoteAt(point: { x: number; y: number }, snap: boolean): string | null {
  const position = snap
    ? {
        x: Math.round(point.x / GRID_SIZE) * GRID_SIZE,
        y: Math.round(point.y / GRID_SIZE) * GRID_SIZE,
      }
    : point;
  const flowId = useDocumentStore.getState().addNote(position);
  const id = flowId === null ? null : noteIdOf(flowId);
  if (id !== null) {
    useNoteEditStore.getState().start(id);
  }
  return flowId;
}

export function PaneMenuItems({ onAddNote }: { onAddNote: () => void }) {
  return (
    <button type="button" role="menuitem" data-testid="add-note" onClick={onAddNote}>
      Add note (N)
    </button>
  );
}

/** The menu of a note: edit, the five colours (for every selected note), delete. */
export function NoteMenuItems({
  flowId,
  onDone,
  onDelete,
}: {
  flowId: string;
  onDone: () => void;
  onDelete: () => void;
}) {
  const id = noteIdOf(flowId);
  const current = useDocumentStore((state) => {
    const diagram = state.doc === null ? null : activeDiagram(state.doc, state.activePath);
    const note = diagram?.annotations?.find((entry) => entry.id === id);
    return note === undefined ? null : noteColor(note);
  });
  if (id === null) {
    return null;
  }
  const recolour = (color: AnnotationColor): void => {
    const selected = selectedNoteIds(useDocumentStore.getState().selection.nodes);
    useDocumentStore.getState().setNoteColor(selected.includes(id) ? selected : [id], color);
    onDone();
  };
  return (
    <>
      <button
        type="button"
        role="menuitem"
        data-testid="note-edit"
        onClick={() => {
          useNoteEditStore.getState().start(id);
          onDone();
        }}
      >
        Edit text (double-click)
      </button>
      <div className="editor-menu__swatches" role="group" aria-label="Note colour">
        {NOTE_COLORS.map((color) => (
          <button
            key={color}
            type="button"
            role="menuitemradio"
            aria-checked={current === color}
            className={`note-swatch note-swatch--${color}${current === color ? " is-current" : ""}`}
            data-testid={`note-color-${color}`}
            title={NOTE_COLOR_LABELS[color]}
            aria-label={`${NOTE_COLOR_LABELS[color]} note`}
            onClick={() => recolour(color)}
          />
        ))}
      </div>
      <button type="button" role="menuitem" data-testid="note-delete" onClick={onDelete}>
        Delete (Del)
      </button>
    </>
  );
}
