/**
 * What copied elements need from their model and project (clipboard envelope
 * `dependencies`), collected through every nested subsystem:
 *
 * - project library blocks: every `project:<Name>` ref, and the project blocks that a
 *   library or inline source instantiates (`gear = MyGear(...)` in `@components`);
 * - global parameters: every global a copied param, start or string constant reads,
 *   plus the globals those depend on (the dependency closure, as the compiler folds them);
 * - docs images: `assets/<hash>.<ext>` named in a copied sticky note;
 * - data files: the `data/<file>.csv` of a copied CsvSource and the `data/<file>.modal.json` of a
 *   copied ModalBody3D (the GLB of its mode shapes is not carried: the scene binding that shows
 *   it is model-level and is not copied either).
 *
 * Pure functions; the paste side (`pasteFlow.ts`) decides what the target lacks.
 */

import type {
  ClipboardDependencies,
  ClipboardLibraryBlock,
} from "../contracts/clipboard";
import type {
  ModelAnnotation,
  ModelDiagram,
  ModelGlobalParameter,
  ModelNode,
} from "../contracts/model";
import { assetRefs } from "../docs/docsImages";
import { namesIn } from "../globals/globals";
import { isCsvSourceRef } from "../inspector/csvSource";
import { isModalBodyRef, MODAL_DATA_FILE } from "../inspector/modalBody";

/** The project library as the copying editor knows it (the open project's catalog). */
export interface LibraryLookup {
  /** The source of `project:<name>`, or null when the editor does not have it. */
  source: (name: string) => string | null;
  /** Every project block name the editor knows. */
  names: ReadonlySet<string>;
}

export const PROJECT_PREFIX = "project:";

/** A CsvSource's file constant names a project data file as `data/<file>.csv`. */
const DATA_FILE = /^data\/([A-Za-z0-9_.-]+\.csv)$/i;

/** Every node of `nodes`, nested subsystem nodes included, depth first. */
export function walkNodes(nodes: readonly ModelNode[], visit: (node: ModelNode) => void): void {
  for (const node of nodes) {
    visit(node);
    if ("subsystem" in node.block) {
      walkNodes(node.block.subsystem.diagram.nodes, visit);
    }
  }
}

/** Every diagram nested in `nodes` (not the level they sit on). */
export function walkNestedDiagrams(
  nodes: readonly ModelNode[],
  visit: (diagram: ModelDiagram) => void,
): void {
  walkNodes(nodes, (node) => {
    if ("subsystem" in node.block) {
      visit(node.block.subsystem.diagram);
    }
  });
}

