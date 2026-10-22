/**
 * Document factories (plan 3.3): an empty model, a block instance and a
 * junction instance. Every optional field the schema allows is written
 * explicitly, so a document round-trips through the backend's pydantic model
 * without gaining or losing keys.
 */

import type { CatalogBlock } from "../contracts/catalog";
import type {
  ConnectionKind,
  JunctionType,
  Model,
  ModelConnection,
  ModelEndpoint,
  ModelNode,
  ModelPoint,
} from "../contracts/model";

export const LANGUAGE_VERSION = "0.1.0";

export function emptyDiagram(): Model["diagram"] {
  return { nodes: [], connections: [], subsystemPorts: [], annotations: [] };
}

/** A new, unsaved model document. */
export function createEmptyModel(name: string, language: string = LANGUAGE_VERSION): Model {
  return {
    format: "bgsim.model",
    language,
    name,
    diagram: emptyDiagram(),
    settings: {
      t_start: 0,
      t_end: 1,
      solver: "auto",
      reltol: 1e-6,
      abstol: 1e-8,
      max_step: null,
      output: { mode: "points", points: 5000 },
      event_limit: 10000,
    },
    plots: [],
    scene: null,
    bindings: [],
  };
}

/** Initial parameter map: every catalog default as an expression string. */
export function defaultParams(block: CatalogBlock): Record<string, string> {
  const params: Record<string, string> = {};
  for (const parameter of block.parameters) {
    params[parameter.name] = parameter.default;
  }
  return params;
}

export function createNodeFromBlock(
  block: CatalogBlock,
  position: ModelPoint,
  id: string,
  name: string,
): ModelNode {
  return {
    id,
    name,
    block: { ref: block.ref },
    position: { x: position.x, y: position.y },
    rotation: 0,
    flipX: false,
    params: defaultParams(block),
    constants: {},
    starts: {},
    ui: { showLabel: true, color: null },
  };
}

export function createJunctionNode(
  junction: JunctionType,
  position: ModelPoint,
  id: string,
  name: string,
): ModelNode {
  return {
    id,
    name,
    block: { junction },
    position: { x: position.x, y: position.y },
    rotation: 0,
    flipX: false,
    params: {},
    constants: {},
    starts: {},
    ui: { showLabel: true, color: null },
  };
}

/** An endpoint for a connection; junction endpoints carry no port (plan 3.3). */
export function endpoint(nodeId: string, port: string | null): ModelEndpoint {
  return port === null || port === "" ? { node: nodeId } : { node: nodeId, port };
}

export function createConnection(
  id: string,
  kind: ConnectionKind,
  from: ModelEndpoint,
  to: ModelEndpoint,
): ModelConnection {
  return { id, kind, from, to, route: [], label: null };
}

/** True for a junction node (`block.junction`). */
export function isJunctionNode(node: ModelNode): boolean {
  return "junction" in node.block;
}

/** The catalog ref of a node, or null for a junction/inline/subsystem node. */
export function nodeRef(node: ModelNode): string | null {
  return "ref" in node.block ? node.block.ref : null;
}
