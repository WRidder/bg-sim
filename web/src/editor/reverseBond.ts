/**
 * Reversing an existing bond (plan/PORT_ORIENTATION_PLAN.md O8, O14): whether it may be done and what to tell the user.
 */

import type { ModelConnection } from "../contracts/model";
import type { CatalogIndex } from "../library/catalogIndex";
import { descriptorForPort } from "./nodeInterface";
import { allowedRoles, whyNotRole, type DiagramView } from "./portOrientation";

export const REVERSE_JUNCTION_NOTE =
  "Reverses the reference direction of everything behind this bond: the sign of the relative flow or displacement it sets changes, and so do the results.";

export type ReverseCheck =
  | { ok: true; /** Set for a bond between a 0-junction and a 1-junction (O14). */ note: string | null }
  | { ok: false; reason: string };

function junctionKind(doc: DiagramView, nodeId: string): "0" | "1" | null {
  const node = doc.diagram.nodes.find((entry) => entry.id === nodeId);
  return node !== undefined && "junction" in node.block ? node.block.junction : null;
}

/**
 * May this bond be reversed? Reversing puts the old head at the tail and the reverse, so each end must
 * accept its new role. A fixed end refuses (the bond is already as the port wants it, or, for a bond
 * stored the wrong way round, the reversal that fixes it is allowed); a `through` pair refuses when
 * the pair's other bond already takes the role. A 0-1 junction bond stays free but carries a note that
 * says what the reversal does (O14); it is never described as harmless.
 */
export function checkReverse(
  doc: DiagramView,
  index: CatalogIndex,
  connection: ModelConnection,
): ReverseCheck {
  if (connection.kind !== "bond") {
    return { ok: false, reason: "Only a bond has a direction" };
  }
  const nodes = doc.diagram.nodes;
  const tail = descriptorForPort(nodes, index, connection.from.node, connection.from.port ?? null);
  const head = descriptorForPort(nodes, index, connection.to.node, connection.to.port ?? null);
  if (tail === null || head === null) {
    return { ok: true, note: null };
  }
  // After the reversal the old tail is the head and the old head is the tail.
  const tailRoles = allowedRoles(doc, tail, connection.id);
  const headRoles = allowedRoles(doc, head, connection.id);
  const reasons: string[] = [];
  if (!tailRoles.has("to")) {
    reasons.push(whyNotRole(doc, tail, connection.id));
  }
  if (!headRoles.has("from")) {
    reasons.push(whyNotRole(doc, head, connection.id));
  }
  if (reasons.length > 0) {
    return { ok: false, reason: reasons.join("; ") };
  }
  const a = junctionKind(doc, connection.from.node);
  const b = junctionKind(doc, connection.to.node);
  return { ok: true, note: a !== null && b !== null && a !== b ? REVERSE_JUNCTION_NOTE : null };
}

