/**
 * The subsystem boundary as the inner canvas shows it.
 *
 * Inside a subsystem every exposed port gets a terminal: a virtual canvas
 * node derived from the subsystem's `ports` (it is never a model node), with
 * a dashed boundary wire to the internal port it maps to and a second line
 * naming where the port goes in the parent diagram. This module is the pure
 * part: the boundary facts of the open subsystem, the outside-connection
 * lookup, and where each terminal sits.
 *
 * Placement: a port with `ui.position` sits there. The others stack along the
 * inner content's bounding box: signal inputs on the left edge, outputs on
 * the right, power ports on the edge where the port sits on the outside
 * block, each edge in the outside block's order.
 */

import type { Model, ModelDiagram, ModelNode, ModelSubsystemPort } from "../contracts/model";
import type { CatalogIndex } from "../library/catalogIndex";
import { nodeLayout, type Point, type Side } from "./geometry";
import { activeModel } from "./subsystemPath";
import {
  endpointLabel,
  outsideConnections,
  subsystemAtPath,
  terminalKindOf,
  type TerminalKind,
} from "./subsystemPorts";

/** Canvas ids of terminals; model node ids cannot contain `:`. */
export const TERMINAL_PREFIX = "terminal:";
export const GHOST_PREFIX = "terminal-ghost:";

export function terminalId(portName: string): string {
  return `${TERMINAL_PREFIX}${portName}`;
}

export function terminalPortName(id: string): string | null {
  return id.startsWith(TERMINAL_PREFIX) ? id.slice(TERMINAL_PREFIX.length) : null;
}

export function isTerminalId(id: string): boolean {
  return id.startsWith(TERMINAL_PREFIX);
}

export function ghostId(kind: TerminalKind): string {
  return `${GHOST_PREFIX}${kind}`;
}

export function ghostKind(id: string | null | undefined): TerminalKind | null {
  if (id === null || id === undefined || !id.startsWith(GHOST_PREFIX)) {
    return null;
  }
  const kind = id.slice(GHOST_PREFIX.length);
  return kind === "input" || kind === "output" || kind === "power" ? kind : null;
}

/** Any canvas element that stands for the boundary rather than a model node. */
export function isBoundaryElementId(id: string): boolean {
  return isTerminalId(id) || id.startsWith(GHOST_PREFIX);
}

/** One outside connection of an exposed port, as the terminal names it. */
export interface OutsideLink {
  connectionId: string;
  /** `Traj.q_ref`, or the node name for a junction end. */
  peer: string;
}

export interface SubsystemBoundary {
  /** The subsystem node (in the parent diagram). */
  nodeId: string;
  nodeName: string;
  ports: readonly ModelSubsystemPort[];
  /** The edge each port sits on on the outside block, and its offset along it. */
  outer: ReadonlyMap<string, { side: Side; offset: number }>;
  outside: ReadonlyMap<string, readonly OutsideLink[]>;
}

/**
 * Where exposed port `portName` of subsystem node `nodeId` goes in the parent
 * diagram: one entry per outside connection, naming the other end.
 */
export function outsideLinks(
  parent: ModelDiagram,
  nodeId: string,
  portName: string,
): OutsideLink[] {
  return outsideConnections(parent, nodeId, portName).map((connection) => {
    const other =
      connection.from.node === nodeId && connection.from.port === portName
        ? connection.to
        : connection.from;
    return {
      connectionId: connection.id,
      peer: endpointLabel(parent.nodes, other.node, other.port),
    };
  });
}

/** The boundary of the subsystem at the end of `path`, or null at the root. */
export function subsystemBoundary(
  doc: Model,
  path: readonly string[],
  index: CatalogIndex,
): SubsystemBoundary | null {
  const found = subsystemAtPath(doc, path);
  if (found === null) {
    return null;
  }
  const { node, parent } = found;
  const parentView = activeModel(doc, path.slice(0, -1));
  const layout = parentView === null ? null : nodeLayout(node, index, parentView);
  const outer = new Map<string, { side: Side; offset: number }>();
  const outside = new Map<string, OutsideLink[]>();
  for (const port of node.block.subsystem.ports) {
    const position = layout?.ports.get(port.name);
    if (position !== undefined) {
      outer.set(port.name, {
        side: position.side,
        offset: position.side === "left" || position.side === "right" ? position.y : position.x,
      });
    }
    outside.set(port.name, outsideLinks(parent, node.id, port.name));
  }
  return {
    nodeId: node.id,
    nodeName: node.name,
    ports: node.block.subsystem.ports,
    outer,
    outside,
  };
}

