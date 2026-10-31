/**
 * The UI state of a paste: the conflict dialog (a promise the paste flow awaits) and
 * the notice that reports what a paste imported and what it left behind.
 */

import { create } from "zustand";

import type { Choices, Conflict } from "./resolve";

export interface PasteNotice {
  /** Increments per notice, so a new notice replaces an older one visibly. */
  id: number;
  tone: "info" | "error";
  title: string;
  lines: string[];
}

export interface PasteDialogRequest {
  conflicts: Conflict[];
  /** The target project, named in the dialog. */
  project: string;
  /** Some choices write library files, which Undo does not remove. */
  writesFiles: boolean;
  settle: (choices: Choices | null) => void;
}

interface PasteUiState {
  dialog: PasteDialogRequest | null;
  notice: PasteNotice | null;
  /** A paste is reading or writing dependencies. */
  busy: boolean;
  ask: (conflicts: Conflict[], project: string, writesFiles: boolean) => Promise<Choices | null>;
  answer: (choices: Choices | null) => void;
  showNotice: (notice: Omit<PasteNotice, "id">) => void;
  dismissNotice: () => void;
  setBusy: (busy: boolean) => void;
}

let noticeCounter = 0;

export const usePasteUiStore = create<PasteUiState>()((set, get) => ({
  dialog: null,
  notice: null,
  busy: false,
  ask: (conflicts, project, writesFiles) =>
    new Promise<Choices | null>((settle) => {
      get().dialog?.settle(null);
      set({ dialog: { conflicts, project, writesFiles, settle } });
    }),
  answer: (choices) => {
    const dialog = get().dialog;
    set({ dialog: null });
    dialog?.settle(choices);
  },
  showNotice: (notice) => {
    noticeCounter += 1;
    set({ notice: { ...notice, id: noticeCounter } });
  },
  dismissNotice: () => set({ notice: null }),
  setBusy: (busy) => set({ busy }),
}));
