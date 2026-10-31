/**
 * Leaving the open project for the library (the start page): the brand in the
 * top bar. Work that is not on disk yet asks first: the model (auto-save
 * pending or failed), a project-library block in the Code tab and Docs pages.
 * The Code tab registers itself while it has an unsaved draft; the Docs tab
 * goes through its own lazily registered leave guard.
 */

import { create } from "zustand";

import { confirmLeave, hasUnsavedDocs, saveUnsavedDocs } from "../docs/leaveGuard";
import { useDocumentStore } from "../state/documentStore";
import { saveCurrentModel } from "../state/persistence";
import { navigation } from "./openSession";

export interface UnsavedWork {
  /** What is unsaved, for the prompt: "the model “arm”". */
  label: string;
  save: () => Promise<boolean>;
}

const extraSources = new Map<string, () => UnsavedWork | null>();

/** Register a source of unsaved work; returns the unregister function. */
export function registerUnsavedWork(key: string, probe: () => UnsavedWork | null): () => void {
  extraSources.set(key, probe);
  return () => {
    if (extraSources.get(key) === probe) {
      extraSources.delete(key);
    }
  };
}

export function unsavedWork(): UnsavedWork[] {
  const work: UnsavedWork[] = [];
  const state = useDocumentStore.getState();
  if (
    state.project !== null &&
    state.doc !== null &&
    (state.revision !== state.savedRevision || state.saveState === "error")
  ) {
    work.push({ label: `the model “${state.modelName ?? "model"}”`, save: saveCurrentModel });
  }
  for (const probe of extraSources.values()) {
    const item = probe();
    if (item !== null) {
      work.push(item);
    }
  }
  if (hasUnsavedDocs()) {
    work.push({ label: "Docs pages", save: saveUnsavedDocs });
  }
  return work;
}

/** The start page URL: the current one without `project` and `model`. */
export function libraryUrl(href: string = window.location.href): string {
  const url = new URL(href);
  url.searchParams.delete("project");
  url.searchParams.delete("model");
  return url.toString();
}

interface LeaveState {
  /** The unsaved work the open prompt lists; null while no prompt is open. */
  pending: string[] | null;
  error: string | null;
  busy: boolean;
  open: (labels: string[]) => void;
  close: () => void;
  setBusy: (busy: boolean) => void;
  setError: (error: string | null) => void;
}

export const useLeaveProjectStore = create<LeaveState>()((set) => ({
  pending: null,
  error: null,
  busy: false,
  open: (labels) => set({ pending: labels, error: null, busy: false }),
  close: () => set({ pending: null, error: null, busy: false }),
  setBusy: (busy) => set({ busy }),
  setError: (error) => set({ error, busy: false }),
}));

/** Go to the library now, or open the prompt when something is unsaved. */
export function requestLeaveProject(): void {
  const work = unsavedWork();
  if (work.length === 0) {
    navigation.assign(libraryUrl());
    return;
  }
  useLeaveProjectStore.getState().open(work.map((item) => item.label));
}

/** "Save and leave": save everything unsaved, then leave; stays on a failed save. */
export async function saveAndLeave(): Promise<void> {
  const store = useLeaveProjectStore.getState();
  store.setBusy(true);
  for (const item of unsavedWork()) {
    if (!(await item.save())) {
      useLeaveProjectStore
        .getState()
        .setError(`Could not save ${item.label}. Fix the save error, or leave without saving.`);
      return;
    }
  }
  navigation.assign(libraryUrl());
}

export function leaveWithoutSaving(): void {
  confirmLeave();
  navigation.assign(libraryUrl());
}
