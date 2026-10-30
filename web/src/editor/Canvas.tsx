/**
 * The xyflow canvas of plan 7.2/7.3.
 *
 * Interactions:
 * * drag a library row onto the canvas -> add a block or junction;
 * * drag between port glyphs -> bond / wire / signal, with live compatibility
 *   highlighting and the plan's refusal tooltip;
 * * release a connection on empty canvas -> a filterable list of compatible
 *   elements to add at that point and connect automatically;
 * * drag nodes -> move (one undo entry per drag);
 * * drag on empty canvas -> a selection rectangle (every node it touches),
 *   committed to the document store once, on release;
 *   pan with the middle or right mouse button, Space+drag or the arrow keys
 *   (Shift: larger steps); the wheel zooms;
 * * Del, R, F, Ctrl+C/V, Ctrl+Z/Y;
 * * right-click an edge -> reverse a bond; right-click a node -> transform.
 */

import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  BackgroundVariant,
  ConnectionLineType,
  ConnectionMode,
  Panel,
  ReactFlow,
  ReactFlowProvider,
  SelectionMode,
  useReactFlow,
  useStoreApi,
  useUpdateNodeInternals,
  useViewport,
  ViewportPortal,
  type Connection,
  type Edge,
  type FinalConnectionState,
  type Node,
  type OnConnect,
  type OnConnectEnd,
  type OnConnectStart,
  type OnSelectionChangeFunc,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { useDocumentStore } from "../state/documentStore";
import { saveCurrentModel } from "../state/persistence";
import { useCatalogStore } from "../library/catalogStore";
import { readDragPayload } from "../library/dnd";
import { useOpenSourceEvents, requestSource } from "../code/codeSession";
import { useInlineInterfaceStore } from "../code/inlineInterfaces";
import {
  connectionPlotTargets,
  nodeForMenu,
  nodeOutputIds,
} from "../plot/plotTargets";
import { useRunStore } from "../plot/runStore";
import { useDiagnosticsStore } from "../diagnostics/store";
import {
  applySelection,
  buildDiagram,
  EDGE_TYPES,
  NODE_TYPES,
  type SelectionOrigins,
} from "./buildFlow";
import { imageFromDataTransfer } from "./nodeImage";
import { applyNodeImage } from "./nodeImageApply";
import { activeDiagram } from "./subsystemPath";
import { checkConnection, type PortDescriptor } from "./connectionRules";
import {
  descriptorForPort,
  interfaceForBlock,
  interfaceForNode,
} from "./nodeInterface";
import { firstCompatiblePort, noAutoTargetMessage } from "./quickConnectTarget";
import {
  GRID_SIZE,
  JUNCTION_NODE_SIZE,
  NODE_HALF_SHIFT,
  isBondGraph,
  layoutNode,
  nearestSourcePort,
  nodeLayout,
  nodeVisualOffset,
  connectionAnchors,
  snapRouteVertex,
} from "./geometry";
import { suggestTargets, type TargetSuggestion } from "./suggestTargets";
import { TargetSuggestions } from "./TargetSuggestions";
import { decorateFlow } from "./edges/decorateFlow";
import { CanvasLegend } from "./legend";
import { HoverReadout } from "./ports/HoverReadout";
import { powerHoverSignalIds, signalHoverSignalId } from "./ports/hoverValues";
import { SignalMenuItems } from "../debug/panels/SignalMenu";
import { ProbeLeads } from "../probe/ProbeLeads";
import { ProbeGlyph } from "../probe/ProbeGlyph";
import { probeSignalIds } from "../probe/probeSignals";
import { activeModel, subsystemPathCrumbs } from "./subsystemPath";
import { QuickConnectContext } from "./quickConnect";
import { SubsystemBreadcrumbs } from "./SubsystemBreadcrumbs";
import { requestPlotsTab } from "../app/dockBus";
import { useExportDialogStore } from "../export/exportStore";
import {
  ghostId,
  ghostKind,
  isBoundaryElementId,
  REVEAL_PORT_EVENT,
  subsystemBoundary,
  terminalId,
  terminalPortName,
} from "./subsystemBoundary";
import { exposeIssue, type TerminalKind } from "./subsystemPorts";
import { TerminalActionsContext } from "./nodes/PortTerminal";
import {
  PortDeleteConfirm,
  requestSubsystemPortDelete,
  selectedTerminalPorts,
  usePortDeleteStore,
} from "./PortDeleteConfirm";
import "./editor.css";

// The probe plot pulls in uPlot; it loads when a diagram has a probe (code splitting, W5.4).
const ProbeWindow = lazy(() =>
  import("../probe/ProbeWindow").then((m) => ({ default: m.ProbeWindow })),
);

const ZOOM = 0.85;
const GRID_KEY = "bgsim.canvas.grid";
const SNAP_KEY = "bgsim.canvas.snap";
const NO_SELECTION = { nodes: [], connections: [] } as const;
/**
 * Pointer travel (px) between press and release that still counts as a click
 * on a node or on empty canvas. xyflow's node default is 0: d3-drag then
 * swallows the click after any movement, while a drag only starts beyond 1 px,
 * so a 1 px jitter neither selected nor moved the node.
 */
const CLICK_DISTANCE = 5;

function readPreference(key: string, fallback: boolean): boolean {
  try {
    const value = window.localStorage.getItem(key);
    return value === null ? fallback : value === "1";
  } catch {
    return fallback;
  }
}

function writePreference(key: string, value: boolean): void {
  try {
    window.localStorage.setItem(key, value ? "1" : "0");
  } catch {
    // A private-mode browser has no storage; the toggle still works for this session.
  }
}

interface QuickGesture {
  origin: PortDescriptor;
  startClient: { x: number; y: number };
  startLocal: { x: number; y: number };
  active: boolean;
}

interface Tooltip {
  x: number;
  y: number;
  message: string;
}

/**
 * What a connection drag that ended on empty canvas offers: the elements that
 * can be added at the release point and connected to the dragged port.
 */
interface SuggestionState {
  origin: PortDescriptor;
  items: TargetSuggestion[];
  /** Release point in flow coordinates, used to place the new element. */
  flow: { x: number; y: number };
  /** Release point in client coordinates, used for follow-up tooltips. */
  client: { x: number; y: number };
  /** Where the filter panel sits (clamped to the viewport). */
  panel: { x: number; y: number };
}

interface MenuState {
  x: number;
  y: number;
  kind: "node" | "edge";
  id: string;
  /** The click in flow coordinates, used to place a new routing vertex. */
  flow?: { x: number; y: number };
  /** The port under the pointer when a node menu opened on one (M4: "Break when..." / "Explain signal"). */
  port?: { name: string; power: boolean };
}

function distanceToSegment(point: { x: number; y: number }, a: { x: number; y: number }, b: { x: number; y: number }): number {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const lengthSquared = dx * dx + dy * dy;
  if (lengthSquared < 1e-6) {
    return Math.hypot(point.x - a.x, point.y - a.y);
  }
  const t = Math.max(
    0,
    Math.min(1, ((point.x - a.x) * dx + (point.y - a.y) * dy) / lengthSquared),
  );
  return Math.hypot(point.x - (a.x + t * dx), point.y - (a.y + t * dy));
}

function eventPoint(event: MouseEvent | TouchEvent): { x: number; y: number } {
  if ("clientX" in event) {
    return { x: event.clientX, y: event.clientY };
  }
  const touch = event.changedTouches[0];
  return { x: touch?.clientX ?? 0, y: touch?.clientY ?? 0 };
}

/** Arrow key -> the direction the view moves over the diagram (screen pixels). */
const ARROW_PAN: Record<string, [number, number]> = {
  ArrowLeft: [-1, 0],
  ArrowRight: [1, 0],
  ArrowUp: [0, -1],
  ArrowDown: [0, 1],
};
const PAN_STEP = 40;
const PAN_STEP_LARGE = 200;

function editableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  const tag = target.tagName;
  return (
    tag === "INPUT" ||
    tag === "TEXTAREA" ||
    tag === "SELECT" ||
    target.isContentEditable
  );
}

/** Inside the inspector's image paste area, which handles Ctrl+V itself. */
function imagePasteTarget(target: EventTarget | null): boolean {
  return target instanceof Element && target.closest("[data-node-image-paste]") !== null;
}

/**
 * How long Ctrl+V on a selected subsystem waits for the browser's `paste` event before it
 * falls back to the node paste (a browser that fires no paste event outside text fields).
 */
const PASTE_EVENT_WAIT_MS = 300;

/** The id of the only selected element when it is a subsystem node, else null. */
function soleSelectedSubsystem(): string | null {
  const state = useDocumentStore.getState();
  if (state.doc === null || state.selection.nodes.length !== 1 || state.selection.connections.length > 0) {
    return null;
  }
  const id = state.selection.nodes[0];
  const node = activeDiagram(state.doc, state.activePath)?.nodes.find((entry) => entry.id === id);
  return node !== undefined && "subsystem" in node.block ? node.id : null;
}

/** After a port is exposed (or "Rename port"), the inspector's name field takes the focus. */
function focusPortNameField(): void {
  requestAnimationFrame(() =>
    requestAnimationFrame(() => {
      const input = document.querySelector<HTMLInputElement>('[data-testid="inspector-port-name"]');
      input?.focus();
      input?.select();
    }),
  );
}

