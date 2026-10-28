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

/** 2x2 elements are centred in the 3x3 grid: shift their visual origin by half a cell. */
export const NODE_HALF_SHIFT = 10;

/** Editor grid size. Node origins sit on grid lines; routing vertices use a
 * double-resolution grid: corners (grid lines) and cell centres (half a cell
 * off the lines), so they can sit at every 10 px. */
export const GRID_SIZE = 20;
export const ROUTE_GRID_SIZE = GRID_SIZE / 2;

/** How far a corner may be off 45, 90 or 135 degrees and still get a marker.
 * Deliberately tight: the marker promises an exact angle, not an approximate
 * one, so a corner that merely looks square must not earn it. */
export const MARKER_ANGLE_TOLERANCE_DEG = 0.1;
/** Side length of the square that marks a right angle, in flow units. */
export const RIGHT_ANGLE_MARKER_SIZE = 10;
/** Radius of the arc that marks a 45 or 135 degree corner, in flow units. */
export const ANGLE_MARKER_RADIUS = 20;
/** Gap between that arc and its "45°"/"135°" label, in flow units. */
export const ANGLE_LABEL_GAP = 12;

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

/** Snap a routing vertex to the double-resolution grid: corners and centres. */
export function snapRouteVertex(point: Point): Point {
  const snap = (value: number): number => {
    const snapped = Math.round(value / ROUTE_GRID_SIZE) * ROUTE_GRID_SIZE;
    return snapped === 0 ? 0 : snapped;
  };
  return { x: snap(point.x), y: snap(point.y) };
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
  peerPoints?: ReadonlyMap<string, Point>,
  connectedPorts?: ReadonlySet<string>,
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
  // Two connections that approach one edge from different directions must not
  // swap places: order each side by where its peer sits, so the upper incoming
  // line lands on the upper port. Connected ports come first; unconnected ones
  // keep their interface order.
  const ordered = (side: Side, ports: readonly PortSpec[]): PortSpec[] => {
    const horizontalEdge = side === "left" || side === "right";
    return ports
      .map((port, order) => ({
        port,
        order,
        peer: peerPoints?.get(port.name),
      }))
      .sort((left, right) => {
        if (left.peer === undefined && right.peer === undefined) {
          return left.order - right.order;
        }
        if (left.peer === undefined) {
          return 1;
        }
        if (right.peer === undefined) {
          return -1;
        }
        const leftKey = horizontalEdge ? left.peer.y : left.peer.x;
        const rightKey = horizontalEdge ? right.peer.y : right.peer.x;
        return leftKey - rightKey || left.order - right.order;
      })
      .map((entry) => entry.port);
  };

  /**
   * Place ports along one edge. Connected ports keep the even spacing they
   * would have on their own, so one connection can stay on the exact centre
   * line; free ports park in the remaining gaps at the ends. Without a
   * connected-port set (legacy callers) every port is distributed normally.
   */
  const offsetsFor = (
    side: Side,
    ports: readonly PortSpec[],
    start: number,
    end: number,
  ): Map<string, number> => {
    const result = new Map<string, number>();
    const arranged = ordered(side, ports);
    if (connectedPorts === undefined) {
      arranged.forEach((port, index) => {
        result.set(port.name, distribute(index, ports.length, start, end));
      });
      return result;
    }
    const connected = arranged.filter((port) => connectedPorts.has(port.name));
    const free = arranged.filter((port) => !connectedPorts.has(port.name));
    const connectedOffsets = connected.map((port, index) => {
      const offset = distribute(index, connected.length, start, end);
      result.set(port.name, offset);
      return offset;
    });
    if (free.length === 0) {
      return result;
    }
    if (connected.length === 0) {
      free.forEach((port, index) => {
        result.set(port.name, distribute(index, free.length, start, end));
      });
      return result;
    }

    const span = end - start;
    const slots = connected.length + free.length + 2;
    const candidates = [start, end];
    for (let index = 1; index < slots; index += 1) {
      candidates.push(start + (span * index) / slots);
    }
    const minGap = Math.max(5, span / (connected.length + free.length + 1) / 2);
    const available = candidates.filter((candidate) =>
      connectedOffsets.every((offset) => Math.abs(offset - candidate) >= minGap),
    );
    const chosen: number[] = [];
    for (let index = 0; index < free.length; index += 1) {
      let best: number | undefined;
      let bestScore = -1;
      let bestIndex = -1;
      available.forEach((candidate, candidateIndex) => {
        if (chosen.some((offset) => Math.abs(offset - candidate) < 0.5)) {
          return;
        }
        const score = Math.min(
          ...connectedOffsets.map((offset) => Math.abs(offset - candidate)),
        );
        if (score > bestScore) {
          bestScore = score;
          best = candidate;
          bestIndex = candidateIndex;
        }
      });
      if (best === undefined) {
        break;
      }
      chosen.push(best);
      available.splice(bestIndex, 1);
    }
    chosen.sort((left, right) => left - right);
    free.forEach((port, index) => {
      result.set(
        port.name,
        chosen[index] ?? distribute(index, free.length, start, end),
      );
    });
    return result;
  };

  const place = (
    side: Side,
    ports: readonly PortSpec[],
    start: number,
    end: number,
    width: number,
    height: number,
  ): void => {
    for (const [name, raw] of offsetsFor(side, ports, start, end)) {
      const offset = Math.round(raw * 10) / 10;
      if (side === "left" || side === "right") {
        positions.set(name, {
          side,
          x: side === "left" ? 0 : width,
          y: offset,
        });
      } else {
        positions.set(name, {
          side,
          x: offset,
          y: side === "top" ? 0 : height,
        });
      }
    }
  };

  if (isBondGraph(iface)) {
    const size = BOND_NODE_SIZE;
    for (const [side, ports] of Object.entries(groups) as [Side, PortSpec[]][]) {
      place(side, ports, 6, size - 6, size, size);
    }
    return { width: size, height: size, ports: positions };
  }

  if (isCompactBlock(iface)) {
    const size = COMPACT_NODE_SIZE;
    const inset = 10;
    for (const [side, ports] of Object.entries(groups) as [Side, PortSpec[]][]) {
      place(side, ports, inset, size - inset, size, size);
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
    if (side === "left" || side === "right") {
      place(side, ports, bodyTop, bodyBottom, BLOCK_NODE_WIDTH, height);
    } else {
      place(side, ports, 22, BLOCK_NODE_WIDTH - 22, BLOCK_NODE_WIDTH, height);
    }
  }
  return { width: BLOCK_NODE_WIDTH, height, ports: positions };
}

export interface ConnectionHints {
  /** Which edge each connected port moves to. */
  sides: Map<string, Map<string, Side>>;
  /** The peer centre that decides a port's order along that edge. */
  peerPoints: Map<string, Map<string, Point>>;
  /** Every port name that has at least one circuit connection. */
  connected: Map<string, Set<string>>;
}

/**
 * Which edge of a node each port should sit on, and where its peer sits so the
 * ports can be ordered along that edge.
 *
 * A port with exactly one connection faces the other endpoint, so the port (and
 * the bond leaving it) always points along the arrow. A port with no
 * connection, or a fan-out with several, keeps the classic left/right split.
 */
export function connectionHints(doc: Model, index: CatalogIndex): ConnectionHints {
  const centres = new Map<string, Point>();
  for (const node of doc.diagram.nodes) {
    const layout = layoutNode(interfaceForNode(node, index));
    const offset = nodeVisualOffset(node, index);
    centres.set(node.id, {
      x: node.position.x + offset.x + layout.width / 2,
      y: node.position.y + offset.y + layout.height / 2,
    });
  }

  const peers = new Map<string, Point[]>();
  const connected = new Map<string, Set<string>>();
  const addConnected = (nodeId: string, portName: string | null | undefined) => {
    if (portName === null || portName === undefined) {
      return;
    }
    const ports = connected.get(nodeId) ?? new Set<string>();
    ports.add(portName);
    connected.set(nodeId, ports);
  };
  const addPeer = (nodeId: string, portName: string | null | undefined, peer: Point | undefined) => {
    if (portName === null || portName === undefined || peer === undefined) {
      return;
    }
    const key = `${nodeId}\u0000${portName}`;
    const list = peers.get(key) ?? [];
    list.push(peer);
    peers.set(key, list);
  };
  for (const connection of doc.diagram.connections) {
    const fromCentre = centres.get(connection.from.node);
    const toCentre = centres.get(connection.to.node);
    const route = connection.route ?? [];
    // A route's first/last waypoint is the direction the line actually leaves
    // or enters, so a manually routed connection moves its ports to that edge.
    const sourcePeer = route[0] ?? toCentre;
    const targetPeer = route[route.length - 1] ?? fromCentre;
    addConnected(connection.from.node, connection.from.port);
    addConnected(connection.to.node, connection.to.port);
    addPeer(connection.from.node, connection.from.port, sourcePeer);
    addPeer(connection.to.node, connection.to.port, targetPeer);
  }

  const sides = new Map<string, Map<string, Side>>();
  const peerPoints = new Map<string, Map<string, Point>>();
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
    const nodeSides = sides.get(nodeId) ?? new Map<string, Side>();
    nodeSides.set(portName, sideToward(centre, other));
    sides.set(nodeId, nodeSides);
    const nodePeers = peerPoints.get(nodeId) ?? new Map<string, Point>();
    nodePeers.set(portName, other);
    peerPoints.set(nodeId, nodePeers);
  }
  return { sides, peerPoints, connected };
}

