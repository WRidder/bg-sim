/**
 * The editor's view of a node's interface (plan 3.2 catalog declarations).
 *
 * A node's ports come from the catalog block, from a subsystem's exposed
 * ports, or from the junction kind. The canvas and the connection rules both
 * read this one shape, so what is drawn is exactly what is checked.
 */

import type { DomainName, ValueType } from "../contracts/catalog";
import type { ModelNode } from "../contracts/model";
import type { CatalogIndex } from "../library/catalogIndex";
import type { PortDescriptor } from "./connectionRules";

export interface PortSpec {
  name: string;
  kind: "power" | "input" | "output";
  /** Power ports have their declared domain; signal ports are dimensionless. */
  domain: DomainName;
  type: ValueType;
  size: number[];
  unit: string | null;
}

export interface NodeInterface {
  /** Human title: the block's name, or the junction kind. */
  title: string;
  icon: string;
  ports: PortSpec[];
  isJunction: boolean;
  /** Catalog ref, or null for junction/inline/subsystem nodes. */
  ref: string | null;
  /** Present for junction nodes. */
  junction: "0" | "1" | null;
}

export const INLINE_ICON = "inline-block";
export const SUBSYSTEM_ICON = "subsystem-block";
export const JUNCTION_ICON = "junction";

/** The interface of a library block. */
export function interfaceForBlock(block: {
  name: string;
  icon: string;
  ref: string;
  ports: { name: string; domain: DomainName; size: number[] }[];
  inputs: { name: string; type: ValueType; size: number[]; unit: string | null }[];
  outputs: { name: string; type: ValueType; size: number[]; unit: string | null }[];
}): NodeInterface {
  const ports: PortSpec[] = [];
  for (const port of block.ports) {
    ports.push({
      name: port.name,
      kind: "power",
      domain: port.domain,
      type: "Real",
      size: port.size,
      unit: null,
    });
  }
  for (const input of block.inputs) {
    ports.push({
      name: input.name,
      kind: "input",
      domain: "Generic",
      type: input.type,
      size: input.size,
      unit: input.unit,
    });
  }
  for (const output of block.outputs) {
    ports.push({
      name: output.name,
      kind: "output",
      domain: "Generic",
      type: output.type,
      size: output.size,
      unit: output.unit,
    });
  }
  return {
    title: block.name,
    icon: block.icon,
    ports,
    isJunction: false,
    ref: block.ref,
    junction: null,
  };
}

/** The interface of one document node; unknown refs get an empty interface. */
export function interfaceForNode(node: ModelNode, index: CatalogIndex): NodeInterface {
  if ("junction" in node.block) {
    return {
      title: `Junction ${node.block.junction}`,
      icon: JUNCTION_ICON,
      ports: [],
      isJunction: true,
      ref: null,
      junction: node.block.junction,
    };
  }
  if ("ref" in node.block) {
    const block = index.blocksByRef.get(node.block.ref);
    if (block === undefined) {
      return {
        title: node.block.ref,
        icon: INLINE_ICON,
        ports: [],
        isJunction: false,
        ref: node.block.ref,
        junction: null,
      };
    }
    return interfaceForBlock(block);
  }
  if ("subsystem" in node.block) {
    const ports: PortSpec[] = node.block.subsystem.ports.map((port) =>
      port.kind === "power"
        ? {
            name: port.name,
            kind: "power",
            domain: port.domain,
            type: "Real",
            size: port.size,
            unit: null,
          }
        : {
            name: port.name,
            kind: port.direction === "input" ? "input" : "output",
            domain: "Generic",
            type: port.type,
            size: port.size,
            unit: port.unit,
          },
    );
    return {
      title: "Subsystem",
      icon: SUBSYSTEM_ICON,
      ports,
      isJunction: false,
      ref: null,
      junction: null,
    };
  }
  return {
    title: "Inline block",
    icon: INLINE_ICON,
    ports: [],
    isJunction: false,
    ref: null,
    junction: null,
  };
}

/** The descriptor the connection rules compare for one node port. */
export function portDescriptor(
  node: ModelNode,
  iface: NodeInterface,
  portName: string | null,
): PortDescriptor | null {
  if (iface.isJunction) {
    return {
      nodeId: node.id,
      portName: null,
      isJunction: true,
      kind: "power",
      direction: null,
      domain: "Generic",
      type: null,
      size: [],
      unit: null,
    };
  }
  if (portName === null) {
    return null;
  }
  const port = iface.ports.find((entry) => entry.name === portName);
  if (port === undefined) {
    return null;
  }
  if (port.kind === "power") {
    return {
      nodeId: node.id,
      portName: port.name,
      isJunction: false,
      kind: "power",
      direction: null,
      domain: port.domain,
      type: null,
      size: port.size,
      unit: port.unit,
    };
  }
  return {
    nodeId: node.id,
    portName: port.name,
    isJunction: false,
    kind: "signal",
    direction: port.kind === "input" ? "input" : "output",
    domain: "Generic",
    type: port.type,
    size: port.size,
    unit: port.unit,
  };
}

/** Look up a node and one of its ports; null when either does not exist. */
export function descriptorForPort(
  nodes: readonly ModelNode[],
  index: CatalogIndex,
  nodeId: string | null,
  portName: string | null,
): PortDescriptor | null {
  if (nodeId === null) {
    return null;
  }
  const node = nodes.find((entry) => entry.id === nodeId);
  if (node === undefined) {
    return null;
  }
  return portDescriptor(node, interfaceForNode(node, index), portName);
}
