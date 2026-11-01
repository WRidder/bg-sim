/**
 * Dependencies of a paste into another model or project (pure decisions).
 *
 * `analyse` (in pasteFlow.ts, which does the I/O) compares what the envelope carries
 * with what the target has and produces an {@link Analysis}: per library block, global
 * and data file whether it is new, identical, a conflict or unavailable. A conflict
 * needs a choice; the defaults never change the target's existing definitions:
 *
 * - `existing`: use the target's own definition (the default);
 * - `rename`: import the copy under a free name and rewrite the pasted references;
 * - `inline` (library blocks only): turn the pasted instances into inline blocks.
 *
 * `resolve` turns the analysis and the choices into the side effects (library files,
 * data files) and the document rewrites of the paste. It walks the dependency graph from
 * what the pasted nodes use, so a global or block that is only needed by a definition
 * the target keeps is not imported.
 */

import type { ClipboardEnvelope } from "../contracts/clipboard";
import type { ModelGlobalParameter } from "../contracts/model";
import { globalNameIssue, namesIn } from "../globals/globals";
import { renameIdentifier } from "../inspector/expression";
import { renameBlockDeclaration } from "../library/projectBlocks";
import {
  blockUses,
  globalRoots,
  inlineSources,
  projectRefs,
  PROJECT_PREFIX,
  renameBlockUses,
} from "./dependencies";
import type { PasteRewrites } from "./pastePlan";

export type ConflictKind = "library" | "global" | "dataFile";
export type ConflictChoice = "existing" | "rename" | "inline";

export interface Conflict {
  /** `<kind>:<name>`, the key of the choice. */
  key: string;
  kind: ConflictKind;
  /** The name in the copy. */
  name: string;
  /** The target's name (a library block may differ in case only). */
  existing: string;
  /** The name `rename` imports under. */
  renameTo: string;
  /** One line that says how the two differ. */
  detail: string;
  choices: ConflictChoice[];
}

export type Choices = Readonly<Record<string, ConflictChoice>>;

export interface LibraryEntry {
  name: string;
  source: string | null;
  status: "create" | "same" | "conflict" | "unavailable";
  /** The target's block of the same name (ignoring case), when there is one. */
  existing?: string;
}

export interface GlobalEntry {
  entry: ModelGlobalParameter;
  /** `kept`: the same model has a different value now; its own value stays, unasked. */
  status: "add" | "same" | "conflict" | "kept";
  existingValue?: string;
}

export interface DataEntry {
  file: string;
  text: string | null;
  status: "copy" | "same" | "conflict" | "unavailable";
}

export interface Analysis {
  library: LibraryEntry[];
  globals: GlobalEntry[];
  data: DataEntry[];
  /** Docs images to copy from the source model, and from where. */
  assets: { files: string[]; from: { project: string; model: string } } | null;
  conflicts: Conflict[];
}

export interface LibraryWrite {
  /** The file stem and block name written. */
  name: string;
  source: string;
  /** The name in the copy when the block is imported under a new name. */
  renamedFrom?: string;
}

export interface DataWrite {
  file: string;
  text: string;
  renamedFrom?: string;
}

export interface Resolution {
  rewrites: PasteRewrites;
  addGlobals: ModelGlobalParameter[];
  /** Globals imported under a new name, old -> new. */
  renamedGlobals: Record<string, string>;
  libraryWrites: LibraryWrite[];
  dataWrites: DataWrite[];
  /** Library blocks the pasted instances now carry inline. */
  inlined: string[];
  /** One line per definition of the target that was kept instead of the copy's. */
  kept: string[];
  /** Dependencies the paste could not read from the source. */
  unavailable: string[];
}

/** Line endings and trailing white space do not make two sources different. */
export function normaliseSource(text: string): string {
  return text
    .replace(/\r\n?/g, "\n")
    .split("\n")
    .map((line) => line.trimEnd())
    .join("\n")
    .trim();
}

export function normaliseValue(text: string): string {
  return text.replace(/\s+/g, "");
}

