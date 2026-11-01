/**
 * Leaving the open model: for the library (the start page, the brand in the
 * top bar), for the project's model picker (the project name) or for another
 * model of the project (the model menu). Work that is not on disk yet asks
 * first: the model (auto-save pending or failed), a project-library block in
 * the Code tab and Docs pages.
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

/**
 * Where the editor is going: the library (start page), the model picker of the
 * open project, or another model of the project.
 */
export type LeaveDestination = "library" | "project" | "model";

interface LeaveState {
  /** The unsaved work the open prompt lists; null while no prompt is open. */
  pending: string[] | null;
  /** The URL the prompt leaves for. */
  target: string | null;
  destination: LeaveDestination;
  error: string | null;
  busy: boolean;
  open: (labels: string[], target?: string, destination?: LeaveDestination) => void;
  close: () => void;
  setBusy: (busy: boolean) => void;
  setError: (error: string | null) => void;
}

export const useLeaveProjectStore = create<LeaveState>()((set) => ({
  pending: null,
  target: null,
  destination: "library",
  error: null,
  busy: false,
  open: (labels, target, destination = "library") =>
    set({ pending: labels, target: target ?? null, destination, error: null, busy: false }),
  close: () => set({ pending: null, target: null, destination: "library", error: null, busy: false }),
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
  useLeaveProjectStore.getState().open(work.map((item) => item.label), libraryUrl(), "library");
}

const SAVE_WAIT_MS = 5000;

/** Resolve once an in-flight save of the model has finished (or after a few seconds). */
function settledSave(): Promise<void> {
  if (useDocumentStore.getState().saveState !== "saving") {
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    const timer = window.setTimeout(done, SAVE_WAIT_MS);
    const unsubscribe = useDocumentStore.subscribe((state) => {
      if (state.saveState !== "saving") {
        done();
      }
    });
    function done(): void {
      window.clearTimeout(timer);
      unsubscribe();
      resolve();
    }
  });
}

/**
 * Leave the open model for another model of the project or for the project's
 * model picker. The model autosaves anyway, so a pending change is saved
 * quietly first (as the Open dialog always did); other unsaved work (a Code
 * tab draft, Docs pages) or a failed model save asks first, like leaving for
 * the library.
 */
export async function requestLeaveModel(
  target: string,
  destination: Exclude<LeaveDestination, "library"> = "model",
): Promise<void> {
  await settledSave();
  const state = useDocumentStore.getState();
  if (state.project !== null && state.doc !== null && state.revision !== state.savedRevision) {
    await saveCurrentModel();
  }
  const work = unsavedWork();
  if (work.length === 0) {
    navigation.assign(target);
    return;
  }
  useLeaveProjectStore.getState().open(work.map((item) => item.label), target, destination);
}

function pendingTarget(): string {
  return useLeaveProjectStore.getState().target ?? libraryUrl();
}

/** "Save and leave": save everything unsaved, then leave; stays on a failed save. */
export async function saveAndLeave(): Promise<void> {
  const store = useLeaveProjectStore.getState();
  const target = pendingTarget();
  store.setBusy(true);
  for (const item of unsavedWork()) {
    if (!(await item.save())) {
      useLeaveProjectStore
        .getState()
        .setError(`Could not save ${item.label}. Fix the save error, or leave without saving.`);
      return;
    }
  }
  navigation.assign(target);
}

export function leaveWithoutSaving(): void {
  const target = pendingTarget();
  confirmLeave();
  navigation.assign(target);
}
