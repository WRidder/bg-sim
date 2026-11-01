/**
 * The clipboard envelope of the diagram editor (contract `clipboard.schema.json`).
 *
 * Copy puts one envelope on the system clipboard as `text/plain` JSON (and under
 * {@link CLIPBOARD_MIME} where the browser keeps custom types), so a paste works in
 * another model, another browser window and another project of the same backend. The
 * document store keeps the last envelope too, as a fallback for a browser that gives
 * the page no clipboard data.
 *
 * Everything here is pure: building an envelope from a selection, serialising it, and
 * the cheap checks a paste runs before the schema validation (`validate.ts`, loaded on
 * demand because it brings Ajv along).
 */

import type {
  ClipboardEnvelope,
  ClipboardOmitted,
  ClipboardSource,
} from "../contracts/clipboard";
import type { Model, ModelDiagram, ModelNode } from "../contracts/model";
import { selectedNoteIds } from "../editor/notes";
import { selectedShapeIds } from "../editor/shapes";
import { activeDiagram, subsystemPathCrumbs } from "../editor/subsystemPath";
import { collectDependencies, type LibraryLookup } from "./dependencies";

export type { ClipboardEnvelope } from "../contracts/clipboard";

export const CLIPBOARD_FORMAT = "bgsim-clipboard";
export const CLIPBOARD_VERSION = 1;
/** The custom clipboard type; text/plain carries the same JSON and is what a paste needs. */
export const CLIPBOARD_MIME = "application/x-bgsim-clipboard+json";
/**
 * The largest envelope (characters of JSON) the editor writes or reads: about thirty
 * subsystem images of 512 KiB each. A larger copy stays in this window only.
 */
export const MAX_CLIPBOARD_CHARS = 16 * 1024 * 1024;

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

export function emptyEnvelope(): ClipboardEnvelope {
  return {
    format: CLIPBOARD_FORMAT,
    version: CLIPBOARD_VERSION,
    source: { project: null, model: null, path: [] },
    nodes: [],
    connections: [],
    annotations: [],
    shapes: [],
    dependencies: { libraryBlocks: [], globals: [], assets: [], dataFiles: [] },
  };
}

export function isEmptyEnvelope(envelope: {
  nodes: readonly unknown[];
  annotations: readonly unknown[];
  shapes: readonly unknown[];
}): boolean {
  return envelope.nodes.length === 0 && envelope.annotations.length === 0 && envelope.shapes.length === 0;
}

