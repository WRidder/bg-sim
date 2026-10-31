/**
 * From code to a reusable block (plan 7.7): "Save to project library" turns
 * an inline Equation/Discrete-code node into a project library block, and
 * "+ Library block" in the Code tab starts a new one from a template.
 *
 * Both write `library/<Name>.jl` and re-read the catalog through
 * library/projectBlocks.ts (shared with "Copy to project library"). The save
 * then re-points the inline node — and, on request, every inline node with
 * the identical source — to `project:<Name>` in one undo step. When the
 * refreshed catalog does not list the block (the fake worker serves a fixed
 * catalog) nothing is re-pointed: the outcome says so and the caller reports
 * it.
 */

import type { Model, ModelDiagram, ModelNode } from "../contracts/model";
import { useCatalogStore } from "../library/catalogStore";
import { revealLibraryBlock } from "../library/libraryReveal";
import {
  freeBlockName,
  publishProjectBlock,
  renameBlockDeclaration,
  type PublishOutcome,
} from "../library/projectBlocks";
import { useDocumentStore } from "../state/documentStore";
import { useCodeSessionStore } from "./codeSession";
import type { CodeTarget } from "./sources";
import { blockNameOf, DISCRETE_TEMPLATE, EQUATION_TEMPLATE } from "./templates";

export type NewBlockKind = "equation" | "discrete";

export interface InlineNodeEntry {
  id: string;
  /** Instance path, e.g. `Plant/Equation1`. */
  path: string;
  node: ModelNode;
}

export interface SaveInlineOutcome extends PublishOutcome {
  /** The node ids now pointing at `ref` (empty when nothing was re-pointed). */
  repointed: string[];
  /** Why re-pointing failed after the write, or null. */
  repointError: string | null;
}

function walk(
  diagram: ModelDiagram,
  prefix: string,
  visit: (node: ModelNode, path: string) => void,
): void {
  for (const node of diagram.nodes) {
    const path = prefix.length === 0 ? node.name : `${prefix}/${node.name}`;
    visit(node, path);
    if ("subsystem" in node.block) {
      walk(node.block.subsystem.diagram, path, visit);
    }
  }
}

/** Every inline code node of the model, subsystems included, in diagram order. */
export function inlineNodesOf(doc: Model | null): InlineNodeEntry[] {
  const out: InlineNodeEntry[] = [];
  if (doc === null) {
    return out;
  }
  walk(doc.diagram, "", (node, path) => {
    if ("inline" in node.block) {
      out.push({ id: node.id, path, node });
    }
  });
  return out;
}

/** The inline node `nodeId`, anywhere in the model, or null. */
export function findInlineNode(doc: Model | null, nodeId: string): InlineNodeEntry | null {
  return inlineNodesOf(doc).find((entry) => entry.id === nodeId) ?? null;
}

/** The other inline nodes whose source is exactly `source` (candidates to re-point too). */
export function identicalInlineNodes(
  doc: Model | null,
  nodeId: string,
  source: string,
): InlineNodeEntry[] {
  return inlineNodesOf(doc).filter(
    (entry) =>
      entry.id !== nodeId && "inline" in entry.node.block && entry.node.block.inline.source === source,
  );
}

/** The proposed block name: the `@block` name of the source, made free in the project library. */
export function suggestedBlockName(source: string, taken: Iterable<string>, fallback = "MyBlock"): string {
  return freeBlockName(blockNameOf(source) ?? fallback, taken);
}

/** The starter source of a new library block of `kind`. */
export function templateFor(kind: NewBlockKind): string {
  return kind === "equation" ? EQUATION_TEMPLATE : DISCRETE_TEMPLATE;
}

/** The Code tab target of a project library block (also before the catalog lists it). */
export function projectTarget(outcome: PublishOutcome): CodeTarget {
  return {
    kind: "library",
    sourceKind: "project",
    blockRef: outcome.ref ?? `project:${outcome.name}`,
    name: outcome.name,
    path: outcome.file,
    line: 1,
    col: 1,
    seed: outcome.source,
  };
}

/**
 * Save the inline source as `library/<name>.jl` (its `@block` declaration
 * renamed to `name`, as the loader requires) and re-point `nodeIds` to
 * `project:<name>` in one undo step when the refreshed catalog lists it.
 *
 * A Code tab that has one of the re-pointed nodes open switches to the
 * library block, and the library browser shows the new entry.
 */
export async function saveInlineToProjectLibrary(
  project: string,
  options: { name: string; source: string; nodeIds: readonly string[]; libraryDir?: string },
): Promise<SaveInlineOutcome> {
  const source = renameBlockDeclaration(options.source, options.name);
  const outcome = await publishProjectBlock(project, options.name, source, {
    libraryDir: options.libraryDir,
    failure: "The block could not be saved to the project library",
  });
  if (outcome.catalog !== null) {
    useCatalogStore.getState().setCatalog(outcome.catalog);
  }
  if (outcome.ref === null) {
    return { ...outcome, repointed: [], repointError: null };
  }
  const result = useDocumentStore.getState().replaceInlineWithRef(options.nodeIds, outcome.ref);
  const repointed = result.ok ? (result.replaced ?? []) : [];
  const session = useCodeSessionStore.getState();
  if (session.target?.kind === "inline" && repointed.includes(session.target.nodeId)) {
    session.open(projectTarget(outcome));
  }
  revealLibraryBlock(outcome.ref);
  return {
    ...outcome,
    repointed,
    repointError: result.ok ? null : (result.error ?? "The block could not be re-pointed."),
  };
}

/**
 * Create `library/<name>.jl` from the Equation or Discrete template with
 * `@block <name>`, re-read the catalog and show the block in the library. It
 * is not placed on the diagram.
 */
export async function createProjectLibraryBlock(
  project: string,
  options: { name: string; kind: NewBlockKind; libraryDir?: string },
): Promise<PublishOutcome> {
  const source = renameBlockDeclaration(templateFor(options.kind), options.name);
  const outcome = await publishProjectBlock(project, options.name, source, {
    libraryDir: options.libraryDir,
    failure: "The library block could not be created",
  });
  if (outcome.catalog !== null) {
    useCatalogStore.getState().setCatalog(outcome.catalog);
  }
  if (outcome.ref !== null) {
    revealLibraryBlock(outcome.ref);
  }
  return outcome;
}

/** One status line for a finished save, naming what happened to the instances. */
export function saveInlineMessage(outcome: SaveInlineOutcome, nodeName: string): string {
  if (outcome.repointed.length > 0) {
    const others = outcome.repointed.length - 1;
    const also =
      others === 0 ? "" : ` (and ${others} other identical inline block${others === 1 ? "" : "s"})`;
    return `Saved to ${outcome.file}; ${nodeName}${also} now uses ${outcome.ref}. Drag ${outcome.name} from the library's Project category to add more.`;
  }
  if (outcome.repointError !== null) {
    return `Saved to ${outcome.file}, but ${nodeName} could not be re-pointed (${outcome.repointError}).`;
  }
  if (outcome.catalogError !== null) {
    return `Saved to ${outcome.file}, but the catalog could not be refreshed (${outcome.catalogError}). ${nodeName} stays an inline block; reopen the project to use ${outcome.name}.`;
  }
  return `Saved to ${outcome.file}. The catalog does not list project:${outcome.name} yet, so ${nodeName} stays an inline block; reopen the project to use the library block.`;
}