/**
 * A free global name: the name itself, else `<name>_2`, `<name>_3`, ... (a suffix, so
 * `J0` does not become the unrelated-looking `J1`), never taken, reserved or a function.
 */
export function freeGlobalName(
  base: string,
  globals: readonly ModelGlobalParameter[],
  taken: Iterable<string>,
): string {
  const used = new Set([...taken, ...globals.map((entry) => entry.name)]);
  const free = (name: string): boolean => !used.has(name) && globalNameIssue(globals, name) === null;
  if (free(base)) {
    return base;
  }
  let value = 2;
  while (!free(`${base}_${value}`)) {
    value += 1;
  }
  return `${base}_${value}`;
}

/**
 * A free data file name: `profile2.csv`, `bracket2.modal.json`, ... (file names ignore case on
 * Windows).
 */
export function freeDataName(file: string, taken: Iterable<string>): string {
  const lower = new Set([...taken].map((name) => name.toLowerCase()));
  const match = /^(.*?)(\.modal\.json|\.csv)$/i.exec(file);
  const stem = match?.[1] ?? file;
  const extension = match?.[2] ?? ".csv";
  if (!lower.has(file.toLowerCase())) {
    return file;
  }
  const numbered = /^(.*?)(\d+)$/.exec(stem);
  const root = numbered?.[1] && numbered[1].length > 0 ? numbered[1] : stem;
  let value = numbered ? Number(numbered[2]) + 1 : 2;
  while (lower.has(`${root}${value}${extension}`.toLowerCase())) {
    value += 1;
  }
  return `${root}${value}${extension}`;
}

/** The choice for each conflict: the given one when it is offered, else `existing`. */
export function choiceFor(conflict: Conflict, choices: Choices): ConflictChoice {
  const choice = choices[conflict.key];
  return choice !== undefined && conflict.choices.includes(choice) ? choice : "existing";
}

/** The defaults: every conflict keeps the target's definition. */
export function defaultChoices(conflicts: readonly Conflict[]): Record<string, ConflictChoice> {
  return Object.fromEntries(conflicts.map((conflict) => [conflict.key, "existing" as ConflictChoice]));
}

