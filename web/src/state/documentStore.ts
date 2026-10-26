/**
 * The document store (plan 7.4): every mutation is an immer producer whose
 * patches go on a 200-entry undo stack.
 *
 * Design points:
 *
 * * **Undo/redo from the first edit.** `produceWithPatches` returns forward and
 *   inverse patches; undo applies the inverse, redo the forward patch set. No
 *   command replays its logic, so a command can never drift from the document.
 * * **Gestures coalesce.** A node drag calls `beginGesture("node-drag")` once
 *   and `setNodePositions` per mouse move. The first move pushes an entry; the
 *   later moves extend its patches and prepend their inverse patches, so one
 *   drag is one undo step.
 * * **Selection and clipboard are not history.** Clicking around never changes
 *   the undo stack.
 * * **The document is the only source of truth.** The canvas and the inspector
 *   render `doc`; nothing keeps a second copy of a position or a connection.
 */

import { applyPatches, enablePatches, produceWithPatches, type Patch } from "immer";
import { create } from "zustand";

import type { CatalogBlock } from "../contracts/catalog";
import type {
  ConnectionKind,
  JunctionType,
  Model,
  ModelConnection,
  ModelConstantValue,
  ModelDiagram,
  ModelNode,
  ModelPoint,
} from "../contracts/model";
import {
  checkConnection,
  type ConnectionCheck,
  type PortDescriptor,
} from "../editor/connectionRules";
import {
  activeDiagram,
  activeModel,
  allConnectionIds,
  allNodeIds,
  clampPath,
} from "../editor/subsystemPath";
import { groupSelectionIntoSubsystem } from "../editor/subsystemGroup";
import type { CatalogIndex } from "../library/catalogIndex";
import {
  createConnection,
  createEmptyModel,
  createJunctionNode,
  createNodeFromBlock,
  endpoint,
} from "./modelFactory";
import { nextId, uniqueName } from "./ids";

enablePatches();

export const HISTORY_LIMIT = 200;
export const PASTE_OFFSET = 24;

export type DocumentStatus = "idle" | "loading" | "ready" | "error";
export type SaveState = "idle" | "dirty" | "saving" | "saved" | "error";
/** The two inline code node flavours of plan 7.7. */
export type InlineBlockKind = "equation" | "discrete";

export interface Selection {
  nodes: string[];
  connections: string[];
}

export interface HistoryEntry {
  patches: Patch[];
  inversePatches: Patch[];
}

export interface Clipboard {
  nodes: ModelNode[];
  connections: ModelConnection[];
}

export interface ConnectResult {
  ok: boolean;
  reason?: string;
  id?: string;
  kind?: ConnectionKind;
}

/** Result of an inspector edit command; the message is user-facing. */
export interface EditResult {
  ok: boolean;
  error?: string;
}

/** Instance names are path segments (plan 3.1); the schema is the source. */
export const NODE_NAME_PATTERN = /^[A-Za-z_][A-Za-z0-9_]*$/;

/**
 * Why `name` cannot be an instance name for `nodeId`, or null when it can.
 * Names must be identifiers and unique within their diagram (plan 3.1).
 */
export function nodeNameIssue(
  nodes: readonly ModelNode[],
  nodeId: string,
  name: string,
): string | null {
  if (name.length === 0) {
    return "Enter a name.";
  }
  if (!NODE_NAME_PATTERN.test(name)) {
    return "Names start with a letter or underscore and use only letters, digits and underscores.";
  }
  const clash = nodes.find((node) => node.id !== nodeId && node.name === name);
  if (clash !== undefined) {
    return `The diagram already has a block named "${name}".`;
  }
  return null;
}

export interface DocumentActions {
  openDocument: (
    project: string,
    modelName: string,
    doc: Model,
    options?: { persisted?: boolean },
  ) => void;
  setStatus: (status: DocumentStatus, error?: string | null) => void;
  setSaving: () => void;
  setSaved: (revision: number) => void;
  setSaveError: (message: string) => void;

  addBlock: (block: CatalogBlock, position: ModelPoint) => string | null;
  addJunction: (junction: JunctionType, position: ModelPoint) => string | null;
  /**
   * Add an inline Equation or Discrete-code node (plan 7.4/7.7). The caller
   * supplies the source template; `position` defaults to a free grid slot.
   */
  addInlineBlock: (
    kind: InlineBlockKind,
    source: string,
    position?: ModelPoint,
  ) => string | null;

