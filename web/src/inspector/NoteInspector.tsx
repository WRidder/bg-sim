/**
 * Inspector for selected sticky notes: the colour, and for one note its
 * Markdown text. Notes are editor state; the model ignores them.
 */

import { useEffect, useState } from "react";

import type { AnnotationColor, ModelAnnotation } from "../contracts/model";
import { beginNoteTextGesture, endNoteTextGesture, useNoteEditStore } from "../editor/noteEditing";
import { NOTE_COLOR_LABELS, NOTE_COLORS, noteColor } from "../editor/notes";
import { useDocumentStore } from "../state/documentStore";
import "../editor/nodes/note.css";

function NoteTextField({ note }: { note: ModelAnnotation }) {
  const [draft, setDraft] = useState(note.text);
  const [focused, setFocused] = useState(false);
  // Follow the document (undo, the canvas editor) while not typing here.
  useEffect(() => {
    if (!focused) {
      setDraft(note.text);
    }
  }, [note.text, focused]);
  useEffect(() => () => endNoteTextGesture(note.id), [note.id]);
  return (
    <textarea
      className="note-inspector__text"
      data-testid="note-inspector-text"
      aria-label="Note text (Markdown)"
      rows={8}
      value={draft}
      onFocus={() => {
        setFocused(true);
        beginNoteTextGesture(note.id);
      }}
      onBlur={() => {
        setFocused(false);
        endNoteTextGesture(note.id);
      }}
      onChange={(event) => {
        setDraft(event.target.value);
        useDocumentStore.getState().setNoteText(note.id, event.target.value, { coalesce: true });
      }}
    />
  );
}

export function NoteInspector({ notes }: { notes: readonly ModelAnnotation[] }) {
  const first = notes[0];
  if (first === undefined) {
    return null;
  }
  const colours = new Set(notes.map((note) => noteColor(note)));
  const current: AnnotationColor | null = colours.size === 1 ? noteColor(first) : null;
  const ids = notes.map((note) => note.id);
  const single = notes.length === 1;
  return (
    <div className="inspector-body note-inspector" data-testid="note-inspector">
      <header className="inspector-header">
        <div className="inspector-header__text">
          <p className="inspector-header__kicker">{single ? "Sticky note" : "Sticky notes"}</p>
          <h3 className="inspector-header__title">{single ? "Note" : `${notes.length} notes`}</h3>
          <p className="inspector-header__description">
            Markdown notes on the diagram. Simulation, checks and export ignore them.
          </p>
        </div>
      </header>

      <section className="note-inspector__section">
        <h4 id="note-colour-label">Colour</h4>
        <div className="note-swatches" role="radiogroup" aria-labelledby="note-colour-label">
          {NOTE_COLORS.map((color) => (
            <button
              key={color}
              type="button"
              role="radio"
              aria-checked={current === color}
              className={`note-swatch note-swatch--${color}${current === color ? " is-current" : ""}`}
              data-testid={`note-inspector-color-${color}`}
              title={NOTE_COLOR_LABELS[color]}
              aria-label={NOTE_COLOR_LABELS[color]}
              onClick={() => useDocumentStore.getState().setNoteColor(ids, color)}
            />
          ))}
        </div>
      </section>

      {single ? (
        <section className="note-inspector__section">
          <h4>Text</h4>
          <NoteTextField key={first.id} note={first} />
          <p className="note-inspector__hint">
            Markdown: **bold**, *italic*, lists, `code`, $math$ and links to{" "}
            <code>page:</code>, <code>block:</code> or <code>signal:</code>. Images and tables
            are not shown in notes. Double-click the note to edit it on the canvas.
          </p>
          <div className="note-inspector__actions">
            <button
              type="button"
              className="button button--compact"
              data-testid="note-inspector-edit"
              onClick={() => useNoteEditStore.getState().start(first.id)}
            >
              Edit on canvas
            </button>
            <button
              type="button"
              className="button button--compact"
              data-testid="note-inspector-delete"
              onClick={() => useDocumentStore.getState().deleteSelection()}
            >
              Delete note
            </button>
          </div>
        </section>
      ) : null}
    </div>
  );
}
