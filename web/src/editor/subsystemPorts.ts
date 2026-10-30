/**
 * Exposed subsystem ports, edited from inside the subsystem.
 *
 * A subsystem port (plan 3.3 `subsystemPort`) maps an outside port name to an
 * internal `(node, port)`. The flattener resolves an outside connection on
 * that name to the internal port itself (`_bind_boundary!`), so an exposed
 * port behaves like one more connection on the internal port:
 *
 * * a signal input takes its value from outside, so it may not already have a
 *   source inside (one source per input);
 * * a power port takes at most one bond, so one that already has a bond inside
 *   cannot be exposed; wires join into one node, so a wired port can;
 * * one internal port is exposed under one name.
 *
 * Everything here is pure: the document store calls it and commits the result
 * as one undo entry. The port shapes are the ones grouping into a subsystem
 * creates (`subsystemGroup.ts` uses the same builders).
 */

import type { DomainName } from "../contracts/catalog";
import type {
  Model,
  ModelBlockSubsystem,
  ModelConnection,
  ModelDiagram,
  ModelNode,
  ModelSubsystemPort,
  ModelSubsystemPowerPort,
  ModelSubsystemSignalPort,
} from "../contracts/model";
import type { CatalogIndex } from "../library/catalogIndex";
import { uniqueName } from "../state/ids";
import { analyseDiagram } from "./connectionAnalysis";
import type { PortDescriptor } from "./connectionRules";
import { activeDiagram } from "./subsystemPath";

/** The schema's port name pattern (`subsystemPort.name`). */
export const SUBSYSTEM_PORT_NAME_PATTERN = /^[A-Za-z_][A-Za-z0-9_]*$/;

/** What a terminal on the inner canvas stands for. */
export type TerminalKind = "input" | "output" | "power";

/** The `port` a subsystem port stores for a junction face (the schema requires a string). */
export const JUNCTION_PORT = "junction";

export function terminalKindOf(port: ModelSubsystemPort): TerminalKind {
  return port.kind === "power" ? "power" : port.direction;
}

export function terminalKindOfDescriptor(descriptor: PortDescriptor): TerminalKind {
  return descriptor.kind === "power" ? "power" : descriptor.direction === "output" ? "output" : "input";
}

/** `Motor1_shaft` style: identifier-safe, with a leading `_` if needed. */
export function portNameFor(nodeName: string, portName: string | null): string {
  const raw = portName === null || portName.length === 0 ? nodeName : `${nodeName}_${portName}`;
  const cleaned = raw.replace(/[^A-Za-z0-9_]/g, "_");
  return /^[A-Za-z_]/.test(cleaned) ? cleaned : `_${cleaned}`;
}

/** The internal port name a subsystem port stores for an endpoint (junctions have none). */
export function internalPortName(portName: string | null | undefined): string {
  return portName === null || portName === undefined || portName.length === 0
    ? JUNCTION_PORT
    : portName;
}

/**
 * A subsystem signal port. The internal descriptor wins; the external one is
 * the fallback grouping has when an inline block's interface is not checked yet.
 */
export function signalPortFor(input: {
  name: string;
  direction: "input" | "output";
  internal: PortDescriptor | null;
  external?: PortDescriptor | null;
  node: string;
  port: string | null;
}): ModelSubsystemSignalPort {
  const { internal } = input;
  const external = input.external ?? null;
  return {
    name: input.name,
    kind: "signal",
    direction: input.direction,
    type: internal?.type ?? external?.type ?? "Real",
    size: [...(internal?.size ?? external?.size ?? [])],
    unit: internal?.unit ?? external?.unit ?? null,
    node: input.node,
    port: internalPortName(input.port),
  };
}

/** The domain a power port gets: the adopted one, else a concrete end, else Generic. */
export function powerDomainFor(
  adopted: DomainName | undefined,
  internal: PortDescriptor | null,
  external: PortDescriptor | null = null,
): DomainName {
  const concrete =
    internal !== null && internal.domain !== "Generic"
      ? internal.domain
      : external !== null && external.domain !== "Generic"
        ? external.domain
        : undefined;
  return adopted ?? concrete ?? "Generic";
}