/** The expression strings of a node: params, starts and string constants. */
export function nodeExpressions(node: ModelNode): string[] {
  const out = [...Object.values(node.params ?? {}), ...Object.values(node.starts ?? {})];
  for (const value of Object.values(node.constants ?? {})) {
    if (typeof value === "string") {
      out.push(value);
    }
  }
  return out;
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * The block names of `candidates` that a block source instantiates: an identifier
 * followed by `(`, as in `gear = MyGear(n = 3)` of an `@components` section.
 */
export function blockUses(source: string, candidates: Iterable<string>): string[] {
  const found: string[] = [];
  for (const name of candidates) {
    const pattern = new RegExp(`(?<![A-Za-z0-9_.])${escapeRegExp(name)}\\s*\\(`);
    if (pattern.test(source)) {
      found.push(name);
    }
  }
  return found;
}

/** Rewrite every instantiation `from(` in a block source to `to(`. */
export function renameBlockUses(source: string, from: string, to: string): string {
  const pattern = new RegExp(`(?<![A-Za-z0-9_.])${escapeRegExp(from)}(?=\\s*\\()`, "g");
  return source.replace(pattern, to);
}

/** The project block names `project:<Name>` refs of `nodes` use, in first-use order. */
export function projectRefs(nodes: readonly ModelNode[]): string[] {
  const names = new Set<string>();
  walkNodes(nodes, (node) => {
    if ("ref" in node.block && node.block.ref.startsWith(PROJECT_PREFIX)) {
      names.add(node.block.ref.slice(PROJECT_PREFIX.length));
    }
  });
  return [...names];
}

/** The inline block sources of `nodes`. */
export function inlineSources(nodes: readonly ModelNode[]): string[] {
  const out: string[] = [];
  walkNodes(nodes, (node) => {
    if ("inline" in node.block) {
      out.push(node.block.inline.source);
    }
  });
  return out;
}

/** The global names the expressions of `nodes` read (only names in `known`). */
export function globalRoots(nodes: readonly ModelNode[], known: ReadonlySet<string>): string[] {
  const names = new Set<string>();
  walkNodes(nodes, (node) => {
    for (const text of nodeExpressions(node)) {
      for (const name of namesIn(text)) {
        if (known.has(name)) {
          names.add(name);
        }
      }
    }
  });
  return [...names];
}

/** `roots` plus every global their values read, transitively; in the table order of `globals`. */
export function globalClosure(
  globals: readonly ModelGlobalParameter[],
  roots: readonly string[],
): ModelGlobalParameter[] {
  const byName = new Map(globals.map((entry) => [entry.name, entry] as const));
  const needed = new Set<string>();
  const queue = [...roots];
  while (queue.length > 0) {
    const name = queue.shift() as string;
    if (needed.has(name)) {
      continue;
    }
    const entry = byName.get(name);
    if (entry === undefined) {
      continue;
    }
    needed.add(name);
    for (const used of namesIn(entry.value)) {
      if (byName.has(used) && !needed.has(used)) {
        queue.push(used);
      }
    }
  }
  return globals.filter((entry) => needed.has(entry.name)).map((entry) => ({ ...entry }));
}

/**
 * The data file names that the nodes of `nodes` read: the CSV files of CsvSource nodes and the
 * reduced-model files of ModalBody3D nodes.
 */
export function dataFiles(nodes: readonly ModelNode[]): string[] {
  const files = new Set<string>();
  walkNodes(nodes, (node) => {
    if (!("ref" in node.block)) {
      return;
    }
    const pattern = isCsvSourceRef(node.block.ref)
      ? DATA_FILE
      : isModalBodyRef(node.block.ref)
        ? MODAL_DATA_FILE
        : null;
    if (pattern === null) {
      return;
    }
    const file = node.constants?.file;
    const match = typeof file === "string" ? pattern.exec(file.trim()) : null;
    if (match?.[1] !== undefined) {
      files.add(match[1]);
    }
  });
  return [...files];
}

/** The docs images the copied notes (top level and nested) name. */
export function noteAssets(nodes: readonly ModelNode[], annotations: readonly ModelAnnotation[]): string[] {
  const files = new Set<string>();
  const add = (notes: readonly ModelAnnotation[] | undefined): void => {
    for (const note of notes ?? []) {
      for (const file of assetRefs(note.text)) {
        files.add(file);
      }
    }
  };
  add(annotations);
  walkNestedDiagrams(nodes, (diagram) => add(diagram.annotations));
  return [...files];
}

/**
 * The project library blocks `nodes` need: their refs and, through the known sources,
 * the project blocks those instantiate. A block whose source the editor does not have
 * is listed without one; the paste reads it from the source project.
 */
export function libraryClosure(
  nodes: readonly ModelNode[],
  library: LibraryLookup | undefined,
): ClipboardLibraryBlock[] {
  const known = library?.names ?? new Set<string>();
  const queue = [...projectRefs(nodes)];
  for (const source of inlineSources(nodes)) {
    queue.push(...blockUses(source, known));
  }
  const seen = new Set<string>();
  const out: ClipboardLibraryBlock[] = [];
  while (queue.length > 0) {
    const name = queue.shift() as string;
    if (seen.has(name)) {
      continue;
    }
    seen.add(name);
    const source = library?.source(name) ?? null;
    out.push(source === null ? { name } : { name, source });
    if (source !== null) {
      queue.push(...blockUses(source, [...known].filter((other) => other !== name)));
    }
  }
  return out;
}

export interface CollectInput {
  nodes: readonly ModelNode[];
  annotations: readonly ModelAnnotation[];
  /** The source model's global parameters. */
  globals: readonly ModelGlobalParameter[];
  library?: LibraryLookup;
}

export function collectDependencies(input: CollectInput): ClipboardDependencies {
  const globalNames = new Set(input.globals.map((entry) => entry.name));
  return {
    libraryBlocks: libraryClosure(input.nodes, input.library),
    globals: globalClosure(input.globals, globalRoots(input.nodes, globalNames)),
    assets: noteAssets(input.nodes, input.annotations),
    dataFiles: dataFiles(input.nodes),
  };
}

/** A library lookup over a catalog's `project:` blocks. */
export function catalogLibrary(
  blocks: readonly { ref: string; source: string }[] | null | undefined,
): LibraryLookup {
  const sources = new Map<string, string>();
  for (const block of blocks ?? []) {
    if (block.ref.startsWith(PROJECT_PREFIX)) {
      sources.set(block.ref.slice(PROJECT_PREFIX.length), block.source);
    }
  }
  return { source: (name) => sources.get(name) ?? null, names: new Set(sources.keys()) };
}
