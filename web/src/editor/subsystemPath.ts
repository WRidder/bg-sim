/**
 * Path-aware document navigation (plan 3.1, 5.2 and 7.4).
 *
 * A subsystem node nests the same diagram shape as the model root, so the
 * editor edits "the active diagram": the root, or one reached by entering
 * subsystem nodes. `activePath` in the document store is the list of subsystem
 * node ids from the root to the open diagram. Everything here is a pure
 * function of a document and that path, which is what lets the store route
 * every command through one `activeDiagram` lookup.
 */

import type { Model, ModelDiagram } from "../contracts/model";

/**
 * The diagram at `path`, or null when a segment is missing or is not a
 * subsystem node (for example after an undo removed it).
 */
export function activeDiagram(
  doc: Pick<Model, "diagram">,
  path: readonly string[],
): ModelDiagram | null {
  let diagram = doc.diagram;
  for (const id of path) {
    const node = diagram.nodes.find((entry) => entry.id === id);
    if (node === undefined || !("subsystem" in node.block)) {
      return null;
    }
    diagram = node.block.subsystem.diagram;
  }
  return diagram;
}

/** The document as the editor sees it: `doc` with its active diagram in place. */
export function activeModel(doc: Model, path: readonly string[]): Model | null {
  if (path.length === 0) {
    return doc;
  }
  const diagram = activeDiagram(doc, path);
  return diagram === null ? null : { ...doc, diagram };
}

/** The longest prefix of `path` that still resolves; used after undo/redo. */
export function clampPath(doc: Pick<Model, "diagram">, path: readonly string[]): string[] {
  const result: string[] = [];
  let diagram = doc.diagram;
  for (const id of path) {
    const node = diagram.nodes.find((entry) => entry.id === id);
    if (node === undefined || !("subsystem" in node.block)) {
      break;
    }
    result.push(id);
    diagram = node.block.subsystem.diagram;
  }
  return result;
}

export interface SubsystemCrumb {
  /** The subsystem node id, which is also the path segment. */
  id: string;
  /** The instance name shown on the crumb. */
  name: string;
}

/** The named crumb for every segment of `path`; invalid trailing segments drop. */
export function subsystemPathCrumbs(
  doc: Pick<Model, "diagram">,
  path: readonly string[],
): SubsystemCrumb[] {
  const crumbs: SubsystemCrumb[] = [];
  let diagram = doc.diagram;
  for (const id of path) {
    const node = diagram.nodes.find((entry) => entry.id === id);
    if (node === undefined || !("subsystem" in node.block)) {
      break;
    }
    crumbs.push({ id, name: node.name });
    diagram = node.block.subsystem.diagram;
  }
  return crumbs;
}

/** Every node id in the document, nested diagrams included. */
export function allNodeIds(doc: Pick<Model, "diagram">): string[] {
  const ids: string[] = [];
  const walk = (diagram: ModelDiagram): void => {
    for (const node of diagram.nodes) {
      ids.push(node.id);
      if ("subsystem" in node.block) {
        walk(node.block.subsystem.diagram);
      }
    }
  };
  walk(doc.diagram);
  return ids;
}

/** Every connection id in the document, nested diagrams included. */
export function allConnectionIds(doc: Pick<Model, "diagram">): string[] {
  const ids: string[] = [];
  const walk = (diagram: ModelDiagram): void => {
    for (const connection of diagram.connections) {
      ids.push(connection.id);
    }
    for (const node of diagram.nodes) {
      if ("subsystem" in node.block) {
        walk(node.block.subsystem.diagram);
      }
    }
  };
  walk(doc.diagram);
  return ids;
}
