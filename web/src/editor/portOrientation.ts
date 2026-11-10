/**
 * Port orientation in the editor (plan/PORT_ORIENTATION_PLAN.md O2, O4, O8, O13, O14).
 *
 * A power port of a block declares how a bond may meet it (`@orientation`, carried by the catalog as
 * `orientation: [{ ports, kind }]`):
 *
 * * `in`: the bond ends here, so the port is at the bond's `to` (the half arrow points into the block);
 * * `out`: the bond starts here, so the port is at the bond's `from`;
 * * `through`: a pair; exactly one of the pair's two bonds arrives at the block and the other
 *   leaves, which one is free;
 * * `any`: no constraint (default, junctions, iconic ports).
 *
 * Everything here is pure. The compiler (E114) is the authority; this module only keeps the editor from
 * drawing a bond the compiler would reject, and says why it refuses. A subsystem port forwards the
 * orientation of the internal port it exposes (`nodeInterface.ts` builds that, through nested subsystems).
 * Existing bonds are never rewritten: paste, duplicate and import keep their stored direction.
 */

import type { OrientationDecl } from "../contracts/catalog";
import type { ModelConnection, ModelNode } from "../contracts/model";
import type { PortDescriptor } from "./connectionRules";

/** What the rules read of a document: the nodes and bonds of one diagram. */
export interface DiagramView {
  diagram: { nodes: readonly ModelNode[]; connections: readonly ModelConnection[] };
}

export type OrientationKind = "in" | "out" | "through" | "any";

/** Where a bond meets a block: it arrives at it (the port is the bond's `to`) or leaves it. */
export type BondArrival = "arrives" | "leaves";

/** The role of a port within a bond: the tail (`from`) or the head (`to`). */
export type BondRole = "from" | "to";

export interface PortOrientation {
  kind: OrientationKind;
  /**
   * `through` only: the other port of the pair, as a port of the same node (for a subsystem port: the
   * subsystem port that exposes the other internal port, when there is one).
   */
  partner?: string | null;
  /**
   * `through` only: the direction of a bond that is already fixed behind the node (inside a subsystem
   * that bonds the partner internally), when the partner is not a port of the node.
   */
  partnerFixed?: BondArrival | null;
}

export const ANY_ORIENTATION: PortOrientation = { kind: "any" };

/** The orientation a catalog block (or a `block.check` interface) declares for one port. */
export function blockPortOrientation(
  declarations: readonly OrientationDecl[] | undefined,
  port: string,
): PortOrientation {
  for (const entry of declarations ?? []) {
    if (!entry.ports.includes(port)) {
      continue;
    }
    if (entry.kind === "through") {
      const partner = entry.ports.find((name) => name !== port) ?? null;
      return { kind: "through", partner, partnerFixed: null };
    }
    return { kind: entry.kind };
  }
  return ANY_ORIENTATION;
}

/** The bond direction a fixed port needs, in words (`in`: "a bond must end there"). */
export function describeOrientation(orientation: PortOrientation): string {
  switch (orientation.kind) {
    case "in":
      return "in: a bond must end here";
    case "out":
      return "out: a bond must start here";
    case "through":
      return orientation.partner === null || orientation.partner === undefined
        ? "through: one bond arrives, the other leaves"
        : `through with ${orientation.partner}: one of the two bonds arrives, the other leaves`;
    default:
      return "any";
  }
}

/** A short label for the port tooltip and the inspector list. */
export function orientationLabel(orientation: PortOrientation): string {
  return orientation.kind === "through" && orientation.partner
    ? `through ${orientation.partner}`
    : orientation.kind;
}

// ---------------------------------------------------------------- the rules

type EndpointLike = { node: string; port?: string | null };

function sameEnd(endpoint: EndpointLike, nodeId: string, portName: string | null): boolean {
  return endpoint.node === nodeId && (endpoint.port ?? null) === portName;
}

/** How the bond at a port meets its block, ignoring one bond; null when the port has no bond. */
function bondArrivalAt(
  doc: DiagramView,
  nodeId: string,
  portName: string,
  ignoreId: string | null,
): BondArrival | null {
  for (const connection of doc.diagram.connections) {
    if (connection.kind !== "bond" || connection.id === ignoreId) {
      continue;
    }
    if (sameEnd(connection.to, nodeId, portName)) {
      return "arrives";
    }
    if (sameEnd(connection.from, nodeId, portName)) {
      return "leaves";
    }
  }
  return null;
}

