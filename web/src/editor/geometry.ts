/**
 * Canvas geometry: node sizes, port anchor positions, orthogonal wire routes
 * and the SVG shapes of plan 7.3 (half arrows, causal strokes, arrowheads).
 *
 * Everything here is pure: given the document and the catalog index it returns
 * coordinates. The xyflow nodes and edges only render what these functions
 * compute, which keeps the canvas and the tests on the same geometry.
 */

import type { DomainName, ValueType } from "../contracts/catalog";
import type { Model, ModelConnection, ModelNode, ModelPoint } from "../contracts/model";
import type { CatalogIndex } from "../library/catalogIndex";
import {
  INLINE_ICON,
  SUBSYSTEM_ICON,
  interfaceForNode,
  type NodeInterface,
  type PortSpec,
} from "./nodeInterface";

export const BLOCK_NODE_WIDTH = 164;
export const BLOCK_NODE_MIN_HEIGHT = 86;
export const PORT_ROW_HEIGHT = 26;
export const JUNCTION_NODE_SIZE = 40;
export const JUNCTION_RADIUS = JUNCTION_NODE_SIZE / 2;
/** Gap between a junction's rim and the end of a bond; the arrow must not touch it. */
export const JUNCTION_BOND_GAP = 6;

/** Signal arrow glyph size, shared by the port renderer and the edge trim. */
export const SIGNAL_ARROW_SIZE = 11;
export const SIGNAL_ARROW_HALF = SIGNAL_ARROW_SIZE / 2;
/** Radius of the solid input dot; incoming arrows stop on its outer edge. */
export const SIGNAL_DOT_RADIUS = 3.5;

/**
 * The footprint of a bond-graph element: just its letter, with the ports on the
 * perimeter facing the bonds that leave it. The instance name hangs outside it.
 * 40 px is exactly two 20 px grid cells.
 */
export const BOND_NODE_SIZE = 40;

/**
 * Most stdlib blocks draw as a compact square icon (Simulink-like), with the
 * instance name outside the square. Inline code nodes and subsystems keep the
 * taller card because they carry a title/kind header and many ports.
 * 60 px is exactly three 20 px grid cells.
 */
export const COMPACT_NODE_SIZE = 60;

export interface Point {
  x: number;
  y: number;
}

export type Side = "left" | "right" | "top" | "bottom";

export interface PortPosition {
  side: Side;
  x: number;
  y: number;
}

export interface NodeLayout {
  width: number;
  height: number;
  ports: Map<string, PortPosition>;
}

/** Bond-graph elements render as their letter, not as a block card (plan 7.3). */
export function isBondGraph(iface: NodeInterface): boolean {
  return iface.icon.startsWith("bg-");
}

/**
 * A normal library block draws as a compact icon square. Bond-graph letters,
 * inline code nodes and subsystems have their own presentations.
 */
export function isCompactBlock(iface: NodeInterface): boolean {
  return (
    !iface.isJunction &&
    !isBondGraph(iface) &&
    iface.icon !== INLINE_ICON &&
    iface.icon !== SUBSYSTEM_ICON
  );
}

export interface Anchor {
  point: Point;
  side: Side;
}

/** Split the ports into the left and right card edges. */
export function splitPorts(ports: readonly PortSpec[]): {
  left: PortSpec[];
  right: PortSpec[];
} {
  const inputs = ports.filter((port) => port.kind === "input");
  const outputs = ports.filter((port) => port.kind === "output");
  const power = ports.filter((port) => port.kind === "power");
  const half = Math.ceil(power.length / 2);
  return {
    left: [...inputs, ...power.slice(0, half)],
    right: [...outputs, ...power.slice(half)],
  };
}

function distribute(index: number, count: number, start: number, end: number): number {
  if (count <= 0) {
    return (start + end) / 2;
  }
  return start + ((end - start) * (index + 1)) / (count + 1);
}

function groupBySide(ports: readonly PortSpec[], sides: ReadonlyMap<string, Side> | undefined) {
  const groups: Record<Side, PortSpec[]> = { left: [], right: [], top: [], bottom: [] };
  for (const port of ports) {
    const side = sides?.get(port.name);
    if (side !== undefined) {
      groups[side].push(port);
    }
  }
  return groups;
}

