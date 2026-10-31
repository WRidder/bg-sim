/**
 * Copy and paste of diagram elements through the system clipboard (the I/O half).
 *
 * Copy: {@link copyForClipboard} builds the envelope from the selection (with the
 * project library sources the open catalog knows) and keeps it in the document store;
 * the canvas writes it to the `copy` event's clipboard data.
 *
 * Paste: {@link pasteEnvelopeValue} validates a parsed envelope against the schema,
 * then {@link analyse} compares its dependencies with the target (library blocks of the
 * target project, globals of the target model, CSV files, docs images), asks about
 * conflicts in one dialog, writes what the target lacks (library files, data files,
 * images) and commits the elements, the rewrites and the added globals as ONE undo
 * step. A notice lists what was imported and what was not carried along. Library and
 * data files written to the project stay when the paste is undone.
 */

import { fetchDataText, writeDataText } from "../api/data";
import type { Catalog } from "../contracts/catalog";
import type { ClipboardEnvelope } from "../contracts/clipboard";
import type { ModelGlobalParameter, ModelPoint } from "../contracts/model";
import { copyAssets } from "../docs/docsApi";
import { listDataFiles } from "../api/data";
import { fetchCatalog } from "../library/catalogClient";
import { useCatalogStore } from "../library/catalogStore";
import {
  freeBlockName,
  loadProjectLibraryInfo,
  readProjectLibrarySource,
  writeProjectLibrary,
} from "../library/projectBlocks";
import { PASTE_OFFSET, useDocumentStore } from "../state/documentStore";
import { blockUses, catalogLibrary } from "./dependencies";
import { usePasteUiStore } from "./pasteUi";
import {
  freeDataName,
  freeGlobalName,
  normaliseSource,
  normaliseValue,
  resolve,
  type Analysis,
  type Choices,
  type Conflict,
  type DataEntry,
  type GlobalEntry,
  type LibraryEntry,
  type Resolution,
} from "./resolve";

/** The backend calls of a paste; tests pass fakes. */
export interface PasteIo {
  libraryNames: (project: string) => Promise<string[]>;
  librarySource: (project: string, name: string) => Promise<string | null>;
  writeLibrary: (project: string, name: string, source: string) => Promise<void>;
  /** Re-read the catalog after library writes; null when that failed. */
  refreshCatalog: (project: string) => Promise<Catalog | null>;
  dataFileNames: (project: string) => Promise<string[]>;
  dataText: (project: string, file: string) => Promise<string | null>;
  writeData: (project: string, file: string, text: string) => Promise<void>;
  copyAssets: (
    target: { project: string; model: string },
    from: { project: string; model: string },
    files: readonly string[],
  ) => Promise<{ copied: string[]; existing: string[]; missing: string[] }>;
  /** The conflict dialog; null is Cancel. */
  ask: (conflicts: Conflict[], project: string, writesFiles: boolean) => Promise<Choices | null>;
}

export const browserPasteIo: PasteIo = {
  libraryNames: async (project) => (await loadProjectLibraryInfo(project)).libraryNames,
  librarySource: readProjectLibrarySource,
  writeLibrary: (project, name, source) =>
    writeProjectLibrary(project, name, source, `The library block ${name} could not be written`),
  refreshCatalog: async (project) => {
    try {
      const catalog = await fetchCatalog(project);
      useCatalogStore.getState().setCatalog(catalog);
      return catalog;
    } catch {
      return null;
    }
  },
  dataFileNames: async (project) => (await listDataFiles(project)).map((entry) => entry.file),
  dataText: fetchDataText,
  writeData: writeDataText,
  copyAssets: (target, from, files) => copyAssets(target.project, target.model, from, files),
  ask: (conflicts, project, writesFiles) => usePasteUiStore.getState().ask(conflicts, project, writesFiles),
};

export interface PasteTarget {
  project: string | null;
  model: string | null;
  path: readonly string[];
  globals: readonly ModelGlobalParameter[];
}

async function quietly<T>(work: Promise<T>, fallback: T): Promise<T> {
  try {
    return await work;
  } catch {
    return fallback;
  }
}

