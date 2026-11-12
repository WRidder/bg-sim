/**
 * The save of "Save to project library" for a subsystem
 * (library/subsystemToBlock.ts plans it; this file carries it out).
 *
 *   1. every planned source is checked (`POST /api/check/block`);
 *   2. the files are written to `library/` and the catalog is re-read;
 *   3. the model with the subsystem replaced by an instance is checked next
 *      to the model as it is (`POST /api/check/model`): the replacement may
 *      not add an error;
 *   4. the node is replaced in one undo step.
 *
 * A failure in 1 writes nothing. A failure in 3 removes the files again, so a
 * block that does not stand in for its subsystem never stays in the library.
 * As with an inline block, a catalog that does not list the new block (the
 * fake worker) leaves the files and the subsystem as they are.
 */

import { enclosingInstance } from "./linkedSubsystems";
import { API_BASE } from "../api/client";
import { checkBlockSource } from "../code/blockCheck";
import type { Catalog } from "../contracts/catalog";
import type { Diagnostic } from "../contracts/diagnostic";
import type { Model } from "../contracts/model";
import { checkModel } from "../diagnostics/modelCheckClient";
import { useDocumentStore } from "../state/documentStore";
import { fetchCatalog } from "./catalogClient";
import { useCatalogStore } from "./catalogStore";
import { revealLibraryBlock } from "./libraryReveal";
import { writeProjectLibrary } from "./projectBlocks";
import { applySubsystemReplacement, type PlannedBlock, type SubsystemBlockPlan } from "./subsystemToBlock";

export interface SaveSubsystemOutcome {
  name: string;
  /** Display path of the block's file, e.g. `library/Actuator.jl`. */
  file: string;
  /** Every file written, dependencies first. */
  blocks: PlannedBlock[];
  /** `project:<name>` when the node was replaced, else null. */
  ref: string | null;
  /** Why the node was not replaced although the files were written, or null. */
  pending: string | null;
}

function errorText(entry: Diagnostic): string {
  const where = entry.path === undefined || entry.path === null || entry.path.length === 0 ? "" : ` (${entry.path})`;
  return `${entry.code}: ${entry.message}${where}`;
}

function errorsOf(diagnostics: readonly Diagnostic[]): Diagnostic[] {
  return diagnostics.filter((entry) => entry.severity === "error");
}

function listed(errors: readonly string[]): string {
  const shown = errors.slice(0, 3).join(" · ");
  return errors.length > 3 ? `${shown} · and ${errors.length - 3} more` : shown;
}

/** Remove written library files again; a failure here is not worth reporting over the cause. */
async function removeBlocks(project: string, names: readonly string[]): Promise<void> {
  for (const name of names) {
    try {
      await fetch(
        `${API_BASE}/api/projects/${encodeURIComponent(project)}/library/${encodeURIComponent(name)}`,
        { method: "DELETE" },
      );
    } catch {
      // The file stays; the user sees it in the Project category.
    }
  }
}

async function refreshCatalog(project: string): Promise<Catalog | null> {
  try {
    const catalog = await fetchCatalog(project);
    useCatalogStore.getState().setCatalog(catalog);
    return catalog;
  } catch {
    return null;
  }
}

/** The errors `candidate` has that `baseline` does not. */
export function addedErrors(baseline: readonly Diagnostic[], candidate: readonly Diagnostic[]): string[] {
  const known = new Set(errorsOf(baseline).map(errorText));
  return [...new Set(errorsOf(candidate).map(errorText))].filter((entry) => !known.has(entry));
}