/**
 * The card (or bond-graph letter) size and every port's anchor.
 *
 * Without `sides` the classic split is used (signal inputs and the first half
 * of the power ports on the left, outputs and the rest on the right). With
 * `sides` a port moves to whichever edge faces its bond, so an output always
 * leaves in the direction the arrow goes.
 */
export function layoutNode(
  iface: NodeInterface,
  sides?: ReadonlyMap<string, Side>,
): NodeLayout {
  if (iface.isJunction) {
    return {
      width: JUNCTION_NODE_SIZE,
      height: JUNCTION_NODE_SIZE,
      ports: new Map(),
    };
  }

  const split = splitPorts(iface.ports);
  const sideOf = new Map<string, Side>();
  for (const port of split.left) {
    sideOf.set(port.name, "left");
  }
  for (const port of split.right) {
    sideOf.set(port.name, "right");
  }
  for (const [name, side] of sides ?? []) {
    sideOf.set(name, side);
  }
  const groups = groupBySide(iface.ports, sideOf);

  const positions = new Map<string, PortPosition>();

  if (isBondGraph(iface)) {
    const size = BOND_NODE_SIZE;
    for (const [side, ports] of Object.entries(groups) as [Side, PortSpec[]][]) {
      ports.forEach((port, index) => {
        const offset = distribute(index, ports.length, 6, size - 6);
        if (side === "left") {
          positions.set(port.name, { side, x: 0, y: offset });
        } else if (side === "right") {
          positions.set(port.name, { side, x: size, y: offset });
        } else if (side === "top") {
          positions.set(port.name, { side, x: offset, y: 0 });
        } else {
          positions.set(port.name, { side, x: offset, y: size });
        }
      });
    }
    return { width: size, height: size, ports: positions };
  }

  if (isCompactBlock(iface)) {
    const size = COMPACT_NODE_SIZE;
    const inset = 10;
    for (const [side, ports] of Object.entries(groups) as [Side, PortSpec[]][]) {
      ports.forEach((port, index) => {
        const offset =
          Math.round(distribute(index, ports.length, inset, size - inset) * 10) / 10;
        if (side === "left") {
          positions.set(port.name, { side, x: 0, y: offset });
        } else if (side === "right") {
          positions.set(port.name, { side, x: size, y: offset });
        } else if (side === "top") {
          positions.set(port.name, { side, x: offset, y: 0 });
        } else {
          positions.set(port.name, { side, x: offset, y: size });
        }
      });
    }
    return { width: size, height: size, ports: positions };
  }

  // The card height is computed from the default split, so moving a port to
  // another edge (which depends on the connections) never resizes the card.
  const rows = Math.max(split.left.length, split.right.length);
  const bodyTop = 34;
  const bottom = 18;
  const height = Math.max(
    BLOCK_NODE_MIN_HEIGHT,
    bodyTop + Math.max(rows, 1) * PORT_ROW_HEIGHT + bottom,
  );
  const bodyBottom = height - bottom;

  for (const [side, ports] of Object.entries(groups) as [Side, PortSpec[]][]) {
    ports.forEach((port, index) => {
      if (side === "left" || side === "right") {
        positions.set(port.name, {
          side,
          x: side === "left" ? 0 : BLOCK_NODE_WIDTH,
          y: Math.round(distribute(index, ports.length, bodyTop, bodyBottom) * 10) / 10,
        });
      } else {
        positions.set(port.name, {
          side,
          x: Math.round(distribute(index, ports.length, 22, BLOCK_NODE_WIDTH - 22) * 10) / 10,
          y: side === "top" ? 0 : height,
        });
      }
    });
  }
  return { width: BLOCK_NODE_WIDTH, height, ports: positions };
}

/**
 * Which edge of a node each port should sit on, given the connections.
 *
 * A port with exactly one connection faces the other endpoint, so the port (and
 * the bond leaving it) always points along the arrow. A port with no
 * connection, or a fan-out with several, keeps the classic left/right split.
 */
