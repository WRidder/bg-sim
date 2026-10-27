/**
 * Document -> xyflow elements. One pass over the nodes and one over the
 * connections; the diagram analysis is computed once and shared, so colours,
 * wire hubs and drag states always agree.
 */

import type { Edge, Node } from "@xyflow/react";

import type { DomainName } from "../contracts/catalog";
import type { Model, ModelPoint } from "../contracts/model";
import type { CatalogIndex } from "../library/catalogIndex";
import {
  analyseDiagram,
  dragCompatibility,
  type DiagramAnalysis,
  type PortDragState,
} from "./connectionAnalysis";
import type { PortDescriptor } from "./connectionRules";
import {
  connectionAnchors,
  isBondGraph,
  isCompactBlock,
  layoutNode,
  nodeLayouts,
  nodeVisualOffset,
  type NodeLayout,
  type Side,
} from "./geometry";
import {
  BlockNode,
  JunctionNode,
  type BlockNodeData,
  type JunctionNodeData,
} from "./nodes/BlockNode";
import { interfaceForNode, missingPortFor } from "./nodeInterface";
import type { EditorEdge, EditorEdgeData } from "./edges/EditorEdges";
import { BondEdge, SignalEdge, WireEdge } from "./edges/EditorEdges";

export type DiagramNode =
  | Node<BlockNodeData, "block" | "subsystem">
  | Node<JunctionNodeData, "junction">;

export const NODE_TYPES = {
  block: BlockNode,
  subsystem: BlockNode,
  junction: JunctionNode,
};
export const EDGE_TYPES = { bond: BondEdge, wire: WireEdge, signal: SignalEdge };

export interface DiagramFlow {
  nodes: DiagramNode[];
  edges: EditorEdge[];
  analysis: DiagramAnalysis;
}

function junctionHandle(side: Side): string {
  switch (side) {
    case "left":
      return "j-left";
    case "right":
      return "j-right";
    case "top":
      return "j-top";
    case "bottom":
      return "j-bottom";
    default:
      return "j-left";
  }
}

function portStateMap(
  iface: ReturnType<typeof interfaceForNode>,
  states: Map<string, PortDragState>,
  domains: Map<string, DomainName>,
  nodeId: string,
): { portStates: Record<string, PortDragState>; portDomains: Record<string, DomainName> } {
  const portStates: Record<string, PortDragState> = {};
  const portDomains: Record<string, DomainName> = {};
  for (const port of iface.ports) {
    const key = `${nodeId}\u0000${port.name}`;
    portStates[port.name] = states.get(key) ?? "idle";
    portDomains[port.name] = domains.get(key) ?? port.domain;
  }
  return { portStates, portDomains };
}

interface LabelRect {
  x: number;
  y: number;
  w: number;
  h: number;
}

function labelRect(
  node: { name: string; position: ModelPoint },
  layout: NodeLayout,
  side: Side,
): LabelRect {
  const w = Math.max(28, node.name.length * 6.8 + 8);
  const h = 15;
  const gap = 5;
  switch (side) {
    case "top":
      return {
        x: node.position.x + layout.width / 2 - w / 2,
        y: node.position.y - gap - h,
        w,
        h,
      };
    case "right":
      return {
        x: node.position.x + layout.width + gap,
        y: node.position.y + layout.height / 2 - h / 2,
        w,
        h,
      };
    case "left":
      return {
        x: node.position.x - gap - w,
        y: node.position.y + layout.height / 2 - h / 2,
        w,
        h,
      };
    case "bottom":
    default:
      return {
        x: node.position.x + layout.width / 2 - w / 2,
        y: node.position.y + layout.height + gap,
        w,
        h,
      };
  }
}

function overlaps(a: LabelRect, b: LabelRect): boolean {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}

/**
 * Where an element's instance name hangs: below by default, but it moves
 * outward when another element is there or when a bond leaves through that edge.
 */
export function bondLabelSide(
  node: { name: string; position: ModelPoint },
  layout: NodeLayout,
  others: readonly LabelRect[],
): Side {
  const portSides = new Set([...layout.ports.values()].map((port) => port.side));
  const order: Side[] = ["bottom", "top", "right", "left"];
  const free = order.filter((side) => !portSides.has(side));
  const candidates = [...free, ...order.filter((side) => portSides.has(side))];
  let best: Side = candidates[0] ?? "bottom";
  let bestOverlap = Infinity;
  for (const side of candidates) {
    const rect = labelRect(node, layout, side);
    const overlap = others.reduce(
      (total, other) => total + (overlaps(rect, other) ? 1 : 0),
      0,
    );
    if (overlap === 0) {
      return side;
    }
    if (overlap < bestOverlap) {
      bestOverlap = overlap;
      best = side;
    }
  }
  return best;
}