  beginGesture: (key: string) => void;
  endGesture: () => void;
  setNodePositions: (positions: Record<string, ModelPoint>, coalesce?: boolean) => void;

  setSelection: (nodes: readonly string[], connections: readonly string[]) => void;
  /** Enter a subsystem node of the active diagram (plan 7.4). */
  enterSubsystem: (nodeId: string) => boolean;
  /** Leave one subsystem level; Esc uses this (plan 7.5/7.8). */
  leaveSubsystem: () => void;
  /** Move to a path of subsystem node ids from the root; invalid tails drop. */
  navigateToPath: (path: readonly string[]) => void;
  /** Open the diagram at `path` and select `nodeId` there (model tree). */
  selectNodeAt: (path: readonly string[], nodeId: string) => boolean;
  /** Group the selection into a new subsystem (plan 7.4, W2.2). */
  createSubsystem: (index: CatalogIndex) => EditResult;
  deleteSelection: () => void;
  rotateSelection: () => void;
  flipSelection: () => void;
  copySelection: () => void;
  paste: () => void;
  reverseConnection: (id: string) => void;

  connect: (a: PortDescriptor, b: PortDescriptor) => ConnectResult;

  /** Rename a node; refuses invalid identifiers and sibling name clashes. */
  renameNode: (nodeId: string, name: string) => EditResult;
  /** Set one parameter expression string (plan 3.3 `params`). */
  setNodeParam: (nodeId: string, name: string, value: string) => EditResult;
  /** Set one constant override, or remove it with null (plan 3.3 `constants`). */
  setNodeConstant: (
    nodeId: string,
    name: string,
    value: ModelConstantValue | null,
  ) => EditResult;
  /** Set one start-value override, or remove it with null (plan 3.3 `starts`). */
  setNodeStart: (nodeId: string, name: string, value: string | null) => EditResult;
  /** Re-point a library instance, used by "Copy to project library" (plan 7.4). */
  setNodeBlockRef: (nodeId: string, ref: string) => EditResult;
  /**
   * Replace the embedded source of an inline code node (plan 7.7). Pass
   * `coalesce` while the editor has a typing gesture open so one editing
   * session is one undo step.
   */
  setInlineSource: (
    nodeId: string,
    source: string,
    options?: { coalesce?: boolean },
  ) => EditResult;

  undo: () => void;
  redo: () => void;
}

export interface DocumentState {
  project: string | null;
  modelName: string | null;
  doc: Model | null;
  status: DocumentStatus;
  loadError: string | null;
  /** Increments on every document mutation (including undo/redo). */
  revision: number;
  /** The revision whose content is on disk. */
  savedRevision: number;
  saveState: SaveState;
  saveError: string | null;
  past: HistoryEntry[];
  future: HistoryEntry[];
  selection: Selection;
  /** Subsystem node ids from the root to the diagram being edited. */
  activePath: string[];
  clipboard: Clipboard;
  /** The key of the gesture currently in progress, or null. */
  gestureKey: string | null;
  lastHistKey: string | null;
}

export type DocumentStore = DocumentState & DocumentActions;

const EMPTY_SELECTION: Selection = { nodes: [], connections: [] };
const EMPTY_CLIPBOARD: Clipboard = { nodes: [], connections: [] };

const INITIAL_STATE: DocumentState = {
  project: null,
  modelName: null,
  doc: null,
  status: "idle",
  loadError: null,
  revision: 0,
  savedRevision: 0,
  saveState: "idle",
  saveError: null,
  past: [],
  future: [],
  selection: EMPTY_SELECTION,
  activePath: [],
  clipboard: EMPTY_CLIPBOARD,
  gestureKey: null,
  lastHistKey: null,
};

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function roundPosition(point: ModelPoint): ModelPoint {
  return {
    x: Math.round(point.x * 10) / 10,
    y: Math.round(point.y * 10) / 10,
  };
}

function sameIds(a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && a.every((id, index) => id === b[index]);
}

