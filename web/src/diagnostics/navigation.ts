/**
 * Click-to-navigate for diagnostics (plan 7.3): resolve a diagnostic to the
 * editor node (by `node` id first, then by instance path), select it and ask
 * the canvas decorator to pan to it. A source-level diagnostic also announces
 * its range so the code tab can open at the line when that tab lands.
 *
 * Paths follow plan 3.1: a top-level instance is `Name`, a nested one is
 * `Parent/Child`. Subsystem diagrams are walked so a path can resolve into a
 * nested instance; only top-level instances are rendered on the canvas today,
 * so navigation stops at the top level and the resolver says so.
 */

import type { Diagnostic, DiagnosticSource } from "../contracts/diagnostic";
import type { Model, ModelDiagram } from "../contracts/model";
import { useDocumentStore } from "../state/documentStore";
import { useDiagnosticsStore } from "./store";

/** The DOM event a code view listens for once W1.2/W1.4 mounts it. */
export const OPEN_SOURCE_EVENT = "bgsim:open-source";

export interface OpenSourceDetail {
  kind: DiagnosticSource["kind"];
  ref: string;
  line: number;
  col: number;
}

export interface NodePaths {
  /** Instance path (`Plant/Motor1`) -> node id, for the first instance at that path. */
  paths: Map<string, string>;
  /** Node id -> instance path. */
  byId: Map<string, string>;
}

function walkDiagram(
  diagram: ModelDiagram,
  prefix: string,
  out: NodePaths,
): void {
  for (const node of diagram.nodes) {
    const path = prefix.length === 0 ? node.name : `${prefix}/${node.name}`;
    if (!out.paths.has(path)) {
      out.paths.set(path, node.id);
    }
    out.byId.set(node.id, path);
    if ("subsystem" in node.block) {
      walkDiagram(node.block.subsystem.diagram, path, out);
    }
  }
}

/** Every instance path and node id in the document, including subsystems. */
export function collectNodePaths(doc: Model | null): NodePaths {
  const out: NodePaths = { paths: new Map(), byId: new Map() };
  if (doc !== null) {
    walkDiagram(doc.diagram, "", out);
  }
  return out;
}

function topLevelNodeIds(doc: Model): Set<string> {
  return new Set(doc.diagram.nodes.map((node) => node.id));
}

/**
 * The editor node a path points at, or null. An exact instance path wins; a
 * diagnostic path that names a suffix (`Plant/Motor1` for `Motor1`) or only
 * the instance name still resolves when it is unambiguous.
 */
export function resolvePathToNode(doc: Model | null, path: string | null): string | null {
  if (doc === null || path === null || path.length === 0) {
    return null;
  }
  return createNodeResolver(doc)({ code: "", severity: "info", message: "", path });
}

/** The node a diagnostic highlights, by editor id first and path second. */
export type NodeResolver = (diagnostic: Diagnostic) => string | null;

/**
 * Build a resolver once for a document. The panel resolves every row and the
 * canvas resolves every diagnostic, so walking the diagram per row would be
 * quadratic on a large model.
 */
export function createNodeResolver(doc: Model | null): NodeResolver {
  if (doc === null) {
    return () => null;
  }
  const { paths } = collectNodePaths(doc);
  const topLevel = topLevelNodeIds(doc);

  const fromPath = (path: string | null): string | null => {
    if (path === null || path.length === 0) {
      return null;
    }
    const exact = paths.get(path);
    if (exact !== undefined) {
      return topLevel.has(exact) ? exact : null;
    }

    const suffixMatches: string[] = [];
    for (const [candidate, id] of paths) {
      if (
        (candidate.endsWith(`/${path}`) || path.endsWith(`/${candidate}`)) &&
        topLevel.has(id) &&
        !suffixMatches.includes(id)
      ) {
        suffixMatches.push(id);
      }
    }
    if (suffixMatches.length === 1) {
      return suffixMatches[0] ?? null;
    }

    const lastSegment = path.includes("/") ? path.slice(path.lastIndexOf("/") + 1) : path;
    const byName = doc.diagram.nodes.filter((node) => node.name === lastSegment);
    return byName.length === 1 ? (byName[0]?.id ?? null) : null;
  };

  return (diagnostic) => {
    if (
      typeof diagnostic.node === "string" &&
      diagnostic.node.length > 0 &&
      topLevel.has(diagnostic.node)
    ) {
      return diagnostic.node;
    }
    return fromPath(diagnostic.path ?? null);
  };
}

/** The node a diagnostic highlights, by editor id first and path second. */
export function resolveDiagnosticNode(doc: Model | null, diagnostic: Diagnostic): string | null {
  return createNodeResolver(doc)(diagnostic);
}

export type NavigationTarget = "node" | "source" | "none";

/**
 * Select the diagnostic's node/connection and request a pan. Returns what the
 * click actually reached: a node, a source range, or nothing clickable.
 */
export function navigateToDiagnostic(diagnostic: Diagnostic): NavigationTarget {
  const documentState = useDocumentStore.getState();
  const doc = documentState.doc;
  const nodeId = resolveDiagnosticNode(doc, diagnostic);
  const connectionId =
    doc !== null &&
    typeof diagnostic.connection === "string" &&
    doc.diagram.connections.some((connection) => connection.id === diagnostic.connection)
      ? diagnostic.connection
      : null;

  if (nodeId !== null || connectionId !== null) {
    documentState.setSelection(nodeId === null ? [] : [nodeId], connectionId === null ? [] : [connectionId]);
  }

  if (nodeId !== null) {
    useDiagnosticsStore.getState().requestFocus(nodeId);
  }

  if (diagnostic.source !== null && diagnostic.source !== undefined) {
    focusSource(diagnostic.source);
  }

  if (nodeId !== null) {
    return "node";
  }
  return diagnostic.source !== null && diagnostic.source !== undefined ? "source" : "none";
}

/** Focus the node at an instance path (the `related` links in the panel). */
export function navigateToPath(path: string | null): boolean {
  const store = useDocumentStore.getState();
  const nodeId = resolvePathToNode(store.doc, path);
  if (nodeId === null) {
    return false;
  }
  store.setSelection([nodeId], []);
  useDiagnosticsStore.getState().requestFocus(nodeId);
  return true;
}

function focusSource(source: DiagnosticSource): void {
  useDiagnosticsStore.getState().requestSourceFocus({
    ref: source.ref,
    line: source.range.line,
    col: source.range.col,
  });
  if (typeof window === "undefined") {
    return;
  }
  const detail: OpenSourceDetail = {
    kind: source.kind,
    ref: source.ref,
    line: source.range.line,
    col: source.range.col,
  };
  window.dispatchEvent(new CustomEvent<OpenSourceDetail>(OPEN_SOURCE_EVENT, { detail }));
}
