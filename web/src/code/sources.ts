/**
 * What the Code tab has open (plan 7.7).
 *
 * There are two kinds of source: an inline block's text, which lives in the
 * model document, and a library block's source, which lives in `stdlib/` or in
 * the project library. Targets are resolved once from the `bgsim:open-source`
 * detail (kind + ref + line) so the editor and the banner do not have to
 * understand catalog refs, instance paths and `inline:<id>` prefixes.
 */

import type { SourceKind } from "../contracts/diagnostic";
import type { Model, ModelNode } from "../contracts/model";
import type { CatalogIndex } from "../library/catalogIndex";
import { collectNodePaths } from "../diagnostics/navigation";

export interface OpenSourceDetail {
  kind: SourceKind;
  ref: string;
  line: number;
  col: number;
}

export type LibrarySourceKind = "stdlib" | "project";

export type CodeTarget =
  | {
      kind: "inline";
      nodeId: string;
      ref: string;
      line: number;
      col: number;
    }
  | {
      kind: "library";
      sourceKind: LibrarySourceKind;
      blockRef: string;
      name: string;
      path: string;
      line: number;
      col: number;
      /** Source used when the catalog does not know the ref yet (after a copy). */
      seed?: string;
    };

/** The inline node a ref names: an id, `inline:<id>`, a path or a name. */
export function resolveInlineNode(
  doc: Model | null,
  ref: string,
): ModelNode | null {
  if (doc === null) {
    return null;
  }
  const inline = doc.diagram.nodes.filter((node) => "inline" in node.block);
  if (inline.length === 0) {
    return null;
  }
  const trimmed = ref.startsWith("inline:") ? ref.slice("inline:".length) : ref;
  const byId = inline.find((node) => node.id === trimmed || node.id === ref);
  if (byId !== undefined) {
    return byId;
  }
  const { paths } = collectNodePaths(doc);
  for (const [path, id] of paths) {
    if (path === trimmed || path.endsWith(`/${trimmed}`)) {
      const node = inline.find((entry) => entry.id === id);
      if (node !== undefined) {
        return node;
      }
    }
  }
  return inline.find((node) => node.name === trimmed) ?? null;
}

function validPosition(line: number, col: number): { line: number; col: number } {
  return {
    line: Number.isFinite(line) && line >= 1 ? Math.trunc(line) : 1,
    col: Number.isFinite(col) && col >= 1 ? Math.trunc(col) : 1,
  };
}

/**
 * Resolve an `open source` request. Null means the document or the catalog
 * has not loaded yet, or the ref does not exist; the caller turns that into a
 * message rather than opening the wrong thing.
 */
export function resolveOpenDetail(
  detail: OpenSourceDetail,
  doc: Model | null,
  index: CatalogIndex | null,
): CodeTarget | null {
  const position = validPosition(detail.line, detail.col);
  if (detail.kind === "inline") {
    const node = resolveInlineNode(doc, detail.ref);
    if (node === null) {
      return null;
    }
    return { kind: "inline", nodeId: node.id, ref: `inline:${node.id}`, ...position };
  }

  if (index === null) {
    return null;
  }
  const direct = index.blocksByRef.get(detail.ref);
  const block =
    direct ??
    index.blocks.find((entry) => entry.path === detail.ref) ??
    index.blocks.find((entry) => entry.name === detail.ref) ??
    index.blocks.find((entry) => entry.path.endsWith(`/${detail.ref}`));
  if (block === undefined) {
    return null;
  }
  return {
    kind: "library",
    sourceKind: block.ref.startsWith("project:") ? "project" : "stdlib",
    blockRef: block.ref,
    name: block.name,
    path: block.path,
    ...position,
  };
}

