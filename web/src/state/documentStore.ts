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
  AnnotationColor,
  Binding,
  ConnectionKind,
  JunctionType,
  Model,
  ModelAnnotation,
  ModelConnection,
  ModelConstantValue,
  ModelDashboard,
  ModelDiagram,
  ModelGlobalParameter,
  ModelNode,
  ModelNodeImage,
  ModelPoint,
  ModelProbePanel,
  ModelShape,
  ProbeKind,
  ShapeKind,
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
import {
  applyParameterChanges as applyChangesToDraft,
  type ParameterChange,
} from "../debug/panels/editsModel";
import { nodeImageIssue } from "../editor/nodeImage";
import {
  type EditPlan,
  type FieldRef,
  type GlobalPatch,
  planAddGlobal,
  planDeleteGlobal,
  planMoveGlobal,
  planRenameGlobal,
  planSetField,
  planUpdateGlobal,
} from "../globals/globalEdits";
import { groupSelectionIntoSubsystem } from "../editor/subsystemGroup";
import { terminalId, terminalPortName } from "../editor/subsystemBoundary";
import {
  exposedOneLevelUp,
  exposedPortFor,
  outsideConnections,
  subsystemAtPath,
  subsystemPortNameIssue,
  type TerminalKind,
} from "../editor/subsystemPorts";
import type { CatalogIndex } from "../library/catalogIndex";
import { probeSignalOptions } from "../probe/probeSignals";
import {
  createConnection,
  createEmptyModel,
  createJunctionNode,
  createNodeFromBlock,
  endpoint,
} from "./modelFactory";
import { nextId, uniqueName } from "./ids";
import {
  NOTE_DEFAULT_SIZE,
  NOTE_MIN_SIZE,
  noteFlowId,
  noteIdOf,
  selectedNoteIds,
} from "../editor/notes";
import {
  applyShapeStyle,
  isLineKind,
  isLocked,
  reorderShapes as reorderShapeList,
  SHAPE_DEFAULT_SIZE,
  SHAPE_MIN_SIZE,
  shapeFlowId,
  shapeIdOf,
  shapeOriginAt,
  selectedShapeIds,
  type ShapeOrder,
  type ShapeStylePatch,
} from "../editor/shapes";

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
  /** Sticky notes (diagram.annotations) of the copied selection. */
  annotations: ModelAnnotation[];
  /** Background shapes (diagram.shapes) of the copied selection, back to front. */
  shapes: ModelShape[];
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
  /** Replace a connection's ordered waypoints (one undo entry). */
  setConnectionRoute: (id: string, route: readonly ModelPoint[]) => void;

  /** Add an oscilloscope probe (a 3x3 block or a floating plot window). */
  addProbe: (
    kind: ProbeKind,
    position: ModelPoint,
    panelPosition: ModelPoint,
  ) => string | null;
  deleteProbe: (id: string) => void;
  setProbePosition: (id: string, position: ModelPoint, coalesce?: boolean) => void;
  setProbeFrame: (
    id: string,
    frame: { x: number; y: number; width: number; height: number },
  ) => void;
  setProbeOpen: (id: string, open: boolean) => void;
  addProbeLink: (probeId: string, connectionId: string) => string | null;
  removeProbeLink: (probeId: string, linkId: string) => void;
  setProbeLinkSignals: (probeId: string, linkId: string, signals: readonly string[]) => void;
  setProbePanels: (probeId: string, panels: readonly ModelProbePanel[]) => void;

  /** Replace the model's viewer bindings (plan 7.6 binding editor); one undo entry, `[]` removes the field. */
  setBindings: (bindings: readonly Binding[]) => void;
  /**
   * Edit the dashboard (DASHBOARD_PLAN.md) in one undo entry; an empty dashboard is removed.
   * `coalesce` merges a gesture (a slider drag) into one entry, like node moves.
   */
  editDashboard: (
    recipe: (dashboard: ModelDashboard) => void,
    options?: { coalesce?: string },
  ) => void;

  connect: (a: PortDescriptor, b: PortDescriptor) => ConnectResult;

  /** Rename a node; refuses invalid identifiers and sibling name clashes. */
  renameNode: (nodeId: string, name: string) => EditResult;
  /** Set one parameter expression string (plan 3.3 `params`). */
  setNodeParam: (nodeId: string, name: string, value: string) => EditResult;
  /**
   * Write edited parameter values (by instance path) into the model as one undo
   * entry (M4 debug: "Save parameters to model"). Returns the targets no block answers to.
   */
  applyParameterChanges: (changes: readonly ParameterChange[]) => string[];
  /** Set one constant override, or remove it with null (plan 3.3 `constants`). */
  setNodeConstant: (
    nodeId: string,
    name: string,
    value: ModelConstantValue | null,
  ) => EditResult;
  /** Set one start-value override, or remove it with null (plan 3.3 `starts`). */
  setNodeStart: (nodeId: string, name: string, value: string | null) => EditResult;

  /** Global parameters (the Equations manager); each edit is one undo step. */
  addGlobalParameter: (init?: Partial<ModelGlobalParameter>) => EditResult & { name?: string };
  updateGlobalParameter: (name: string, patch: GlobalPatch) => EditResult;
  /** Rename a global and rewrite every whole-identifier reference in the model. */
  renameGlobalParameter: (name: string, next: string) => EditResult;
  /** Refused while any block field or other global still uses it. */
  deleteGlobalParameter: (name: string) => EditResult;
  moveGlobalParameter: (name: string, toIndex: number) => EditResult;
  /** Set a params/starts/constants expression of any node in the model (the Equations view). */
  setFieldExpression: (field: FieldRef, text: string) => EditResult;
  /**
   * Set the image drawn in a subsystem card (plan 3.3 `ui.image`), or remove it with null.
   * The caller has already fitted the image into the 512 KiB limit (editor/nodeImage.ts).
   */
  setNodeImage: (nodeId: string, image: ModelNodeImage | null) => EditResult;
  /** Change how the image fills the card: `contain` keeps the aspect ratio, `stretch` fills. */
  setNodeImageFit: (nodeId: string, fit: ModelNodeImage["fit"]) => EditResult;
  /** Re-point a library instance, used by "Copy to project library" (plan 7.4). */
  setNodeBlockRef: (nodeId: string, ref: string) => EditResult;
  /**
   * Turn inline code nodes, anywhere in the model, into instances of the
   * library block `ref` ("Save to project library", plan 7.7) in ONE undo
   * step. Name, position, params, constants, starts and look are kept; only
   * `block` changes. Ids that are not inline nodes are ignored; it fails when
   * none is.
   */
  replaceInlineWithRef: (nodeIds: readonly string[], ref: string) => EditResult & { replaced?: string[] };
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

  /**
   * Inside a subsystem: expose an internal port as a new subsystem port (one
   * undo entry). Kind, direction, type, size, unit and domain come from the
   * internal port; the name is proposed from it and made unique. `wanted` is
   * the "+ input" / "+ output" / "+ power" target the port was dropped on.
   * The new port's terminal is selected.
   */
  exposeSubsystemPort: (
    index: CatalogIndex,
    internal: PortDescriptor,
    wanted?: TerminalKind,
  ) => EditResult & { name?: string };
  /** Rename an exposed port of the open subsystem; outside connections follow. */
  renameSubsystemPort: (name: string, next: string) => EditResult;
  /** Remove exposed ports of the open subsystem and their outside connections (one undo entry). */
  deleteSubsystemPorts: (names: readonly string[]) => EditResult;
  /** Store where the terminals of exposed ports sit (`ui.position`); a drag coalesces. */
  setSubsystemPortPositions: (positions: Record<string, ModelPoint>, coalesce?: boolean) => void;
  /**
   * Leave the subsystem and select the outside connections of exposed port
   * `name` (or the subsystem node when it has none). Returns the selected ids.
   */
  revealSubsystemPort: (name: string) => { nodeId: string; connections: string[] } | null;

  /**
   * Add a sticky note (a `diagram.annotations` entry) to the active diagram at
   * `position` (its top-left corner) and select it. Returns its canvas id
   * (`note:<id>`), or null when no model is open.
   */
  addNote: (
    position: ModelPoint,
    options?: { text?: string; color?: AnnotationColor; size?: { w: number; h: number } },
  ) => string | null;
  /**
   * Replace a note's Markdown text. Pass `coalesce` while an editing session
   * has a `note-text:<id>` gesture open, so one session is one undo step.
   */
  setNoteText: (id: string, text: string, options?: { coalesce?: boolean }) => void;
  /** Colour notes by annotation id (yellow removes the field: absent means yellow). */
  setNoteColor: (ids: readonly string[], color: AnnotationColor) => void;
  /** Move and resize a note; a resize drag coalesces into one undo step. */
  setNoteFrame: (
    id: string,
    frame: { x: number; y: number; w: number; h: number },
    coalesce?: boolean,
  ) => void;

  /**
   * Add a background shape (a `diagram.shapes` entry) in front of the other
   * shapes of the active diagram, at `position` (its top-left corner, or a
   * line's start), and select it. Returns its canvas id (`shape:<id>`).
   */
  addShape: (
    kind: ShapeKind,
    position: ModelPoint,
    options?: { size?: { w: number; h: number }; style?: ShapeStylePatch; text?: string },
  ) => string | null;
  /** Restyle shapes by shape id (a default value removes its field). */
  setShapeStyle: (ids: readonly string[], patch: ShapeStylePatch, options?: { coalesce?: string }) => void;
  /** Replace a shape's label; `coalesce` makes one undo step of a typing session. */
  setShapeText: (id: string, text: string, options?: { coalesce?: boolean }) => void;
  /**
   * Move and resize an unlocked shape: a rectangle kind's frame (with a
   * minimum size), or a line's start and `w`/`h` to its end.
   */
  setShapeFrame: (
    id: string,
    frame: { x: number; y: number; w: number; h: number },
    coalesce?: string,
  ) => void;
  /** Lock or unlock shapes by shape id (unlocked removes the field). */
  setShapeLocked: (ids: readonly string[], locked: boolean) => void;
  /** Change the z order of shapes by shape id (one undo step; a no-op adds none). */
  reorderShapes: (ids: readonly string[], order: ShapeOrder) => void;
  /** Copy shapes in front of all shapes, offset and unlocked, and select the copies. */
  duplicateShapes: (ids: readonly string[]) => string[];

  undo: () => void;
  redo: () => void;
}

