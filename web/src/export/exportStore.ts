/**
 * Opening the Export dialog from anywhere: the top bar (the whole model), a subsystem's
 * context menu ("Export subsystem…", which preselects that subsystem as the scope), or the
 * background tasks indicator ("Show details", which attaches the dialog to an existing job,
 * running or finished, so its progress and report come back after the dialog was closed).
 *
 * The job itself lives in the task registry (`tasks/exportTasks.ts`); the dialog only keeps
 * the id of the job it shows. Closing the dialog never cancels the job.
 */

import { create } from "zustand";

interface ExportDialogState {
  open: boolean;
  /** The scope the dialog opens with: a subsystem instance path, or null for the model. */
  scope: string | null;
  /** Bumped on every open, so the dialog resets its form for the new request. */
  openCount: number;
  /** The export job the dialog shows (started here or attached), or null. */
  jobId: string | null;
  /** The last open came from `showExport`: show that job instead of a fresh form. */
  attached: boolean;
  openExport: (scope?: string | null) => void;
  /** Open the dialog on an existing job (from the background tasks indicator). */
  showExport: (jobId: string) => void;
  /** The job the dialog shows from now on (after Export), or null for none. */
  setJobId: (jobId: string | null) => void;
  closeExport: () => void;
}

export const useExportDialogStore = create<ExportDialogState>((set) => ({
  open: false,
  scope: null,
  openCount: 0,
  jobId: null,
  attached: false,
  openExport: (scope = null) =>
    set((state) => ({ open: true, scope, attached: false, openCount: state.openCount + 1 })),
  showExport: (jobId) =>
    set((state) => ({ open: true, scope: null, jobId, attached: true, openCount: state.openCount + 1 })),
  setJobId: (jobId) => set({ jobId }),
  closeExport: () => set({ open: false }),
}));