function orientationOf(port: PortDescriptor): PortOrientation {
  return port.isJunction || port.kind !== "power" ? ANY_ORIENTATION : (port.orientation ?? ANY_ORIENTATION);
}

/** The arrival of a through port's partner: the bond in the document first, then one fixed behind the node. */
function partnerArrival(
  doc: DiagramView,
  port: PortDescriptor,
  ignoreId: string | null,
): BondArrival | null {
  const orientation = orientationOf(port);
  if (orientation.kind !== "through") {
    return null;
  }
  if (orientation.partner !== null && orientation.partner !== undefined) {
    const found = bondArrivalAt(doc, port.nodeId, orientation.partner, ignoreId);
    if (found !== null) {
      return found;
    }
  }
  return orientation.partnerFixed ?? null;
}

/** The roles a port can take in a new bond, given the bonds already in the document. */
export function allowedRoles(
  doc: DiagramView,
  port: PortDescriptor,
  ignoreId: string | null = null,
): ReadonlySet<BondRole> {
  const orientation = orientationOf(port);
  switch (orientation.kind) {
    case "in":
      return new Set<BondRole>(["to"]);
    case "out":
      return new Set<BondRole>(["from"]);
    case "through": {
      const other = partnerArrival(doc, port, ignoreId);
      // The other bond arrives, so this one leaves (this port is the tail), and the reverse.
      return other === "arrives"
        ? new Set<BondRole>(["from"])
        : other === "leaves"
          ? new Set<BondRole>(["to"])
          : new Set<BondRole>(["from", "to"]);
    }
    default:
      return new Set<BondRole>(["from", "to"]);
  }
}

function portName(doc: DiagramView, port: PortDescriptor): string {
  const node = doc.diagram.nodes.find((entry) => entry.id === port.nodeId);
  const name = node?.name ?? port.nodeId;
  return port.portName === null ? name : `${name}.${port.portName}`;
}

/** Why `port` cannot take the role it was refused, in the sentence the canvas shows. */
export function whyNotRole(
  doc: DiagramView,
  port: PortDescriptor,
  ignoreId: string | null = null,
): string {
  const orientation = orientationOf(port);
  const name = portName(doc, port);
  if (orientation.kind === "in") {
    return `the port \`${name}\` is declared \`in\`: a bond must end there`;
  }
  if (orientation.kind === "out") {
    return `the port \`${name}\` is declared \`out\`: a bond must start there`;
  }
  if (orientation.kind === "through") {
    const other = partnerArrival(doc, port, ignoreId);
    const partner = orientation.partner ?? "its pair";
    return other === "arrives"
      ? `the port \`${name}\` is paired with \`${partner}\`, whose bond arrives at the block: a bond here must start there`
      : `the port \`${name}\` is paired with \`${partner}\`, whose bond leaves the block: a bond here must end there`;
  }
  return `the port \`${name}\` takes either direction`;
}

export type OrientResult =
  | { ok: true; from: PortDescriptor; to: PortDescriptor }
  | { ok: false; reason: string };

/**
 * Orient a proposed bond between `a` and `b`, whichever end the user started at. The order of `a` and
 * `b` only breaks a tie: when both directions are allowed, `a` is the tail.
 */
export function orientBond(
  doc: DiagramView,
  a: PortDescriptor,
  b: PortDescriptor,
  ignoreId: string | null = null,
): OrientResult {
  const aRoles = allowedRoles(doc, a, ignoreId);
  const bRoles = allowedRoles(doc, b, ignoreId);
  if (aRoles.has("from") && bRoles.has("to")) {
    return { ok: true, from: a, to: b };
  }
  if (bRoles.has("from") && aRoles.has("to")) {
    return { ok: true, from: b, to: a };
  }
  const kindA = orientationOf(a).kind;
  const kindB = orientationOf(b).kind;
  if ((kindA === "in" || kindA === "out") && kindA === kindB) {
    return {
      ok: false,
      reason: `\`${portName(doc, a)}\` and \`${portName(doc, b)}\` are both declared \`${kindA}\`: put a junction in between`,
    };
  }
  const reasons: string[] = [];
  for (const [port, roles] of [
    [a, aRoles],
    [b, bRoles],
  ] as const) {
    if (roles.size < 2) {
      reasons.push(whyNotRole(doc, port, ignoreId));
    }
  }
  return {
    ok: false,
    reason: `No direction fits both ports (${reasons.join("; ")}): put a junction in between`,
  };
}