/** The canvas menu of a subsystem port terminal. */
function TerminalMenuItems({
  portName,
  onReveal,
  onRename,
  onDelete,
}: {
  portName: string;
  onReveal: (name: string) => void;
  onRename: (name: string) => void;
  onDelete: () => void;
}) {
  return (
    <>
      <button
        type="button"
        role="menuitem"
        data-testid="terminal-reveal"
        onClick={() => onReveal(portName)}
      >
        Show outside connection
      </button>
      <button
        type="button"
        role="menuitem"
        data-testid="terminal-rename"
        onClick={() => onRename(portName)}
      >
        Rename port…
      </button>
      <button type="button" role="menuitem" data-testid="terminal-delete" onClick={onDelete}>
        Delete port (Del)
      </button>
    </>
  );
}

function saveLabel(saveState: string, dirty: boolean): string {
  switch (saveState) {
    case "saving":
      return "Saving…";
    case "error":
      return "Save failed";
    case "dirty":
      return "Unsaved changes";
    default:
      return dirty ? "Unsaved changes" : "Saved";
  }
}

export function Canvas() {
  return (
    <ReactFlowProvider>
      <CanvasInner />
    </ReactFlowProvider>
  );
}

/**
 * Keep the diagnostic count badges at a constant screen size: the nodes scale
 * with the viewport, so the badge counter-scales by 1/zoom.
 */
function CanvasZoomVariable(): null {
  const { zoom } = useViewport();
  useEffect(() => {
    document.documentElement.style.setProperty(
      "--bgsim-canvas-zoom",
      String(zoom),
    );
  }, [zoom]);
  return null;
}