export function resolve(
  envelope: Pick<ClipboardEnvelope, "nodes">,
  analysis: Analysis,
  choices: Choices,
): Resolution {
  const conflicts = new Map(analysis.conflicts.map((conflict) => [conflict.key, conflict] as const));
  const rewrites: Record<"refs" | "inline" | "globals" | "dataFiles" | "blockRenames", Record<string, string>> = {
    refs: {},
    inline: {},
    globals: {},
    dataFiles: {},
    blockRenames: {},
  };
  const kept: string[] = [];
  const unavailable: string[] = [];
  const inlined: string[] = [];

  // ------------------------------------------------------------ library blocks
  const library = new Map(analysis.library.map((entry) => [entry.name, entry] as const));
  const libraryNames = [...library.keys()];
  const writes: LibraryWrite[] = [];
  const inlineSourcesByRef: Record<string, string> = {};
  const queue = [...projectRefs(envelope.nodes)];
  for (const source of inlineSources(envelope.nodes)) {
    queue.push(...blockUses(source, libraryNames));
  }
  const seen = new Set<string>();
  while (queue.length > 0) {
    const name = queue.shift() as string;
    if (seen.has(name)) {
      continue;
    }
    seen.add(name);
    const entry = library.get(name);
    if (entry === undefined || entry.status === "same") {
      continue;
    }
    if (entry.status === "unavailable" || entry.source === null) {
      unavailable.push(`library block ${name}`);
      continue;
    }
    const uses = blockUses(entry.source, libraryNames.filter((other) => other !== name));
    if (entry.status === "create") {
      writes.push({ name, source: entry.source });
      queue.push(...uses);
      continue;
    }
    const conflict = conflicts.get(`library:${name}`);
    const choice = conflict === undefined ? "existing" : choiceFor(conflict, choices);
    const existing = entry.existing ?? name;
    if (choice === "existing") {
      if (existing !== name) {
        rewrites.refs[`${PROJECT_PREFIX}${name}`] = `${PROJECT_PREFIX}${existing}`;
        rewrites.blockRenames[name] = existing;
      }
      kept.push(`library block ${existing}`);
    } else if (choice === "rename") {
      const renameTo = conflict?.renameTo ?? name;
      writes.push({ name: renameTo, source: renameBlockDeclaration(entry.source, renameTo, name), renamedFrom: name });
      rewrites.refs[`${PROJECT_PREFIX}${name}`] = `${PROJECT_PREFIX}${renameTo}`;
      rewrites.blockRenames[name] = renameTo;
      queue.push(...uses);
    } else {
      inlineSourcesByRef[`${PROJECT_PREFIX}${name}`] = entry.source;
      inlined.push(name);
      queue.push(...uses);
    }
  }
  // A renamed block is instantiated under its new name by the sources that travel.
  const renameUses = (source: string): string =>
    Object.entries(rewrites.blockRenames).reduce(
      (text, [from, to]) => renameBlockUses(text, from, to),
      source,
    );
  const libraryWrites = writes.map((write) => ({ ...write, source: renameUses(write.source) }));
  for (const [ref, source] of Object.entries(inlineSourcesByRef)) {
    rewrites.inline[ref] = renameUses(source);
  }

  // ------------------------------------------------------------ globals
  const globals = new Map(analysis.globals.map((state) => [state.entry.name, state] as const));
  const added: ModelGlobalParameter[] = [];
  const globalQueue = globalRoots(envelope.nodes, new Set(globals.keys()));
  const globalSeen = new Set<string>();
  while (globalQueue.length > 0) {
    const name = globalQueue.shift() as string;
    if (globalSeen.has(name)) {
      continue;
    }
    globalSeen.add(name);
    const state = globals.get(name);
    if (state === undefined || state.status === "same") {
      continue;
    }
    if (state.status === "kept") {
      kept.push(`global ${name} = ${state.existingValue ?? ""}`);
      continue;
    }
    if (state.status === "conflict") {
      const conflict = conflicts.get(`global:${name}`);
      const choice = conflict === undefined ? "existing" : choiceFor(conflict, choices);
      if (choice !== "rename") {
        kept.push(`global ${name} = ${state.existingValue ?? ""}`);
        continue;
      }
      rewrites.globals[name] = conflict?.renameTo ?? name;
    }
    added.push(state.entry);
    for (const used of namesIn(state.entry.value)) {
      if (globals.has(used)) {
        globalQueue.push(used);
      }
    }
  }
  const renameValue = (value: string): string =>
    Object.entries(rewrites.globals).reduce((text, [from, to]) => renameIdentifier(text, from, to), value);
  const order = analysis.globals.map((state) => state.entry.name);
  const addGlobals = added
    .sort((a, b) => order.indexOf(a.name) - order.indexOf(b.name))
    .map((entry) => ({ ...entry, name: rewrites.globals[entry.name] ?? entry.name, value: renameValue(entry.value) }));

  // ------------------------------------------------------------ data files
  const dataWrites: DataWrite[] = [];
  for (const entry of analysis.data) {
    if (entry.status === "same") {
      continue;
    }
    if (entry.status === "unavailable" || entry.text === null) {
      unavailable.push(`data file ${entry.file}`);
      continue;
    }
    if (entry.status === "copy") {
      dataWrites.push({ file: entry.file, text: entry.text });
      continue;
    }
    const conflict = conflicts.get(`dataFile:${entry.file}`);
    const choice = conflict === undefined ? "existing" : choiceFor(conflict, choices);
    if (choice === "rename") {
      const renameTo = conflict?.renameTo ?? entry.file;
      dataWrites.push({ file: renameTo, text: entry.text, renamedFrom: entry.file });
      rewrites.dataFiles[`data/${entry.file}`] = `data/${renameTo}`;
    } else {
      kept.push(`data file ${entry.file}`);
    }
  }

  return {
    rewrites,
    addGlobals,
    renamedGlobals: { ...rewrites.globals },
    libraryWrites,
    dataWrites,
    inlined,
    kept,
    unavailable,
  };
}
