/**
 * Quick-connect target resolution.
 *
 * Ctrl-dragging from an element body to another element body should just work:
 * when the pointer is not over a specific port, pick the first compatible port
 * on the target in declaration order. Signal sources look for an available
 * input; power sources look for an available power port. An explicit drop on a
 * port still wins.
 */

import type { Model } from "../contracts/model";
import type { CatalogIndex } from "../library/catalogIndex";
import { checkConnection, type PortDescriptor } from "./connectionRules";
import { descriptorForPort, interfaceForNode } from "./nodeInterface";

export function firstCompatiblePort(
  doc: Model,
  index: CatalogIndex,
  nodeId: string,
  origin: PortDescriptor,
): PortDescriptor | null {
  const node = doc.diagram.nodes.find((entry) => entry.id === nodeId);
  if (node === undefined) {
    return null;
  }
  if ("junction" in node.block) {
    return descriptorForPort(doc.diagram.nodes, index, nodeId, null);
  }
  const iface = interfaceForNode(node, index);
  const wanted = origin.kind === "signal" ? "input" : "power";
  for (const port of iface.ports) {
    if (port.kind !== wanted) {
      continue;
    }
    const candidate = descriptorForPort(
      doc.diagram.nodes,
      index,
      nodeId,
      port.name,
    );
    if (candidate !== null && checkConnection(doc, origin, candidate).ok) {
      return candidate;
    }
  }
  return null;
}

/** Why an automatic drop found no target, for the canvas tooltip. */
export function noAutoTargetMessage(origin: PortDescriptor): string {
  return origin.kind === "signal"
    ? "This block has no available compatible input port"
    : "This block has no available compatible power port";
}