export function connectionSides(doc: Model, index: CatalogIndex): Map<string, Map<string, Side>> {
  return connectionHints(doc, index).sides;
}


export function nodeLayout(node: ModelNode, index: CatalogIndex, doc?: Model): NodeLayout {
  const iface = interfaceForNode(node, index);
  if (doc === undefined) {
    return layoutNode(iface);
  }
  const hints = connectionHints(doc, index);
  return layoutNode(
    iface,
    hints.sides.get(node.id),
    hints.peerPoints.get(node.id),
    hints.connected.get(node.id),
  );
}

/** Every node's connection-aware layout, with `connectionHints` computed once. */
export function nodeLayouts(doc: Model, index: CatalogIndex): Map<string, NodeLayout> {
  const hints = connectionHints(doc, index);
  const layouts = new Map<string, NodeLayout>();
  for (const node of doc.diagram.nodes) {
    layouts.set(
      node.id,
      layoutNode(
        interfaceForNode(node, index),
        hints.sides.get(node.id),
        hints.peerPoints.get(node.id),
        hints.connected.get(node.id),
      ),
    );
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

export function nodeCentre(node: ModelNode, layout: NodeLayout, offset: Point = { x: 0, y: 0 }): Point {
  return {
    x: node.position.x + offset.x + layout.width / 2,
    y: node.position.y + offset.y + layout.height / 2,
  };
}

/** Visual half-cell offset for the 2x2 bond-graph letters and junctions. */
export function nodeVisualOffset(node: ModelNode, index?: CatalogIndex): Point {
  if ("junction" in node.block) {
    return { x: NODE_HALF_SHIFT, y: NODE_HALF_SHIFT };
  }
  if (index !== undefined && "ref" in node.block) {
    const iface = interfaceForNode(node, index);
    if (isBondGraph(iface)) {
      return { x: NODE_HALF_SHIFT, y: NODE_HALF_SHIFT };
    }
  }
  return { x: 0, y: 0 };
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
  const offset = nodeVisualOffset(node, index);
  if (isJunction(node)) {
    const centre = nodeCentre(node, layout, offset);
    return {
      point: circleAnchor(centre, towards, JUNCTION_RADIUS + JUNCTION_BOND_GAP),
      side: sideToward(centre, towards),
    };
  }
  const anchor = portAnchor(node, layout, portName);
  if (anchor !== null) {
    return {
      ...anchor,
      point: { x: anchor.point.x + offset.x, y: anchor.point.y + offset.y },
    };
  }
  const centre = nodeCentre(node, layout, offset);
  return { point: centre, side: sideToward(centre, towards) };
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
  const sourceCentre = nodeCentre(
    sourceNode,
    nodeLayout(sourceNode, index, doc),
    nodeVisualOffset(sourceNode, index),
  );
  const targetCentre = nodeCentre(
    targetNode,
    nodeLayout(targetNode, index, doc),
    nodeVisualOffset(targetNode, index),
  );

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

interface CornerShape {
  /** Unit vectors from the corner along each segment. */
  first: Point;
  second: Point;
  /** The angle between the two segments, 0 < angle <= 180 degrees. */
  angleDeg: number;
}

/** The two rays of a corner and the angle between them, or null when degenerate. */
function cornerShape(previous: Point, corner: Point, next: Point): CornerShape | null {
  const ray = (to: Point): Point | null => {
    const dx = to.x - corner.x;
    const dy = to.y - corner.y;
    const length = Math.hypot(dx, dy);
    return length < 1e-6 ? null : { x: dx / length, y: dy / length };
  };
  const first = ray(previous);
  const second = ray(next);
  if (first === null || second === null) {
    return null;
  }
  const dot = Math.max(-1, Math.min(1, first.x * second.x + first.y * second.y));
  return { first, second, angleDeg: (Math.acos(dot) * 180) / Math.PI };
}

/**
 * The right-angle marker for a corner whose two segments meet at 90 degrees:
 * an open square drawn inside the wedge, with its sides along the segments.
 * Returns null for any other angle or a degenerate corner, so the caller can
 * show the marker only when the lines really are square.
 */
export function rightAngleMarker(
  previous: Point,
  corner: Point,
  next: Point,
  size = RIGHT_ANGLE_MARKER_SIZE,
  toleranceDeg = MARKER_ANGLE_TOLERANCE_DEG,
): string | null {
  const shape = cornerShape(previous, corner, next);
  if (shape === null || Math.abs(shape.angleDeg - 90) > toleranceDeg) {
    return null;
  }
  const { first, second } = shape;
  const alongFirst = { x: corner.x + first.x * size, y: corner.y + first.y * size };
  const inner = {
    x: alongFirst.x + second.x * size,
    y: alongFirst.y + second.y * size,
  };
  const alongSecond = { x: corner.x + second.x * size, y: corner.y + second.y * size };
  return `M ${round(alongFirst.x)} ${round(alongFirst.y)} L ${round(inner.x)} ${round(inner.y)} L ${round(alongSecond.x)} ${round(alongSecond.y)}`;
}

export interface CornerAngleMarker {
  /** The angle the marker reports. */
  angle: 45 | 135;
  /** The arc across the corner. */
  arc: string;
  /** The label text, e.g. "45°". */
  text: string;
  /** Where the centre of that label sits, on the corner's bisector. */
  label: Point;
}

const MARKED_ANGLES = [45, 135] as const;

/**
 * The arc-and-label marker for a corner whose segments meet at 45 or 135
 * degrees, or null for any other angle. The arc runs inside the wedge and the
 * label names the angle, which a bare square cannot do.
 */
export function cornerAngleMarker(
  previous: Point,
  corner: Point,
  next: Point,
  radius = ANGLE_MARKER_RADIUS,
  toleranceDeg = MARKER_ANGLE_TOLERANCE_DEG,
): CornerAngleMarker | null {
  const shape = cornerShape(previous, corner, next);
  if (shape === null) {
    return null;
  }
  const angle = MARKED_ANGLES.find(
    (candidate) => Math.abs(shape.angleDeg - candidate) <= toleranceDeg,
  );
  if (angle === undefined) {
    return null;
  }
  const { first, second } = shape;
  const start = { x: corner.x + first.x * radius, y: corner.y + first.y * radius };
  const end = { x: corner.x + second.x * radius, y: corner.y + second.y * radius };
  // Sweep towards the second ray the short way round, so the arc stays inside
  // the (at most 135 degree) wedge rather than bulging out of it.
  const cross = first.x * second.y - first.y * second.x;
  const sweep = cross >= 0 ? 1 : 0;
  const arc = `M ${round(start.x)} ${round(start.y)} A ${radius} ${radius} 0 0 ${sweep} ${round(end.x)} ${round(end.y)}`;
  const sum = { x: first.x + second.x, y: first.y + second.y };
  const length = Math.hypot(sum.x, sum.y);
  const bisector =
    length < 1e-6 ? first : { x: sum.x / length, y: sum.y / length };
  return {
    angle,
    arc,
    text: `${angle}\u00b0`,
    label: {
      x: corner.x + bisector.x * (radius + ANGLE_LABEL_GAP),
      y: corner.y + bisector.y * (radius + ANGLE_LABEL_GAP),
    },
  };
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

// ---------------------------------------------------------------- multibonds
//
// Visual rule (plan 7.1, D-MB12): the stroke count encodes the model
// dimension, not the port size. Planar (3 components) draws two strokes,
// Spatial (6 components) draws three, every scalar domain one.

/** The distance between adjacent strokes of a multibond bundle, in flow px. */
export const MULTIBOND_GAP = 4.2;
/** The stroke width of one stroke of a multibond bundle, in px (plan 7.2). */
export const MULTIBOND_STROKE_WIDTH = 1.5;
/** The half-arrow size of a multibond stroke: smaller than the scalar 10 px. */
export const MULTIBOND_ARROW_SIZE = 8;
/**
 * The longest miter a waypoint may produce, as a multiple of `distance`.
 * A very sharp corner would otherwise shoot the bundle far past the element.
 */
export const MULTIBOND_MITER_LIMIT = 4;

export type MultibondStrokeCount = 1 | 2 | 3;

/**
 * How many parallel strokes a bond of `domain` draws (plan 7.1): Planar two,
 * Spatial three, every other (scalar) domain one. Unknown names are scalar.
 */
export function multibondStrokes(domain: DomainName | string | null): MultibondStrokeCount {
  switch (domain) {
    case "Planar":
      return 2;
    case "Spatial":
      return 3;
    default:
      return 1;
  }
}

/** The number of physical components a domain's port carries (Planar 3, Spatial 6). */
export function multibondComponents(domain: DomainName | string | null): number {
  switch (domain) {
    case "Planar":
      return 3;
    case "Spatial":
      return 6;
    default:
      return 1;
  }
}

/**
 * The per-stroke offsets of a bundle (plan 7.2): `[-gap/2, +gap/2]` for two
 * strokes, `[-gap, 0, +gap]` for three, `[0]` for the scalar centre path.
 */
export function multibondOffsets(strokes: MultibondStrokeCount): number[] {
  if (strokes === 2) {
    return [-MULTIBOND_GAP / 2, MULTIBOND_GAP / 2];
  }
  if (strokes === 3) {
    return [-MULTIBOND_GAP, 0, MULTIBOND_GAP];
  }
  return [0];
}

/** The half width of a bundle: the outer stroke's offset plus half its stroke. */
export function multibondBundleHalf(strokes: MultibondStrokeCount): number {
  const offsets = multibondOffsets(strokes);
  return Math.max(...offsets.map(Math.abs)) + MULTIBOND_STROKE_WIDTH / 2;
}

/** Consecutive points closer than this are one point, so no normal is undefined. */
const MIN_SEGMENT = 1e-6;

function finite(point: Point): boolean {
  return Number.isFinite(point.x) && Number.isFinite(point.y);
}

function copy(point: Point): Point {
  return { x: point.x, y: point.y };
}

function dedupe(points: readonly Point[]): Point[] {
  const result: Point[] = [];
  for (const point of points) {
    if (!finite(point)) {
      return [];
    }
    const last = result[result.length - 1];
    if (last === undefined || Math.hypot(point.x - last.x, point.y - last.y) >= MIN_SEGMENT) {
      result.push(copy(point));
    }
  }
  return result;
}

/**
 * Offset a routed polyline by `distance` along each segment's normal, mitering
 * at the waypoints (plan 7.2).
 *
 * A positive `distance` moves each stroke to the **left of the direction of
 * travel** in flow coordinates (x right, y down): a segment travelling +x is
 * offset towards -y (up on the canvas); a segment travelling +y is offset
 * towards +x. A negative distance moves it to the right.
 *
 * Endpoints use the terminal segment's normal. Interior waypoints take the
 * intersection of the two offset lines, i.e. they move along the average of
 * the adjacent unit normals, and the miter length is clamped to
 * `MULTIBOND_MITER_LIMIT * |distance|` so a hairpin cannot spike. Degenerate
 * input (no points, zero-length segments, non-finite coordinates) yields a
 * finite result: the repeated points collapse, and a single point stays a
 * single point.
 *
 * A straight or collinear polyline keeps its exact length (to floating point);
 * at a corner the miter trims the outside segment and extends the inside one,
 * which is the normal length change of a parallel offset.
 */
export function offsetPolyline(points: readonly Point[], distance: number): Point[] {
  const path = dedupe(points);
  if (path.length === 0) {
    return [];
  }
  if (path.length === 1 || distance === 0) {
    return path;
  }
  if (!Number.isFinite(distance)) {
    return [];
  }

  const normals: Point[] = [];
  for (let index = 0; index < path.length - 1; index += 1) {
    const from = path[index];
    const to = path[index + 1];
    if (from === undefined || to === undefined) {
      continue;
    }
    const dx = to.x - from.x;
    const dy = to.y - from.y;
    const length = Math.hypot(dx, dy);
    // Left of travel in flow coordinates (x right, y down): (dy, -dx).
    normals.push({ x: dy / length, y: -dx / length });
  }

  const offsets: Point[] = [];
  const first = path[0];
  const firstNormal = normals[0];
  if (first === undefined || firstNormal === undefined) {
    return path;
  }
  offsets.push({
    x: first.x + firstNormal.x * distance,
    y: first.y + firstNormal.y * distance,
  });

  for (let index = 1; index < path.length - 1; index += 1) {
    const corner = path[index];
    const before = normals[index - 1];
    const after = normals[index];
    if (corner === undefined || before === undefined || after === undefined) {
      continue;
    }
    const sum = { x: before.x + after.x, y: before.y + after.y };
    const length = Math.hypot(sum.x, sum.y);
    if (length < MIN_SEGMENT) {
      // A 180 degree reversal: both offset lines are parallel and distinct, so
      // there is no miter; use the incoming normal to stay finite.
      offsets.push({
        x: corner.x + before.x * distance,
        y: corner.y + before.y * distance,
      });
      continue;
    }
    const bisector = { x: sum.x / length, y: sum.y / length };
    // The miter point is d / cos(half angle) along the bisector; `cosine` is
    // that half-angle cosine, which is also the projection on either normal.
    const cosine = bisector.x * before.x + bisector.y * before.y;
    const raw = Math.abs(cosine) < 1e-9 ? Number.POSITIVE_INFINITY : distance / cosine;
    const limit = MULTIBOND_MITER_LIMIT * Math.abs(distance);
    const miter = Math.max(-limit, Math.min(limit, raw));
    offsets.push({
      x: corner.x + bisector.x * miter,
      y: corner.y + bisector.y * miter,
    });
  }

  const last = path[path.length - 1];
  const lastNormal = normals[normals.length - 1];
  if (last === undefined || lastNormal === undefined) {
    return path;
  }
  offsets.push({
    x: last.x + lastNormal.x * distance,
    y: last.y + lastNormal.y * distance,
  });
  return offsets;
}

/** The SVG `d` of a bundle stroke: a polyline through the offset points. */
export function multibondPath(points: readonly Point[], distance: number): string {
  return offsetPolyline(points, distance)
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`)
    .join(" ");
}

export interface BundleCausalBar {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

/**
 * One causal bar across a whole bundle (plan 7.2), perpendicular to the bond at
 * its effort-in end. `to` is that end and `halfSpan` the bundle's half width;
 * the bar spans `2 * (halfSpan + 3)`, so it clears the outer strokes.
 */
export function bundleCausalBar(
  from: Point,
  to: Point,
  halfSpan: number,
): BundleCausalBar {
  const unit = unitVector(from, to);
  const normal = { x: -unit.y, y: unit.x };
  const half = Math.abs(halfSpan) + 3;
  return {
    x1: to.x + normal.x * half,
    y1: to.y + normal.y * half,
    x2: to.x - normal.x * half,
    y2: to.y - normal.y * half,
  };
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
    case "Planar":
      return "var(--domain-planar)";
    case "Spatial":
      return "var(--domain-spatial)";
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