/**
 * A subsystem power port. Its shape is one axis (catalog `domain.size`): [1]
 * scalar, [3] Planar, [6] Spatial; the descriptor size is the block's array
 * shape, which is empty for a scalar port.
 */
export function powerPortFor(input: {
  name: string;
  domain: DomainName;
  index: CatalogIndex;
  node: string;
  port: string | null;
}): ModelSubsystemPowerPort {
  const portSize = input.index.domains.get(input.domain)?.size ?? 1;
  return {
    name: input.name,
    kind: "power",
    domain: input.domain,
    size: [portSize],
    node: input.node,
    // A junction has no named port; the worker ignores this field for a
    // junction face, and the schema still requires a string.
    port: internalPortName(input.port),
  };
}

/** Why `name` cannot name a subsystem port (other than `current`), or null. */
export function subsystemPortNameIssue(
  ports: readonly ModelSubsystemPort[],
  current: string | null,
  name: string,
): string | null {
  if (name.length === 0) {
    return "Enter a port name.";
  }
  if (!SUBSYSTEM_PORT_NAME_PATTERN.test(name)) {
    return "Port names start with a letter or underscore and use only letters, digits and underscores.";
  }
  if (ports.some((port) => port.name === name && port.name !== current)) {
    return `The subsystem already has a port named "${name}".`;
  }
  return null;
}

/** The subsystem port that already exposes `(node, port)`, if any. */
export function exposingPort(
  ports: readonly ModelSubsystemPort[],
  nodeId: string,
  portName: string | null,
): ModelSubsystemPort | undefined {
  const internal = internalPortName(portName);
  return ports.find((port) => port.node === nodeId && port.port === internal);
}

function endpointIs(
  endpoint: { node: string; port?: string },
  nodeId: string,
  portName: string | null,
): boolean {
  return endpoint.node === nodeId && (endpoint.port ?? null) === portName;
}

const KIND_LABEL: Record<TerminalKind, string> = {
  input: "a signal input",
  output: "a signal output",
  power: "a power port",
};

/** A short `Node.port` (or `Node` for a junction) for messages and labels. */
export function endpointLabel(nodes: readonly ModelNode[], nodeId: string, portName: string | null | undefined): string {
  const name = nodes.find((node) => node.id === nodeId)?.name ?? nodeId;
  return portName === null || portName === undefined || portName.length === 0 || portName === JUNCTION_PORT
    ? name
    : `${name}.${portName}`;
}

/**
 * Why the internal port `descriptor` cannot be exposed on `diagram` (the
 * subsystem's nested diagram), or null when it can. `wanted` is the kind of
 * the "+ input" / "+ output" / "+ power" target, when the user picked one.
 */
export function exposeIssue(
  diagram: ModelDiagram,
  ports: readonly ModelSubsystemPort[],
  descriptor: PortDescriptor,
  wanted?: TerminalKind,
): string | null {
  const label = endpointLabel(diagram.nodes, descriptor.nodeId, descriptor.portName);
  const kind = terminalKindOfDescriptor(descriptor);
  if (wanted !== undefined && wanted !== kind) {
    return `+ ${wanted} exposes ${KIND_LABEL[wanted]}; ${label} is ${KIND_LABEL[kind]}.`;
  }
  const already = exposingPort(ports, descriptor.nodeId, descriptor.portName);
  if (already !== undefined) {
    return `${label} is already exposed as ${already.name}.`;
  }
  if (descriptor.kind === "signal" && descriptor.direction === "input") {
    const source = diagram.connections.find(
      (connection) =>
        connection.kind === "signal" &&
        endpointIs(connection.to, descriptor.nodeId, descriptor.portName),
    );
    if (source !== undefined) {
      return `${label} already has a source inside the subsystem (${endpointLabel(diagram.nodes, source.from.node, source.from.port)}); an exposed input is driven from outside. Remove that connection first.`;
    }
  }
  if (descriptor.kind === "power" && !descriptor.isJunction) {
    const bond = diagram.connections.find(
      (connection) =>
        connection.kind === "bond" &&
        (endpointIs(connection.from, descriptor.nodeId, descriptor.portName) ||
          endpointIs(connection.to, descriptor.nodeId, descriptor.portName)),
    );
    if (bond !== undefined) {
      return `${label} already has a bond inside the subsystem; a power port takes one bond. Expose a junction on that bond instead.`;
    }
  }
  return null;
}