/** The library blocks of the envelope with sources, reading missing ones from the source project. */
async function completeLibrary(envelope: ClipboardEnvelope, io: PasteIo): Promise<{ name: string; source: string | null }[]> {
  const blocks = envelope.dependencies.libraryBlocks.map((block) => ({
    name: block.name,
    source: block.source ?? null,
  }));
  const from = envelope.source.project;
  if (from === null || blocks.every((block) => block.source !== null)) {
    return blocks;
  }
  const sourceNames = await quietly(io.libraryNames(from), [] as string[]);
  const queue = blocks.filter((block) => block.source === null);
  const listed = new Set(blocks.map((block) => block.name));
  while (queue.length > 0) {
    const block = queue.shift() as { name: string; source: string | null };
    block.source = await quietly(io.librarySource(from, block.name), null);
    if (block.source === null) {
      continue;
    }
    for (const used of blockUses(block.source, sourceNames)) {
      if (!listed.has(used)) {
        listed.add(used);
        const added = { name: used, source: null };
        blocks.push(added);
        queue.push(added);
      }
    }
  }
  return blocks;
}

/** Compare the envelope's dependencies with the target; reads what it needs through `io`. */
export async function analyse(envelope: ClipboardEnvelope, target: PasteTarget, io: PasteIo): Promise<Analysis> {
  const source = envelope.source;
  const sameProject = source.project !== null && source.project === target.project;
  const sameModel = sameProject && source.model === target.model;
  const conflicts: Conflict[] = [];

  // Library blocks live in the project: nothing to do inside the same project.
  const library: LibraryEntry[] = [];
  if (!sameProject && target.project !== null && envelope.dependencies.libraryBlocks.length > 0) {
    const blocks = await completeLibrary(envelope, io);
    const targetNames = await io.libraryNames(target.project);
    const planned = new Set(targetNames);
    for (const block of blocks) {
      if (block.source === null) {
        library.push({ name: block.name, source: null, status: "unavailable" });
        continue;
      }
      const existing = targetNames.find((name) => name.toLowerCase() === block.name.toLowerCase());
      if (existing === undefined) {
        library.push({ name: block.name, source: block.source, status: "create" });
        planned.add(block.name);
        continue;
      }
      const existingSource = await io.librarySource(target.project, existing);
      if (existing === block.name && existingSource !== null && normaliseSource(existingSource) === normaliseSource(block.source)) {
        library.push({ name: block.name, source: block.source, status: "same", existing });
        continue;
      }
      library.push({ name: block.name, source: block.source, status: "conflict", existing });
      const renameTo = freeBlockName(block.name, [...planned, ...blocks.map((other) => other.name)]);
      planned.add(renameTo);
      conflicts.push({
        key: `library:${block.name}`,
        kind: "library",
        name: block.name,
        existing,
        renameTo,
        detail:
          existing === block.name
            ? `The project library of ${target.project} has a different ${existing}.`
            : `The project library of ${target.project} has ${existing} (block file names ignore case).`,
        choices: ["existing", "rename", "inline"],
      });
    }
  }

  // Globals live in the model.
  const globals: GlobalEntry[] = [];
  const own = new Map(target.globals.map((entry) => [entry.name, entry] as const));
  const plannedGlobals = new Set(envelope.dependencies.globals.map((entry) => entry.name));
  for (const entry of envelope.dependencies.globals) {
    const existing = own.get(entry.name);
    if (existing === undefined) {
      globals.push({ entry, status: "add" });
    } else if (normaliseValue(existing.value) === normaliseValue(entry.value)) {
      globals.push({ entry, status: "same" });
    } else if (sameModel) {
      globals.push({ entry, status: "kept", existingValue: existing.value });
    } else {
      globals.push({ entry, status: "conflict", existingValue: existing.value });
      const renameTo = freeGlobalName(entry.name, target.globals, plannedGlobals);
      plannedGlobals.add(renameTo);
      conflicts.push({
        key: `global:${entry.name}`,
        kind: "global",
        name: entry.name,
        existing: entry.name,
        renameTo,
        detail: `This model has ${entry.name} = ${existing.value}; the copy has ${entry.name} = ${entry.value}.`,
        choices: ["existing", "rename"],
      });
    }
  }

  // CSV files live in the project.
  const data: DataEntry[] = [];
  if (!sameProject && target.project !== null && source.project !== null && envelope.dependencies.dataFiles.length > 0) {
    const targetFiles = await quietly(io.dataFileNames(target.project), [] as string[]);
    const planned = new Set(targetFiles);
    for (const file of envelope.dependencies.dataFiles) {
      const text = await quietly(io.dataText(source.project, file), null);
      if (text === null) {
        data.push({ file, text: null, status: "unavailable" });
        continue;
      }
      const existing = await quietly(io.dataText(target.project, file), null);
      if (existing === null) {
        data.push({ file, text, status: "copy" });
      } else if (normaliseSource(existing) === normaliseSource(text)) {
        data.push({ file, text, status: "same" });
      } else {
        data.push({ file, text, status: "conflict" });
        const renameTo = freeDataName(file, planned);
        planned.add(renameTo);
        conflicts.push({
          key: `dataFile:${file}`,
          kind: "dataFile",
          name: file,
          existing: file,
          renameTo,
          detail: `The data folder of ${target.project} has a different ${file}.`,
          choices: ["existing", "rename"],
        });
      }
    }
  }

  // Docs images live next to the model; content-hash names never conflict.
  const assets =
    !sameModel &&
    source.project !== null &&
    source.model !== null &&
    target.project !== null &&
    target.model !== null &&
    envelope.dependencies.assets.length > 0
      ? { files: [...envelope.dependencies.assets], from: { project: source.project, model: source.model } }
      : null;

  return { library, globals, data, assets, conflicts };
}