const ARROW: Record<TerminalKind, string> = { input: "←", output: "→", power: "↔" };

/** The terminal's second line: `← Traj.q_ref`, `→ PD.q +2`, or `unconnected`. */
export function outsideText(kind: TerminalKind, links: readonly OutsideLink[]): string {
  const first = links[0];
  if (first === undefined) {
    return "unconnected";
  }
  const more = links.length > 1 ? ` +${links.length - 1}` : "";
  return `${ARROW[kind]} ${first.peer}${more}`;
}

/** Every outside peer, for the tooltip. */
export function outsideTitle(kind: TerminalKind, links: readonly OutsideLink[], nodeName: string): string {
  if (links.length === 0) {
    return `Not connected outside ${nodeName}`;
  }
  const verb = kind === "input" ? "from" : kind === "output" ? "to" : "with";
  return `Connected ${verb} ${links.map((link) => link.peer).join(", ")} outside ${nodeName}. Click to show it on the parent diagram.`;
}

export const TERMINAL_HEIGHT = 36;
export const GHOST_HEIGHT = 24;
/** Gap between the content box and a terminal column. */
export const TERMINAL_GAP = 80;
/** Vertical pitch of a terminal column. */
export const TERMINAL_PITCH = 48;

export function terminalWidth(name: string, second: string): number {
  const text = Math.max(name.length * 7.4 + 26, second.length * 6.4 + 28);
  return Math.round(Math.min(200, Math.max(76, text)));
}

export const GHOST_WIDTH = 76;

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** The bounding box of the nested content, or a box at the origin for an empty diagram. */
export function contentBox(rects: readonly Rect[]): Rect {
  if (rects.length === 0) {
    return { x: 0, y: 0, w: 200, h: 120 };
  }
  const minX = Math.min(...rects.map((rect) => rect.x));
  const minY = Math.min(...rects.map((rect) => rect.y));
  const maxX = Math.max(...rects.map((rect) => rect.x + rect.w));
  const maxY = Math.max(...rects.map((rect) => rect.y + rect.h));
  return { x: minX, y: minY, w: maxX - minX, h: maxY - minY };
}

/** The content-box edge a terminal stacks on by default. */
export function defaultTerminalSide(
  port: ModelSubsystemPort,
  outer: SubsystemBoundary["outer"],
): Side {
  if (port.kind === "signal") {
    return port.direction === "input" ? "left" : "right";
  }
  return outer.get(port.name)?.side ?? "right";
}

export interface TerminalPlacement {
  position: Point;
  /** The edge it stacks on (also for a stored position: its default edge). */
  side: Side;
  width: number;
  height: number;
  /** Whether the position comes from `ui.position`. */
  stored: boolean;
}

export interface BoundaryPlacement {
  terminals: Map<string, TerminalPlacement>;
  ghosts: Map<TerminalKind, Point>;
}

function round(value: number): number {
  return Math.round(value * 10) / 10;
}

/**
 * Where every terminal and the three "+ input" / "+ output" / "+ power"
 * ghosts sit. `widths` gives each terminal's width (it depends on the text).
 */