/** The proposed name for exposing `(node, port)`: the port name if free, else `Node_port`. */
export function proposePortName(
  ports: readonly ModelSubsystemPort[],
  nodeName: string,
  portName: string | null,
): string {
  const taken = ports.map((port) => port.name);
  const plain = portName === null || portName.length === 0 ? null : portName;
  if (plain !== null && SUBSYSTEM_PORT_NAME_PATTERN.test(plain) && !taken.includes(plain)) {
    return plain;
  }
  return uniqueName(portNameFor(nodeName, plain), taken);
}

/**
 * The new subsystem port for exposing `descriptor` from `inner` (the nested
 * diagram as a model view), or the refusal.
 */
export function exposedPortFor(input: {
  inner: Model;
  ports: readonly ModelSubsystemPort[];
  descriptor: PortDescriptor;
  index: CatalogIndex;
  wanted?: TerminalKind;
}): { ok: true; port: ModelSubsystemPort } | { ok: false; reason: string } {
  const { inner, ports, descriptor, index } = input;
  const issue = exposeIssue(inner.diagram, ports, descriptor, input.wanted);
  if (issue !== null) {
    return { ok: false, reason: issue };
  }
  const node = inner.diagram.nodes.find((entry) => entry.id === descriptor.nodeId);
  if (node === undefined) {
    return { ok: false, reason: "That block is no longer in the diagram." };
  }
  const name = proposePortName(ports, node.name, descriptor.portName);
  if (descriptor.kind === "signal") {
    return {
      ok: true,
      port: signalPortFor({
        name,
        direction: descriptor.direction === "output" ? "output" : "input",
        internal: descriptor,
        node: node.id,
        port: descriptor.portName,
      }),
    };
  }
  const adopted = analyseDiagram(inner, index).portDomains.get(
    `${node.id}\u0000${descriptor.portName ?? ""}`,
  );
  return {
    ok: true,
    port: powerPortFor({
      name,
      domain: powerDomainFor(adopted, descriptor),
      index,
      node: node.id,
      port: descriptor.portName,
    }),
  };
}

/** The parent-diagram connections on port `portName` of subsystem node `nodeId`. */
export function outsideConnections(
  parent: ModelDiagram,
  nodeId: string,
  portName: string,
): ModelConnection[] {
  return parent.connections.filter(
    (connection) =>
      (connection.from.node === nodeId && connection.from.port === portName) ||
      (connection.to.node === nodeId && connection.to.port === portName),
  );
}

/** A node whose block is a subsystem. */
export type SubsystemNode = ModelNode & { block: ModelBlockSubsystem };

export function isSubsystemNode(node: ModelNode): node is SubsystemNode {
  return "subsystem" in node.block;
}

/** The subsystem node a path ends in, with the diagram it sits in. */
export function subsystemAtPath(
  doc: Pick<Model, "diagram">,
  path: readonly string[],
): { node: SubsystemNode; parent: ModelDiagram } | null {
  if (path.length === 0) {
    return null;
  }
  const parent = activeDiagram(doc, path.slice(0, -1));
  const id = path[path.length - 1];
  const node = parent?.nodes.find((entry) => entry.id === id);
  if (parent === null || node === undefined || !isSubsystemNode(node)) {
    return null;
  }
  return { node, parent };
}

/**
 * The port one level further up that exposes port `portName` of this
 * subsystem (the subsystem is itself inside a subsystem), if any.
 */
export function exposedOneLevelUp(
  doc: Pick<Model, "diagram">,
  path: readonly string[],
  portName: string,
): { owner: string; port: ModelSubsystemPort } | null {
  if (path.length < 2) {
    return null;
  }
  const outer = subsystemAtPath(doc, path.slice(0, -1));
  const id = path[path.length - 1];
  if (outer === null || id === undefined) {
    return null;
  }
  const port = outer.node.block.subsystem.ports.find(
    (entry) => entry.node === id && entry.port === portName,
  );
  return port === undefined ? null : { owner: outer.node.name, port };
}
