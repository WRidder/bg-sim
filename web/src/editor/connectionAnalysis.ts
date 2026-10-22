/**
 * Diagram analysis for the canvas (plan 5.5, 5.6 and 7.3):
 *
 * * the domain of every connection, including domain adoption for Generic
 *   ports through bond islands;
 * * the shared hub of every wire component with 3 or more ports, so the canvas
 *   draws one dot per wire node;
 * * the compatible/incompatible state of every port while a connection drag is
 *   in progress.
 */

import type { DomainName, ValueType } from "../contracts/catalog";
import type { Model } from "../contracts/model";
import type { CatalogIndex } from "../library/catalogIndex";
import { checkConnection, portKey, type PortDescriptor } from "./connectionRules";
import { connectionAnchors, midpoint, nodeLayout, type Point } from "./geometry";
import { descriptorForPort } from "./nodeInterface";

export interface ConnectionVisual {
  domain: DomainName;
  signalType: ValueType | null;
  /** The shared wire node when 3+ ports join, else null. */
  wireHub: Point | null;
}

export interface DiagramAnalysis {
  connections: Map<string, ConnectionVisual>;
  /** Domain each power port draws; Generic ports inherit their island's domain. */
  portDomains: Map<string, DomainName>;
}

class UnionFind {
  private readonly parent = new Map<string, string>();

  find(key: string): string {
    const parent = this.parent.get(key);
    if (parent === undefined) {
      this.parent.set(key, key);
      return key;
    }
    if (parent === key) {
      return key;
    }
    const root = this.find(parent);
    this.parent.set(key, root);
    return root;
  }

  union(a: string, b: string): void {
    const rootA = this.find(a);
    const rootB = this.find(b);
    if (rootA !== rootB) {
      this.parent.set(rootB, rootA);
    }
  }
}

function endpointKey(node: string, port: string | null | undefined): string {
  return `${node}\u0000${port ?? ""}`;
}

function descriptor(
  doc: Model,
  index: CatalogIndex,
  node: string,
  port: string | null | undefined,
): PortDescriptor | null {
  return descriptorForPort(doc.diagram.nodes, index, node, port ?? null);
}

/**
 * The colour/domain view of every connection plus the adopted domain of every
 * Generic port.
 */
