/**
 * Auto-save (plan 7.4): a debounced PUT after every edit, plus a manual save.
 *
 * The store's `revision` counter is the sync point: the request sends the
 * document as it was when the save started, and only that revision is marked
 * as on disk. Edits made while the PUT is in flight leave the model dirty and
 * schedule the next save.
 */

import { useEffect } from "react";

import { fetchCatalog } from "../library/catalogClient";
import { useCatalogStore } from "../library/catalogStore";
import { saveDefinitions } from "./definitionFiles";
import { useDocumentStore } from "./documentStore";
import { putModel } from "./modelApi";

export const AUTOSAVE_DELAY_MS = 500;

/** Save the current document now; true when the backend accepted it. */
export async function saveCurrentModel(): Promise<boolean> {
  const state = useDocumentStore.getState();
  const { project, modelName, doc, revision } = state;
  if (project === null || modelName === null || doc === null) {
    return false;
  }
  if (state.saveState === "saving") {
    return false;
  }
  state.setSaving();
  try {
    // Library subsystems first: the model refers to them (state/definitionFiles.ts).
    const { model, libraryChanged, finish } = await saveDefinitions(project, doc);
    await putModel(project, modelName, model);
    useDocumentStore.getState().setSaved(revision);
    // Only now, with the model stored, the files of removed library subsystems go.
    const deleted = await finish();
    if (libraryChanged || deleted) {
      // The catalog lists the library subsystems; a failure here only delays the listing.
      void fetchCatalog(project)
        .then((catalog) => {
          if (useDocumentStore.getState().project === project) {
            useCatalogStore.getState().setCatalog(catalog);
          }
        })
        .catch(() => undefined);
    }
    return true;
  } catch (error) {
    const message =
      error instanceof Error ? error.message : `Could not save the model: ${String(error)}`;
    useDocumentStore.getState().setSaveError(message);
    return false;
  }
}

/** Debounce a save whenever the document revision moves ahead of the disk. */
export function useModelAutosave(delay: number = AUTOSAVE_DELAY_MS): void {
  const project = useDocumentStore((state) => state.project);
  const modelName = useDocumentStore((state) => state.modelName);
  const doc = useDocumentStore((state) => state.doc);
  const revision = useDocumentStore((state) => state.revision);
  const savedRevision = useDocumentStore((state) => state.savedRevision);

  useEffect(() => {
    if (project === null || modelName === null || doc === null) {
      return;
    }
    if (revision === savedRevision) {
      return;
    }
    const timer = setTimeout(() => {
      void saveCurrentModel();
    }, delay);
    return () => clearTimeout(timer);
  }, [project, modelName, doc, revision, savedRevision, delay]);
}
