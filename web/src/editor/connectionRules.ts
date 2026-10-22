/**
 * Client-side connection compatibility: the TypeScript port of plan sections
 * 5.5 (connection semantics) and 5.6 (domain adoption).
 *
 * The rules cover the four things the editor can decide before the backend
 * checks the model again (E102):
 *
 * 1. **kind** — a power port never joins a signal port;
 * 2. **direction and single source** — a signal runs from one output to an
 *    input, and an input has exactly one source;
 * 3. **domain** — concrete power domains must match; a Generic port adopts the
 *    concrete domain through a bond;
 * 4. **type and size** — signal types and vector sizes must match.
 *
 * Every refusal carries the exact sentence the canvas shows in its tooltip.
 * The message texts are exported so the tests and the UI cannot drift apart.
 */

import type { DomainName, ValueType } from "../contracts/catalog";
import type { ConnectionKind, Model } from "../contracts/model";

export type PortKind = "power" | "signal";
export type SignalDirection = "input" | "output";

/** Everything the rules (and the port glyph) need to know about one port. */
export interface PortDescriptor {
  nodeId: string;
  /**
   * Port/input/output name, or null for a junction (plan 3.3 omits the port
   * field on junction endpoints).
   */
  portName: string | null;
  isJunction: boolean;
  kind: PortKind;
  direction: SignalDirection | null;
  domain: DomainName;
  type: ValueType | null;
  size: number[];
  unit: string | null;
}

export type ConnectionCheck =
  | {
      ok: true;
      kind: ConnectionKind;
      /** Host/source side after normalisation (signal: the output). */
      from: PortDescriptor;
      /** Target side after normalisation (signal: the input). */
      to: PortDescriptor;
      /** The domain the connection uses; Generic for a dimensionless bond. */
      domain: DomainName;
    }
  | { ok: false; reason: string };

const DOMAIN_LETTER: Record<DomainName, string> = {
  Electrical: "E",
  Translation: "T",
  Rotation: "R",
  Hydraulic: "H",
  Generic: "G",
};

export function domainLetter(domain: DomainName): string {
  return DOMAIN_LETTER[domain] ?? "G";
}

export function portKey(port: Pick<PortDescriptor, "nodeId" | "portName">): string {
  return `${port.nodeId}\u0000${port.portName ?? ""}`;
}

/** The message bundle; exact strings are part of the editor's contract. */
export const CONNECTION_MESSAGES = {
  self: "A block cannot connect to itself",
  selfJunction: "A junction cannot connect to itself",
  kind: "Power port cannot connect to a signal port; use a sensor or a source",
  direction: "Signal connections must run from an output to an input",
  type: (from: ValueType, to: ValueType): string =>
    `${from} cannot connect to ${to}; insert a Type conversion`,
  size: (from: string, to: string): string =>
    `${from} cannot connect to ${to}; insert a Reshape`,
  powerSize: (from: string, to: string): string =>
    `${from} power port cannot connect to ${to} power port; use matching sizes`,
  source: (name: string): string => `Input ${name} already has a source`,
  duplicate: "These ports are already connected",
  bond: (name: string): string => `Port ${name} already has a bond`,
  converter: (from: DomainName, to: DomainName): string =>
    `${from} port cannot connect to ${to}; use a converter (DC motor, EM converter)`,
  converterOther: (from: DomainName, to: DomainName): string =>
    `${from} port cannot connect to ${to}; use a converter block`,
} as const;

/** `Scalar`, `Vec{3}` or `Mat{2x3}` for a declaration's size. */
export function formatSize(size: readonly number[]): string {
  if (size.length === 0) {
    return "Scalar";
  }
  if (size.length === 1) {
    return `Vec{${size[0]}}`;
  }
  return `Mat{${size.join("x")}}`;
}

function sizeKey(size: readonly number[]): string {
  return size.length === 0 ? "scalar" : size.join("x");
}

function endpointsEqual(
  endpoint: { node: string; port?: string },
  nodeId: string,
  portName: string | null,
): boolean {
  return endpoint.node === nodeId && (endpoint.port ?? null) === portName;
}

function touches(connection: Model["diagram"]["connections"][number], port: PortDescriptor): boolean {
  return (
    endpointsEqual(connection.from, port.nodeId, port.portName) ||
    endpointsEqual(connection.to, port.nodeId, port.portName)
  );
}

function alreadyConnected(
  connections: Model["diagram"]["connections"],
  a: PortDescriptor,
  b: PortDescriptor,
): boolean {
  return connections.some(
    (connection) =>
      (endpointsEqual(connection.from, a.nodeId, a.portName) &&
        endpointsEqual(connection.to, b.nodeId, b.portName)) ||
      (endpointsEqual(connection.from, b.nodeId, b.portName) &&
        endpointsEqual(connection.to, a.nodeId, a.portName)),
  );
}