/**
 * Build the xyflow nodes and edges. `dragOrigin` is the port a connection drag
 * started from, if any; it drives the compatible/incompatible glyph states.
 */
export function buildDiagram(
  doc: Model,
  index: CatalogIndex,
  selection: { nodes: readonly string[]; connections: readonly string[] },
  dragOrigin: PortDescriptor | null = null,
  snap = true,
): DiagramFlow {
  const analysis = analyseDiagram(doc, index);
  const dragStates = dragCompatibility(doc, index, dragOrigin);
  const selectedNodes = new Set(selection.nodes);
  const selectedConnections = new Set(selection.connections);
  const nodeById = new Map(doc.diagram.nodes.map((node) => [node.id, node]));
  const layouts = nodeLayouts(doc, index);
  const nodeRects = doc.diagram.nodes.map((node) => {
    const layout = layouts.get(node.id);
    const width = layout?.width ?? 0;
    const height = layout?.height ?? 0;
    const offset = nodeVisualOffset(node, index);
    return {
      id: node.id,
      x: node.position.x + offset.x - 4,
      y: node.position.y + offset.y - 4,
      w: width + 8,
      h: height + 8,
    };
  });

  const missingPort = (endpoint: { node: string; port?: string }): string | null => {
    const node = nodeById.get(endpoint.node);
    if (node === undefined) {
      return null;
    }
    return missingPortFor(node, interfaceForNode(node, index), endpoint.port);
  };

  const nodes: DiagramNode[] = doc.diagram.nodes.map((node) => {
    const iface = interfaceForNode(node, index);
    const layout = layouts.get(node.id) ?? layoutNode(iface);
    const position: ModelPoint = { x: node.position.x, y: node.position.y };
    if (iface.isJunction) {
      const data: JunctionNodeData = {
        nodeId: node.id,
        name: node.name,
        junction: iface.junction ?? "0",
        position,
      };
      return {
        id: node.id,
        type: "junction",
        position,
        data,
        selected: selectedNodes.has(node.id),
        connectable: true,
        deletable: false,
      };
    }
    const { portStates, portDomains } = portStateMap(
      iface,
      dragStates,
      analysis.portDomains,
      node.id,
    );
    const bond = isBondGraph(iface);
    const compact = isCompactBlock(iface);
    const outsideLabel = bond || compact;
    const offset = nodeVisualOffset(node, index);
    const labelNode =
      offset.x === 0 && offset.y === 0
        ? node
        : {
            ...node,
            position: {
              x: node.position.x + offset.x,
              y: node.position.y + offset.y,
            },
          };
    const data: BlockNodeData = {
      nodeId: node.id,
      name: node.name,
      interface: iface,
      layout,
      position,
      rotation: node.rotation ?? 0,
      flipX: node.flipX ?? false,
      portStates,
      portDomains,
      bond,
      compact,
      labelSide: outsideLabel
        ? bondLabelSide(
            labelNode,
            layout,
            nodeRects.filter((rect) => rect.id !== node.id),
          )
        : "bottom",
    };
    const type: "block" | "subsystem" = "subsystem" in node.block ? "subsystem" : "block";
    return {
      id: node.id,
      type,
      position,
      data,
      selected: selectedNodes.has(node.id),
      connectable: true,
      deletable: false,
    };
  });

  const edges: EditorEdge[] = doc.diagram.connections.map((connection) => {
    const anchors = connectionAnchors(doc, index, connection);
    const visual = analysis.connections.get(connection.id);
    const missingPorts = [missingPort(connection.from), missingPort(connection.to)].filter(
      (name): name is string => name !== null,
    );
    const data: EditorEdgeData = {
      kind: connection.kind,
      domain: visual?.domain ?? "Generic",
      baseDomain: visual?.domain ?? "Generic",
      signalType: visual?.signalType ?? null,
      route: (connection.route ?? []).map((point) => ({ x: point.x, y: point.y })),
      sourceAnchor: { point: anchors.source.point, side: anchors.source.side },
      targetAnchor: { point: anchors.target.point, side: anchors.target.side },
      wireHub: visual?.wireHub ?? null,
      label: connection.label ?? null,
      unitFactor: null,
      causalStroke: null,
      missingPorts,
      snap,
    };
    return {
      id: connection.id,
      type: connection.kind,
      source: connection.from.node,
      target: connection.to.node,
      sourceHandle: connection.from.port ?? junctionHandle(anchors.source.side),
      targetHandle: connection.to.port ?? junctionHandle(anchors.target.side),
      data,
      selected: selectedConnections.has(connection.id),
      selectable: true,
      deletable: false,
      reconnectable: false,
      interactionWidth: 18,
    };
  });

  return { nodes, edges, analysis };
}

/** Selected node ids for the traffic from xyflow back into the store. */
export function selectedIds(elements: readonly { id: string }[]): string[] {
  return elements.map((element) => element.id);
}

export type { Edge };
