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
  ModelNode,
  ModelPoint,
} from "../contracts/model";
import {
  checkConnection,
  type ConnectionCheck,
  type PortDescriptor,
} from "../editor/connectionRules";
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

  beginGesture: (key: string) => void;
  endGesture: () => void;
  setNodePositions: (positions: Record<string, ModelPoint>, coalesce?: boolean) => void;

  setSelection: (nodes: readonly string[], connections: readonly string[]) => void;
  deleteSelection: () => void;
  rotateSelection: () => void;
  flipSelection: () => void;
  copySelection: () => void;
  paste: () => void;
  reverseConnection: (id: string) => void;

  connect: (a: PortDescriptor, b: PortDescriptor) => ConnectResult;

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

/** Drop ids that a deletion or undo removed from the document. */
function pruneSelection(doc: Model, selection: Selection): Selection {
  const nodeIds = new Set(doc.diagram.nodes.map((node) => node.id));
  const connectionIds = new Set(doc.diagram.connections.map((connection) => connection.id));
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

    set({
      doc: next,
      revision: state.revision + 1,
      past,
      future: [],
      saveState: "dirty",
      saveError: null,
      lastHistKey: key,
      selection: pruneSelection(next, state.selection),
    });
    return next;
  };

  const addNode = (node: ModelNode): string | null => {
    const state = get();
    if (state.doc === null) {
      return null;
    }
    const next = commit((draft) => {
      draft.diagram.nodes.push(node);
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
      if (doc === null) {
        return null;
      }
      const id = nextId(
        "n",
        doc.diagram.nodes.map((node) => node.id),
      );
      const name = uniqueName(
        block.name,
        doc.diagram.nodes.map((node) => node.name),
      );
      const node = createNodeFromBlock(block, roundPosition(position), id, name);
      return addNode(node);
    },

    addJunction: (junction, position) => {
      const doc = get().doc;
      if (doc === null) {
        return null;
      }
      const id = nextId(
        "n",
        doc.diagram.nodes.map((node) => node.id),
      );
      const name = uniqueName(
        `Junction${junction}`,
        doc.diagram.nodes.map((node) => node.name),
      );
      const node = createJunctionNode(junction, roundPosition(position), id, name);
      return addNode(node);
    },

    beginGesture: (key) => set({ gestureKey: key, lastHistKey: null }),

    endGesture: () => set({ gestureKey: null, lastHistKey: null }),

    setNodePositions: (positions, coalesce = true) => {
      const entries = Object.entries(positions);
      if (entries.length === 0) {
        return;
      }
      commit(
        (draft) => {
          for (const [id, position] of entries) {
            const node = draft.diagram.nodes.find((entry) => entry.id === id);
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
          : pruneSelection(doc, { nodes: nodeList, connections: connectionList });
      if (
        sameIds(selection.nodes, state.selection.nodes) &&
        sameIds(selection.connections, state.selection.connections)
      ) {
        return;
      }
      set({ selection });
    },

    deleteSelection: () => {
      const { doc, selection } = get();
      if (doc === null) {
        return;
      }
      const nodes = new Set(selection.nodes);
      const connections = new Set(selection.connections);
      if (nodes.size === 0 && connections.size === 0) {
        return;
      }
      commit((draft) => {
        draft.diagram.nodes = draft.diagram.nodes.filter((node) => !nodes.has(node.id));
        draft.diagram.connections = draft.diagram.connections.filter(
          (connection) =>
            !connections.has(connection.id) &&
            !nodes.has(connection.from.node) &&
            !nodes.has(connection.to.node),
        );
      });
      set({ selection: EMPTY_SELECTION });
    },

    rotateSelection: () => {
      const { doc, selection } = get();
      if (doc === null || selection.nodes.length === 0) {
        return;
      }
      const nodes = new Set(selection.nodes);
      commit((draft) => {
        for (const node of draft.diagram.nodes) {
          if (nodes.has(node.id) && !isJunction(node)) {
            node.rotation = ((node.rotation ?? 0) + 90) % 360;
          }
        }
      });
    },

    flipSelection: () => {
      const { doc, selection } = get();
      if (doc === null || selection.nodes.length === 0) {
        return;
      }
      const nodes = new Set(selection.nodes);
      commit((draft) => {
        for (const node of draft.diagram.nodes) {
          if (nodes.has(node.id) && !isJunction(node)) {
            node.flipX = !(node.flipX ?? false);
          }
        }
      });
    },

    copySelection: () => {
      const { doc, selection } = get();
      if (doc === null || selection.nodes.length === 0) {
        return;
      }
      const selected = new Set(selection.nodes);
      const nodes = doc.diagram.nodes
        .filter((node) => selected.has(node.id))
        .map((node) => clone(node));
      const nodeIds = new Set(nodes.map((node) => node.id));
      const connections = doc.diagram.connections
        .filter(
          (connection) =>
            nodeIds.has(connection.from.node) && nodeIds.has(connection.to.node),
        )
        .map((connection) => clone(connection));
      set({ clipboard: { nodes, connections } });
    },

    paste: () => {
      const { doc, clipboard } = get();
      if (doc === null || clipboard.nodes.length === 0) {
        return;
      }
      const existingNodeIds = new Set(doc.diagram.nodes.map((node) => node.id));
      const existingConnectionIds = new Set(
        doc.diagram.connections.map((connection) => connection.id),
      );
      const existingNames = new Set(doc.diagram.nodes.map((node) => node.name));
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

      commit((draft) => {
        draft.diagram.nodes.push(...pastedNodes);
        draft.diagram.connections.push(...pastedConnections);
      });
      set({
        selection: { nodes: pastedNodes.map((node) => node.id), connections: [] },
      });
    },

    reverseConnection: (id) => {
      const { doc } = get();
      if (doc === null) {
        return;
      }
      commit((draft) => {
        const connection = draft.diagram.connections.find((entry) => entry.id === id);
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
      const doc = get().doc;
      if (doc === null) {
        return { ok: false, reason: "No model is open" };
      }
      const result: ConnectionCheck = checkConnection(doc, a, b);
      if (!result.ok) {
        return { ok: false, reason: result.reason };
      }
      const id = nextId(
        "c",
        doc.diagram.connections.map((connection) => connection.id),
      );
      const connection = createConnection(
        id,
        result.kind,
        endpoint(result.from.nodeId, result.from.portName),
        endpoint(result.to.nodeId, result.to.portName),
      );
      commit((draft) => {
        draft.diagram.connections.push(connection);
      });
      return { ok: true, id, kind: result.kind };
    },

    undo: () => {
      const state = get();
      const doc = state.doc;
      const entry = state.past[state.past.length - 1];
      if (doc === null || entry === undefined) {
        return;
      }
      const next = applyPatches(doc, entry.inversePatches);
      set({
        doc: next,
        past: state.past.slice(0, -1),
        future: [...state.future, entry],
        revision: state.revision + 1,
        saveState: "dirty",
        saveError: null,
        selection: pruneSelection(next, state.selection),
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
      set({
        doc: next,
        past: [...state.past, entry],
        future: state.future.slice(0, -1),
        revision: state.revision + 1,
        saveState: "dirty",
        saveError: null,
        selection: pruneSelection(next, state.selection),
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