export function connectionSides(doc: Model, index: CatalogIndex): Map<string, Map<string, Side>> {
  const centres = new Map<string, Point>();
  const layouts = new Map<string, NodeLayout>();
  for (const node of doc.diagram.nodes) {
    const layout = layoutNode(interfaceForNode(node, index));
    layouts.set(node.id, layout);
    centres.set(node.id, {
      x: node.position.x + layout.width / 2,
      y: node.position.y + layout.height / 2,
    });
  }

  const peers = new Map<string, Point[]>();
  const addPeer = (nodeId: string, portName: string | null | undefined, peer: string | undefined) => {
    if (portName === null || portName === undefined || peer === undefined) {
      return;
    }
    const centre = centres.get(peer);
    if (centre === undefined) {
      return;
    }
    const key = `${nodeId}\u0000${portName}`;
    const list = peers.get(key) ?? [];
    list.push(centre);
    peers.set(key, list);
  };
  for (const connection of doc.diagram.connections) {
    addPeer(connection.from.node, connection.from.port, connection.to.node);
    addPeer(connection.to.node, connection.to.port, connection.from.node);
  }

  const result = new Map<string, Map<string, Side>>();
  for (const [key, points] of peers) {
    if (points.length !== 1) {
      continue;
    }
    const [nodeId, portName] = key.split("\u0000");
    const centre = centres.get(nodeId);
    const other = points[0];
    if (centre === undefined || portName === undefined || other === undefined) {
      continue;
    }
    const sides = result.get(nodeId) ?? new Map<string, Side>();
    sides.set(portName, sideToward(centre, other));
    result.set(nodeId, sides);
  }
  return result;
}


export function nodeLayout(node: ModelNode, index: CatalogIndex, doc?: Model): NodeLayout {
  const iface = interfaceForNode(node, index);
  if (doc === undefined) {
    return layoutNode(iface);
  }
  return layoutNode(iface, connectionSides(doc, index).get(node.id));
}

/** Every node's connection-aware layout, with `connectionSides` computed once. */
export function nodeLayouts(doc: Model, index: CatalogIndex): Map<string, NodeLayout> {
  const sides = connectionSides(doc, index);
  const layouts = new Map<string, NodeLayout>();
  for (const node of doc.diagram.nodes) {
    layouts.set(node.id, layoutNode(interfaceForNode(node, index), sides.get(node.id)));
  }
  return layouts;
}

/** The ports a Ctrl-drag may start from: outputs and power ports. */
export function sourcePortNames(iface: NodeInterface): string[] {
  return iface.ports.filter((port) => port.kind !== "input").map((port) => port.name);
}

/**
 * The source port nearest to a point in flow coordinates, or null when the
 * node has no source-capable port. This is what a Ctrl-drag on the element
 * itself uses to pick its outgoing port.
 */
export function nearestSourcePort(
  iface: NodeInterface,
  layout: NodeLayout,
  origin: ModelPoint,
  point: Point,
): string | null {
  let best: string | null = null;
  let bestDistance = Infinity;
  for (const name of sourcePortNames(iface)) {
    const position = layout.ports.get(name);
    if (position === undefined) {
      continue;
    }
    const dx = origin.x + position.x - point.x;
    const dy = origin.y + position.y - point.y;
    const distance = dx * dx + dy * dy;
    if (distance < bestDistance) {
      bestDistance = distance;
      best = name;
    }
  }
  return best;
}

export function nodeCentre(node: ModelNode, layout: NodeLayout): Point {
  return {
    x: node.position.x + layout.width / 2,
    y: node.position.y + layout.height / 2,
  };
}

/** The absolute anchor of one block port. */
export function portAnchor(
  node: ModelNode,
  layout: NodeLayout,
  portName: string | null,
): Anchor | null {
  if (portName === null) {
    return null;
  }
  const position = layout.ports.get(portName);
  if (position === undefined) {
    return null;
  }
  return {
    point: { x: node.position.x + position.x, y: node.position.y + position.y },
    side: position.side,
  };
}

export function unitVector(from: Point, to: Point): Point {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const length = Math.hypot(dx, dy);
  if (length < 1e-6) {
    return { x: 1, y: 0 };
  }
  return { x: dx / length, y: dy / length };
}

/** The point where a line from the centre toward `towards` leaves a circle. */
export function circleAnchor(centre: Point, towards: Point, radius: number): Point {
  const unit = unitVector(centre, towards);
  return {
    x: centre.x + unit.x * radius,
    y: centre.y + unit.y * radius,
  };
}

/** Which side of a junction faces the other endpoint. */
export function sideToward(centre: Point, towards: Point): Side {
  const dx = towards.x - centre.x;
  const dy = towards.y - centre.y;
  if (Math.abs(dx) >= Math.abs(dy)) {
    return dx >= 0 ? "right" : "left";
  }
  return dy >= 0 ? "bottom" : "top";
}

