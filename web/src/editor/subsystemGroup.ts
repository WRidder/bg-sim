/**
 * "Create subsystem from selection" (plan 7.4, W2.2).
 *
 * The selected nodes move into a new `subsystem` node's nested diagram, and
 * every connection with both ends selected moves with them. A connection with
 * exactly one selected end becomes a subsystem port: the port records the
 * internal node/port face, and the connection in the parent diagram is
 * rewritten to the subsystem node and that port name.
 *
 * The pure function returns the new parent diagram plus the pieces so the
 * store can commit the whole grouping as one undo entry.
 */

import type {
  Model,
  ModelConnection,
  ModelDiagram,
  ModelEndpoint,
  ModelNode,
  ModelSubsystemPort,
  ModelPoint,
} from "../contracts/model";
import type { CatalogIndex } from "../library/catalogIndex";
import { analyseDiagram } from "./connectionAnalysis";
import { descriptorForPort } from "./nodeInterface";
import { portNameFor, powerDomainFor, powerPortFor, signalPortFor } from "./subsystemPorts";
import { uniqueName } from "../state/ids";

export { portNameFor };

export interface SubsystemGroupInput {
  /** The diagram to group in; for a nested diagram this is the active view. */
  doc: Model;
  index: CatalogIndex;
  nodeIds: readonly string[];
  /** Id and instance name for the new subsystem node. */
  id: string;
  name: string;
}

export interface SubsystemGroupResult {
  /** The parent diagram after the grouping. */
  diagram: ModelDiagram;
  node: ModelNode;
  ports: ModelSubsystemPort[];
  /** The grouped nodes with positions rebased to the group's top-left. */
  internalNodes: ModelNode[];
  /** The connections whose both ends moved inside, routes rebased too. */
  internalConnections: ModelConnection[];
}

function round(value: number): number {
  return Math.round(value * 10) / 10;
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function endpoint(node: string, port: string | null): ModelEndpoint {
  return port === null || port.length === 0 ? { node } : { node, port };
}

function endpointKey(endpointValue: { node: string; port?: string }): string {
  return `${endpointValue.node}\u0000${endpointValue.port ?? ""}`;
}

/**
 * Group `nodeIds` (all in `doc.diagram`) into a subsystem. Returns null when
 * the selection is empty or names no node in this diagram.
 */
export function groupSelectionIntoSubsystem(
  input: SubsystemGroupInput,
): SubsystemGroupResult | null {
  const { doc, index, name, id } = input;
  const selected = new Set(input.nodeIds);
  const nodes = doc.diagram.nodes.filter((node) => selected.has(node.id));
  if (nodes.length === 0) {
    return null;
  }
  const analysis = analyseDiagram(doc, index);

  const originX = Math.min(...nodes.map((node) => node.position.x));
  const originY = Math.min(...nodes.map((node) => node.position.y));
  const origin: ModelPoint = { x: originX, y: originY };
  const rebasePoint = (point: ModelPoint): ModelPoint => ({
    x: round(point.x - origin.x),
    y: round(point.y - origin.y),
  });

  const internalNodes = nodes.map((node) => {
    const copy = clone(node);
    copy.position = rebasePoint(node.position);
    return copy;
  });

  const internalConnections: ModelConnection[] = [];
  const crossing: ModelConnection[] = [];
  const unrelated: ModelConnection[] = [];
  for (const connection of doc.diagram.connections) {
    const fromInside = selected.has(connection.from.node);
    const toInside = selected.has(connection.to.node);
    if (fromInside && toInside) {
      const copy = clone(connection);
      copy.route = (connection.route ?? []).map(rebasePoint);
      internalConnections.push(copy);
    } else if (fromInside !== toInside) {
      crossing.push(connection);
    } else {
      unrelated.push(connection);
    }
  }

  const ports: ModelSubsystemPort[] = [];
  const usedPortNames = new Set<string>();
  const rewritten = new Map<string, ModelConnection>();

  for (const connection of crossing) {
    const internalEnd = selected.has(connection.from.node)
      ? connection.from
      : connection.to;
    const externalEnd = endpointKey(internalEnd) === endpointKey(connection.from)
      ? connection.to
      : connection.from;
    const internalPort = internalEnd.port ?? null;
    const groupNode = doc.diagram.nodes.find((node) => node.id === internalEnd.node);
    if (groupNode === undefined) {
      continue;
    }
    const internalDescriptor = descriptorForPort(
      doc.diagram.nodes,
      index,
      internalEnd.node,
      internalPort,
    );
    const externalDescriptor = descriptorForPort(
      doc.diagram.nodes,
      index,
      externalEnd.node,
      externalEnd.port ?? null,
    );
    const portName = uniqueName(
      portNameFor(groupNode.name, internalPort),
      usedPortNames,
    );
    usedPortNames.add(portName);

    if (connection.kind === "signal") {
      // A signal always runs output -> input, so the internal end's position in
      // the connection is its direction even when an inline block's interface
      // has not been checked yet.
      const direction = endpointKey(internalEnd) === endpointKey(connection.from)
        ? "output"
        : "input";
      ports.push(
        signalPortFor({
          name: portName,
          direction,
          internal: internalDescriptor,
          external: externalDescriptor,
          node: internalEnd.node,
          port: internalPort,
        }),
      );
    } else {
      const adopted = analysis.connections.get(connection.id)?.domain;
      ports.push(
        powerPortFor({
          name: portName,
          domain: powerDomainFor(adopted, internalDescriptor, externalDescriptor),
          index,
          node: internalEnd.node,
          port: internalPort,
        }),
      );
    }

    const copy = clone(connection);
    // The outside route led to the old internal node; it no longer applies.
    copy.route = [];
    if (endpointKey(connection.from) === endpointKey(internalEnd)) {
      copy.from = endpoint(id, portName);
    } else {
      copy.to = endpoint(id, portName);
    }
    rewritten.set(connection.id, copy);
  }

  const centroid = {
    x: round(nodes.reduce((sum, node) => sum + node.position.x, 0) / nodes.length),
    y: round(nodes.reduce((sum, node) => sum + node.position.y, 0) / nodes.length),
  };

  const node: ModelNode = {
    id,
    name,
    block: {
      subsystem: {
        ports,
        diagram: {
          nodes: internalNodes,
          connections: internalConnections,
          subsystemPorts: [],
          annotations: [],
        },
      },
    },
    position: centroid,
    rotation: 0,
    flipX: false,
    params: {},
    constants: {},
    starts: {},
    ui: { showLabel: true, color: null },
  };

  const parentConnections: ModelConnection[] = [];
  for (const connection of doc.diagram.connections) {
    const fromInside = selected.has(connection.from.node);
    const toInside = selected.has(connection.to.node);
    if (fromInside && toInside) {
      continue;
    }
    if (fromInside !== toInside) {
      const copy = rewritten.get(connection.id);
      if (copy !== undefined) {
        parentConnections.push(copy);
      }
      continue;
    }
    parentConnections.push(connection);
  }

  return {
    diagram: {
      ...doc.diagram,
      nodes: [...doc.diagram.nodes.filter((entry) => !selected.has(entry.id)), node],
      connections: parentConnections,
    },
    node,
    ports,
    internalNodes,
    internalConnections,
  };
}
