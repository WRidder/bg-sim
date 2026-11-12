/**
 * Library subsystems between the open document and the project library.
 *
 * A model is opened with its instances as working copies and the definitions in
 * `doc.definitions` (library/linkedSubsystems.ts). Saving writes the model with
 * its instances as references, and every definition that differs from its
 * library file to `library/<Name>.bgsub.json`. What is on disk is remembered
 * here, per project, so an unchanged definition is not written again.
 *
 * A library file is only ever deleted for a definition the user removed from
 * the library (`markDefinitionRemoved`), never because the open document does
 * not hold it: the library belongs to every model of the project. The delete
 * happens after the model is stored, so a save that fails halfway never leaves
 * a model on disk that refers to a file that is gone.
 */

import type { Model, SubsystemDefinition } from "../contracts/model";
import { dehydrateModel, hydrateModel, type Definitions } from "../library/linkedSubsystems";
import { deleteSubsystem, putSubsystem } from "./modelApi";

/** The library files as last read or written: project -> name -> JSON text. */
const onDisk = new Map<string, Map<string, string>>();
/** The definitions the user removed from the library and that are still on disk. */
const removed = new Map<string, Set<string>>();

/** The user removed `name` from the library: the next save deletes its file. */
export function markDefinitionRemoved(project: string, name: string): void {
  const names = removed.get(project) ?? new Set<string>();
  names.add(name);
  removed.set(project, names);
}

/**
 * The model as the editor holds it, with the project's library subsystems in
 * place; what the library holds now is remembered for the next save.
 */
export function openWithDefinitions(project: string, model: Model, files: Definitions): Model {
  const hydrated = hydrateModel(model, files);
  const known = new Map<string, string>();
  for (const [name, file] of Object.entries(dehydrateModel(hydrated).files)) {
    known.set(name, JSON.stringify(file));
  }
  onDisk.set(project, known);
  removed.delete(project);
  return hydrated;
}

/**
 * Write the document's new and changed definitions to the project library.
 * Returns the model to store, whether a library file changed (the catalog lists
 * the library subsystems, so it has to be read again then), and `finish`, to be
 * called once the model is stored: it deletes the files of the definitions the
 * user removed, and says whether it deleted any.
 */
export async function saveDefinitions(
  project: string,
  doc: Model,
): Promise<{ model: Model; libraryChanged: boolean; finish: () => Promise<boolean> }> {
  const { model, files } = dehydrateModel(doc);
  const known = onDisk.get(project) ?? new Map<string, string>();
  onDisk.set(project, known);
  const gone = removed.get(project);
  let libraryChanged = false;
  for (const [name, file] of Object.entries(files) as [string, SubsystemDefinition][]) {
    // Back in the document (an undo of the removal): it stays in the library.
    gone?.delete(name);
    const text = JSON.stringify(file);
    if (known.get(name) === text) {
      continue;
    }
    await putSubsystem(project, name, file);
    known.set(name, text);
    libraryChanged = true;
  }
  const finish = async (): Promise<boolean> => {
    let deleted = false;
    for (const name of [...(removed.get(project) ?? [])]) {
      if (files[name] !== undefined) {
        continue;
      }
      await deleteSubsystem(project, name);
      known.delete(name);
      removed.get(project)?.delete(name);
      deleted = true;
    }
    return deleted;
  };
  return { model, libraryChanged, finish };
}

/** Test hook: forget what is on disk. */
export function resetDefinitionFiles(): void {
  onDisk.clear();
  removed.clear();
}