function CanvasInner() {
  const doc = useDocumentStore((state) => state.doc);
  const activePath = useDocumentStore((state) => state.activePath);
  const project = useDocumentStore((state) => state.project);
  const modelName = useDocumentStore((state) => state.modelName);
  const selection = useDocumentStore((state) => state.selection);
  const pastLength = useDocumentStore((state) => state.past.length);
  const futureLength = useDocumentStore((state) => state.future.length);
  const revision = useDocumentStore((state) => state.revision);
  const savedRevision = useDocumentStore((state) => state.savedRevision);
  const saveState = useDocumentStore((state) => state.saveState);
  const saveError = useDocumentStore((state) => state.saveError);
  const index = useCatalogStore((state) => state.index);
  const inlineRevision = useInlineInterfaceStore((state) => state.revision);
  const checkedDomains = useDiagnosticsStore((state) => state.domains);
  const checkedCausality = useDiagnosticsStore((state) => state.causality);
  const checkedUnitFactors = useDiagnosticsStore((state) => state.unitFactors);
  const checkedFrames = useDiagnosticsStore((state) => state.frames);

  useOpenSourceEvents();

  const [dragOrigin, setDragOrigin] = useState<ReturnType<typeof descriptorForPort>>(null);
  const [tooltip, setTooltip] = useState<Tooltip | null>(null);
  const [menu, setMenu] = useState<MenuState | null>(null);
  const probeDragRef = useRef<string | null>(null);
  const [quickMode, setQuickMode] = useState(false);
  const [quickLine, setQuickLine] = useState<{ from: { x: number; y: number }; to: { x: number; y: number } } | null>(null);
  const [suggestions, setSuggestions] = useState<SuggestionState | null>(null);
  // The click that follows a connection release must not close the palette.
  const suppressPaneClickUntil = useRef(0);
  const [showGrid, setShowGrid] = useState(() => readPreference(GRID_KEY, true));
  const [snap, setSnap] = useState(() => readPreference(SNAP_KEY, true));
  const tooltipTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const quickGesture = useRef<QuickGesture | null>(null);
  const suppressClick = useRef(false);
  // While a selection rectangle is drawn, the nodes it touches are shown from
  // this local state; the document store gets the result once, on release, so
  // the inspector, the plots and the dock do not re-render per pointer move.
  const [boxSelection, setBoxSelection] = useState<readonly string[] | null>(null);
  const boxing = useRef(false);
  // From a pointer press on the canvas to one frame after its release.
  const pointerGesture = useRef(false);
  const repairFrame = useRef(0);
  const selectionOrigins = useRef<SelectionOrigins>(new WeakMap());
  const flowStore = useStoreApi();
  const { fitView, screenToFlowPosition, getViewport, setViewport } = useReactFlow();
  // The shortcut handler is registered once; it reads the viewport API here.
  const viewportApi = useRef({ getViewport, setViewport });
  viewportApi.current = { getViewport, setViewport };

  // Commands mutate the active diagram; rendering reads the same document
  // view, so entering a subsystem shows its nested diagram.
  const view = useMemo(
    () => (doc === null ? null : activeModel(doc, activePath)),
    [doc, activePath],
  );
  // Inside a subsystem: its exposed ports, drawn as terminals on this canvas.
  const boundary = useMemo(
    () => (doc === null || index === null ? null : subsystemBoundary(doc, activePath, index)),
    [doc, activePath, index],
  );

  // The diagram is built without a selection: the analysis and the node
  // layouts are the expensive part, and a click must not redo them. The
  // selection is applied on top, copying only the elements it changes.
  const unselectedFlow = useMemo(
    () =>
      view === null || index === null
        ? null
        : decorateFlow(buildDiagram(view, index, NO_SELECTION, dragOrigin, snap, boundary), {
            domains: checkedDomains,
            causality: checkedCausality,
            unitFactors: checkedUnitFactors,
            frames: checkedFrames,
          }),
    [
      view,
      index,
      dragOrigin,
      snap,
      boundary,
      inlineRevision,
      checkedDomains,
      checkedCausality,
      checkedUnitFactors,
      checkedFrames,
    ],
  );
  const shownSelection = useMemo(
    () => (boxSelection === null ? selection : { nodes: boxSelection, connections: [] }),
    [boxSelection, selection],
  );
  const flow = useMemo(
    () =>
      unselectedFlow === null
        ? { nodes: [], edges: [], analysis: null }
        : applySelection(unselectedFlow, shownSelection, selectionOrigins.current, (id) => {
            const internal = flowStore.getState().nodeLookup.get(id);
            return internal === undefined
              ? undefined
              : { node: internal.internals.userNode, measured: internal.measured };
          }),
    [unselectedFlow, shownSelection, flowStore],
  );
  // The boundary wires are drawn after the connections and never selected.
  const flowEdges = useMemo(
    () =>
      (unselectedFlow?.boundaryEdges ?? []).length === 0
        ? flow.edges
        : [...flow.edges, ...(unselectedFlow?.boundaryEdges ?? [])],
    [flow.edges, unselectedFlow],
  );
  // A rebuilt node keeps the size xyflow measured (`applySelection`), so it
  // stays visible; its ports can still have moved, which xyflow measures here.
  const updateNodeInternals = useUpdateNodeInternals();
  useEffect(() => {
    if (unselectedFlow !== null && unselectedFlow.nodes.length > 0) {
      updateNodeInternals(unselectedFlow.nodes.map((node) => node.id));
    }
  }, [unselectedFlow, updateNodeInternals]);

  const pathPrefix = useMemo(
    () =>
      doc === null
        ? ""
        : subsystemPathCrumbs(doc, activePath)
            .map((crumb) => crumb.name)
            .join("/"),
    [doc, activePath],
  );

  const scopeSignals = useMemo(() => {
    if (view === null) {
      return [];
    }
    const ids: string[] = [];
    for (const probe of view.diagram.probes ?? []) {
      if (!(probe.open ?? true)) {
        continue;
      }
      ids.push(...probeSignalIds(view, probe));
    }
    return [...new Set(ids)];
  }, [view]);
  const scopeKey = scopeSignals.join(",");
  const runManifestId = useRunStore((state) => state.manifest?.id ?? null);
  useEffect(() => {
    useRunStore.getState().setScopeSignals(scopeSignals);
  }, [scopeKey, scopeSignals, runManifestId]);
  useEffect(
    () => () => {
      useRunStore.getState().setScopeSignals([]);
    },
    [],
  );

  const dirty = revision !== savedRevision;

  const showTooltip = useCallback((point: { x: number; y: number }, message: string) => {
    if (tooltipTimer.current !== null) {
      clearTimeout(tooltipTimer.current);
    }
    setTooltip({ x: point.x, y: point.y, message });
    tooltipTimer.current = setTimeout(() => setTooltip(null), 3200);
  }, []);

  useEffect(
    () => () => {
      if (tooltipTimer.current !== null) {
        clearTimeout(tooltipTimer.current);
      }
    },
    [],
  );

  /**
   * Expose an internal port of the open subsystem; the new terminal is
   * selected and the inspector's name field takes the focus for a rename.
   */
  const exposePort = useCallback(
    (internal: PortDescriptor, wanted: TerminalKind | undefined, point: { x: number; y: number }) => {
      const indexNow = useCatalogStore.getState().index;
      if (indexNow === null) {
        return;
      }
      const result = useDocumentStore.getState().exposeSubsystemPort(indexNow, internal, wanted);
      if (!result.ok) {
        showTooltip(point, result.error ?? "The port cannot be exposed.");
        return;
      }
      focusPortNameField();
    },
    [showTooltip],
  );

  // A terminal's outside link leaves the subsystem; the view then frames the
  // subsystem node and the peers of the revealed connections.
  const pendingFocus = useRef<string[] | null>(null);
  const revealPort = useCallback((portName: string) => {
    const store = useDocumentStore.getState();
    const result = store.revealSubsystemPort(portName);
    if (result === null) {
      return;
    }
    const after = useDocumentStore.getState();
    const parent = after.doc === null ? null : activeDiagram(after.doc, after.activePath);
    const ids = new Set([result.nodeId]);
    for (const connection of parent?.connections ?? []) {
      if (result.connections.includes(connection.id)) {
        ids.add(connection.from.node);
        ids.add(connection.to.node);
      }
    }
    pendingFocus.current = [...ids];
  }, []);
  const terminalActions = useMemo(() => ({ reveal: revealPort }), [revealPort]);
  // The inspector's "Show on the parent diagram" asks through an event.
  useEffect(() => {
    const onReveal = (event: Event): void => {
      const name = (event as CustomEvent<string>).detail;
      if (typeof name === "string") {
        event.preventDefault();
        revealPort(name);
      }
    };
    window.addEventListener(REVEAL_PORT_EVENT, onReveal);
    return () => window.removeEventListener(REVEAL_PORT_EVENT, onReveal);
  }, [revealPort]);
  useEffect(() => {
    const ids = pendingFocus.current;
    if (ids === null || ids.some((id) => !flow.nodes.some((node) => node.id === id))) {
      return;
    }
    pendingFocus.current = null;
    void fitView({ nodes: ids.map((id) => ({ id })), padding: 0.35, maxZoom: 1.1, duration: 250 });
  }, [flow, fitView]);

  // Delete with selected terminals: a port connected outside asks first.
  const requestDelete = useCallback(() => {
    const ports = selectedTerminalPorts();
    if (ports.length === 0) {
      useDocumentStore.getState().deleteSelection();
      return;
    }
    const refusal = requestSubsystemPortDelete(ports, "selection");
    if (refusal !== null) {
      showTooltip({ x: window.innerWidth / 2, y: 120 }, refusal);
    }
  }, [showTooltip]);
  const requestDeleteRef = useRef(requestDelete);
  requestDeleteRef.current = requestDelete;

  /**
   * Offer the compatible elements at an empty release point. The list is
   * already ranked by `suggestTargets`; picking one adds it and connects the
   * port the drag started from.
   */
  const openSuggestions = useCallback(
    (origin: PortDescriptor, point: { x: number; y: number }) => {
      const state = useDocumentStore.getState();
      const indexNow = useCatalogStore.getState().index;
      const docNow =
        state.doc === null ? null : activeModel(state.doc, state.activePath);
      if (docNow === null || indexNow === null) {
        return;
      }
      const items = suggestTargets(docNow, indexNow, origin);
      const width = 300;
      const height = 380;
      const panel = {
        x: Math.max(8, Math.min(point.x + 14, window.innerWidth - width - 8)),
        y: Math.max(8, Math.min(point.y + 14, window.innerHeight - height - 8)),
      };
      setSuggestions({
        origin,
        items,
        flow: screenToFlowPosition(point, { snapToGrid: false }),
        client: point,
        panel,
      });
      // React Flow reports the release as a pane click; keep the palette open.
      suppressPaneClickUntil.current = Date.now() + 300;
    },
    [screenToFlowPosition],
  );

  // Any press outside the palette dismisses it (a press on a row is inside and
  // still reaches the row's click handler).
  useEffect(() => {
    if (suggestions === null) {
      return undefined;
    }
    const onPointerDown = (event: PointerEvent): void => {
      const target = event.target;
      if (target instanceof Element && target.closest(".target-suggest") !== null) {
        return;
      }
      setSuggestions(null);
    };
    window.addEventListener("pointerdown", onPointerDown, true);
    return () => window.removeEventListener("pointerdown", onPointerDown, true);
  }, [suggestions]);

  const chooseSuggestion = useCallback(
    (suggestion: TargetSuggestion) => {
      const current = suggestions;
      if (current === null) {
        return;
      }
      const state = useDocumentStore.getState();
      const indexNow = useCatalogStore.getState().index;
      if (indexNow === null) {
        return;
      }

      let width: number;
      let height: number;
      let offset: { x: number; y: number };
      if (suggestion.kind === "junction") {
        width = JUNCTION_NODE_SIZE;
        height = JUNCTION_NODE_SIZE;
        offset = { x: NODE_HALF_SHIFT, y: NODE_HALF_SHIFT };
      } else {
        const iface = interfaceForBlock(suggestion.block);
        const layout = layoutNode(iface);
        width = layout.width;
        height = layout.height;
        offset = isBondGraph(iface)
          ? { x: NODE_HALF_SHIFT, y: NODE_HALF_SHIFT }
          : { x: 0, y: 0 };
      }
      // Centre the new element on the release point; its ports stay reachable.
      const position = {
        x: current.flow.x - offset.x - width / 2,
        y: current.flow.y - offset.y - height / 2,
      };
      const placement = snap
        ? {
            x: Math.round(position.x / GRID_SIZE) * GRID_SIZE,
            y: Math.round(position.y / GRID_SIZE) * GRID_SIZE,
          }
        : position;

      const nodeId =
        suggestion.kind === "junction"
          ? state.addJunction(suggestion.junction, placement)
          : state.addBlock(suggestion.block, placement);
      setSuggestions(null);
      if (nodeId === null) {
        return;
      }

      const after = useDocumentStore.getState();
      const docAfter =
        after.doc === null ? null : activeModel(after.doc, after.activePath);
      if (docAfter === null) {
        return;
      }
      const target = descriptorForPort(
        docAfter.diagram.nodes,
        indexNow,
        nodeId,
        suggestion.portName,
      );
      if (target === null) {
        return;
      }
      const result = after.connect(current.origin, target);
      if (!result.ok && result.reason !== undefined) {
        showTooltip(current.client, result.reason);
      }
    },
    [suggestions, snap, showTooltip],
  );

  // Holding Ctrl (or Cmd) turns element drags into connections: the element
  // does not move, and a drag from it starts at its nearest source port.
  useEffect(() => {
    const isModifier = (event: KeyboardEvent): boolean =>
      event.key === "Control" || event.key === "Meta";
    const down = (event: KeyboardEvent): void => {
      if (isModifier(event)) {
        setQuickMode(true);
      }
    };
    const up = (event: KeyboardEvent): void => {
      if (isModifier(event)) {
        setQuickMode(false);
      }
    };
    const blur = (): void => setQuickMode(false);
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    window.addEventListener("blur", blur);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
      window.removeEventListener("blur", blur);
    };
  }, []);

  /**
   * Ctrl-drag from an element: pick the source port nearest the press and
   * track the pointer with a preview line. A plain Ctrl+click (no movement)
   * falls through to the normal selection click. Port handles keep React
   * Flow's own connection drag.
   */
  const startQuickConnect = useCallback(
    (event: React.PointerEvent, nodeId: string) => {
      if (!quickMode || event.button !== 0) {
        return;
      }
      setSuggestions(null);
      if ((event.target as HTMLElement | null)?.closest("[data-port]")) {
        return;
      }
      const current = useDocumentStore.getState();
      const catalogIndex = useCatalogStore.getState().index;
      const docNow =
        current.doc === null ? null : activeModel(current.doc, current.activePath);
      if (docNow === null || catalogIndex === null) {
        return;
      }
      const node = docNow.diagram.nodes.find((entry) => entry.id === nodeId);
      if (node === undefined) {
        return;
      }
      const iface = interfaceForNode(node, catalogIndex);
      let origin: PortDescriptor | null;
      if (iface.isJunction) {
        origin = descriptorForPort(docNow.diagram.nodes, catalogIndex, nodeId, null);
      } else {
        const layout = nodeLayout(node, catalogIndex, docNow);
        const flowPoint = screenToFlowPosition({ x: event.clientX, y: event.clientY });
        const offset = nodeVisualOffset(node, catalogIndex);
        const originPosition = {
          x: node.position.x + offset.x,
          y: node.position.y + offset.y,
        };
        const portName = nearestSourcePort(iface, layout, originPosition, flowPoint);
        origin =
          portName === null
            ? null
            : descriptorForPort(docNow.diagram.nodes, catalogIndex, nodeId, portName);
      }
      if (origin === null) {
        return;
      }
      const rect = canvasRef.current?.getBoundingClientRect();
      if (rect === undefined) {
        return;
      }
      quickGesture.current = {
        origin,
        startClient: { x: event.clientX, y: event.clientY },
        startLocal: { x: event.clientX - rect.left, y: event.clientY - rect.top },
        active: false,
      };

      const move = (moveEvent: PointerEvent): void => {
        const gesture = quickGesture.current;
        if (gesture === null) {
          return;
        }
        const distance = Math.hypot(
          moveEvent.clientX - gesture.startClient.x,
          moveEvent.clientY - gesture.startClient.y,
        );
        if (!gesture.active && distance < 4) {
          return;
        }
        gesture.active = true;
        const bounds = canvasRef.current?.getBoundingClientRect();
        if (bounds === undefined) {
          return;
        }
        setQuickLine({
          from: gesture.startLocal,
          to: { x: moveEvent.clientX - bounds.left, y: moveEvent.clientY - bounds.top },
        });
        setDragOrigin(gesture.origin);
        moveEvent.preventDefault();
      };

      const finish = (upEvent: PointerEvent): void => {
        window.removeEventListener("pointermove", move, true);
        window.removeEventListener("pointerup", finish, true);
        window.removeEventListener("pointercancel", finish, true);
        window.removeEventListener("keydown", cancelOnEscape, true);
        const gesture = quickGesture.current;
        quickGesture.current = null;
        setQuickLine(null);
        setDragOrigin(null);
        if (gesture === null || !gesture.active) {
          return;
        }
        // A click still follows the pointerup; it must not add to the selection.
        suppressClick.current = true;
        window.setTimeout(() => {
          suppressClick.current = false;
        }, 0);
        if (upEvent.type === "pointercancel") {
          return;
        }

        const element = document.elementFromPoint(upEvent.clientX, upEvent.clientY);
        let targetNodeId: string | null = null;
        let targetPort: string | null = null;
        let autoTarget = false;
        const ghost = element?.closest<HTMLElement>("[data-terminal-ghost]") ?? null;
        if (ghost !== null) {
          const kind = ghostKind(ghostId(ghost.getAttribute("data-terminal-ghost") as TerminalKind));
          if (kind !== null) {
            exposePort(gesture.origin, kind, { x: upEvent.clientX, y: upEvent.clientY });
          }
          return;
        }
        if (element instanceof Element) {
          const portElement = element.closest<HTMLElement>("[data-port]");
          if (portElement !== null) {
            targetNodeId = portElement.getAttribute("data-node-id");
            const port = portElement.getAttribute("data-port");
            targetPort = port === null || port.length === 0 ? null : port;
          } else {
            const nodeElement = element.closest<HTMLElement>('[data-testid="diagram-node"]');
            if (nodeElement !== null) {
              targetNodeId = nodeElement.getAttribute("data-node-id");
              // Dropping on the body picks the first compatible port; a
              // junction has no port and keeps its own descriptor.
              autoTarget = !nodeElement.hasAttribute("data-node-junction");
            }
          }
        }
        if (targetNodeId === null) {
          // Released on empty canvas: offer what could go there.
          openSuggestions(gesture.origin, {
            x: upEvent.clientX,
            y: upEvent.clientY,
          });
          return;
        }
        const state = useDocumentStore.getState();
        const rootDoc = state.doc;
        const indexNow = useCatalogStore.getState().index;
        const docNow =
          rootDoc === null ? null : activeModel(rootDoc, state.activePath);
        if (docNow === null || indexNow === null) {
          return;
        }
        const target = autoTarget
          ? firstCompatiblePort(docNow, indexNow, targetNodeId, gesture.origin)
          : descriptorForPort(docNow.diagram.nodes, indexNow, targetNodeId, targetPort);
        if (target === null) {
          if (autoTarget) {
            showTooltip(
              { x: upEvent.clientX, y: upEvent.clientY },
              noAutoTargetMessage(gesture.origin),
            );
          }
          return;
        }
        const result = state.connect(gesture.origin, target);
        if (!result.ok && result.reason !== undefined) {
          showTooltip({ x: upEvent.clientX, y: upEvent.clientY }, result.reason);
        }
      };

      // Plan 7.8: Esc cancels the drag; it ends like a pointercancel, so nothing is connected.
      const cancelOnEscape = (keyEvent: KeyboardEvent): void => {
        if (keyEvent.key === "Escape") {
          keyEvent.stopPropagation();
          finish(new PointerEvent("pointercancel"));
        }
      };

      window.addEventListener("pointermove", move, true);
      window.addEventListener("pointerup", finish, true);
      window.addEventListener("pointercancel", finish, true);
      window.addEventListener("keydown", cancelOnEscape, true);
    },
    [exposePort, quickMode, openSuggestions, screenToFlowPosition, showTooltip],
  );

  // --------------------------------------------------------------- shortcuts
  useEffect(() => {
    // Ctrl+V on a selected subsystem: the browser's paste event decides. An image on the
    // clipboard becomes the subsystem's image (ui.image); anything else is the node paste.
    let pendingImagePaste: { nodeId: string; timer: number } | null = null;
    const onPaste = (event: ClipboardEvent): void => {
      const pending = pendingImagePaste;
      if (pending === null) {
        return;
      }
      pendingImagePaste = null;
      window.clearTimeout(pending.timer);
      const load = imageFromDataTransfer(event.clipboardData);
      if (load === null) {
        useDocumentStore.getState().paste();
        return;
      }
      event.preventDefault();
      void applyNodeImage(pending.nodeId, load);
    };
    const onKeyDown = (event: KeyboardEvent): void => {
      if (editableTarget(event.target) || imagePasteTarget(event.target)) {
        return;
      }
      // The port-delete confirmation is modal.
      if (usePortDeleteStore.getState().request !== null) {
        return;
      }
      const store = useDocumentStore.getState();
      const mod = event.ctrlKey || event.metaKey;
      const key = event.key.toLowerCase();
      if (key === "escape") {
        setMenu(null);
        setTooltip(null);
        setSuggestions(null);
        // Plan 7.5/7.8: Esc cancels a drag or leaves a subsystem.
        if (store.activePath.length > 0) {
          store.leaveSubsystem();
        }
        return;
      }
      if (mod && key === "z") {
        event.preventDefault();
        if (event.shiftKey) {
          store.redo();
        } else {
          store.undo();
        }
        return;
      }
      if (mod && key === "y") {
        event.preventDefault();
        store.redo();
        return;
      }
      if (mod && key === "c") {
        if (store.selection.nodes.length > 0) {
          event.preventDefault();
          store.copySelection();
        }
        return;
      }
      if (mod && key === "v") {
        const subsystem = soleSelectedSubsystem();
        if (subsystem !== null) {
          // No preventDefault: that would cancel the paste event and its clipboard data.
          if (pendingImagePaste !== null) {
            window.clearTimeout(pendingImagePaste.timer);
          }
          pendingImagePaste = {
            nodeId: subsystem,
            timer: window.setTimeout(() => {
              pendingImagePaste = null;
              useDocumentStore.getState().paste();
            }, PASTE_EVENT_WAIT_MS),
          };
          return;
        }
        event.preventDefault();
        store.paste();
        return;
      }
      if (key === "delete" || key === "backspace") {
        if (store.selection.nodes.length > 0 || store.selection.connections.length > 0) {
          event.preventDefault();
          requestDeleteRef.current();
        }
        return;
      }
      if (!mod && !event.altKey && key === "r") {
        event.preventDefault();
        store.rotateSelection();
        return;
      }
      if (!mod && !event.altKey && key === "f") {
        event.preventDefault();
        store.flipSelection();
        return;
      }
      const pan = ARROW_PAN[event.key];
      if (pan !== undefined && !mod && !event.altKey) {
        // Arrows pan the canvas (Shift: a larger step). Only when focus is on
        // the canvas, on a container of it (the diagram tab) or nowhere, so
        // lists and panels keep their own arrow keys, and not on a focused
        // selected node, where React Flow moves the selection.
        const target = event.target as Element | null;
        const canvas = canvasRef.current;
        const onCanvas =
          target === document.body ||
          (target !== null && canvas !== null && (canvas.contains(target) || target.contains(canvas)));
        if (!onCanvas || target?.closest(".react-flow__node.selected") != null) {
          return;
        }
        event.preventDefault();
        const step = event.shiftKey ? PAN_STEP_LARGE : PAN_STEP;
        const { getViewport: get, setViewport: set } = viewportApi.current;
        const viewport = get();
        void set({ ...viewport, x: viewport.x - pan[0] * step, y: viewport.y - pan[1] * step });
      }
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("paste", onPaste);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("paste", onPaste);
      if (pendingImagePaste !== null) {
        window.clearTimeout(pendingImagePaste.timer);
      }
    };
  }, []);

  // --------------------------------------------------------------- connect
  const descriptorFor = useCallback(
    (nodeId: string | null | undefined, handleId: string | null | undefined) =>
      view === null || index === null || nodeId === null || nodeId === undefined
        ? null
        : descriptorForPort(view.diagram.nodes, index, nodeId, handleId ?? null),
    [view, index],
  );

  /**
   * A connection between an internal port and a "+ input" / "+ output" /
   * "+ power" ghost: the internal port's descriptor and the ghost's kind.
   */
  const ghostConnection = useCallback(
    (
      connection: Pick<Connection, "source" | "target" | "sourceHandle" | "targetHandle">,
    ): { kind: TerminalKind; internal: PortDescriptor | null } | null => {
      const sourceGhost = ghostKind(connection.source);
      const targetGhost = ghostKind(connection.target);
      const kind = sourceGhost ?? targetGhost;
      if (kind === null) {
        return null;
      }
      const [nodeId, handle] =
        sourceGhost !== null
          ? [connection.target, connection.targetHandle]
          : [connection.source, connection.sourceHandle];
      if (nodeId === null || isBoundaryElementId(nodeId)) {
        return { kind, internal: null };
      }
      return { kind, internal: descriptorFor(nodeId, handle ?? null) };
    },
    [descriptorFor],
  );
  // The "+ kind" ghost a connection drag started from, if any.
  const ghostDragRef = useRef<TerminalKind | null>(null);

  const onConnect: OnConnect = useCallback(
    (connection: Connection) => {
      if (probeDragRef.current !== null) {
        return;
      }
      const ghost = ghostConnection(connection);
      if (ghost !== null) {
        if (ghost.internal !== null) {
          exposePort(ghost.internal, ghost.kind, { x: window.innerWidth / 2, y: 120 });
        }
        return;
      }
      const from = descriptorFor(connection.source, connection.sourceHandle);
      const to = descriptorFor(connection.target, connection.targetHandle);
      if (from === null || to === null) {
        return;
      }
      const result = useDocumentStore.getState().connect(from, to);
      if (!result.ok && result.reason !== undefined) {
        showTooltip({ x: window.innerWidth / 2, y: 120 }, result.reason);
      }
    },
    [descriptorFor, exposePort, ghostConnection, showTooltip],
  );

  const onConnectStart: OnConnectStart = useCallback(
    (_event, params) => {
      setMenu(null);
      setSuggestions(null);
      ghostDragRef.current = ghostKind(params.nodeId);
      if (ghostDragRef.current !== null) {
        probeDragRef.current = null;
        setDragOrigin(null);
        return;
      }
      const probe = view?.diagram.probes?.find(
        (entry) => entry.id === params.nodeId && entry.kind === "block",
      );
      if (probe !== undefined) {
        probeDragRef.current = probe.id;
        setDragOrigin(null);
        return;
      }
      probeDragRef.current = null;
      setDragOrigin(descriptorFor(params.nodeId, params.handleId));
    },
    [descriptorFor, view],
  );

  const onConnectEnd: OnConnectEnd = useCallback(
    (event, state: FinalConnectionState) => {
      if (probeDragRef.current !== null) {
        const probeId = probeDragRef.current;
        probeDragRef.current = null;
        setDragOrigin(null);
        const point = eventPoint(event);
        const element = document.elementFromPoint(point.x, point.y);
        const edgeElement = element?.closest('[data-testid^="edge-"]') ?? null;
        const connectionId = edgeElement
          ?.getAttribute("data-testid")
          ?.replace(/^edge-/, "");
        if (connectionId === undefined || connectionId.length === 0) {
          showTooltip({ x: point.x, y: point.y }, "Drop the probe lead on a connection.");
          return;
        }
        const linkId = useDocumentStore.getState().addProbeLink(probeId, connectionId);
        if (linkId === null) {
          showTooltip(
            { x: point.x, y: point.y },
            "This connection is already on the probe.",
          );
        }
        return;
      }
      const origin = dragOrigin;
      setDragOrigin(null);
      const fromGhost = ghostDragRef.current;
      ghostDragRef.current = null;
      const nodeId = state.toHandle?.nodeId ?? state.toNode?.id ?? null;
      // A drag between an internal port and a "+ kind" ghost exposes the port;
      // a refused drop says why (`onConnect` handles the accepted one).
      if (fromGhost !== null || ghostKind(nodeId) !== null) {
        if (state.isValid !== false || nodeId === null) {
          return;
        }
        const ghost =
          fromGhost !== null
            ? ghostConnection({
                source: ghostId(fromGhost),
                sourceHandle: "g",
                target: nodeId,
                targetHandle: state.toHandle?.id ?? null,
              })
            : ghostConnection({
                source: origin?.nodeId ?? "",
                sourceHandle: origin?.portName ?? null,
                target: nodeId,
                targetHandle: "g",
              });
        const current = useDocumentStore.getState();
        const inner = current.doc === null ? null : activeDiagram(current.doc, current.activePath);
        if (ghost === null || ghost.internal === null || inner === null || boundary === null) {
          return;
        }
        const issue = exposeIssue(inner, boundary.ports, ghost.internal, ghost.kind);
        if (issue !== null) {
          showTooltip(eventPoint(event), issue);
        }
        return;
      }
      if (origin === null) {
        return;
      }
      // A release on the bare canvas is not a refusal: it offers compatible
      // elements to add at that point.
      if (nodeId === null) {
        openSuggestions(origin, eventPoint(event));
        return;
      }
      // A completed connection is already in the document; re-checking it would
      // call it a duplicate. Only an interaction that did not validate shows a
      // refusal.
      if (state.isValid !== false) {
        return;
      }
      const portId = state.toHandle?.id ?? null;
      const target = descriptorFor(nodeId, portId);
      const current = useDocumentStore.getState();
      const viewNow =
        current.doc === null ? null : activeModel(current.doc, current.activePath);
      if (target === null || viewNow === null) {
        return;
      }
      const result = checkConnection(viewNow, origin, target);
      if (!result.ok) {
        showTooltip(eventPoint(event), result.reason);
      }
    },
    [boundary, descriptorFor, dragOrigin, ghostConnection, openSuggestions, showTooltip],
  );

  const isValidConnection = useCallback(
    (connection: Connection | Edge) => {
      if (view === null) {
        return false;
      }
      const ghost = ghostConnection({
        source: connection.source,
        target: connection.target,
        sourceHandle: connection.sourceHandle ?? null,
        targetHandle: connection.targetHandle ?? null,
      });
      if (ghost !== null) {
        return (
          ghost.internal !== null &&
          boundary !== null &&
          exposeIssue(view.diagram, boundary.ports, ghost.internal, ghost.kind) === null
        );
      }
      if (isBoundaryElementId(connection.source) || isBoundaryElementId(connection.target)) {
        return false;
      }
      const from = descriptorFor(connection.source, connection.sourceHandle ?? null);
      const to = descriptorFor(connection.target, connection.targetHandle ?? null);
      if (from === null || to === null) {
        return false;
      }
      return checkConnection(view, from, to).ok;
    },
    [boundary, descriptorFor, ghostConnection, view],
  );

  // ------------------------------------------------------------------- drop
  const onDrop = useCallback(
    (event: React.DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      setSuggestions(null);
      const payload = readDragPayload(event.dataTransfer);
      if (payload === null || index === null) {
        return;
      }
      const position = screenToFlowPosition({ x: event.clientX, y: event.clientY });
      const placement = snap
        ? {
            x: Math.round(position.x / GRID_SIZE) * GRID_SIZE,
            y: Math.round(position.y / GRID_SIZE) * GRID_SIZE,
          }
        : position;
      const store = useDocumentStore.getState();
      if (payload.kind === "junction") {
        store.addJunction(payload.junction, placement);
        return;
      }
      const block = index.blocksByRef.get(payload.ref);
      if (block !== undefined) {
        store.addBlock(block, placement);
      }
    },
    [index, screenToFlowPosition, snap],
  );

  const onDragOver = useCallback((event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
  }, []);

  // --------------------------------------------------------------- xyflow
  const onSelectionChange: OnSelectionChangeFunc = useCallback(
    ({ nodes, edges }: { nodes: Node[]; edges: Edge[] }) => {
      // During a box selection the touched nodes only feed the canvas's own
      // highlight (`boxSelection`); `onSelectionEnd` commits the result.
      if (boxing.current) {
        setBoxSelection(nodes.map((node) => node.id));
        return;
      }
      // A pointer gesture mirrors its own result (`onNodeClick`, `onEdgeClick`,
      // `onNodeDragStart`, `onPaneClick`). The event trails it by a render and
      // reports xyflow's view, which can differ: xyflow toggles with Ctrl only
      // when it saw the key itself, so it would undo a Ctrl-click.
      // What is left is keyboard selection (Enter or Space on a focused node).
      if (pointerGesture.current) {
        return;
      }
      // React Flow can emit an empty selection while it adopts a replaced
      // `nodes` prop (for example when the Code tab hands the canvas a new
      // inline interface). That is not a user action: clearing on a pane click
      // is done by `onPaneClick`, and on an empty rectangle by
      // `onSelectionEnd`. Ignoring the transient keeps the document selection
      // from oscillating with the canvas's internal one.
      if (nodes.length === 0 && edges.length === 0) {
        return;
      }
      useDocumentStore
        .getState()
        .setSelection(
          nodes.map((node) => node.id),
          edges.map((edge) => edge.id),
        );
    },
    [],
  );

  /**
   * xyflow selects nodes by mutating its internal node records ("the
   * onNodesChange callback comes too late", in its source) and, with
   * controlled nodes and no `onNodesChange`, nothing re-renders them. When the
   * store's selection then does not change, for example a click on a node the
   * store already has selected, the canvas shows a selection the document does
   * not have. Re-adopting just the diverged nodes resynchronises the two; it
   * runs one frame after a pointer release, once React has applied the store.
   * The release is caught on the window: a drag can end outside the canvas.
   */
  const repairSelection = useCallback(() => {
    cancelAnimationFrame(repairFrame.current);
    repairFrame.current = requestAnimationFrame(() => {
      pointerGesture.current = false;
      if (boxing.current) {
        return;
      }
      const { nodes, nodeLookup, setNodes } = flowStore.getState();
      let diverged = false;
      const next = nodes.map((node) => {
        const internal = nodeLookup.get(node.id);
        if (internal !== undefined && (internal.selected ?? false) !== (node.selected ?? false)) {
          diverged = true;
          // The measured size keeps xyflow from hiding and re-measuring it.
          const { width, height } = internal.measured;
          const copy =
            width !== undefined && height !== undefined
              ? { ...node, measured: { width, height } }
              : { ...node };
          selectionOrigins.current.set(copy, selectionOrigins.current.get(node) ?? node);
          return copy;
        }
        return node;
      });
      if (diverged) {
        setNodes(next);
      }
    });
  }, [flowStore]);
  useEffect(
    () => () => {
      window.removeEventListener("pointerup", repairSelection, true);
      window.removeEventListener("pointercancel", repairSelection, true);
      cancelAnimationFrame(repairFrame.current);
    },
    [repairSelection],
  );

  const onSelectionStart = useCallback(() => {
    boxing.current = true;
    setBoxSelection([]);
  }, []);

  const onSelectionEnd = useCallback(() => {
    boxing.current = false;
    const ids: string[] = [];
    for (const [id, internal] of flowStore.getState().nodeLookup) {
      if (internal.selected === true) {
        ids.push(id);
      }
    }
    setBoxSelection(null);
    // One store update per rectangle; an empty rectangle clears, as xyflow
    // has already cleared its own selection when the rectangle started.
    useDocumentStore.getState().setSelection(ids, []);
    repairSelection();
  }, [flowStore, repairSelection]);

  /**
   * xyflow follows a box selection with a persistent `NodesSelection` box
   * around the selected nodes. It lingers until a pane click and sits on top
   * of the nodes, so the next click on one of them hit the box instead. The
   * editor drags a selection by any of its nodes, so the box is switched off
   * whenever xyflow turns it on.
   */
  useEffect(
    () =>
      flowStore.subscribe((state) => {
        if (state.nodesSelectionActive) {
          flowStore.setState({ nodesSelectionActive: false });
        }
      }),
    [flowStore],
  );

  /**
   * React Flow's `onSelectionChange` is driven by an effect and can trail the
   * pointer by one interaction with controlled nodes. Clicking is therefore
   * mirrored into the store directly; a box selection is committed by
   * `onSelectionEnd`.
   */
  const onNodeClick = useCallback((event: React.MouseEvent, node: Node) => {
    if (suppressClick.current) {
      suppressClick.current = false;
      return;
    }
    const ghost = ghostKind(node.id);
    if (ghost !== null) {
      showTooltip(
        { x: event.clientX, y: event.clientY },
        ghost === "power"
          ? "Drag a connection from an internal power port or junction onto + power to expose it."
          : `Drag a connection from an internal signal ${ghost} onto + ${ghost} to expose it.`,
      );
      return;
    }
    const store = useDocumentStore.getState();
    const additive = event.ctrlKey || event.metaKey;
    if (!additive) {
      store.setSelection([node.id], []);
      return;
    }
    const current = store.selection.nodes;
    const next = current.includes(node.id)
      ? current.filter((id) => id !== node.id)
      : [...current, node.id];
    store.setSelection(next, []);
  }, [showTooltip]);

  const onEdgeClick = useCallback((event: React.MouseEvent, edge: Edge) => {
    const store = useDocumentStore.getState();
    const additive = event.ctrlKey || event.metaKey;
    if (!additive) {
      store.setSelection([], [edge.id]);
      return;
    }
    const current = store.selection.connections;
    const next = current.includes(edge.id)
      ? current.filter((id) => id !== edge.id)
      : [...current, edge.id];
    store.setSelection([], next);
  }, []);

  /**
   * Plan 7.4/7.7: a double-click on a subsystem enters its nested diagram; a
   * double-click on an inline node opens its source in the Code tab.
   */
  const onNodeDoubleClick = useCallback((_event: React.MouseEvent, node: Node) => {
    // A terminal leaves the subsystem and shows its outside connection.
    const terminal = terminalPortName(node.id);
    if (terminal !== null) {
      revealPort(terminal);
      return;
    }
    if (ghostKind(node.id) !== null) {
      return;
    }
    const doc = useDocumentStore.getState().doc;
    const path = useDocumentStore.getState().activePath;
    const view = doc === null ? null : activeModel(doc, path);
    const target = view?.diagram.nodes.find((entry) => entry.id === node.id);
    if (target === undefined) {
      const probe = view?.diagram.probes?.find((entry) => entry.id === node.id);
      if (probe !== undefined) {
        useDocumentStore.getState().setSelection([probe.id], []);
        useDocumentStore.getState().setProbeOpen(probe.id, !(probe.open ?? true));
      }
      return;
    }
    if ("subsystem" in target.block) {
      useDocumentStore.getState().enterSubsystem(target.id);
      return;
    }
    if ("inline" in target.block) {
      requestSource({ kind: "inline", ref: target.id, line: 1, col: 1 }, { reveal: true });
    }
  }, [revealPort]);

  const onEdgeContextMenu = useCallback((event: React.MouseEvent, edge: Edge) => {
    event.preventDefault();
    useDocumentStore.getState().setSelection([], [edge.id]);
    setMenu({
      x: event.clientX,
      y: event.clientY,
      kind: "edge",
      id: edge.id,
      flow: screenToFlowPosition(
        { x: event.clientX, y: event.clientY },
        { snapToGrid: false },
      ),
    });
  }, [screenToFlowPosition]);

  const onNodeContextMenu = useCallback((event: React.MouseEvent, node: Node) => {
    event.preventDefault();
    if (ghostKind(node.id) !== null) {
      setMenu(null);
      return;
    }
    const store = useDocumentStore.getState();
    if (!store.selection.nodes.includes(node.id)) {
      store.setSelection([node.id], []);
    }
    const portElement =
      event.target instanceof Element ? event.target.closest<HTMLElement>("[data-port]") : null;
    const portName = portElement?.getAttribute("data-port") ?? "";
    setMenu({
      x: event.clientX,
      y: event.clientY,
      kind: "node",
      id: node.id,
      port:
        portElement !== null && portName.length > 0
          ? { name: portName, power: portElement.getAttribute("data-kind") === "power" }
          : undefined,
    });
  }, []);

  const menuConnection = useMemo(
    () =>
      menu?.kind === "edge"
        ? view?.diagram.connections.find((connection) => connection.id === menu.id) ?? null
        : null,
    [view, menu],
  );

  // Plotting from the canvas (plan 7.5): a bond offers the port's effort/flow/
  // power, an instance offers its recorded outputs. The signal ids come from
  // the current run manifest, so the store can reject an id the run lacks.
  const runSignals = useRunStore((state) => state.manifest?.signals ?? null);
  const menuNode = useMemo(
    () => (menu?.kind === "node" && view !== null ? nodeForMenu(view, menu.id) : undefined),
    [view, menu],
  );
  const menuPlotTargets = useMemo(
    () =>
      view !== null && menuConnection !== null
        ? connectionPlotTargets(view, menuConnection)
        : [],
    [view, menuConnection],
  );
  const menuOutputIds = useMemo(
    () =>
      menuNode === undefined
        ? []
        : nodeOutputIds(runSignals ?? [], menuNode, pathPrefix),
    [menuNode, runSignals, pathPrefix],
  );
  // The signals a debug action on the menu offers: a port's e/f/P (or its one signal), else the instance outputs.
  const menuDebugSignals = useMemo(() => {
    if (menuNode === undefined) {
      return [];
    }
    if (menu?.port !== undefined) {
      if (menu.port.power) {
        const ids = powerHoverSignalIds(pathPrefix, menuNode.name, menu.port.name);
        return [ids.e, ids.f, ids.P];
      }
      return [signalHoverSignalId(pathPrefix, menuNode.name, menu.port.name)];
    }
    return menuOutputIds;
  }, [menu, menuNode, menuOutputIds, pathPrefix]);

  // Inside a subsystem, a right-click on an internal port (or a junction)
  // offers to expose it as a subsystem port.
  const menuExpose = useMemo((): PortDescriptor | null => {
    if (menu?.kind !== "node" || boundary === null || menuNode === undefined) {
      return null;
    }
    if ("junction" in menuNode.block) {
      return descriptorFor(menuNode.id, null);
    }
    return menu.port === undefined ? null : descriptorFor(menuNode.id, menu.port.name);
  }, [boundary, descriptorFor, menu, menuNode]);

  const startProbeLead = useCallback(
    (probeId: string, event: React.PointerEvent<HTMLElement>) => {
      if (event.button !== 0) {
        return;
      }
      const bounds = canvasRef.current?.getBoundingClientRect();
      if (bounds === undefined) {
        return;
      }
      const start = { x: event.clientX, y: event.clientY };
      let active = false;
      const move = (moveEvent: PointerEvent): void => {
        const distance = Math.hypot(
          moveEvent.clientX - start.x,
          moveEvent.clientY - start.y,
        );
        if (!active && distance < 4) {
          return;
        }
        active = true;
        setQuickLine({
          from: { x: start.x - bounds.left, y: start.y - bounds.top },
          to: {
            x: moveEvent.clientX - bounds.left,
            y: moveEvent.clientY - bounds.top,
          },
        });
        moveEvent.preventDefault();
      };
      const finish = (upEvent: PointerEvent): void => {
        window.removeEventListener("pointermove", move, true);
        window.removeEventListener("pointerup", finish, true);
        window.removeEventListener("pointercancel", cancel, true);
        setQuickLine(null);
        if (!active) {
          return;
        }
        const element = document.elementFromPoint(upEvent.clientX, upEvent.clientY);
        const edgeElement = element?.closest('[data-testid^="edge-"]') ?? null;
        const connectionId = edgeElement
          ?.getAttribute("data-testid")
          ?.replace(/^edge-/, "");
        if (connectionId === undefined || connectionId.length === 0) {
          showTooltip(
            { x: upEvent.clientX, y: upEvent.clientY },
            "Drop the probe lead on a connection.",
          );
          return;
        }
        const linkId = useDocumentStore.getState().addProbeLink(probeId, connectionId);
        if (linkId === null) {
          showTooltip(
            { x: upEvent.clientX, y: upEvent.clientY },
            "This connection is already on the probe.",
          );
        }
      };
      const cancel = (): void => {
        window.removeEventListener("pointermove", move, true);
        window.removeEventListener("pointerup", finish, true);
        window.removeEventListener("pointercancel", cancel, true);
        setQuickLine(null);
      };
      window.addEventListener("pointermove", move, true);
      window.addEventListener("pointerup", finish, true);
      window.addEventListener("pointercancel", cancel, true);
    },
    [showTooltip],
  );

  const createProbeOnMenu = (kind: "block" | "window"): void => {
    if (view === null || index === null || menuConnection === null) {
      return;
    }
    const { source, target } = connectionAnchors(view, index, menuConnection);
    const tap = {
      x: (source.point.x + target.point.x) / 2,
      y: (source.point.y + target.point.y) / 2,
    };
    const panelPosition =
      kind === "block"
        ? { x: tap.x + 140, y: tap.y - 60 }
        : { x: tap.x + 20, y: tap.y + 20 };
    const id = useDocumentStore.getState().addProbe(
      kind,
      kind === "block" ? { x: tap.x + 80, y: tap.y - 30 } : tap,
      panelPosition,
    );
    if (id !== null) {
      useDocumentStore.getState().addProbeLink(id, menuConnection.id);
      useDocumentStore.getState().setSelection([id], []);
    }
  };

  const runMenuAction = (action: () => void): void => {
    action();
    setMenu(null);
  };

  /**
   * Routing aids for long connections: insert a waypoint at the clicked point
   * (on the closest segment), or clear all waypoints. The new point snaps to the
   * double-resolution route grid (grid corners and cell centres). Dragging the
   * resulting handles (rendered by the selected edge) does the fine adjustment.
   */
  const addRouteVertex = (): void => {
    if (view === null || index === null || menuConnection === null) {
      return;
    }
    const { source, target } = connectionAnchors(view, index, menuConnection);
    const route = [...(menuConnection.route ?? [])];
    const points = [source.point, ...route, target.point];
    const click =
      menu?.flow !== undefined &&
      Number.isFinite(menu.flow.x) &&
      Number.isFinite(menu.flow.y)
        ? menu.flow
        : undefined;
    let bestIndex = 0;
    let bestDistance = Infinity;
    if (click !== undefined) {
      for (let segment = 0; segment < points.length - 1; segment += 1) {
        const start = points[segment]!;
        const end = points[segment + 1]!;
        const distance = distanceToSegment(click, start, end);
        if (distance < bestDistance) {
          bestDistance = distance;
          bestIndex = segment;
        }
      }
    } else {
      let bestLength = -1;
      for (let segment = 0; segment < points.length - 1; segment += 1) {
        const start = points[segment]!;
        const end = points[segment + 1]!;
        const length = Math.hypot(end.x - start.x, end.y - start.y);
        if (length > bestLength) {
          bestLength = length;
          bestIndex = segment;
        }
      }
    }
    const start = points[bestIndex]!;
    const end = points[bestIndex + 1]!;
    const raw =
      click ?? { x: (start.x + end.x) / 2, y: (start.y + end.y) / 2 };
    route.splice(bestIndex, 0, snap ? snapRouteVertex(raw) : raw);
    useDocumentStore.getState().setConnectionRoute(menuConnection.id, route);
  };

  return (
    <div className="editor" data-testid="editor">
      <div className="editor__toolbar">
        <div className="editor__session" data-testid="session-label">
          <span className="editor__project">{project ?? "No project"}</span>
          <span className="editor__breadcrumb" aria-hidden="true">
            ▸
          </span>
          <span className="editor__model">{modelName ?? "No model"}</span>
        </div>
        <div className="editor__toolbar-spacer" />
        <span
          className="editor__save"
          data-testid="save-status"
          data-state={saveState === "error" ? "error" : dirty ? "dirty" : saveState}
          title={saveError ?? "The model is saved through PUT /api/projects/{p}/models/{m}"}
        >
          {dirty ? <span className="editor__dirty" data-testid="dirty-marker" aria-hidden="true" /> : null}
          {saveLabel(saveState, dirty)}
        </span>
        <button
          type="button"
          className="button button--compact"
          data-testid="create-subsystem"
          onClick={() => {
            if (index !== null) {
              const result = useDocumentStore.getState().createSubsystem(index);
              if (!result.ok && result.error !== undefined) {
                showTooltip({ x: window.innerWidth / 2, y: 120 }, result.error);
              }
            }
          }}
          disabled={selection.nodes.length === 0 || index === null}
          aria-label="Create subsystem from selection"
          title={
            selection.nodes.length === 0
              ? "Select blocks to group into a subsystem"
              : "Group the selected blocks and the connections inside them into a subsystem"
          }
        >
          ⧉ Subsystem
        </button>
        <button
          type="button"
          className="icon-button"
          data-testid="undo"
          onClick={() => useDocumentStore.getState().undo()}
          disabled={pastLength === 0}
          aria-label="Undo"
          title="Undo (Ctrl+Z)"
        >
          ↶
        </button>
        <button
          type="button"
          className="icon-button"
          data-testid="redo"
          onClick={() => useDocumentStore.getState().redo()}
          disabled={futureLength === 0}
          aria-label="Redo"
          title="Redo (Ctrl+Y)"
        >
          ↷
        </button>
        <button
          type="button"
          className="icon-button"
          data-testid="fit-view"
          onClick={() => void fitView({ padding: 0.2, maxZoom: 1.2, duration: 200 })}
          aria-label="Fit view"
          title="Fit the diagram in the canvas"
        >
          ⤢
        </button>
        <button
          type="button"
          className={`icon-button${showGrid ? " is-active" : ""}`}
          data-testid="toggle-grid"
          aria-pressed={showGrid}
          onClick={() => {
            const next = !showGrid;
            setShowGrid(next);
            writePreference(GRID_KEY, next);
          }}
          aria-label="Show grid"
          title="Show or hide the grid"
        >
          ▦
        </button>
        <button
          type="button"
          className={`icon-button${snap ? " is-active" : ""}`}
          data-testid="toggle-snap"
          aria-pressed={snap}
          onClick={() => {
            const next = !snap;
            setSnap(next);
            writePreference(SNAP_KEY, next);
          }}
          aria-label="Snap to grid"
          title={`Snap to grid (${GRID_SIZE} px)`}
        >
          ⌗
        </button>
        <button
          type="button"
          className="icon-button"
          data-testid="add-probe-block"
          aria-label="Add probe block"
          title="Add a 3×3 oscilloscope probe block"
          onClick={() => {
            const rect = canvasRef.current?.getBoundingClientRect();
            if (rect === undefined) {
              return;
            }
            const position = screenToFlowPosition(
              { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 },
              { snapToGrid: false },
            );
            useDocumentStore.getState().addProbe(
              "block",
              position,
              { x: position.x + 80, y: position.y - 60 },
            );
          }}
        >
          <ProbeGlyph size={16} />
        </button>
        <button
          type="button"
          className="icon-button"
          data-testid="add-probe-window"
          aria-label="Add probe plot window"
          title="Add a floating oscilloscope plot window"
          onClick={() => {
            const rect = canvasRef.current?.getBoundingClientRect();
            if (rect === undefined) {
              return;
            }
            const position = screenToFlowPosition(
              { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 },
              { snapToGrid: false },
            );
            useDocumentStore.getState().addProbe("window", position, {
              x: position.x - 190,
              y: position.y - 120,
            });
          }}
        >
          <span aria-hidden="true">▤</span>
        </button>
        <button
          type="button"
          className="icon-button"
          data-testid="save-now"
          onClick={() => void saveCurrentModel()}
          aria-label="Save now"
          title="Save now"
        >
          ⌘
        </button>
      </div>

      <SubsystemBreadcrumbs />

      <div
        className="editor__canvas"
        data-testid="canvas-surface"
        ref={canvasRef}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onPointerDownCapture={() => {
          pointerGesture.current = true;
          // The same listener twice is one listener; `once` removes it.
          window.addEventListener("pointerup", repairSelection, { capture: true, once: true });
          window.addEventListener("pointercancel", repairSelection, {
            capture: true,
            once: true,
          });
        }}
      >
        <QuickConnectContext.Provider
          value={{ enabled: quickMode, start: startQuickConnect }}
        >
          <TerminalActionsContext.Provider value={terminalActions}>
            <ReactFlow
              className={quickMode ? "is-quick-connect" : undefined}
              nodes={flow.nodes}
              edges={flowEdges}
              nodeTypes={NODE_TYPES}
              edgeTypes={EDGE_TYPES}
              connectionMode={ConnectionMode.Loose}
              connectionLineType={ConnectionLineType.SmoothStep}
              connectionLineStyle={{ stroke: "var(--color-accent)", strokeWidth: 1.6 }}
              connectionRadius={20}
              defaultViewport={{ x: 0, y: 0, zoom: ZOOM }}
              minZoom={0.1}
              maxZoom={2}
              nodesDraggable={!quickMode}
              snapToGrid={snap}
              snapGrid={[GRID_SIZE, GRID_SIZE]}
              deleteKeyCode={null}
              selectionKeyCode="Shift"
              multiSelectionKeyCode={["Meta", "Control"]}
              // A left drag on empty canvas draws a selection rectangle; panning
              // moves to the middle and right buttons (and Space+drag).
              selectionOnDrag
              selectionMode={SelectionMode.Partial}
              panOnDrag={[1, 2]}
              onSelectionStart={onSelectionStart}
              onSelectionEnd={onSelectionEnd}
              nodeClickDistance={CLICK_DISTANCE}
              paneClickDistance={CLICK_DISTANCE}
              onConnect={onConnect}
              onConnectStart={onConnectStart}
              onConnectEnd={onConnectEnd}
              isValidConnection={isValidConnection}
              onNodeDragStart={(event, _node, nodes) => {
                const store = useDocumentStore.getState();
                const ids = nodes.map((dragged) => dragged.id);
                if (!ids.every((id) => store.selection.nodes.includes(id))) {
                  if (event.ctrlKey || event.metaKey) {
                    store.setSelection([...new Set([...store.selection.nodes, ...ids])], []);
                  } else {
                    store.setSelection(ids, []);
                  }
                }
                store.beginGesture("node-drag");
              }}
              onNodeDrag={(_event, _node, nodes) => {
                const positions: Record<string, { x: number; y: number }> = {};
                const terminals: Record<string, { x: number; y: number }> = {};
                for (const dragged of nodes) {
                  const port = terminalPortName(dragged.id);
                  const point = { x: dragged.position.x, y: dragged.position.y };
                  if (port !== null) {
                    terminals[port] = point;
                  } else {
                    positions[dragged.id] = point;
                  }
                }
                const store = useDocumentStore.getState();
                // Both coalesce into the drag gesture: one undo step.
                store.setNodePositions(positions, true);
                store.setSubsystemPortPositions(terminals, true);
                for (const dragged of nodes) {
                  store.setProbePosition(
                    dragged.id,
                    { x: dragged.position.x, y: dragged.position.y },
                    true,
                  );
                }
              }}
              onNodeDragStop={() => useDocumentStore.getState().endGesture()}
              onSelectionChange={onSelectionChange}
              onNodeClick={onNodeClick}
              onNodeDoubleClick={onNodeDoubleClick}
              onEdgeClick={onEdgeClick}
              onEdgeContextMenu={onEdgeContextMenu}
              onNodeContextMenu={onNodeContextMenu}
              onPaneClick={() => {
                // The release that opened the suggestion palette also produces a
                // pane click; it must not close the palette it just opened.
                if (Date.now() < suppressPaneClickUntil.current) {
                  return;
                }
                setMenu(null);
                setTooltip(null);
                setSuggestions(null);
                useDocumentStore.getState().setSelection([], []);
              }}
              onPaneContextMenu={(event) => {
                event.preventDefault();
                setMenu(null);
              }}
              proOptions={{ hideAttribution: true }}
            >
              <CanvasZoomVariable />
              {showGrid ? (
                <Background
                  variant={BackgroundVariant.Lines}
                  gap={GRID_SIZE}
                  size={1}
                  color="var(--color-border)"
                />
              ) : null}
              <Panel position="bottom-left">
                <CanvasLegend />
              </Panel>
              <ViewportPortal>
                <Suspense fallback={null}>
                  {view?.diagram.probes?.map((probe) => (
                    <ProbeWindow
                      key={probe.id}
                      model={view}
                      probe={probe}
                      onProbeLeadStart={startProbeLead}
                    />
                  ))}
                </Suspense>
              </ViewportPortal>
            </ReactFlow>
          </TerminalActionsContext.Provider>
        </QuickConnectContext.Provider>
        {view !== null && index !== null ? (
          <ProbeLeads model={view} index={index} />
        ) : null}
        {quickLine !== null ? (
          <svg className="editor-quick-line" data-testid="quick-connect-line" aria-hidden="true">
            <line
              x1={quickLine.from.x}
              y1={quickLine.from.y}
              x2={quickLine.to.x}
              y2={quickLine.to.y}
            />
            <circle cx={quickLine.from.x} cy={quickLine.from.y} r={3} />
          </svg>
        ) : null}
        {suggestions !== null ? (
          <TargetSuggestions
            suggestions={suggestions.items}
            origin={suggestions.origin}
            x={suggestions.panel.x}
            y={suggestions.panel.y}
            onPick={chooseSuggestion}
            onClose={() => setSuggestions(null)}
          />
        ) : null}
        {flow.nodes.length === 0 ? (
          <div className="editor__empty" data-testid="canvas-empty">
            <p>Drag a block from the library onto the canvas.</p>
            <p className="editor__empty-hint">
              Power ports connect as bonds or wires; outputs connect to inputs as signals. Press{" "}
              <kbd>/</kbd> to search the library, <kbd>?</kbd> for all shortcuts.
            </p>
          </div>
        ) : null}
      </div>

      <HoverReadout canvasRef={canvasRef} model={view} pathPrefix={pathPrefix} />

      {tooltip !== null ? (
        <div
          className="editor-tooltip"
          role="alert"
          data-testid="connection-refusal"
          style={{ left: tooltip.x, top: tooltip.y }}
        >
          {tooltip.message}
        </div>
      ) : null}

      <PortDeleteConfirm
        onRefused={(message) => showTooltip({ x: window.innerWidth / 2, y: 120 }, message)}
      />

      {menu !== null ? (
        <div
          className="editor-menu"
          role="menu"
          data-testid="canvas-menu"
          style={{ left: menu.x, top: menu.y }}
        >
          {menu.kind === "edge" && menuConnection !== null ? (
            <>
              {menuConnection.kind === "bond" ? (
                <button
                  type="button"
                  role="menuitem"
                  data-testid="reverse-bond"
                  onClick={() =>
                    runMenuAction(() =>
                      useDocumentStore.getState().reverseConnection(menuConnection.id),
                    )
                  }
                >
                  Reverse bond direction
                </button>
              ) : null}
              {menuPlotTargets.map((target) => (
                <button
                  type="button"
                  role="menuitem"
                  key={target.testId}
                  data-testid={target.testId}
                  data-signal-id={target.signalId}
                  title={`Plot ${target.detail} from the current run`}
                  onClick={() =>
                    runMenuAction(() => {
                      useRunStore.getState().addSignal(target.signalId);
                      requestPlotsTab();
                    })
                  }
                >
                  {target.label}
                </button>
              ))}
              {menuPlotTargets[0] !== undefined ? (
                <SignalMenuItems
                  signalId={menuPlotTargets[0].signalId}
                  candidates={menuPlotTargets.map((target) => target.signalId)}
                  onDone={() => setMenu(null)}
                />
              ) : null}
              <button
                type="button"
                role="menuitem"
                data-testid="new-probe-block"
                onClick={() => runMenuAction(() => createProbeOnMenu("block"))}
              >
                New probe block
              </button>
              <button
                type="button"
                role="menuitem"
                data-testid="new-probe-window"
                onClick={() => runMenuAction(() => createProbeOnMenu("window"))}
              >
                New probe plot window
              </button>
              {(view?.diagram.probes ?? []).map((probe) => (
                <button
                  type="button"
                  role="menuitem"
                  key={probe.id}
                  data-testid={`probe-existing-${probe.id}`}
                  onClick={() =>
                    runMenuAction(() => {
                      useDocumentStore.getState().addProbeLink(probe.id, menuConnection.id);
                      useDocumentStore.getState().setSelection([probe.id], []);
                    })
                  }
                >
                  Add to {probe.name}
                </button>
              ))}
              <button
                type="button"
                role="menuitem"
                data-testid="add-vertex"
                onClick={() => runMenuAction(addRouteVertex)}
              >
                Add routing vertex
              </button>
              {(menuConnection.route?.length ?? 0) > 0 ? (
                <button
                  type="button"
                  role="menuitem"
                  data-testid="clear-vertices"
                  onClick={() =>
                    runMenuAction(() =>
                      useDocumentStore.getState().setConnectionRoute(menuConnection.id, []),
                    )
                  }
                >
                  Clear routing vertices
                </button>
              ) : null}
              <button
                type="button"
                role="menuitem"
                data-testid="delete-connection"
                onClick={() =>
                  runMenuAction(() => {
                    useDocumentStore.getState().setSelection([], [menuConnection.id]);
                    useDocumentStore.getState().deleteSelection();
                  })
                }
              >
                Delete connection
              </button>
            </>
          ) : null}
          {menu.kind === "node" && terminalPortName(menu.id) !== null ? (
            <TerminalMenuItems
              portName={terminalPortName(menu.id) ?? ""}
              onReveal={(name) => runMenuAction(() => revealPort(name))}
              onRename={(name) =>
                runMenuAction(() => {
                  useDocumentStore.getState().setSelection([terminalId(name)], []);
                  focusPortNameField();
                })
              }
              onDelete={() => runMenuAction(requestDelete)}
            />
          ) : null}
          {menu.kind === "node" && terminalPortName(menu.id) === null ? (
            <>
              {menuExpose !== null ? (
                <button
                  type="button"
                  role="menuitem"
                  data-testid="expose-port"
                  title="Add a subsystem port that maps to this internal port; the outer block gets it at once"
                  onClick={() =>
                    runMenuAction(() => exposePort(menuExpose, undefined, { x: menu.x, y: menu.y }))
                  }
                >
                  Expose as subsystem port
                </button>
              ) : null}
              <button
                type="button"
                role="menuitem"
                data-testid="rotate-selection"
                onClick={() => runMenuAction(() => useDocumentStore.getState().rotateSelection())}
              >
                Rotate 90° (R)
              </button>
              <button
                type="button"
                role="menuitem"
                data-testid="flip-selection"
                onClick={() => runMenuAction(() => useDocumentStore.getState().flipSelection())}
              >
                Flip horizontally (F)
              </button>
              <button
                type="button"
                role="menuitem"
                data-testid="plot-all-outputs"
                data-output-count={menuOutputIds.length}
                disabled={runSignals !== null && menuOutputIds.length === 0}
                title={
                  runSignals === null
                    ? "Run the model first; its recorded outputs are plotted"
                    : menuOutputIds.length === 0
                      ? "This run recorded no output signals for this instance"
                      : `Plot ${menuOutputIds.join(", ")}`
                }
                onClick={() =>
                  runMenuAction(() => {
                    if (useRunStore.getState().addSignals(menuOutputIds) > 0) {
                      requestPlotsTab();
                    }
                  })
                }
              >
                Plot all outputs
                {menuOutputIds.length > 0 ? ` (${menuOutputIds.length})` : ""}
              </button>
              <SignalMenuItems
                signalId={menuDebugSignals[0] ?? ""}
                candidates={menuDebugSignals}
                onDone={() => setMenu(null)}
                disabledReason={
                  menuDebugSignals.length > 0
                    ? null
                    : runSignals === null
                      ? "Run the model first; the signals of this block are known after a run"
                      : "This run recorded no signals for this selection"
                }
              />
              {menuNode !== undefined && "subsystem" in menuNode.block ? (
                <button
                  type="button"
                  role="menuitem"
                  data-testid="export-subsystem"
                  title="Export this subsystem alone as a C/FMU; its ports are the interface"
                  onClick={() =>
                    runMenuAction(() =>
                      useExportDialogStore
                        .getState()
                        .openExport(pathPrefix.length > 0 ? `${pathPrefix}/${menuNode.name}` : menuNode.name),
                    )
                  }
                >
                  Export subsystem…
                </button>
              ) : null}
              <button
                type="button"
                role="menuitem"
                data-testid="delete-selection"
                onClick={() => runMenuAction(requestDelete)}
              >
                Delete (Del)
              </button>
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