/**
 * The outside connections deleting exposed ports `names` of the subsystem at
 * `path` removes; the canvas confirms first when there are any.
 */
export function subsystemPortDeleteImpact(
  doc: Model,
  path: readonly string[],
  names: readonly string[],
): ModelConnection[] {
  const found = subsystemAtPath(doc, path);
  if (found === null) {
    return [];
  }
  const seen = new Set<string>();
  const result: ModelConnection[] = [];
  for (const name of names) {
    for (const connection of outsideConnections(found.parent, found.node.id, name)) {
      if (!seen.has(connection.id)) {
        seen.add(connection.id);
        result.push(connection);
      }
    }
  }
  return result;
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
const EMPTY_CLIPBOARD: Clipboard = { nodes: [], connections: [], annotations: [], shapes: [] };

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

/**
 * Copies of `shapes` for a paste or a duplicate: fresh ids next to `existing`,
 * offset by the paste offset and unlocked (a copy is placed by hand).
 */
function copiedShapes(shapes: readonly ModelShape[], existing: readonly ModelShape[]): ModelShape[] {
  const ids = new Set(existing.map((shape) => shape.id));
  return shapes.map((shape) => {
    const id = nextId("s", ids);
    ids.add(id);
    const copy: ModelShape = {
      ...clone(shape),
      id,
      x: Math.round((shape.x + PASTE_OFFSET) * 10) / 10,
      y: Math.round((shape.y + PASTE_OFFSET) * 10) / 10,
    };
    delete copy.locked;
    return copy;
  });
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
  const nodeIds = new Set([
    ...diagram.nodes.map((node) => node.id),
    ...(diagram.probes ?? []).map((probe) => probe.id),
    // Inside a subsystem the exposed ports' terminals are selectable too.
    ...(subsystemAtPath(doc, path)?.node.block.subsystem.ports ?? []).map((port) =>
      terminalId(port.name),
    ),
    // Sticky notes are canvas nodes `note:<id>`.
    ...(diagram.annotations ?? []).map((note) => noteFlowId(note.id)),
    // Background shapes are canvas nodes `shape:<id>`.
    ...(diagram.shapes ?? []).map((shape) => shapeFlowId(shape.id)),
  ]);
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

/**
 * Remove exposed ports `names` of the subsystem at `path` from a draft, with
 * every parent-diagram connection on them and the probe links on those.
 */
function removeSubsystemPorts(root: Model, path: readonly string[], names: readonly string[]): void {
  const found = subsystemAtPath(root, path);
  if (found === null) {
    return;
  }
  const { node, parent } = found;
  const removed = new Set(names);
  node.block.subsystem.ports = node.block.subsystem.ports.filter((port) => !removed.has(port.name));
  const dropped = new Set(
    names.flatMap((name) => outsideConnections(parent, node.id, name).map((connection) => connection.id)),
  );
  if (dropped.size === 0) {
    return;
  }
  parent.connections = parent.connections.filter((connection) => !dropped.has(connection.id));
  if (parent.probes !== undefined) {
    for (const probe of parent.probes) {
      probe.links = probe.links.filter((link) => !dropped.has(link.connection));
    }
  }
}

/** The next grid slot of a new code node: three columns after the existing nodes. */
export function inlineNodePosition(nodes: readonly ModelNode[]): ModelPoint {
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

  /** Validate an edit against the open document, then commit its recipe as one step. */
  const runPlan = (plan: (doc: Model) => EditPlan): EditResult & { name?: string } => {
    const doc = get().doc;
    if (doc === null) {
      return { ok: false, error: "No model is open." };
    }
    const result = plan(doc);
    if (!result.ok) {
      return { ok: false, error: result.error };
    }
    commit(result.recipe);
    return result.name === undefined ? { ok: true } : { ok: true, name: result.name };
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
            // A dragged sticky note (`note:<id>`) moves its annotation.
            const noteId = noteIdOf(id);
            if (noteId !== null) {
              const note = (diagram.annotations ?? []).find((entry) => entry.id === noteId);
              if (note !== undefined) {
                const rounded = roundPosition(position);
                note.x = rounded.x;
                note.y = rounded.y;
              }
              continue;
            }
            // A dragged shape (`shape:<id>`; the position is its canvas node's
            // box, a line's padded bounds) moves its frame; a locked one stays.
            const shapeId = shapeIdOf(id);
            if (shapeId !== null) {
              const shape = (diagram.shapes ?? []).find((entry) => entry.id === shapeId);
              if (shape !== undefined && !isLocked(shape)) {
                const rounded = roundPosition(shapeOriginAt(shape, position));
                shape.x = rounded.x;
                shape.y = rounded.y;
              }
              continue;
            }
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
      const notes = new Set(selectedNoteIds(selection.nodes));
      // A locked shape survives Del (and stays selected); unlock it to delete it.
      const lockedShapes = new Set(
        (diagram.shapes ?? []).filter((shape) => isLocked(shape)).map((shape) => shape.id),
      );
      const shapes = new Set(selectedShapeIds(selection.nodes).filter((id) => !lockedShapes.has(id)));
      const kept = selection.nodes.filter((id) => {
        const shapeId = shapeIdOf(id);
        return shapeId !== null && lockedShapes.has(shapeId);
      });
      if (kept.length === nodes.size && connections.size === 0) {
        return;
      }
      const path = [...get().activePath];
      // Selected terminals delete their exposed ports in the same undo entry,
      // except a port the next level up exposes again (the canvas says why).
      const doc = get().doc;
      const portNames = selection.nodes
        .map(terminalPortName)
        .filter(
          (name): name is string =>
            name !== null && doc !== null && exposedOneLevelUp(doc, path, name) === null,
        );
      commit((root) => {
        if (portNames.length > 0) {
          removeSubsystemPorts(root, path, portNames);
        }
        const draft = activeDiagram(root, path);
        if (draft === null) {
          return;
        }
        draft.nodes = draft.nodes.filter((node) => !nodes.has(node.id));
        draft.connections = draft.connections.filter(
          (connection) =>
            !connections.has(connection.id) &&
            !nodes.has(connection.from.node) &&
            !nodes.has(connection.to.node),
        );
        draft.probes = (draft.probes ?? [])
          .filter((probe) => !nodes.has(probe.id))
          .map((probe) => ({
            ...probe,
            links: probe.links.filter((link) =>
              draft.connections.some((connection) => connection.id === link.connection),
            ),
          }));
        if (notes.size > 0 && draft.annotations !== undefined) {
          draft.annotations = draft.annotations.filter((note) => !notes.has(note.id));
        }
        if (shapes.size > 0 && draft.shapes !== undefined) {
          draft.shapes = draft.shapes.filter((shape) => !shapes.has(shape.id));
        }
      });
      set({ selection: kept.length === 0 ? EMPTY_SELECTION : { nodes: kept, connections: [] } });
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
      const noteIds = new Set(selectedNoteIds(selection.nodes));
      const annotations = (diagram.annotations ?? [])
        .filter((note) => noteIds.has(note.id))
        .map((note) => clone(note));
      // Shapes keep their z order (the document order) in the clipboard.
      const shapeIds = new Set(selectedShapeIds(selection.nodes));
      const shapes = (diagram.shapes ?? [])
        .filter((shape) => shapeIds.has(shape.id))
        .map((shape) => clone(shape));
      if (nodes.length === 0 && annotations.length === 0 && shapes.length === 0) {
        return;
      }
      set({ clipboard: { nodes, connections, annotations, shapes } });
    },

    paste: () => {
      const doc = get().doc;
      const diagram = currentDiagram();
      const { clipboard } = get();
      if (doc === null || diagram === null) {
        return;
      }
      const clipNotes = clipboard.annotations ?? [];
      const clipShapes = clipboard.shapes ?? [];
      if (clipboard.nodes.length === 0 && clipNotes.length === 0 && clipShapes.length === 0) {
        return;
      }
      // Pasted shapes land in front of the other shapes, unlocked.
      const pastedShapes = copiedShapes(clipShapes, diagram.shapes ?? []);
      const existingNoteIds = new Set((diagram.annotations ?? []).map((note) => note.id));
      const pastedNotes: ModelAnnotation[] = clipNotes.map((note) => {
        const id = nextId("a", existingNoteIds);
        existingNoteIds.add(id);
        return {
          ...clone(note),
          id,
          x: Math.round((note.x + PASTE_OFFSET) * 10) / 10,
          y: Math.round((note.y + PASTE_OFFSET) * 10) / 10,
        };
      });
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
        if (pastedNotes.length > 0) {
          draft.annotations ??= [];
          draft.annotations.push(...pastedNotes);
        }
        if (pastedShapes.length > 0) {
          draft.shapes ??= [];
          draft.shapes.push(...pastedShapes);
        }
      });
      set({
        selection: {
          nodes: [
            ...pastedNodes.map((node) => node.id),
            ...pastedNotes.map((note) => noteFlowId(note.id)),
            ...pastedShapes.map((shape) => shapeFlowId(shape.id)),
          ],
          connections: [],
        },
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

    setConnectionRoute: (id, route) => {
      const diagram = currentDiagram();
      if (diagram === null) {
        return;
      }
      const points = route.map((point) => ({
        x: Math.round(point.x * 10) / 10,
        y: Math.round(point.y * 10) / 10,
      }));
      commitActive((draft) => {
        const connection = draft.connections.find((entry) => entry.id === id);
        if (connection !== undefined) {
          connection.route = points;
        }
      }, { coalesce: "route-drag" });
    },

    addProbe: (kind, position, panelPosition) => {
      const diagram = currentDiagram();
      if (diagram === null) {
        return null;
      }
      const probes = diagram.probes ?? [];
      const id = nextId("s", probes.map((probe) => probe.id));
      const name = uniqueName(
        kind === "block" ? "Scope" : "Plot",
        probes.map((probe) => probe.name),
      );
      const finite = (value: number, fallback: number): number =>
        Number.isFinite(value) ? value : fallback;
      commitActive((draft) => {
        draft.probes ??= [];
        draft.probes.push({
          id,
          name,
          kind,
          position: roundPosition({
            x: finite(position.x, 80),
            y: finite(position.y, 80),
          }),
          panelPosition: roundPosition({
            x: Math.round(finite(panelPosition.x, 120)),
            y: Math.round(finite(panelPosition.y, 100)),
          }),
          size: { width: 380, height: 240 },
          open: kind === "window",
          links: [],
          panels: [],
        });
      });
      return id;
    },

    deleteProbe: (id) => {
      const diagram = currentDiagram();
      if (diagram === null || !(diagram.probes ?? []).some((probe) => probe.id === id)) {
        return;
      }
      commitActive((draft) => {
        draft.probes = (draft.probes ?? []).filter((probe) => probe.id !== id);
      });
      set({ selection: EMPTY_SELECTION });
    },

    setProbePosition: (id, position, coalesce = true) => {
      const diagram = currentDiagram();
      if (diagram === null) {
        return;
      }
      commitActive(
        (draft) => {
          const probe = (draft.probes ?? []).find((entry) => entry.id === id);
          if (probe !== undefined) {
            probe.position = roundPosition(position);
          }
        },
        coalesce ? { coalesce: "node-drag" } : {},
      );
    },

    setProbeFrame: (id, frame) => {
      const diagram = currentDiagram();
      if (diagram === null) {
        return;
      }
      commitActive((draft) => {
        const probe = (draft.probes ?? []).find((entry) => entry.id === id);
        if (probe !== undefined) {
          probe.panelPosition = roundPosition({ x: frame.x, y: frame.y });
          probe.size = {
            width: Math.max(240, Math.round(frame.width)),
            height: Math.max(140, Math.round(frame.height)),
          };
        }
      });
    },

    setProbeOpen: (id, open) => {
      const diagram = currentDiagram();
      if (diagram === null) {
        return;
      }
      commitActive((draft) => {
        const probe = (draft.probes ?? []).find((entry) => entry.id === id);
        if (probe !== undefined) {
          probe.open = open;
        }
      });
    },

    addProbeLink: (probeId, connectionId) => {
      const diagram = currentDiagram();
      if (diagram === null) {
        return null;
      }
      const probe = (diagram.probes ?? []).find((entry) => entry.id === probeId);
      const connection = diagram.connections.find((entry) => entry.id === connectionId);
      if (probe === undefined || connection === undefined) {
        return null;
      }
      if (probe.links.some((link) => link.connection === connectionId)) {
        return null;
      }
      const options = probeSignalOptions(diagram, connection);
      if (options.length === 0) {
        return null;
      }
      const linkId = nextId(
        "pl",
        (diagram.probes ?? []).flatMap((entry) => entry.links.map((link) => link.id)),
      );
      commitActive((draft) => {
        const target = (draft.probes ?? []).find((entry) => entry.id === probeId);
        if (target !== undefined) {
          target.links.push({
            id: linkId,
            connection: connectionId,
            signals: options.map((option) => option.id),
          });
          target.open = true;
        }
      });
      return linkId;
    },

    removeProbeLink: (probeId, linkId) => {
      const diagram = currentDiagram();
      if (diagram === null) {
        return;
      }
      commitActive((draft) => {
        const probe = (draft.probes ?? []).find((entry) => entry.id === probeId);
        if (probe !== undefined) {
          probe.links = probe.links.filter((link) => link.id !== linkId);
        }
      });
    },

    setProbeLinkSignals: (probeId, linkId, signals) => {
      const diagram = currentDiagram();
      if (diagram === null) {
        return;
      }
      const unique = [...new Set(signals)];
      commitActive((draft) => {
        const probe = (draft.probes ?? []).find((entry) => entry.id === probeId);
        const link = probe?.links.find((entry) => entry.id === linkId);
        if (link !== undefined) {
          link.signals = unique;
        }
      });
    },

    setProbePanels: (probeId, panels) => {
      const diagram = currentDiagram();
      if (diagram === null) {
        return;
      }
      const copy = panels.map((panel) => ({
        id: panel.id,
        title: panel.title,
        signals: [...new Set(panel.signals)],
      }));
      commitActive((draft) => {
        const probe = (draft.probes ?? []).find((entry) => entry.id === probeId);
        if (probe !== undefined) {
          probe.panels = copy;
        }
      });
    },

    editDashboard: (recipe, options = {}) => {
      commit((draft) => {
        const dashboard = draft.dashboard ?? { cards: [] };
        recipe(dashboard);
        if (dashboard.cards.length === 0 && dashboard.autoRerun !== true) {
          delete draft.dashboard;
        } else {
          draft.dashboard = dashboard;
        }
      }, options);
    },

    setBindings: (bindings) => {
      const copy = structuredClone(bindings) as Binding[];
      commit((draft) => {
        if (copy.length === 0) {
          delete draft.bindings;
        } else {
          draft.bindings = copy;
        }
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

    applyParameterChanges: (changes) => {
      let missing: string[] = [];
      commit((draft) => {
        missing = applyChangesToDraft(draft, changes);
      });
      return missing;
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

    addGlobalParameter: (init) => runPlan((doc) => planAddGlobal(doc, init)),
    updateGlobalParameter: (name, patch) => runPlan((doc) => planUpdateGlobal(doc, name, patch)),
    renameGlobalParameter: (name, next) => runPlan((doc) => planRenameGlobal(doc, name, next)),
    deleteGlobalParameter: (name) => runPlan((doc) => planDeleteGlobal(doc, name)),
    moveGlobalParameter: (name, toIndex) => runPlan((doc) => planMoveGlobal(doc, name, toIndex)),
    setFieldExpression: (field, text) => runPlan((doc) => planSetField(doc, field, text)),

    setNodeImage: (nodeId, image) => {
      const diagram = currentDiagram();
      if (diagram === null) {
        return { ok: false, error: "No model is open." };
      }
      const node = diagram.nodes.find((entry) => entry.id === nodeId);
      if (node === undefined) {
        return { ok: false, error: "That block is no longer in the diagram." };
      }
      if (!("subsystem" in node.block)) {
        return { ok: false, error: "Only subsystem blocks carry an image." };
      }
      if (image !== null) {
        const issue = nodeImageIssue(image);
        if (issue !== null) {
          return { ok: false, error: issue };
        }
      }
      commitActive((draft) => {
        const target = draft.nodes.find((entry) => entry.id === nodeId);
        if (target === undefined) {
          return;
        }
        if (image === null) {
          if (target.ui?.image !== undefined) {
            delete target.ui.image;
          }
          return;
        }
        const copy: ModelNodeImage = { mime: image.mime, data: image.data, fit: image.fit };
        if (target.ui === undefined) {
          target.ui = { showLabel: true, color: null, image: copy };
        } else {
          target.ui.image = copy;
        }
      });
      return { ok: true };
    },

    setNodeImageFit: (nodeId, fit) => {
      const diagram = currentDiagram();
      if (diagram === null) {
        return { ok: false, error: "No model is open." };
      }
      const node = diagram.nodes.find((entry) => entry.id === nodeId);
      if (node?.ui?.image === undefined) {
        return { ok: false, error: "That block has no image." };
      }
      if (fit !== "contain" && fit !== "stretch") {
        return { ok: false, error: "The fit is contain or stretch." };
      }
      commitActive((draft) => {
        const image = draft.nodes.find((entry) => entry.id === nodeId)?.ui?.image;
        if (image !== undefined) {
          image.fit = fit;
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

    replaceInlineWithRef: (nodeIds, ref) => {
      const doc = get().doc;
      if (doc === null) {
        return { ok: false, error: "No model is open." };
      }
      const next = ref.trim();
      if (next.length === 0) {
        return { ok: false, error: "Enter a block reference." };
      }
      const wanted = new Set(nodeIds);
      const replaced: string[] = [];
      const visit = (diagram: ModelDiagram): void => {
        for (const node of diagram.nodes) {
          if (wanted.has(node.id) && "inline" in node.block) {
            replaced.push(node.id);
          }
          if ("subsystem" in node.block) {
            visit(node.block.subsystem.diagram);
          }
        }
      };
      visit(doc.diagram);
      if (replaced.length === 0) {
        return { ok: false, error: "Only inline code nodes can be saved to the library." };
      }
      const targets = new Set(replaced);
      commit((draft) => {
        const rewrite = (diagram: ModelDiagram): void => {
          for (const node of diagram.nodes) {
            if (targets.has(node.id) && "inline" in node.block) {
              node.block = { ref: next };
            }
            if ("subsystem" in node.block) {
              rewrite(node.block.subsystem.diagram);
            }
          }
        };
        rewrite(draft.diagram);
      });
      return { ok: true, replaced };
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

    exposeSubsystemPort: (index, internal, wanted) => {
      const state = get();
      const doc = state.doc;
      if (doc === null) {
        return { ok: false, error: "No model is open." };
      }
      const path = [...state.activePath];
      const found = subsystemAtPath(doc, path);
      const inner = activeModel(doc, path);
      if (found === null || inner === null) {
        return { ok: false, error: "Open a subsystem to expose one of its ports." };
      }
      const result = exposedPortFor({
        inner,
        ports: found.node.block.subsystem.ports,
        descriptor: internal,
        index,
        wanted,
      });
      if (!result.ok) {
        return { ok: false, error: result.reason };
      }
      const port = result.port;
      commit((root) => {
        subsystemAtPath(root, path)?.node.block.subsystem.ports.push(clone(port));
      });
      set({ selection: { nodes: [terminalId(port.name)], connections: [] } });
      return { ok: true, name: port.name };
    },

    renameSubsystemPort: (name, next) => {
      const state = get();
      const doc = state.doc;
      if (doc === null) {
        return { ok: false, error: "No model is open." };
      }
      const path = [...state.activePath];
      const found = subsystemAtPath(doc, path);
      const ports = found?.node.block.subsystem.ports ?? [];
      if (found === null || !ports.some((port) => port.name === name)) {
        return { ok: false, error: "That port is no longer on the subsystem." };
      }
      const text = next.trim();
      const issue = subsystemPortNameIssue(ports, name, text);
      if (issue !== null) {
        return { ok: false, error: issue };
      }
      if (text === name) {
        return { ok: true };
      }
      const subsystemId = found.node.id;
      const wasSelected = state.selection.nodes.includes(terminalId(name));
      commit((root) => {
        const target = subsystemAtPath(root, path);
        if (target === null) {
          return;
        }
        const port = target.node.block.subsystem.ports.find((entry) => entry.name === name);
        if (port !== undefined) {
          port.name = text;
        }
        // Outside connections keep their port: they name it.
        for (const connection of target.parent.connections) {
          for (const end of [connection.from, connection.to]) {
            if (end.node === subsystemId && end.port === name) {
              end.port = text;
            }
          }
        }
        // A port one level up that exposes this one follows the rename.
        const outer = path.length >= 2 ? subsystemAtPath(root, path.slice(0, -1)) : null;
        for (const entry of outer?.node.block.subsystem.ports ?? []) {
          if (entry.node === subsystemId && entry.port === name) {
            entry.port = text;
          }
        }
      });
      if (wasSelected) {
        const selection = get().selection;
        set({
          selection: {
            nodes: [...selection.nodes.filter((id) => id !== terminalId(name)), terminalId(text)],
            connections: selection.connections,
          },
        });
      }
      return { ok: true };
    },

    deleteSubsystemPorts: (names) => {
      const state = get();
      const doc = state.doc;
      if (doc === null) {
        return { ok: false, error: "No model is open." };
      }
      const path = [...state.activePath];
      const found = subsystemAtPath(doc, path);
      if (found === null) {
        return { ok: false, error: "Open a subsystem to delete its ports." };
      }
      for (const name of names) {
        const up = exposedOneLevelUp(doc, path, name);
        if (up !== null) {
          return {
            ok: false,
            error: `${name} is exposed again by ${up.owner} as ${up.port.name}; delete that port first.`,
          };
        }
      }
      const known = names.filter((name) =>
        found.node.block.subsystem.ports.some((port) => port.name === name),
      );
      if (known.length === 0) {
        return { ok: false, error: "That port is no longer on the subsystem." };
      }
      commit((root) => removeSubsystemPorts(root, path, known));
      return { ok: true };
    },

    setSubsystemPortPositions: (positions, coalesce = true) => {
      const entries = Object.entries(positions);
      const path = [...get().activePath];
      if (entries.length === 0 || path.length === 0) {
        return;
      }
      commit(
        (root) => {
          const ports = subsystemAtPath(root, path)?.node.block.subsystem.ports ?? [];
          for (const [name, position] of entries) {
            const port = ports.find((entry) => entry.name === name);
            if (port !== undefined) {
              port.ui = { ...(port.ui ?? {}), position: roundPosition(position) };
            }
          }
        },
        coalesce ? { coalesce: "node-drag" } : {},
      );
    },

    revealSubsystemPort: (name) => {
      const state = get();
      const doc = state.doc;
      if (doc === null) {
        return null;
      }
      const found = subsystemAtPath(doc, state.activePath);
      if (found === null || !found.node.block.subsystem.ports.some((port) => port.name === name)) {
        return null;
      }
      const connections = outsideConnections(found.parent, found.node.id, name).map(
        (connection) => connection.id,
      );
      set({
        activePath: state.activePath.slice(0, -1),
        selection:
          connections.length > 0
            ? { nodes: [], connections }
            : { nodes: [found.node.id], connections: [] },
        gestureKey: null,
        lastHistKey: null,
      });
      return { nodeId: found.node.id, connections };
    },

    addNote: (position, options = {}) => {
      const diagram = currentDiagram();
      if (diagram === null || !Number.isFinite(position.x) || !Number.isFinite(position.y)) {
        return null;
      }
      const id = nextId("a", (diagram.annotations ?? []).map((note) => note.id));
      const at = roundPosition(position);
      const size = options.size ?? NOTE_DEFAULT_SIZE;
      const note: ModelAnnotation = {
        id,
        kind: "text",
        text: options.text ?? "",
        x: at.x,
        y: at.y,
        w: Math.max(NOTE_MIN_SIZE.w, Math.round(size.w)),
        h: Math.max(NOTE_MIN_SIZE.h, Math.round(size.h)),
      };
      if (options.color !== undefined && options.color !== "yellow") {
        note.color = options.color;
      }
      const next = commitActive((draft) => {
        draft.annotations ??= [];
        draft.annotations.push(note);
      });
      if (next === null) {
        return null;
      }
      const flowId = noteFlowId(id);
      set({ selection: { nodes: [flowId], connections: [] } });
      return flowId;
    },

    setNoteText: (id, text, options = {}) => {
      const note = (currentDiagram()?.annotations ?? []).find((entry) => entry.id === id);
      if (note === undefined || note.text === text) {
        return;
      }
      commitActive(
        (draft) => {
          const target = (draft.annotations ?? []).find((entry) => entry.id === id);
          if (target !== undefined) {
            target.text = text;
          }
        },
        options.coalesce === true ? { coalesce: `note-text:${id}` } : {},
      );
    },

    setNoteColor: (ids, color) => {
      const wanted = new Set(ids);
      if (wanted.size === 0 || currentDiagram() === null) {
        return;
      }
      commitActive((draft) => {
        for (const note of draft.annotations ?? []) {
          if (!wanted.has(note.id)) {
            continue;
          }
          // Absent means yellow: the default colour leaves no field behind.
          if (color === "yellow") {
            if (note.color !== undefined) {
              delete note.color;
            }
          } else if (note.color !== color) {
            note.color = color;
          }
        }
      });
    },

    setNoteFrame: (id, frame, coalesce = true) => {
      if (
        currentDiagram() === null ||
        ![frame.x, frame.y, frame.w, frame.h].every((value) => Number.isFinite(value))
      ) {
        return;
      }
      const at = roundPosition({ x: frame.x, y: frame.y });
      const w = Math.max(NOTE_MIN_SIZE.w, Math.round(frame.w));
      const h = Math.max(NOTE_MIN_SIZE.h, Math.round(frame.h));
      commitActive(
        (draft) => {
          const note = (draft.annotations ?? []).find((entry) => entry.id === id);
          if (note === undefined) {
            return;
          }
          // Immer records only real changes, so an unchanged frame adds no history.
          note.x = at.x;
          note.y = at.y;
          note.w = w;
          note.h = h;
        },
        coalesce ? { coalesce: "note-resize" } : {},
      );
    },

    addShape: (kind, position, options = {}) => {
      const diagram = currentDiagram();
      if (diagram === null || !Number.isFinite(position.x) || !Number.isFinite(position.y)) {
        return null;
      }
      const id = nextId("s", (diagram.shapes ?? []).map((shape) => shape.id));
      const at = roundPosition(position);
      const size = options.size ?? SHAPE_DEFAULT_SIZE[kind];
      const line = isLineKind(kind);
      const shape: ModelShape = {
        id,
        kind,
        x: at.x,
        y: at.y,
        w: line ? Math.round(size.w) : Math.max(SHAPE_MIN_SIZE.w, Math.round(Math.abs(size.w))),
        h: line ? Math.round(size.h) : Math.max(SHAPE_MIN_SIZE.h, Math.round(Math.abs(size.h))),
      };
      if (options.style !== undefined) {
        applyShapeStyle(shape, options.style);
      }
      if (options.text !== undefined && options.text.length > 0) {
        shape.text = options.text;
      }
      const next = commitActive((draft) => {
        draft.shapes ??= [];
        draft.shapes.push(shape);
      });
      if (next === null) {
        return null;
      }
      const flowId = shapeFlowId(id);
      set({ selection: { nodes: [flowId], connections: [] } });
      return flowId;
    },

    setShapeStyle: (ids, patch, options = {}) => {
      const wanted = new Set(ids);
      if (wanted.size === 0 || currentDiagram() === null) {
        return;
      }
      commitActive(
        (draft) => {
          for (const shape of draft.shapes ?? []) {
            if (wanted.has(shape.id)) {
              applyShapeStyle(shape, patch);
            }
          }
        },
        options.coalesce === undefined ? {} : { coalesce: options.coalesce },
      );
    },

    setShapeText: (id, text, options = {}) => {
      const shape = (currentDiagram()?.shapes ?? []).find((entry) => entry.id === id);
      if (shape === undefined || (shape.text ?? "") === text) {
        return;
      }
      commitActive(
        (draft) => {
          const target = (draft.shapes ?? []).find((entry) => entry.id === id);
          if (target === undefined) {
            return;
          }
          // An empty label leaves no field behind.
          if (text.length === 0) {
            delete target.text;
          } else {
            target.text = text;
          }
        },
        options.coalesce === true ? { coalesce: `shape-text:${id}` } : {},
      );
    },

    setShapeFrame: (id, frame, coalesce) => {
      if (
        currentDiagram() === null ||
        ![frame.x, frame.y, frame.w, frame.h].every((value) => Number.isFinite(value))
      ) {
        return;
      }
      const at = roundPosition({ x: frame.x, y: frame.y });
      commitActive(
        (draft) => {
          const shape = (draft.shapes ?? []).find((entry) => entry.id === id);
          if (shape === undefined || isLocked(shape)) {
            return;
          }
          const line = isLineKind(shape.kind);
          // Immer records only real changes, so an unchanged frame adds no history.
          shape.x = at.x;
          shape.y = at.y;
          shape.w = line
            ? Math.round(frame.w * 10) / 10
            : Math.max(SHAPE_MIN_SIZE.w, Math.round(frame.w));
          shape.h = line
            ? Math.round(frame.h * 10) / 10
            : Math.max(SHAPE_MIN_SIZE.h, Math.round(frame.h));
        },
        coalesce === undefined ? {} : { coalesce },
      );
    },

    setShapeLocked: (ids, locked) => {
      const wanted = new Set(ids);
      if (wanted.size === 0 || currentDiagram() === null) {
        return;
      }
      commitActive((draft) => {
        for (const shape of draft.shapes ?? []) {
          if (!wanted.has(shape.id)) {
            continue;
          }
          if (locked) {
            if (shape.locked !== true) {
              shape.locked = true;
            }
          } else if ("locked" in shape) {
            delete shape.locked;
          }
        }
      });
    },

    reorderShapes: (ids, order) => {
      const shapes = currentDiagram()?.shapes ?? [];
      const next = reorderShapeList(shapes, ids, order);
      if (next === shapes) {
        return;
      }
      const ordered = next.map((shape) => shape.id);
      commitActive((draft) => {
        const byId = new Map((draft.shapes ?? []).map((shape) => [shape.id, shape]));
        draft.shapes = ordered
          .map((id) => byId.get(id))
          .filter((shape): shape is ModelShape => shape !== undefined);
      });
    },

    duplicateShapes: (ids) => {
      const diagram = currentDiagram();
      if (diagram === null) {
        return [];
      }
      const wanted = new Set(ids);
      const existing = diagram.shapes ?? [];
      const copies = copiedShapes(
        existing.filter((shape) => wanted.has(shape.id)),
        existing,
      );
      if (copies.length === 0) {
        return [];
      }
      commitActive((draft) => {
        draft.shapes ??= [];
        draft.shapes.push(...copies);
      });
      const flowIds = copies.map((shape) => shapeFlowId(shape.id));
      set({ selection: { nodes: flowIds, connections: [] } });
      return flowIds;
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