/** Drop ids that a deletion or undo removed from the active diagram. */
function pruneSelection(doc: Model, path: readonly string[], selection: Selection): Selection {
  const diagram = activeDiagram(doc, path);
  if (diagram === null) {
    return EMPTY_SELECTION;
  }
  const nodeIds = new Set(diagram.nodes.map((node) => node.id));
  const connectionIds = new Set(diagram.connections.map((connection) => connection.id));
  const nodes = selection.nodes.filter((id) => nodeIds.has(id));
  const connections = selection.connections.filter((id) => connectionIds.has(id));
  if (sameIds(nodes, selection.nodes) && sameIds(connections, selection.connections)) {
    return selection;
  }
  return { nodes, connections };
}

function isJunction(node: ModelNode): boolean {
  return "junction" in node.block;
}

/** A free grid slot for a new code node when the caller does not give one. */
function inlineNodePosition(nodes: readonly ModelNode[]): ModelPoint {
  const columns = 3;
  const index = nodes.length;
  return {
    x: 80 + (index % columns) * 260,
    y: 80 + Math.floor(index / columns) * 180,
  };
}

export const useDocumentStore = create<DocumentStore>()((set, get) => {
  /**
   * Run a recipe on the document and record it. Returns the new document, or
   * null when nothing changed or no model is open.
   */
  const commit = (
    recipe: (draft: Model) => void,
    options: { coalesce?: string } = {},
  ): Model | null => {
    const state = get();
    const doc = state.doc;
    if (doc === null) {
      return null;
    }
    const [next, patches, inversePatches] = produceWithPatches(doc, recipe);
    if (patches.length === 0) {
      return next;
    }

    const key = options.coalesce ?? null;
    const merge =
      key !== null &&
      state.gestureKey === key &&
      state.lastHistKey === key &&
      state.past.length > 0;

    let past: HistoryEntry[];
    if (merge) {
      const top = state.past[state.past.length - 1];
      if (top === undefined) {
        past = [{ patches, inversePatches }];
      } else {
        past = [
          ...state.past.slice(0, -1),
          {
            patches: [...top.patches, ...patches],
            // Undo applies inverse patches in order, so the newest inverse
            // patches go first.
            inversePatches: [...inversePatches, ...top.inversePatches],
          },
        ];
      }
    } else {
      past = [...state.past, { patches, inversePatches }];
      if (past.length > HISTORY_LIMIT) {
        past = past.slice(past.length - HISTORY_LIMIT);
      }
    }

    const activePath = clampPath(next, state.activePath);
    set({
      doc: next,
      revision: state.revision + 1,
      past,
      future: [],
      saveState: "dirty",
      saveError: null,
      lastHistKey: key,
      activePath,
      selection: pruneSelection(next, activePath, state.selection),
    });
    return next;
  };

  /** The diagram open in the editor, or null when the path no longer resolves. */
  const currentDiagram = (): ModelDiagram | null => {
    const state = get();
    return state.doc === null ? null : activeDiagram(state.doc, state.activePath);
  };

  /** Run a recipe against the active diagram; the single path-aware shape. */
  const commitActive = (
    recipe: (diagram: ModelDiagram) => void,
    options: { coalesce?: string } = {},
  ): Model | null => {
    const path = [...get().activePath];
    return commit((draft) => {
      const diagram = activeDiagram(draft, path);
      if (diagram !== null) {
        recipe(diagram);
      }
    }, options);
  };

  const addNode = (node: ModelNode): string | null => {
    const state = get();
    if (state.doc === null || currentDiagram() === null) {
      return null;
    }
    const next = commitActive((diagram) => {
      diagram.nodes.push(node);
    });
    if (next === null) {
      return null;
    }
    set({ selection: { nodes: [node.id], connections: [] } });
    return node.id;
  };

  return {
    ...INITIAL_STATE,

    openDocument: (project, modelName, doc, options = {}) =>
      set({
        project,
        modelName,
        doc: clone(doc),
        status: "ready",
        loadError: null,
        revision: 0,
        // A model that does not exist on disk yet starts dirty so the
        // auto-save creates its file without waiting for the first edit.
        savedRevision: options.persisted === false ? -1 : 0,
        saveState: options.persisted === false ? "dirty" : "saved",
        saveError: null,
        past: [],
        future: [],
        selection: EMPTY_SELECTION,
        activePath: [],
        clipboard: EMPTY_CLIPBOARD,
        gestureKey: null,
        lastHistKey: null,
      }),

    setStatus: (status, error = null) =>
      set({ status, loadError: error }),

    setSaving: () => set({ saveState: "saving", saveError: null }),

    setSaved: (revision) =>
      set((state) => ({
        savedRevision: revision,
        saveState: state.revision === revision ? "saved" : "dirty",
      })),

    setSaveError: (message) => set({ saveState: "error", saveError: message }),

    addBlock: (block, position) => {
      const doc = get().doc;
      const diagram = currentDiagram();
      if (doc === null || diagram === null) {
        return null;
      }
      const id = nextId("n", allNodeIds(doc));
      const name = uniqueName(
        block.name,
        diagram.nodes.map((node) => node.name),
      );
      const node = createNodeFromBlock(block, roundPosition(position), id, name);
      return addNode(node);
    },

    addJunction: (junction, position) => {
      const doc = get().doc;
      const diagram = currentDiagram();
      if (doc === null || diagram === null) {
        return null;
      }
      const id = nextId("n", allNodeIds(doc));
      const name = uniqueName(
        `Junction${junction}`,
        diagram.nodes.map((node) => node.name),
      );
      const node = createJunctionNode(junction, roundPosition(position), id, name);
      return addNode(node);
    },

    addInlineBlock: (kind, source, position) => {
      const doc = get().doc;
      const diagram = currentDiagram();
      if (doc === null || diagram === null) {
        return null;
      }
      const id = nextId("n", allNodeIds(doc));
      const name = uniqueName(
        kind === "equation" ? "Equation" : "DiscreteCode",
        diagram.nodes.map((node) => node.name),
      );
      const node: ModelNode = {
        id,
        name,
        block: { inline: { source } },
        position: roundPosition(position ?? inlineNodePosition(diagram.nodes)),
        rotation: 0,
        flipX: false,
        params: {},
        constants: {},
        starts: {},
        ui: { showLabel: true, color: null },
      };
      return addNode(node);
    },

    beginGesture: (key) => set({ gestureKey: key, lastHistKey: null }),

    endGesture: () => set({ gestureKey: null, lastHistKey: null }),

    setNodePositions: (positions, coalesce = true) => {
      const entries = Object.entries(positions);
      if (entries.length === 0) {
        return;
      }
      commitActive(
        (diagram) => {
          for (const [id, position] of entries) {
            const node = diagram.nodes.find((entry) => entry.id === id);
            if (node !== undefined) {
              node.position = roundPosition(position);
            }
          }
        },
        coalesce ? { coalesce: "node-drag" } : {},
      );
    },

    setSelection: (nodes, connections) => {
      const state = get();
      const doc = state.doc;
      const nodeList = [...new Set(nodes)];
      const connectionList = [...new Set(connections)];
      const selection =
        doc === null
          ? { nodes: nodeList, connections: connectionList }
          : pruneSelection(doc, state.activePath, {
              nodes: nodeList,
              connections: connectionList,
            });
      if (
        sameIds(selection.nodes, state.selection.nodes) &&
        sameIds(selection.connections, state.selection.connections)
      ) {
        return;
      }
      set({ selection });
    },

    enterSubsystem: (nodeId) => {
      const state = get();
      const doc = state.doc;
      const diagram = currentDiagram();
      if (doc === null || diagram === null) {
        return false;
      }
      const node = diagram.nodes.find((entry) => entry.id === nodeId);
      if (node === undefined || !("subsystem" in node.block)) {
        return false;
      }
      set({
        activePath: [...state.activePath, nodeId],
        selection: EMPTY_SELECTION,
        gestureKey: null,
        lastHistKey: null,
      });
      return true;
    },

    leaveSubsystem: () => {
      const state = get();
      if (state.activePath.length === 0) {
        return;
      }
      set({
        activePath: state.activePath.slice(0, -1),
        selection: EMPTY_SELECTION,
        gestureKey: null,
        lastHistKey: null,
      });
    },

    navigateToPath: (path) => {
      const state = get();
      if (state.doc === null) {
        return;
      }
      const activePath = clampPath(state.doc, path);
      if (
        sameIds(activePath, state.activePath) &&
        state.selection.nodes.length === 0 &&
        state.selection.connections.length === 0
      ) {
        return;
      }
      set({
        activePath,
        selection: EMPTY_SELECTION,
        gestureKey: null,
        lastHistKey: null,
      });
    },

    selectNodeAt: (path, nodeId) => {
      const state = get();
      const doc = state.doc;
      if (doc === null) {
        return false;
      }
      const activePath = clampPath(doc, path);
      const diagram = activeDiagram(doc, activePath);
      if (diagram === null || !diagram.nodes.some((node) => node.id === nodeId)) {
        return false;
      }
      set({
        activePath,
        selection: { nodes: [nodeId], connections: [] },
        gestureKey: null,
        lastHistKey: null,
      });
      return true;
    },

    createSubsystem: (index) => {
      const state = get();
      const doc = state.doc;
      if (doc === null) {
        return { ok: false, error: "No model is open." };
      }
      const view = activeModel(doc, state.activePath);
      if (view === null) {
        return { ok: false, error: "The open diagram no longer exists." };
      }
      if (state.selection.nodes.length === 0) {
        return { ok: false, error: "Select the blocks to group first." };
      }
      const id = nextId("n", allNodeIds(doc));
      const name = uniqueName(
        "Subsystem1",
        view.diagram.nodes.map((node) => node.name),
      );
      const grouped = groupSelectionIntoSubsystem({
        doc: view,
        index,
        nodeIds: state.selection.nodes,
        id,
        name,
      });
      if (grouped === null) {
        return { ok: false, error: "The selection has no blocks to group." };
      }
      commitActive((diagram) => {
        diagram.nodes = grouped.diagram.nodes;
        diagram.connections = grouped.diagram.connections;
      });
      set({ selection: { nodes: [id], connections: [] } });
      return { ok: true };
    },

    deleteSelection: () => {
      const diagram = currentDiagram();
      const { selection } = get();
      if (diagram === null) {
        return;
      }
      const nodes = new Set(selection.nodes);
      const connections = new Set(selection.connections);
      if (nodes.size === 0 && connections.size === 0) {
        return;
      }
      commitActive((draft) => {
        draft.nodes = draft.nodes.filter((node) => !nodes.has(node.id));
        draft.connections = draft.connections.filter(
          (connection) =>
            !connections.has(connection.id) &&
            !nodes.has(connection.from.node) &&
            !nodes.has(connection.to.node),
        );
      });
      set({ selection: EMPTY_SELECTION });
    },

    rotateSelection: () => {
      const { selection } = get();
      if (selection.nodes.length === 0) {
        return;
      }
      const nodes = new Set(selection.nodes);
      commitActive((diagram) => {
        for (const node of diagram.nodes) {
          if (nodes.has(node.id) && !isJunction(node)) {
            node.rotation = ((node.rotation ?? 0) + 90) % 360;
          }
        }
      });
    },

    flipSelection: () => {
      const { selection } = get();
      if (selection.nodes.length === 0) {
        return;
      }
      const nodes = new Set(selection.nodes);
      commitActive((diagram) => {
        for (const node of diagram.nodes) {
          if (nodes.has(node.id) && !isJunction(node)) {
            node.flipX = !(node.flipX ?? false);
          }
        }
      });
    },

    copySelection: () => {
      const diagram = currentDiagram();
      const { selection } = get();
      if (diagram === null || selection.nodes.length === 0) {
        return;
      }
      const selected = new Set(selection.nodes);
      const nodes = diagram.nodes
        .filter((node) => selected.has(node.id))
        .map((node) => clone(node));
      const nodeIds = new Set(nodes.map((node) => node.id));
      const connections = diagram.connections
        .filter(
          (connection) =>
            nodeIds.has(connection.from.node) && nodeIds.has(connection.to.node),
        )
        .map((connection) => clone(connection));
      set({ clipboard: { nodes, connections } });
    },

    paste: () => {
      const doc = get().doc;
      const diagram = currentDiagram();
      const { clipboard } = get();
      if (doc === null || diagram === null || clipboard.nodes.length === 0) {
        return;
      }
      const existingNodeIds = new Set(allNodeIds(doc));
      const existingConnectionIds = new Set(allConnectionIds(doc));
      const existingNames = new Set(diagram.nodes.map((node) => node.name));
      const idMap = new Map<string, string>();
      const pastedNodes: ModelNode[] = [];

      for (const node of clipboard.nodes) {
        const id = nextId("n", existingNodeIds);
        existingNodeIds.add(id);
        idMap.set(node.id, id);
        const name = uniqueName(node.name, existingNames);
        existingNames.add(name);
        pastedNodes.push({
          ...clone(node),
          id,
          name,
          position: {
            x: Math.round((node.position.x + PASTE_OFFSET) * 10) / 10,
            y: Math.round((node.position.y + PASTE_OFFSET) * 10) / 10,
          },
        });
      }

      const pastedConnections: ModelConnection[] = [];
      for (const connection of clipboard.connections) {
        const from = idMap.get(connection.from.node);
        const to = idMap.get(connection.to.node);
        if (from === undefined || to === undefined) {
          continue;
        }
        const id = nextId("c", existingConnectionIds);
        existingConnectionIds.add(id);
        pastedConnections.push({
          ...clone(connection),
          id,
          from: { ...clone(connection.from), node: from },
          to: { ...clone(connection.to), node: to },
        });
      }

      commitActive((draft) => {
        draft.nodes.push(...pastedNodes);
        draft.connections.push(...pastedConnections);
      });
      set({
        selection: { nodes: pastedNodes.map((node) => node.id), connections: [] },
      });
    },

    reverseConnection: (id) => {
      const diagram = currentDiagram();
      if (diagram === null) {
        return;
      }
      commitActive((draft) => {
        const connection = draft.connections.find((entry) => entry.id === id);
        if (connection === undefined) {
          return;
        }
        const from = { node: connection.from.node, port: connection.from.port };
        connection.from = { node: connection.to.node, port: connection.to.port };
        connection.to = from;
        connection.route = [...(connection.route ?? [])].reverse();
      });
    },

    connect: (a, b) => {
      const state = get();
      const doc = state.doc;
      if (doc === null) {
        return { ok: false, reason: "No model is open" };
      }
      const view = activeModel(doc, state.activePath);
      const diagram = currentDiagram();
      if (view === null || diagram === null) {
        return { ok: false, reason: "The open diagram no longer exists" };
      }
      const result: ConnectionCheck = checkConnection(view, a, b);
      if (!result.ok) {
        return { ok: false, reason: result.reason };
      }
      const id = nextId("c", allConnectionIds(doc));
      const connection = createConnection(
        id,
        result.kind,
        endpoint(result.from.nodeId, result.from.portName),
        endpoint(result.to.nodeId, result.to.portName),
      );
      commitActive((draft) => {
        draft.connections.push(connection);
      });
      return { ok: true, id, kind: result.kind };
    },

    renameNode: (nodeId, name) => {
      const doc = get().doc;
      const diagram = currentDiagram();
      if (doc === null || diagram === null) {
        return { ok: false, error: "No model is open." };
      }
      const node = diagram.nodes.find((entry) => entry.id === nodeId);
      if (node === undefined) {
        return { ok: false, error: "That block is no longer in the diagram." };
      }
      const next = name.trim();
      const issue = nodeNameIssue(diagram.nodes, nodeId, next);
      if (issue !== null) {
        return { ok: false, error: issue };
      }
      if (next === node.name) {
        return { ok: true };
      }
      commitActive((draft) => {
        const target = draft.nodes.find((entry) => entry.id === nodeId);
        if (target !== undefined) {
          target.name = next;
        }
      });
      return { ok: true };
    },

    setNodeParam: (nodeId, name, value) => {
      const diagram = currentDiagram();
      if (diagram === null) {
        return { ok: false, error: "No model is open." };
      }
      if (!diagram.nodes.some((entry) => entry.id === nodeId)) {
        return { ok: false, error: "That block is no longer in the diagram." };
      }
      const text = value.trim();
      if (text.length === 0) {
        return { ok: false, error: "Enter a value." };
      }
      commitActive((draft) => {
        const node = draft.nodes.find((entry) => entry.id === nodeId);
        if (node !== undefined) {
          node.params = { ...(node.params ?? {}), [name]: text };
        }
      });
      return { ok: true };
    },

    setNodeConstant: (nodeId, name, value) => {
      const diagram = currentDiagram();
      if (diagram === null) {
        return { ok: false, error: "No model is open." };
      }
      if (!diagram.nodes.some((entry) => entry.id === nodeId)) {
        return { ok: false, error: "That block is no longer in the diagram." };
      }
      commitActive((draft) => {
        const node = draft.nodes.find((entry) => entry.id === nodeId);
        if (node === undefined) {
          return;
        }
        if (value === null) {
          if (node.constants !== undefined) {
            delete node.constants[name];
          }
        } else {
          node.constants = { ...(node.constants ?? {}), [name]: value };
        }
      });
      return { ok: true };
    },

    setNodeStart: (nodeId, name, value) => {
      const diagram = currentDiagram();
      if (diagram === null) {
        return { ok: false, error: "No model is open." };
      }
      if (!diagram.nodes.some((entry) => entry.id === nodeId)) {
        return { ok: false, error: "That block is no longer in the diagram." };
      }
      const text = value?.trim() ?? "";
      commitActive((draft) => {
        const node = draft.nodes.find((entry) => entry.id === nodeId);
        if (node === undefined) {
          return;
        }
        if (text.length === 0) {
          if (node.starts !== undefined) {
            delete node.starts[name];
          }
        } else {
          node.starts = { ...(node.starts ?? {}), [name]: text };
        }
      });
      return { ok: true };
    },

    setNodeBlockRef: (nodeId, ref) => {
      const diagram = currentDiagram();
      if (diagram === null) {
        return { ok: false, error: "No model is open." };
      }
      const node = diagram.nodes.find((entry) => entry.id === nodeId);
      if (node === undefined) {
        return { ok: false, error: "That block is no longer in the diagram." };
      }
      if (!("ref" in node.block)) {
        return { ok: false, error: "Only library blocks can be re-pointed." };
      }
      const next = ref.trim();
      if (next.length === 0) {
        return { ok: false, error: "Enter a block reference." };
      }
      if (node.block.ref === next) {
        return { ok: true };
      }
      commitActive((draft) => {
        const target = draft.nodes.find((entry) => entry.id === nodeId);
        if (target !== undefined) {
          target.block = { ref: next };
        }
      });
      return { ok: true };
    },

    setInlineSource: (nodeId, source, options = {}) => {
      const diagram = currentDiagram();
      if (diagram === null) {
        return { ok: false, error: "No model is open." };
      }
      const node = diagram.nodes.find((entry) => entry.id === nodeId);
      if (node === undefined) {
        return { ok: false, error: "That block is no longer in the diagram." };
      }
      if (!("inline" in node.block)) {
        return { ok: false, error: "Only inline code nodes have editable embedded source." };
      }
      if (node.block.inline.source === source) {
        return { ok: true };
      }
      const next = commitActive(
        (draft) => {
          const target = draft.nodes.find((entry) => entry.id === nodeId);
          if (target !== undefined && "inline" in target.block) {
            target.block.inline.source = source;
          }
        },
        options.coalesce === true ? { coalesce: `inline-source:${nodeId}` } : {},
      );
      if (next === null) {
        return { ok: false, error: "No model is open." };
      }
      return { ok: true };
    },

    undo: () => {
      const state = get();
      const doc = state.doc;
      const entry = state.past[state.past.length - 1];
      if (doc === null || entry === undefined) {
        return;
      }
      const next = applyPatches(doc, entry.inversePatches);
      const activePath = clampPath(next, state.activePath);
      set({
        doc: next,
        past: state.past.slice(0, -1),
        future: [...state.future, entry],
        revision: state.revision + 1,
        saveState: "dirty",
        saveError: null,
        selection: pruneSelection(next, activePath, state.selection),
        activePath,
        gestureKey: null,
        lastHistKey: null,
      });
    },

    redo: () => {
      const state = get();
      const doc = state.doc;
      const entry = state.future[state.future.length - 1];
      if (doc === null || entry === undefined) {
        return;
      }
      const next = applyPatches(doc, entry.patches);
      const activePath = clampPath(next, state.activePath);
      set({
        doc: next,
        past: [...state.past, entry],
        future: state.future.slice(0, -1),
        revision: state.revision + 1,
        saveState: "dirty",
        saveError: null,
        selection: pruneSelection(next, activePath, state.selection),
        activePath,
        gestureKey: null,
        lastHistKey: null,
      });
    },
  };
});

/** Reset every field (and keep the actions); used by tests and on unload. */
export function resetDocumentStore(): void {
  useDocumentStore.setState(INITIAL_STATE);
}

export const selectIsDirty = (state: DocumentState): boolean =>
  state.doc !== null && state.revision !== state.savedRevision;

export const selectCanUndo = (state: DocumentState): boolean => state.past.length > 0;
export const selectCanRedo = (state: DocumentState): boolean => state.future.length > 0;

/** A fresh, unsaved document, for callers that need one without the store. */
export function newModel(name: string, language?: string): Model {
  return createEmptyModel(name, language);
}