function sourceCount(
  connections: Model["diagram"]["connections"],
  input: PortDescriptor,
): number {
  return connections.filter(
    (connection) =>
      connection.kind === "signal" &&
      endpointsEqual(connection.to, input.nodeId, input.portName),
  ).length;
}

function bondAt(
  connections: Model["diagram"]["connections"],
  port: PortDescriptor,
): boolean {
  return connections.some(
    (connection) => connection.kind === "bond" && touches(connection, port),
  );
}

function isConverterPair(a: DomainName, b: DomainName): boolean {
  return (
    (a === "Electrical" && b === "Rotation") || (a === "Rotation" && b === "Electrical")
  );
}

/**
 * The kind a connection between two power ports gets (plan 5.5): a bond when
 * either end is Generic or a junction, otherwise a wire node. Returns null for
 * a power/signal pair.
 */
export function connectionKindFor(a: PortDescriptor, b: PortDescriptor): ConnectionKind | null {
  if (a.kind !== b.kind) {
    return null;
  }
  if (a.kind === "signal") {
    return "signal";
  }
  if (a.isJunction || b.isJunction || a.domain === "Generic" || b.domain === "Generic") {
    return "bond";
  }
  return "wire";
}

/**
 * Decide whether `a` may connect to `b`, and which connection kind the pair
 * produces. The order of the checks is the order the user sees; each refusal
 * is actionable on its own.
 */
export function checkConnection(doc: Model, a: PortDescriptor, b: PortDescriptor): ConnectionCheck {
  const connections = doc.diagram.connections;

  if (a.nodeId === b.nodeId) {
    return {
      ok: false,
      reason:
        a.isJunction || b.isJunction
          ? CONNECTION_MESSAGES.selfJunction
          : CONNECTION_MESSAGES.self,
    };
  }

  if (a.kind !== b.kind) {
    return { ok: false, reason: CONNECTION_MESSAGES.kind };
  }

  if (a.kind === "signal") {
    if (a.direction === null || b.direction === null || a.direction === b.direction) {
      return { ok: false, reason: CONNECTION_MESSAGES.direction };
    }
    const from = a.direction === "output" ? a : b;
    const to = a.direction === "output" ? b : a;

    // The source rule comes before the type rule: two wires into one input is
    // the thing the user can see and fix first.
    if (sourceCount(connections, to) > 0) {
      return { ok: false, reason: CONNECTION_MESSAGES.source(to.portName ?? "?") };
    }

    if (from.type !== null && to.type !== null && from.type !== to.type) {
      return { ok: false, reason: CONNECTION_MESSAGES.type(from.type, to.type) };
    }

    if (sizeKey(from.size) !== sizeKey(to.size)) {
      return {
        ok: false,
        reason: CONNECTION_MESSAGES.size(formatSize(from.size), formatSize(to.size)),
      };
    }

    return { ok: true, kind: "signal", from, to, domain: "Generic" };
  }

  const kind = connectionKindFor(a, b);
  if (kind === null) {
    return { ok: false, reason: CONNECTION_MESSAGES.kind };
  }

  if (alreadyConnected(connections, a, b)) {
    return { ok: false, reason: CONNECTION_MESSAGES.duplicate };
  }

  const bothConcrete = a.domain !== "Generic" && b.domain !== "Generic";
  if (bothConcrete && a.domain !== b.domain) {
    return {
      ok: false,
      reason: isConverterPair(a.domain, b.domain)
        ? CONNECTION_MESSAGES.converter(a.domain, b.domain)
        : CONNECTION_MESSAGES.converterOther(a.domain, b.domain),
    };
  }

  if (sizeKey(a.size) !== sizeKey(b.size)) {
    return {
      ok: false,
      reason: CONNECTION_MESSAGES.powerSize(formatSize(a.size), formatSize(b.size)),
    };
  }

  for (const port of [a, b]) {
    if (!port.isJunction && bondAt(connections, port)) {
      return {
        ok: false,
        reason: CONNECTION_MESSAGES.bond(port.portName ?? "?"),
      };
    }
  }

  const domain: DomainName =
    a.domain === "Generic" ? b.domain : b.domain === "Generic" ? a.domain : a.domain;
  return { ok: true, kind, from: a, to: b, domain };
}

/** A one-line port description for tooltips and the inspector. */
export function describePort(port: PortDescriptor): string {
  if (port.isJunction) {
    return "junction";
  }
  if (port.kind === "signal") {
    return `${port.direction ?? "signal"} ${port.portName} (${port.type ?? "?"}${port.size.length > 0 ? `, ${formatSize(port.size)}` : ""})`;
  }
  return `power ${port.portName} (${port.domain}${port.size.length > 0 ? `, ${formatSize(port.size)}` : ""})`;
}
