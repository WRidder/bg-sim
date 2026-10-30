/**
 * Opening the Export dialog from anywhere: the top bar (the whole model) or a subsystem's
 * context menu ("Export subsystem…", which preselects that subsystem as the scope).
 */

import { create } from "zustand";

interface ExportDialogState {
  open: boolean;
  /** The scope the dialog opens with: a subsystem instance path, or null for the model. */
  scope: string | null;
  /** Bumped on every open, so the dialog resets its form for the new request. */
  openCount: number;
  openExport: (scope?: string | null) => void;
  closeExport: () => void;
}

export const useExportDialogStore = create<ExportDialogState>((set) => ({
  open: false,
  scope: null,
  openCount: 0,
  openExport: (scope = null) =>
    set((state) => ({ open: true, scope, openCount: state.openCount + 1 })),
  closeExport: () => set({ open: false }),
}));