// --------------------------------------------------------------------------- report

function plural(count: number, one: string, many = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`;
}

export interface PasteOutcome {
  pasted: { nodes: number; connections: number; annotations: number; shapes: number; droppedConnections: number };
  resolution: Resolution;
  /** Library blocks the refreshed catalog does not list (the file exists). */
  unpublished: string[];
  catalogError: boolean;
  assetsCopied: number;
  problems: string[];
}

/** The notice lines of a paste into another model or project. */
export function reportLines(envelope: ClipboardEnvelope, outcome: PasteOutcome, crossModel: boolean): string[] {
  const lines: string[] = [];
  const { resolution } = outcome;
  const created = resolution.libraryWrites.map((write) =>
    write.renamedFrom === undefined ? write.name : `${write.renamedFrom} as ${write.name}`,
  );
  if (created.length > 0) {
    lines.push(`Library blocks added: ${created.join(", ")}.`);
  }
  if (resolution.inlined.length > 0) {
    lines.push(`Converted to inline blocks: ${resolution.inlined.join(", ")}.`);
  }
  if (resolution.addGlobals.length > 0) {
    const renamed = Object.fromEntries(Object.entries(resolution.renamedGlobals).map(([from, to]) => [to, from]));
    lines.push(
      `Global parameters added: ${resolution.addGlobals
        .map((entry) => (renamed[entry.name] !== undefined ? `${renamed[entry.name]} as ${entry.name}` : entry.name))
        .join(", ")}.`,
    );
  }
  if (resolution.dataWrites.length > 0) {
    lines.push(
      `Data files copied: ${resolution.dataWrites
        .map((write) => (write.renamedFrom === undefined ? write.file : `${write.renamedFrom} as ${write.file}`))
        .join(", ")}.`,
    );
  }
  if (outcome.assetsCopied > 0) {
    lines.push(`Docs images copied for the notes: ${outcome.assetsCopied}.`);
  }
  if (resolution.kept.length > 0) {
    lines.push(`Kept the target's own ${resolution.kept.join("; ")}.`);
  }
  if (outcome.unpublished.length > 0) {
    lines.push(
      outcome.catalogError
        ? `The catalog could not be re-read; reopen the project to use ${outcome.unpublished.join(", ")}.`
        : `The catalog does not list ${outcome.unpublished.map((name) => `project:${name}`).join(", ")} yet; reopen the project to use ${outcome.unpublished.length === 1 ? "it" : "them"}.`,
    );
  }
  const omitted = envelope.omitted ?? {};
  const left: string[] = [];
  if ((omitted.bindings ?? 0) > 0) left.push(plural(omitted.bindings ?? 0, "3D binding"));
  if ((omitted.probes ?? 0) > 0) left.push(plural(omitted.probes ?? 0, "plot probe"));
  if ((omitted.dashboardCards ?? 0) > 0) left.push(plural(omitted.dashboardCards ?? 0, "dashboard card"));
  if ((omitted.plots ?? 0) > 0) left.push(plural(omitted.plots ?? 0, "saved plot"));
  if (crossModel) {
    left.push("docs pages and their links to the copied blocks");
  }
  if (left.length > 0) {
    lines.push(`Not carried along: ${left.join(", ")}.`);
  }
  if (outcome.pasted.droppedConnections > 0) {
    lines.push(`${plural(outcome.pasted.droppedConnections, "connection")} to elements that were not copied left out.`);
  }
  if (resolution.unavailable.length > 0) {
    lines.push(`Could not be read from the source: ${resolution.unavailable.join(", ")}.`);
  }
  lines.push(...outcome.problems);
  if (resolution.libraryWrites.length > 0 || resolution.dataWrites.length > 0) {
    lines.push("Undo removes the pasted elements and globals; the files written to the project stay.");
  }
  return lines;
}

