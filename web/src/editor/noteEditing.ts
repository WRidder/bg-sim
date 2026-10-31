/**
 * Which sticky note shows its text editor. At most one note edits at a time;
 * the canvas starts an edit (double-click, "Edit text", a new note) and the
 * note ends it (click outside, Esc). Not document state: no undo, no save.
 */

import { create } from "zustand";

import { useDocumentStore } from "../state/documentStore";

export interface NoteEditState {
  /** The annotation id of the note being edited, or null. */
  editing: string | null;
  start: (id: string) => void;
  stop: (id?: string) => void;
}

export const useNoteEditStore = create<NoteEditState>()((set, get) => ({
  editing: null,
  start: (id) => {
    if (get().editing !== id) {
      set({ editing: id });
    }
  },
  // `stop(id)` ends only that note's edit, so a late blur cannot end the next one.
  stop: (id) => {
    const current = get().editing;
    if (current !== null && (id === undefined || id === current)) {
      set({ editing: null });
    }
  },
}));

/**
 * The undo gesture of one editing session: every keystroke coalesces into one
 * history entry, opened when the editor mounts and closed when it leaves.
 */
export function noteTextGesture(id: string): string {
  return `note-text:${id}`;
}

export function beginNoteTextGesture(id: string): void {
  useDocumentStore.getState().beginGesture(noteTextGesture(id));
}

export function endNoteTextGesture(id: string): void {
  if (useDocumentStore.getState().gestureKey === noteTextGesture(id)) {
    useDocumentStore.getState().endGesture();
  }
}
