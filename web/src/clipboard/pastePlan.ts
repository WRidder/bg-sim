/**
 * The document side of a paste: fresh ids (unique across the whole document, nested
 * subsystems included), instance names unique in the target diagram, the placement of
 * the pasted group, and the rewrites the dependency resolution decided (renamed or
 * inlined library blocks, renamed globals, renamed data files). Pure; the document
 * store commits the result as one undo step.
 */

import type {
  ModelAnnotation,
  ModelConnection,
  ModelDiagram,
  ModelNode,
  ModelPoint,
  ModelShape,
} from "../contracts/model";
import { GRID_SIZE } from "../editor/geometry";
import { renameIdentifier } from "../inspector/expression";
import { nextId, uniqueName } from "../state/ids";
import { PROJECT_PREFIX, renameBlockUses } from "./dependencies";

export interface PasteRewrites {
  /** `project:Old` -> `project:New` (a renamed import, or the target's block of another case). */
  refs?: Readonly<Record<string, string>>;
  /** `project:Name` -> the block source: these nodes become inline blocks. */
  inline?: Readonly<Record<string, string>>;
  /** Global renames, applied to every pasted param, start and string constant. */
  globals?: Readonly<Record<string, string>>;
  /**
   * Data file constants (`file` of a CsvSource or ModalBody3D), `data/a.csv` -> `data/a2.csv`,
   * `data/b.modal.json` -> `data/b2.modal.json`.
   */
  dataFiles?: Readonly<Record<string, string>>;
  /** Project blocks instantiated by pasted inline sources under a new name, old -> new. */
  blockRenames?: Readonly<Record<string, string>>;
}

export interface ClipContent {
  nodes: readonly ModelNode[];
  connections: readonly ModelConnection[];
  annotations: readonly ModelAnnotation[];
  shapes: readonly ModelShape[];
}

export interface PrepareInput {
  clip: ClipContent;
  /** The diagram that receives the paste. */
  diagram: ModelDiagram;
  /** Every node id of the document (nested included). */
  nodeIds: Iterable<string>;
  /** Every connection id of the document (nested included). */
  connectionIds: Iterable<string>;
  /** Where the centre of the pasted group goes; null keeps the copied positions plus `offset`. */
  at: ModelPoint | null;
  /** Extra shift (flow units, both axes): the paste offset, or a cascade of repeated pastes. */
  offset: number;
  rewrites?: PasteRewrites;
}