// --------------------------------------------------------------------------- copy

/** The open catalog's project blocks, for the envelope's library sources. */
export function openLibrary(): ReturnType<typeof catalogLibrary> {
  return catalogLibrary(useCatalogStore.getState().catalog?.blocks);
}

/** Copy the selection into the in-window clipboard; the envelope, or null when nothing is selected. */
export function copyForClipboard(): ClipboardEnvelope | null {
  return useDocumentStore.getState().copySelection(openLibrary());
}

// --------------------------------------------------------------------------- paste

/** Repeated pastes of one copy at one place cascade by the paste offset. */
let lastPaste: { key: string; count: number } | null = null;

function repeatShift(envelope: ClipboardEnvelope, target: PasteTarget, at: ModelPoint | null): number {
  const key = JSON.stringify([
    envelope.id ?? null,
    target.project,
    target.model,
    target.path,
    at === null ? null : [Math.round(at.x), Math.round(at.y)],
  ]);
  if (envelope.id === undefined) {
    lastPaste = null;
    return 0;
  }
  if (lastPaste !== null && lastPaste.key === key) {
    lastPaste = { key, count: lastPaste.count + 1 };
  } else {
    lastPaste = { key, count: 0 };
  }
  return lastPaste.count * PASTE_OFFSET;
}

export function resetPasteCascade(): void {
  lastPaste = null;
}

export interface PasteRequest {
  /** Flow position for the centre of the pasted group; null keeps the copied layout + offset. */
  at: ModelPoint | null;
}

export type PasteStatus = "pasted" | "cancelled" | "failed" | "nothing";

/**
 * Paste an envelope into the open diagram: dependencies, one dialog for conflicts,
 * one undo step, one notice. Resolves to what happened.
 */