export function placeTerminals(
  boundary: Pick<SubsystemBoundary, "ports" | "outer">,
  box: Rect,
  widths: ReadonlyMap<string, number>,
): BoundaryPlacement {
  const terminals = new Map<string, TerminalPlacement>();
  const groups: Record<Side, { port: ModelSubsystemPort; order: number }[]> = {
    left: [],
    right: [],
    top: [],
    bottom: [],
  };
  boundary.ports.forEach((port, order) => {
    const side = defaultTerminalSide(port, boundary.outer);
    groups[side].push({ port, order });
  });
  const stacked: Record<Side, number> = { left: 0, right: 0, top: 0, bottom: 0 };
  for (const side of ["left", "right", "top", "bottom"] as const) {
    // The outside block's order along the same edge; other ports keep theirs.
    const entries = groups[side]
      .map((entry) => {
        const outer = boundary.outer.get(entry.port.name);
        return { ...entry, key: outer !== undefined && outer.side === side ? outer.offset : null };
      })
      .sort((a, b) => {
        if (a.key !== null && b.key !== null) {
          return a.key - b.key || a.order - b.order;
        }
        if (a.key !== null) {
          return -1;
        }
        if (b.key !== null) {
          return 1;
        }
        return a.order - b.order;
      });
    const free = entries.filter((entry) => entry.port.ui === undefined);
    stacked[side] = free.length;
    const horizontal = side === "left" || side === "right";
    const total = horizontal
      ? (free.length - 1) * TERMINAL_PITCH
      : free.reduce((sum, entry) => sum + (widths.get(entry.port.name) ?? GHOST_WIDTH) + 16, -16);
    let cursor = horizontal ? box.y + box.h / 2 - total / 2 : box.x + box.w / 2 - total / 2;
    for (const { port } of entries) {
      const width = widths.get(port.name) ?? GHOST_WIDTH;
      const stored = port.ui?.position;
      if (stored !== undefined) {
        terminals.set(port.name, {
          position: { x: stored.x, y: stored.y },
          side,
          width,
          height: TERMINAL_HEIGHT,
          stored: true,
        });
        continue;
      }
      let position: Point;
      if (horizontal) {
        position = {
          x: side === "left" ? box.x - TERMINAL_GAP - width : box.x + box.w + TERMINAL_GAP,
          y: cursor - TERMINAL_HEIGHT / 2,
        };
        cursor += TERMINAL_PITCH;
      } else {
        position = {
          x: cursor,
          y: side === "top" ? box.y - TERMINAL_GAP - TERMINAL_HEIGHT : box.y + box.h + TERMINAL_GAP,
        };
        cursor += width + 16;
      }
      terminals.set(port.name, {
        position: { x: round(position.x), y: round(position.y) },
        side,
        width,
        height: TERMINAL_HEIGHT,
        stored: false,
      });
    }
  }

  // The ghosts sit under the default stacks: "+ input" on the left, "+ output"
  // and "+ power" on the right.
  const below = (side: "left" | "right", slot: number): number => {
    const count = stacked[side];
    const top = box.y + box.h / 2 - ((count - 1) * TERMINAL_PITCH) / 2;
    const first = count === 0 ? box.y + box.h / 2 : top + count * TERMINAL_PITCH;
    return round(first + slot * (GHOST_HEIGHT + 10) - GHOST_HEIGHT / 2);
  };
  const ghosts = new Map<TerminalKind, Point>([
    ["input", { x: round(box.x - TERMINAL_GAP - GHOST_WIDTH), y: below("left", 0) }],
    ["output", { x: round(box.x + box.w + TERMINAL_GAP), y: below("right", 0) }],
    ["power", { x: round(box.x + box.w + TERMINAL_GAP), y: below("right", 1) }],
  ]);
  return { terminals, ghosts };
}

/** `ModelNode` lookup used by the canvas: the internal node a port maps to. */
export function internalNodeOf(
  nodes: readonly ModelNode[],
  port: ModelSubsystemPort,
): ModelNode | undefined {
  return nodes.find((node) => node.id === port.node);
}

export { terminalKindOf };

export const REVEAL_PORT_EVENT = "bgsim:reveal-subsystem-port";

/**
 * Ask the canvas to leave the subsystem and show the outside connections of
 * exposed port `name` (the canvas also frames them). Returns false when no
 * canvas took the request, so the caller can fall back to the store command.
 */
export function requestPortReveal(name: string): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  const event = new CustomEvent<string>(REVEAL_PORT_EVENT, { detail: name, cancelable: true });
  return !window.dispatchEvent(event);
}