export function offsetPoint(point: Point, side: Side, distance: number): Point {
  switch (side) {
    case "left":
      return { x: point.x - distance, y: point.y };
    case "right":
      return { x: point.x + distance, y: point.y };
    case "top":
      return { x: point.x, y: point.y - distance };
    case "bottom":
      return { x: point.x, y: point.y + distance };
    default:
      return point;
  }
}

function nodeById(doc: Model, id: string): ModelNode | undefined {
  return doc.diagram.nodes.find((node) => node.id === id);
}

function isJunction(node: ModelNode): boolean {
  return "junction" in node.block;
}

function anchorFor(
  node: ModelNode,
  index: CatalogIndex,
  portName: string | null,
  towards: Point,
  doc?: Model,
): Anchor {
  const layout = nodeLayout(node, index, doc);
  if (isJunction(node)) {
    const centre = nodeCentre(node, layout);
    return {
      point: circleAnchor(centre, towards, JUNCTION_RADIUS + JUNCTION_BOND_GAP),
      side: sideToward(centre, towards),
    };
  }
  const anchor = portAnchor(node, layout, portName);
  if (anchor !== null) {
    return anchor;
  }
  return { point: nodeCentre(node, layout), side: sideToward(nodeCentre(node, layout), towards) };
}

/**
 * Both anchors of a connection. Junctions attach floating to their circle
 * edge, so their anchor is computed after the other endpoint's anchor.
 */
export function connectionAnchors(
  doc: Model,
  index: CatalogIndex,
  connection: ModelConnection,
): { source: Anchor; target: Anchor } {
  const sourceNode = nodeById(doc, connection.from.node);
  const targetNode = nodeById(doc, connection.to.node);
  if (sourceNode === undefined || targetNode === undefined) {
    return {
      source: { point: { x: 0, y: 0 }, side: "right" },
      target: { point: { x: 0, y: 0 }, side: "left" },
    };
  }
  const sourceCentre = nodeCentre(sourceNode, nodeLayout(sourceNode, index, doc));
  const targetCentre = nodeCentre(targetNode, nodeLayout(targetNode, index, doc));

  if (isJunction(sourceNode) && isJunction(targetNode)) {
    return {
      source: anchorFor(sourceNode, index, null, targetCentre, doc),
      target: anchorFor(targetNode, index, null, sourceCentre, doc),
    };
  }
  if (isJunction(sourceNode)) {
    const target = anchorFor(targetNode, index, connection.to.port ?? null, sourceCentre, doc);
    return {
      source: anchorFor(sourceNode, index, null, target.point, doc),
      target,
    };
  }
  if (isJunction(targetNode)) {
    const source = anchorFor(sourceNode, index, connection.from.port ?? null, targetCentre, doc);
    return {
      source,
      target: anchorFor(targetNode, index, null, source.point, doc),
    };
  }
  return {
    source: anchorFor(sourceNode, index, connection.from.port ?? null, targetCentre, doc),
    target: anchorFor(targetNode, index, connection.to.port ?? null, sourceCentre, doc),
  };
}

// --------------------------------------------------------------------- paths

function round(value: number): number {
  return Math.round(value * 10) / 10;
}

/** An orthogonal path between two anchors with sensible midpoint routing. */
export function orthogonalPath(a: Anchor, b: Anchor): string {
  const start = a.point;
  const end = b.point;
  const horizontalA = a.side === "left" || a.side === "right";
  const horizontalB = b.side === "left" || b.side === "right";

  if (horizontalA && horizontalB) {
    const natural =
      (a.side === "right" && b.side === "left" && b.point.x >= a.point.x) ||
      (a.side === "left" && b.side === "right" && b.point.x <= a.point.x);
    const midX = natural
      ? (start.x + end.x) / 2
      : a.side === "right"
        ? Math.max(start.x, end.x) + 28
        : Math.min(start.x, end.x) - 28;
    return `M ${round(start.x)} ${round(start.y)} H ${round(midX)} V ${round(end.y)} H ${round(end.x)}`;
  }
  if (!horizontalA && !horizontalB) {
    const natural =
      (a.side === "bottom" && b.side === "top" && b.point.y >= a.point.y) ||
      (a.side === "top" && b.side === "bottom" && b.point.y <= a.point.y);
    const midY = natural
      ? (start.y + end.y) / 2
      : a.side === "bottom"
        ? Math.max(start.y, end.y) + 28
        : Math.min(start.y, end.y) - 28;
    return `M ${round(start.x)} ${round(start.y)} V ${round(midY)} H ${round(end.x)} V ${round(end.y)}`;
  }
  if (horizontalA) {
    return `M ${round(start.x)} ${round(start.y)} H ${round(end.x)} V ${round(end.y)}`;
  }
  return `M ${round(start.x)} ${round(start.y)} V ${round(end.y)} H ${round(end.x)}`;
}