/** A short random id for one copy (repeated pastes of the same copy cascade). */
export function copyId(): string {
  const bytes = new Uint8Array(6);
  globalThis.crypto.getRandomValues(bytes);
  return [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

/** Drop the probes of a nested diagram (they point at signal paths of the source model). */
function withoutProbes(node: ModelNode): { node: ModelNode; probes: number } {
  if (!("subsystem" in node.block)) {
    return { node, probes: 0 };
  }
  let probes = 0;
  const strip = (diagram: ModelDiagram): void => {
    probes += diagram.probes?.length ?? 0;
    delete diagram.probes;
    for (const inner of diagram.nodes) {
      if ("subsystem" in inner.block) {
        strip(inner.block.subsystem.diagram);
      }
    }
  };
  strip(node.block.subsystem.diagram);
  return { node, probes };
}

/** Does `text` (any JSON value) name a signal or parameter below one of `prefixes`? */
function mentions(value: unknown, prefixes: readonly string[]): boolean {
  if (prefixes.length === 0) {
    return false;
  }
  const text = JSON.stringify(value ?? null);
  return prefixes.some((prefix) => text.includes(`"${prefix}/`) || text.includes(`"${prefix}.`));
}

/** How many model-level items refer to the copied nodes and stay behind. */
export function countOmitted(
  doc: Model,
  path: readonly string[],
  nodes: readonly ModelNode[],
  connectionIds: ReadonlySet<string>,
  nestedProbes: number,
): ClipboardOmitted {
  const base = subsystemPathCrumbs(doc, path).map((crumb) => crumb.name);
  const prefixes = nodes.map((node) => [...base, node.name].join("/"));
  const diagram = activeDiagram(doc, path);
  const probes =
    nestedProbes +
    (diagram?.probes ?? []).filter((probe) =>
      probe.links.some((link) => connectionIds.has(link.connection)),
    ).length;
  return {
    bindings: (doc.bindings ?? []).filter((binding) => mentions(binding, prefixes)).length,
    probes,
    dashboardCards: (doc.dashboard?.cards ?? []).filter((card) => mentions(card, prefixes)).length,
    plots: (doc.plots ?? []).filter((plot) => mentions([...plot.signals, plot.x ?? ""], prefixes)).length,
  };
}

export interface CopyInput {
  doc: Model;
  /** The diagram level being edited (subsystem node ids from the root). */
  path: readonly string[];
  /** Canvas ids of the selection: node ids, `note:<id>` and `shape:<id>`. */
  selection: readonly string[];
  project: string | null;
  model: string | null;
  /** Project library sources known to the editor (the catalog of the open project). */
  library?: LibraryLookup;
}

/**
 * The envelope of a selection, or null when nothing copyable is selected. Connections
 * are kept only when both ends are copied; the probes of copied subsystems are dropped
 * (and counted in `omitted`).
 */
export function buildEnvelope(input: CopyInput): ClipboardEnvelope | null {
  const diagram = activeDiagram(input.doc, input.path);
  if (diagram === null) {
    return null;
  }
  const selected = new Set(input.selection);
  let nestedProbes = 0;
  const nodes = diagram.nodes
    .filter((node) => selected.has(node.id))
    .map((node) => {
      const stripped = withoutProbes(clone(node));
      nestedProbes += stripped.probes;
      return stripped.node;
    });
  const nodeIds = new Set(nodes.map((node) => node.id));
  const connections = diagram.connections
    .filter((connection) => nodeIds.has(connection.from.node) && nodeIds.has(connection.to.node))
    .map((connection) => clone(connection));
  const noteIds = new Set(selectedNoteIds(input.selection));
  const annotations = (diagram.annotations ?? [])
    .filter((note) => noteIds.has(note.id))
    .map((note) => clone(note));
  // Shapes keep their z order (the document order).
  const shapeIds = new Set(selectedShapeIds(input.selection));
  const shapes = (diagram.shapes ?? [])
    .filter((shape) => shapeIds.has(shape.id))
    .map((shape) => clone(shape));
  if (nodes.length === 0 && annotations.length === 0 && shapes.length === 0) {
    return null;
  }
  const source: ClipboardSource = {
    project: input.project,
    model: input.model,
    path: [...input.path],
  };
  const dependencies = collectDependencies({
    nodes,
    annotations,
    globals: input.doc.parameters ?? [],
    library: input.library,
  });
  const omitted = countOmitted(
    input.doc,
    input.path,
    nodes,
    new Set(connections.map((connection) => connection.id)),
    nestedProbes,
  );
  return {
    format: CLIPBOARD_FORMAT,
    version: CLIPBOARD_VERSION,
    id: copyId(),
    source,
    nodes,
    connections,
    annotations,
    shapes,
    dependencies,
    omitted,
  };
}

export function serializeEnvelope(envelope: ClipboardEnvelope): string {
  return JSON.stringify(envelope);
}

export type EnvelopeRead =
  | { kind: "envelope"; value: unknown }
  | { kind: "foreign" }
  | { kind: "invalid"; message: string };

/**
 * The cheap checks of a paste, before the schema: the size cap, JSON, the format and
 * the version. Text that is not a bg-sim envelope at all is `foreign` (the caller may
 * fall back to the in-window copy); a bg-sim envelope that cannot be read is `invalid`.
 */
export function readEnvelopeText(text: string | null | undefined): EnvelopeRead {
  if (text === null || text === undefined) {
    return { kind: "foreign" };
  }
  const trimmed = text.trim();
  if (!trimmed.startsWith("{") || !trimmed.includes(CLIPBOARD_FORMAT)) {
    return { kind: "foreign" };
  }
  if (trimmed.length > MAX_CLIPBOARD_CHARS) {
    return {
      kind: "invalid",
      message: `The clipboard holds ${(trimmed.length / (1024 * 1024)).toFixed(1)} MB of bg-sim elements; the limit is ${MAX_CLIPBOARD_CHARS / (1024 * 1024)} MB. Copy fewer elements.`,
    };
  }
  let value: unknown;
  try {
    value = JSON.parse(trimmed) as unknown;
  } catch {
    return { kind: "foreign" };
  }
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return { kind: "foreign" };
  }
  const record = value as Record<string, unknown>;
  if (record.format !== CLIPBOARD_FORMAT) {
    return { kind: "foreign" };
  }
  if (record.version !== CLIPBOARD_VERSION) {
    return {
      kind: "invalid",
      message: `The clipboard holds bg-sim elements in format version ${String(record.version)}; this editor reads version ${CLIPBOARD_VERSION}. Copy them again from this version of bg-sim.`,
    };
  }
  return { kind: "envelope", value };
}

/** Same project, model and diagram level as the copy? */
export function sameSource(
  source: ClipboardSource,
  target: { project: string | null; model: string | null; path: readonly string[] },
): boolean {
  return (
    source.project === target.project &&
    source.model === target.model &&
    source.path.length === target.path.length &&
    source.path.every((id, index) => id === target.path[index])
  );
}
