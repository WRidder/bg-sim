/**
 * The Code tab request that opens a diagram node's source: an inline node as
 * `inline:<id>`, a library block by its ref. Junctions, subsystems and blocks the
 * catalog has no source for have none. Shared by the inspector's "Open source"
 * and the canvas context menu's "Show source".
 */

import type { OpenSourceDetail } from "../diagnostics/navigation";
import type { ModelNode } from "../contracts/model";
import type { CatalogIndex } from "../library/catalogIndex";
import { nodeRef } from "../state/modelFactory";
import { requestSource } from "./codeSession";

export function nodeSourceDetail(node: ModelNode, index: CatalogIndex | null): OpenSourceDetail | null {
  if ("inline" in node.block) {
    return { kind: "inline", ref: `inline:${node.id}`, line: 1, col: 1 };
  }
  const ref = nodeRef(node);
  const block = ref === null ? undefined : index?.blocksByRef.get(ref);
  if (block === undefined) {
    return null;
  }
  return { kind: block.ref.startsWith("stdlib:") ? "stdlib" : "project", ref: block.ref, line: 1, col: 1 };
}

/** Open the node's source in the Code tab and bring the tab to the front; false when it has none. */
export function openNodeSource(node: ModelNode, index: CatalogIndex | null): boolean {
  const detail = nodeSourceDetail(node, index);
  if (detail === null) {
    return false;
  }
  requestSource(detail, { reveal: true });
  return true;
}
