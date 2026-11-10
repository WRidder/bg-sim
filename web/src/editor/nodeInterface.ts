/**
 * The editor's view of a node's interface (plan 3.2 catalog declarations).
 *
 * A node's ports come from the catalog block, from a subsystem's exposed
 * ports, or from the junction kind. The canvas and the connection rules both
 * read this one shape, so what is drawn is exactly what is checked.
 */

import type { DomainName, OrientationDecl, ValueType } from "../contracts/catalog";
import type { ModelNode } from "../contracts/model";
import type { BlockInterface } from "../contracts/worker-rpc";
import { inlineInterfaceFor, hasInlineInterface } from "../code/inlineInterfaces";
import type { CatalogIndex } from "../library/catalogIndex";
import type { PortDescriptor } from "./connectionRules";
import {
  ANY_ORIENTATION,
  blockPortOrientation,
  type BondArrival,
  type PortOrientation,
} from "./portOrientation";

export interface PortSpec {
  name: string;
  kind: "power" | "input" | "output";
  /** Power ports have their declared domain; signal ports are dimensionless. */
  domain: DomainName;
  type: ValueType;
  size: number[];
  unit: string | null;
  /**
   * Declared reference frame, unqualified (D-MB5). Identity is face-scoped by the
   * worker (FIX-MB-6): faces compare as (instance path, name). Null is
   * frame-neutral: it unifies with any adjacent frame and never causes E007.
   */
  frame?: string | null;
  /**
   * Per-component unit overrides carried by a subsystem power port, angular
   * first. Absent for catalog ports, whose units come from the domain.
   */
  effortUnits?: readonly string[];
  flowUnits?: readonly string[];
  /**
   * The bond direction a power port declares (`@orientation`). Absent is `any`; a subsystem port
   * forwards the orientation of the internal port it exposes.
   */
  orientation?: PortOrientation;
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
  ports: { name: string; domain: DomainName; size: number[]; frame?: string | null }[];
  inputs: { name: string; type: ValueType; size: number[]; unit: string | null }[];
  outputs: { name: string; type: ValueType; size: number[]; unit: string | null }[];
  orientation?: readonly OrientationDecl[];
}): NodeInterface {
  const ports = portSpecs(block.ports, block.inputs, block.outputs, block.orientation);
  return {
    title: block.name,
    icon: block.icon,
    ports,
    isJunction: false,
    ref: block.ref,
    junction: null,
  };
}

function portSpecs(
  power: {
    name: string;
    domain: DomainName;
    size: number[];
    frame?: string | null;
  }[],
  inputs: { name: string; type: ValueType; size: number[]; unit: string | null }[],
  outputs: { name: string; type: ValueType; size: number[]; unit: string | null }[],
  orientation?: readonly OrientationDecl[],
): PortSpec[] {
  const ports: PortSpec[] = [];
  for (const port of power) {
    const declared = blockPortOrientation(orientation, port.name);
    ports.push({
      name: port.name,
      kind: "power",
      domain: port.domain,
      type: "Real",
      size: port.size,
      unit: null,
      frame: port.frame ?? null,
      ...(declared.kind === "any" ? {} : { orientation: declared }),
    });
  }
  for (const input of inputs) {
    ports.push({
      name: input.name,
      kind: "input",
      domain: "Generic",
      type: input.type,
      size: input.size,
      unit: input.unit,
      frame: null,
    });
  }
  for (const output of outputs) {
    ports.push({
      name: output.name,
      kind: "output",
      domain: "Generic",
      type: output.type,
      size: output.size,
      unit: output.unit,
      frame: null,
    });
  }
  return ports;
}

/**
 * The canvas view of a `block.check` interface (plan 7.7): an inline code node
 * gains and loses its ports as its source changes.
 */
export function interfaceFromBlockCheck(block: BlockInterface, title: string): NodeInterface {
  return {
    title,
    icon: INLINE_ICON,
    ports: portSpecs(block.ports, block.inputs, block.outputs, block.orientation),
    isJunction: false,
    ref: null,
    junction: null,
  };
}

type SubsystemBlock = Extract<ModelNode["block"], { subsystem: unknown }>["subsystem"];

/**
 * The orientation a subsystem power port forwards: that of the internal port it exposes, through nested
 * subsystems. A through pair keeps its relation across the boundary: the partner is the subsystem port
 * that exposes the other internal port, or, when the other internal port is bonded inside, the direction
 * of that bond (junctions have no orientation).
 */
function forwardedOrientation(
  sub: SubsystemBlock,
  port: { node: string; port: string },
  index: CatalogIndex,
): { orientation?: PortOrientation } {
  const inner = sub.diagram.nodes.find((entry) => entry.id === port.node);
  if (inner === undefined) {
    return {};
  }
  const innerPort = interfaceForNode(inner, index).ports.find((entry) => entry.name === port.port);
  const orientation = innerPort?.orientation ?? ANY_ORIENTATION;
  if (orientation.kind === "any") {
    return {};
  }
  if (orientation.kind !== "through") {
    return { orientation };
  }
  const partnerName = orientation.partner ?? null;
  const exposedAs =
    partnerName === null
      ? undefined
      : sub.ports.find(
          (entry) =>
            entry.kind === "power" && entry.node === port.node && entry.port === partnerName,
        );
  let fixed: BondArrival | null = orientation.partnerFixed ?? null;
  if (partnerName !== null) {
    for (const connection of sub.diagram.connections) {
      if (connection.kind !== "bond") {
        continue;
      }
      if (connection.to.node === port.node && (connection.to.port ?? null) === partnerName) {
        fixed = "arrives";
      } else if (connection.from.node === port.node && (connection.from.port ?? null) === partnerName) {
        fixed = "leaves";
      }
    }
  }
  return {
    orientation: { kind: "through", partner: exposedAs?.name ?? null, partnerFixed: fixed },
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
    const sub = node.block.subsystem;
    const ports: PortSpec[] = sub.ports.map((port) =>
      port.kind === "power"
        ? {
            name: port.name,
            kind: "power",
            domain: port.domain,
            type: "Real",
            size: port.size,
            unit: null,
            frame: port.frame ?? null,
            effortUnits: port.effortUnits,
            flowUnits: port.flowUnits,
            ...forwardedOrientation(sub, port, index),
          }
        : {
            name: port.name,
            kind: port.direction === "input" ? "input" : "output",
            domain: "Generic",
            type: port.type,
            size: port.size,
            unit: port.unit,
            frame: null,
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
  const inline = inlineInterfaceFor(node.id);
  if (inline !== null) {
    return inline;
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

/**
 * A port name that an endpoint of `node` no longer exposes, or null. An inline
 * node whose interface has not been checked yet is not reported: until the
 * first `block.check` its port list is unknown, not empty.
 */
export function missingPortFor(
  node: ModelNode,
  iface: NodeInterface,
  portName: string | null | undefined,
): string | null {
  if (portName === undefined || portName === null || portName.length === 0) {
    return null;
  }
  if (iface.isJunction) {
    return null;
  }
  if ("inline" in node.block && !hasInlineInterface(node.id)) {
    return null;
  }
  return iface.ports.some((port) => port.name === portName) ? null : portName;
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
      ...(port.orientation === undefined ? {} : { orientation: port.orientation }),
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