export interface PreparedPaste {
  nodes: ModelNode[];
  connections: ModelConnection[];
  annotations: ModelAnnotation[];
  shapes: ModelShape[];
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function round(value: number): number {
  return Math.round(value * 10) / 10;
}

/** The bounding box centre of a clip (node positions, note and shape frames). */
export function clipCentre(clip: ClipContent): ModelPoint | null {
  const xs: number[] = [];
  const ys: number[] = [];
  for (const node of clip.nodes) {
    xs.push(node.position.x);
    ys.push(node.position.y);
  }
  for (const frame of [...clip.annotations, ...clip.shapes]) {
    xs.push(frame.x, frame.x + frame.w);
    ys.push(frame.y, frame.y + frame.h);
  }
  if (xs.length === 0) {
    return null;
  }
  return {
    x: (Math.min(...xs) + Math.max(...xs)) / 2,
    y: (Math.min(...ys) + Math.max(...ys)) / 2,
  };
}

/** The shift that puts the clip's centre at `at` (whole grid steps, so a snapped layout stays snapped). */
export function placementDelta(clip: ClipContent, at: ModelPoint | null, offset: number): ModelPoint {
  if (at === null) {
    return { x: offset, y: offset };
  }
  const centre = clipCentre(clip);
  if (centre === null) {
    return { x: offset, y: offset };
  }
  return {
    x: Math.round((at.x - centre.x) / GRID_SIZE) * GRID_SIZE + offset,
    y: Math.round((at.y - centre.y) / GRID_SIZE) * GRID_SIZE + offset,
  };
}

function rewriteExpressions(node: ModelNode, renames: Readonly<Record<string, string>>): void {
  const entries = Object.entries(renames).filter(([from, to]) => from !== to);
  if (entries.length === 0) {
    return;
  }
  const apply = (text: string): string =>
    entries.reduce((value, [from, to]) => renameIdentifier(value, from, to), text);
  for (const map of [node.params, node.starts]) {
    if (map === undefined) {
      continue;
    }
    for (const [key, text] of Object.entries(map)) {
      map[key] = apply(text);
    }
  }
  for (const [key, value] of Object.entries(node.constants ?? {})) {
    if (typeof value === "string" && node.constants !== undefined) {
      node.constants[key] = apply(value);
    }
  }
}

/** Apply the dependency rewrites to one node (in place, not recursive). */
function rewriteNode(node: ModelNode, rewrites: PasteRewrites): void {
  if ("ref" in node.block) {
    const ref = node.block.ref;
    if (ref.startsWith(PROJECT_PREFIX)) {
      const inline = rewrites.inline?.[ref];
      if (inline !== undefined) {
        node.block = { inline: { source: inline } };
      } else {
        const next = rewrites.refs?.[ref];
        if (next !== undefined) {
          node.block = { ref: next };
        }
      }
    }
    const file = node.constants?.file;
    if (typeof file === "string" && node.constants !== undefined) {
      const renamed = rewrites.dataFiles?.[file];
      if (renamed !== undefined) {
        node.constants.file = renamed;
      }
    }
  }
  if ("inline" in node.block && rewrites.blockRenames !== undefined) {
    const source = Object.entries(rewrites.blockRenames).reduce(
      (text, [from, to]) => renameBlockUses(text, from, to),
      node.block.inline.source,
    );
    if (source !== node.block.inline.source) {
      node.block = { inline: { ...node.block.inline, source } };
    }
  }
  if (rewrites.globals !== undefined) {
    rewriteExpressions(node, rewrites.globals);
  }
}

interface IdPools {
  nodes: Set<string>;
  connections: Set<string>;
}

/**
 * Give every node and connection of a nested diagram a fresh id, remap the connection
 * ends and the exposed ports, and apply the rewrites; names stay (they are unique in
 * their own diagram already).
 */
function renumberNested(diagram: ModelDiagram, pools: IdPools, rewrites: PasteRewrites, ports: { node: string }[]): void {
  const map = new Map<string, string>();
  for (const node of diagram.nodes) {
    const id = nextId("n", pools.nodes);
    pools.nodes.add(id);
    map.set(node.id, id);
    node.id = id;
    rewriteNode(node, rewrites);
    if ("subsystem" in node.block) {
      const subsystem = node.block.subsystem;
      renumberNested(subsystem.diagram, pools, rewrites, [
        ...subsystem.ports,
        ...(subsystem.diagram.subsystemPorts ?? []),
      ]);
    }
  }
  const connections: ModelConnection[] = [];
  for (const connection of diagram.connections) {
    const from = map.get(connection.from.node);
    const to = map.get(connection.to.node);
    if (from === undefined || to === undefined) {
      continue;
    }
    const id = nextId("c", pools.connections);
    pools.connections.add(id);
    connections.push({ ...connection, id, from: { ...connection.from, node: from }, to: { ...connection.to, node: to } });
  }
  diagram.connections = connections;
  for (const port of ports) {
    const mapped = map.get(port.node);
    if (mapped !== undefined) {
      port.node = mapped;
    }
  }
  // Probes observe signal paths of the source model; they never travel.
  delete diagram.probes;
}

/** The elements a paste adds to `input.diagram`, ready to be pushed. */
export function preparePaste(input: PrepareInput): PreparedPaste {
  const { clip, diagram } = input;
  const rewrites = input.rewrites ?? {};
  const delta = placementDelta(clip, input.at, input.offset);
  const move = (point: ModelPoint): ModelPoint => ({ x: round(point.x + delta.x), y: round(point.y + delta.y) });

  const pools: IdPools = {
    nodes: new Set(input.nodeIds),
    connections: new Set(input.connectionIds),
  };
  const names = new Set(diagram.nodes.map((node) => node.name));
  const idMap = new Map<string, string>();
  const nodes: ModelNode[] = [];
  for (const original of clip.nodes) {
    const node = clone(original);
    const id = nextId("n", pools.nodes);
    pools.nodes.add(id);
    idMap.set(original.id, id);
    const name = uniqueName(node.name, names);
    names.add(name);
    node.id = id;
    node.name = name;
    node.position = move(node.position);
    rewriteNode(node, rewrites);
    if ("subsystem" in node.block) {
      const subsystem = node.block.subsystem;
      renumberNested(subsystem.diagram, pools, rewrites, [
        ...subsystem.ports,
        ...(subsystem.diagram.subsystemPorts ?? []),
      ]);
    }
    nodes.push(node);
  }

  const connections: ModelConnection[] = [];
  for (const original of clip.connections) {
    const from = idMap.get(original.from.node);
    const to = idMap.get(original.to.node);
    // A connection to an element that was not copied stays behind.
    if (from === undefined || to === undefined) {
      continue;
    }
    const id = nextId("c", pools.connections);
    pools.connections.add(id);
    const connection = clone(original);
    connection.id = id;
    connection.from = { ...connection.from, node: from };
    connection.to = { ...connection.to, node: to };
    if (connection.route !== undefined) {
      connection.route = connection.route.map(move);
    }
    connections.push(connection);
  }

  const noteIds = new Set((diagram.annotations ?? []).map((note) => note.id));
  const annotations = clip.annotations.map((original) => {
    const id = nextId("a", noteIds);
    noteIds.add(id);
    const at = move({ x: original.x, y: original.y });
    return { ...clone(original), id, x: at.x, y: at.y };
  });

  // Pasted shapes land in front of the other shapes, unlocked (a copy is placed by hand).
  const shapeIds = new Set((diagram.shapes ?? []).map((shape) => shape.id));
  const shapes = clip.shapes.map((original) => {
    const id = nextId("s", shapeIds);
    shapeIds.add(id);
    const at = move({ x: original.x, y: original.y });
    const shape: ModelShape = { ...clone(original), id, x: at.x, y: at.y };
    delete shape.locked;
    return shape;
  });

  return { nodes, connections, annotations, shapes };
}