export function analyseDiagram(doc: Model, index: CatalogIndex): DiagramAnalysis {
  const connections = new Map<string, ConnectionVisual>();
  const portDomains = new Map<string, DomainName>();
  const uf = new UnionFind();

  const wireRoots = new Map<string, string>();
  const wirePorts = new Map<string, Set<string>>();
  const descriptors = new Map<string, PortDescriptor | null>();
  const descriptorByKey = new Map<string, PortDescriptor>();

  const getDescriptor = (node: string, port: string | null | undefined): PortDescriptor | null => {
    const key = endpointKey(node, port);
    if (descriptors.has(key)) {
      return descriptors.get(key) ?? null;
    }
    const value = descriptor(doc, index, node, port);
    descriptors.set(key, value);
    if (value !== null) {
      descriptorByKey.set(portKey(value), value);
    }
    return value;
  };

  for (const connection of doc.diagram.connections) {
    if (connection.kind === "wire") {
      const from = getDescriptor(connection.from.node, connection.from.port);
      const to = getDescriptor(connection.to.node, connection.to.port);
      if (from !== null && to !== null) {
        uf.union(portKey(from), portKey(to));
      }
    } else if (connection.kind === "bond") {
      uf.union(
        `node\u0000${connection.from.node}`,
        `node\u0000${connection.to.node}`,
      );
    }
  }

  // A second pass is needed because a later union can change a root.
  for (const connection of doc.diagram.connections) {
    if (connection.kind === "wire") {
      const from = getDescriptor(connection.from.node, connection.from.port);
      if (from !== null) {
        const root = uf.find(portKey(from));
        wireRoots.set(connection.id, root);
        const ports = wirePorts.get(root) ?? new Set<string>();
        const to = getDescriptor(connection.to.node, connection.to.port);
        ports.add(portKey(from));
        if (to !== null) {
          ports.add(portKey(to));
        }
        wirePorts.set(root, ports);
      }
    }
  }

  // Concrete domains seen through the ports that actually join an island.
  const bondDomains = new Map<string, Set<DomainName>>();
  for (const connection of doc.diagram.connections) {
    if (connection.kind !== "bond") {
      continue;
    }
    const root = uf.find(`node\u0000${connection.from.node}`);
    const domains = bondDomains.get(root) ?? new Set<DomainName>();
    for (const endpoint of [connection.from, connection.to]) {
      const port = getDescriptor(endpoint.node, endpoint.port);
      if (port !== null && port.kind === "power" && port.domain !== "Generic") {
        domains.add(port.domain);
      }
    }
    bondDomains.set(root, domains);
  }

  const adopted = new Map<string, DomainName>();
  for (const [root, domains] of bondDomains) {
    adopted.set(root, domains.size === 1 ? [...domains][0] ?? "Generic" : "Generic");
  }

  // Every power port's drawn domain; Generic ports inherit the island.
  for (const node of doc.diagram.nodes) {
    const layout = nodeLayout(node, index);
    for (const [portName] of layout.ports) {
      const port = getDescriptor(node.id, portName);
      if (port === null || port.kind !== "power") {
        continue;
      }
      let domain = port.domain;
      if (domain === "Generic") {
        const bonded = doc.diagram.connections.find(
          (connection) =>
            connection.kind === "bond" &&
            (endpointKey(connection.from.node, connection.from.port) ===
              endpointKey(port.nodeId, port.portName) ||
              endpointKey(connection.to.node, connection.to.port) ===
                endpointKey(port.nodeId, port.portName)),
        );
        if (bonded !== undefined) {
          const root = uf.find(`node\u0000${bonded.from.node}`);
          domain = adopted.get(root) ?? "Generic";
        }
      }
      portDomains.set(portKey(port), domain);
    }
  }

  const wireDomains = new Map<string, DomainName>();
  for (const [root, ports] of wirePorts) {
    const domains = new Set<DomainName>();
    for (const key of ports) {
      const port = descriptorByKey.get(key);
      if (port !== undefined && port.domain !== "Generic") {
        domains.add(port.domain);
      }
    }
    wireDomains.set(root, domains.size === 1 ? [...domains][0] ?? "Generic" : "Generic");
  }

  // A hub for a wire component of 3+ ports: the average of its port anchors.
  const wireHubs = new Map<string, Point>();
  for (const [root, ports] of wirePorts) {
    if (ports.size < 3) {
      continue;
    }
    const points: Point[] = [];
    for (const key of ports) {
      const [nodeId, portName] = key.split("\u0000");
      const node = doc.diagram.nodes.find((entry) => entry.id === nodeId);
      if (node === undefined) {
        continue;
      }
      const layout = nodeLayout(node, index);
      const anchor = layout.ports.get(portName ?? "");
      if (anchor !== undefined) {
        points.push({
          x: node.position.x + anchor.x,
          y: node.position.y + anchor.y,
        });
      }
    }
    if (points.length >= 3) {
      const x = points.reduce((sum, point) => sum + point.x, 0) / points.length;
      const y = points.reduce((sum, point) => sum + point.y, 0) / points.length;
      wireHubs.set(root, { x: Math.round(x * 10) / 10, y: Math.round(y * 10) / 10 });
    }
  }

  for (const connection of doc.diagram.connections) {
    if (connection.kind === "signal") {
      const from = getDescriptor(connection.from.node, connection.from.port);
      const to = getDescriptor(connection.to.node, connection.to.port);
      connections.set(connection.id, {
        domain: "Generic",
        signalType: from?.type ?? to?.type ?? null,
        wireHub: null,
      });
      continue;
    }
    if (connection.kind === "bond") {
      const root = uf.find(`node\u0000${connection.from.node}`);
      connections.set(connection.id, {
        domain: adopted.get(root) ?? "Generic",
        signalType: null,
        wireHub: null,
      });
      continue;
    }
    const root = wireRoots.get(connection.id);
    connections.set(connection.id, {
      domain: root === undefined ? "Generic" : (wireDomains.get(root) ?? "Generic"),
      signalType: null,
      wireHub: root === undefined ? null : (wireHubs.get(root) ?? null),
    });
  }

  // Record every wire port's domain so the port glyph shows the adopted colour.
  for (const [root, ports] of wirePorts) {
    const domain = wireDomains.get(root) ?? "Generic";
    for (const key of ports) {
      if (!portDomains.has(key)) {
        portDomains.set(key, domain);
      }
    }
  }

  return { connections, portDomains };
}

export type PortDragState = "idle" | "compatible" | "incompatible" | "origin";

/**
 * For each port, whether a connection from `origin` would be accepted. The
 * dragged port itself is `origin`; ports on the same node are incompatible.
 */
export function dragCompatibility(
  doc: Model,
  index: CatalogIndex,
  origin: PortDescriptor | null,
): Map<string, PortDragState> {
  const states = new Map<string, PortDragState>();
  for (const node of doc.diagram.nodes) {
    const layout = nodeLayout(node, index);
    const names: (string | null)[] =
      layout.ports.size === 0
        ? [null]
        : [...layout.ports.keys()];
    for (const name of names) {
      const port = descriptorForPort(doc.diagram.nodes, index, node.id, name);
      if (port === null) {
        continue;
      }
      if (origin === null) {
        states.set(portKey(port), "idle");
        continue;
      }
      if (portKey(port) === portKey(origin)) {
        states.set(portKey(port), "origin");
        continue;
      }
      states.set(
        portKey(port),
        checkConnection(doc, origin, port).ok ? "compatible" : "incompatible",
      );
    }
  }
  return states;
}

/** The label position for a connection: the midpoint of its two anchors. */
export function connectionLabelPoint(
  doc: Model,
  index: CatalogIndex,
  connectionId: string,
): Point {
  const connection = doc.diagram.connections.find((entry) => entry.id === connectionId);
  if (connection === undefined) {
    return { x: 0, y: 0 };
  }
  const anchors = connectionAnchors(doc, index, connection);
  return midpoint(anchors.source.point, anchors.target.point);
}