/** A star route through a shared wire hub (3 or more ports). */
export function hubPath(a: Point, hub: Point, b: Point): string {
  return `M ${round(a.x)} ${round(a.y)} H ${round(hub.x)} V ${round(hub.y)} H ${round(b.x)} V ${round(b.y)}`;
}

/** Waypoints first, when a connection stores an explicit route. */
export function routedPath(a: Point, route: readonly Point[], b: Point): string {
  const points = [a, ...route, b];
  return points
    .map((point, index) => `${index === 0 ? "M" : "L"} ${round(point.x)} ${round(point.y)}`)
    .join(" ");
}

function direction(from: Point, to: Point): Point {
  return unitVector(from, to);
}

/** A filled arrowhead at `tip`, pointing away from `from` (signals/wires). */
export function arrowHeadPath(from: Point, tip: Point, size = 9): string {
  const unit = direction(from, tip);
  const normal = { x: -unit.y, y: unit.x };
  const base = { x: tip.x - unit.x * size, y: tip.y - unit.y * size };
  const left = { x: base.x + normal.x * size * 0.5, y: base.y + normal.y * size * 0.5 };
  const right = { x: base.x - normal.x * size * 0.5, y: base.y - normal.y * size * 0.5 };
  return `M ${round(tip.x)} ${round(tip.y)} L ${round(left.x)} ${round(left.y)} L ${round(right.x)} ${round(right.y)} Z`;
}

/** The bond graph half arrow: one barb at the `to` end (plan 7.3). */
export function halfArrowPath(from: Point, tip: Point, size = 10): string {
  const unit = direction(from, tip);
  const normal = { x: -unit.y, y: unit.x };
  const barb = {
    x: tip.x - unit.x * size + normal.x * size * 0.5,
    y: tip.y - unit.y * size + normal.y * size * 0.5,
  };
  return `M ${round(tip.x)} ${round(tip.y)} L ${round(barb.x)} ${round(barb.y)}`;
}

/** The causal stroke: a perpendicular bar at one end of a bond. */
export function causalStrokePath(point: Point, towards: Point, length = 12): string {
  const unit = direction(point, towards);
  const normal = { x: -unit.y, y: unit.x };
  const half = length / 2;
  return `M ${round(point.x + normal.x * half)} ${round(point.y + normal.y * half)} L ${round(point.x - normal.x * half)} ${round(point.y - normal.y * half)}`;
}

/** Where a label sits on a path: halfway along the anchor-to-anchor line. */
export function midpoint(a: Point, b: Point): Point {
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
}

// -------------------------------------------------------------------- colours

export function domainColor(domain: DomainName): string {
  switch (domain) {
    case "Electrical":
      return "var(--domain-electrical)";
    case "Translation":
      return "var(--domain-translation)";
    case "Rotation":
      return "var(--domain-rotation)";
    case "Hydraulic":
      return "var(--domain-hydraulic)";
    case "Generic":
    default:
      return "var(--domain-generic)";
  }
}

export function signalColor(type: ValueType | null): string {
  if (type === "Bool") {
    return "var(--signal-bool)";
  }
  if (type === "Int") {
    return "var(--signal-int)";
  }
  return "var(--signal-real)";
}

export function signalDash(type: ValueType | null): string | undefined {
  if (type === "Bool") {
    return "5 3";
  }
  if (type === "Int") {
    return "1.5 3";
  }
  return undefined;
}

export const DOMAIN_LEGEND: readonly { domain: DomainName; label: string }[] = [
  { domain: "Electrical", label: "Electrical" },
  { domain: "Translation", label: "Translation" },
  { domain: "Rotation", label: "Rotation" },
  { domain: "Hydraulic", label: "Hydraulic" },
  { domain: "Generic", label: "Generic" },
];