export async function saveSubsystemToProjectLibrary(
  project: string,
  options: {
    nodeId: string;
    /** Instance path of the subsystem node. */
    path: string;
    name: string;
    plan: SubsystemBlockPlan;
    libraryDir?: string;
  },
): Promise<SaveSubsystemOutcome> {
  const { plan, name, nodeId, path } = options;
  if (plan.problems.length > 0) {
    throw new Error(plan.problems[0]);
  }
  const opened = useDocumentStore.getState();
  const doc = opened.doc;
  if (doc === null) {
    throw new Error("No model is open.");
  }
  // The diagram the node is in, and the document this plan was made for: the node is
  // looked up there only, and nothing is replaced if the document changes meanwhile.
  const within = [...opened.activePath];
  const revision = opened.revision;
  const enclosing = enclosingInstance(doc, within);
  if (enclosing !== null) {
    throw new Error(
      `${options.path} is inside the library subsystem ${enclosing.name}, so exporting it would change every instance of ${enclosing.name}. Detach ${enclosing.node.name} first, or export from an ordinary subsystem.`,
    );
  }

  for (const block of plan.blocks) {
    const result = await checkBlockSource(block.source, `project:${block.name}`);
    const errors = errorsOf(result.diagnostics).map(errorText);
    if (errors.length > 0) {
      throw new Error(`The block ${block.name} would not compile, so nothing was saved: ${listed(errors)}`);
    }
  }

  const written: string[] = [];
  try {
    for (const block of plan.blocks) {
      await writeProjectLibrary(project, block.name, block.source, `The block ${block.name} could not be saved`);
      written.push(block.name);
    }
  } catch (cause) {
    await removeBlocks(project, written);
    throw cause;
  }

  const outcome: SaveSubsystemOutcome = {
    name,
    file: `${options.libraryDir ?? "library"}/${name}.jl`,
    blocks: plan.blocks,
    ref: null,
    pending: null,
  };
  const ref = `project:${name}`;
  const catalog = await refreshCatalog(project);
  if (catalog === null) {
    outcome.pending = "the catalog could not be refreshed";
    return outcome;
  }
  if (!catalog.blocks.some((entry) => entry.ref === ref)) {
    outcome.pending = `the catalog does not list ${ref} yet`;
    return outcome;
  }

  // The instance must stand in for the subsystem: the same model, no new error.
  const candidate = structuredClone(doc) as Model;
  if (!applySubsystemReplacement(candidate, nodeId, ref, path, plan, within)) {
    await removeBlocks(project, written);
    await refreshCatalog(project);
    throw new Error("The subsystem is no longer in the model.");
  }
  let added: string[];
  try {
    const [before, after] = await Promise.all([
      checkModel(doc, { project }),
      checkModel(candidate, { project }),
    ]);
    added = addedErrors(before.diagnostics, after.diagnostics);
  } catch (cause) {
    await removeBlocks(project, written);
    await refreshCatalog(project);
    throw new Error(
      `The model could not be checked with the new block, so nothing was saved: ${cause instanceof Error ? cause.message : String(cause)}`,
      { cause },
    );
  }
  if (added.length > 0) {
    await removeBlocks(project, written);
    await refreshCatalog(project);
    throw new Error(`The library block would not stand in for the subsystem, so nothing was saved: ${listed(added)}`);
  }

  const now = useDocumentStore.getState();
  if (now.revision !== revision || now.activePath.join("/") !== within.join("/")) {
    // An undo, an edit or a move to another diagram while the checks ran: the plan and
    // the check are for a document that is gone.
    await removeBlocks(project, written);
    await refreshCatalog(project);
    throw new Error("The model changed while the block was being checked, so nothing was saved. Try again.");
  }
  const result = now.replaceSubsystemWithRef(nodeId, ref, path, plan);
  if (!result.ok) {
    outcome.pending = result.error ?? "the subsystem could not be replaced";
    return outcome;
  }
  outcome.ref = ref;
  revealLibraryBlock(ref);
  return outcome;
}

/** One status line for a finished save. */
export function saveSubsystemMessage(outcome: SaveSubsystemOutcome, nodeName: string): string {
  const others = outcome.blocks.length - 1;
  const also = others === 0 ? "" : ` (and ${others} block${others === 1 ? "" : "s"} it uses)`;
  if (outcome.ref !== null) {
    return `Saved to ${outcome.file}${also}; ${nodeName} is now an instance of ${outcome.ref}. Drag ${outcome.name} from the library's Project category to add more.`;
  }
  return `Saved to ${outcome.file}${also}, but ${outcome.pending ?? "the block is not available yet"}, so ${nodeName} stays a subsystem. Reopen the project to use ${outcome.name}.`;
}