export async function pasteEnvelope(
  envelope: ClipboardEnvelope,
  request: PasteRequest,
  io: PasteIo = browserPasteIo,
): Promise<PasteStatus> {
  const store = useDocumentStore.getState();
  const ui = usePasteUiStore.getState();
  if (store.doc === null) {
    return "nothing";
  }
  const target: PasteTarget = {
    project: store.project,
    model: store.modelName,
    path: [...store.activePath],
    globals: store.doc.parameters ?? [],
  };
  const unchanged = (): boolean => {
    const now = useDocumentStore.getState();
    return now.doc !== null && now.project === target.project && now.modelName === target.model;
  };
  const crossModel = envelope.source.project !== target.project || envelope.source.model !== target.model;
  const at = request.at;

  ui.setBusy(true);
  try {
    let analysis: Analysis;
    try {
      analysis = await analyse(envelope, target, io);
    } catch (error) {
      ui.showNotice({
        tone: "error",
        title: "Nothing was pasted",
        lines: [error instanceof Error ? error.message : String(error)],
      });
      return "failed";
    }
    let choices: Choices = {};
    if (analysis.conflicts.length > 0) {
      const writesFiles = analysis.conflicts.some((conflict) => conflict.kind !== "global");
      const answer = await io.ask(analysis.conflicts, target.project ?? "", writesFiles);
      if (answer === null) {
        return "cancelled";
      }
      choices = answer;
    }
    if (!unchanged()) {
      ui.showNotice({ tone: "error", title: "Nothing was pasted", lines: ["The model changed while the paste was being prepared; paste again."] });
      return "failed";
    }
    const resolution = resolve(envelope, analysis, choices);

    // Library files first: a pasted instance must not point at a block that failed to arrive.
    const problems: string[] = [];
    if (target.project !== null) {
      for (const write of resolution.libraryWrites) {
        try {
          await io.writeLibrary(target.project, write.name, write.source);
        } catch (error) {
          ui.showNotice({
            tone: "error",
            title: "Nothing was pasted",
            lines: [error instanceof Error ? error.message : String(error)],
          });
          return "failed";
        }
      }
    }
    let unpublished: string[] = [];
    let catalogError = false;
    if (target.project !== null && resolution.libraryWrites.length > 0) {
      const catalog = await io.refreshCatalog(target.project);
      catalogError = catalog === null;
      const refs = new Set((catalog?.blocks ?? []).map((block) => block.ref));
      unpublished = resolution.libraryWrites
        .map((write) => write.name)
        .filter((name) => !refs.has(`project:${name}`));
    }
    if (target.project !== null) {
      for (const write of resolution.dataWrites) {
        try {
          await io.writeData(target.project, write.file, write.text);
        } catch (error) {
          problems.push(error instanceof Error ? error.message : String(error));
        }
      }
    }
    let assetsCopied = 0;
    if (analysis.assets !== null && target.project !== null && target.model !== null) {
      try {
        const result = await io.copyAssets(
          { project: target.project, model: target.model },
          analysis.assets.from,
          analysis.assets.files,
        );
        assetsCopied = result.copied.length;
        if (result.missing.length > 0) {
          problems.push(`Docs images missing in the source model: ${result.missing.join(", ")}.`);
        }
      } catch (error) {
        problems.push(
          `The docs images of the notes were not copied: ${error instanceof Error ? error.message : String(error)}`,
        );
      }
    }
    if (!unchanged()) {
      ui.showNotice({ tone: "error", title: "Nothing was pasted", lines: ["The model changed while the paste was being prepared; paste again."] });
      return "failed";
    }

    const shift = repeatShift(envelope, target, at);
    const result = useDocumentStore.getState().pasteClip(envelope, {
      at: at === null ? null : { x: at.x + shift, y: at.y + shift },
      offset: at === null ? PASTE_OFFSET + shift : 0,
      rewrites: resolution.rewrites,
      addGlobals: resolution.addGlobals,
    });
    if (result === null) {
      return "nothing";
    }
    const lines = reportLines(
      envelope,
      { pasted: result, resolution, unpublished, catalogError, assetsCopied, problems },
      crossModel,
    );
    const interesting =
      crossModel ||
      resolution.libraryWrites.length > 0 ||
      resolution.addGlobals.length > 0 ||
      resolution.inlined.length > 0 ||
      problems.length > 0 ||
      Object.values(envelope.omitted ?? {}).some((count) => typeof count === "number" && count > 0);
    if (interesting && lines.length > 0) {
      const parts = [
        result.nodes > 0 ? plural(result.nodes, "block") : null,
        result.connections > 0 ? plural(result.connections, "connection") : null,
        result.annotations > 0 ? plural(result.annotations, "note") : null,
        result.shapes > 0 ? plural(result.shapes, "shape") : null,
      ].filter((part): part is string => part !== null);
      const from =
        crossModel && envelope.source.model !== null
          ? ` from ${envelope.source.project === target.project ? "" : `${envelope.source.project ?? "?"}/`}${envelope.source.model}`
          : "";
      ui.showNotice({ tone: "info", title: `Pasted ${parts.join(", ")}${from}`, lines });
    }
    return "pasted";
  } finally {
    usePasteUiStore.getState().setBusy(false);
  }
}

/** Validate a parsed envelope (Ajv is loaded on first use), then paste it. */
export async function pasteEnvelopeValue(value: unknown, request: PasteRequest, io?: PasteIo): Promise<PasteStatus> {
  const { validateEnvelope } = await import("./validate");
  const checked = validateEnvelope(value);
  if (!checked.ok) {
    usePasteUiStore.getState().showNotice({ tone: "error", title: "Nothing was pasted", lines: [checked.message] });
    return "failed";
  }
  return pasteEnvelope(checked.envelope, request, io);
}
