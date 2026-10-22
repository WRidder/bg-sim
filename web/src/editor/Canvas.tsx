/**
 * The xyflow canvas of plan 7.2/7.3.
 *
 * Interactions:
 * * drag a library row onto the canvas -> add a block or junction;
 * * drag between port glyphs -> bond / wire / signal, with live compatibility
 *   highlighting and the plan's refusal tooltip;
 * * drag nodes -> move (one undo entry per drag);
 * * Del, R, F, Ctrl+C/V, Ctrl+Z/Y;
 * * right-click an edge -> reverse a bond; right-click a node -> transform.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  BackgroundVariant,
  ConnectionLineType,
  ConnectionMode,
  Panel,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
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
import { buildDiagram, EDGE_TYPES, NODE_TYPES } from "./buildFlow";
import { checkConnection } from "./connectionRules";
import { descriptorForPort } from "./nodeInterface";
import { DOMAIN_LEGEND, domainColor } from "./geometry";
import "./editor.css";

const ZOOM = 0.85;

interface Tooltip {
  x: number;
  y: number;
  message: string;
}

interface MenuState {
  x: number;
  y: number;
  kind: "node" | "edge";
  id: string;
}

function eventPoint(event: MouseEvent | TouchEvent): { x: number; y: number } {
  if ("clientX" in event) {
    return { x: event.clientX, y: event.clientY };
  }
  const touch = event.changedTouches[0];
  return { x: touch?.clientX ?? 0, y: touch?.clientY ?? 0 };
}

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

function CanvasInner() {
  const doc = useDocumentStore((state) => state.doc);
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

  const [dragOrigin, setDragOrigin] = useState<ReturnType<typeof descriptorForPort>>(null);
  const [tooltip, setTooltip] = useState<Tooltip | null>(null);
  const [menu, setMenu] = useState<MenuState | null>(null);
  const tooltipTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { fitView, screenToFlowPosition } = useReactFlow();

  const flow = useMemo(
    () =>
      doc === null || index === null
        ? { nodes: [], edges: [], analysis: null }
        : buildDiagram(doc, index, selection, dragOrigin),
    [doc, index, selection, dragOrigin],
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

  // --------------------------------------------------------------- shortcuts
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if (editableTarget(event.target)) {
        return;
      }
      const store = useDocumentStore.getState();
      const mod = event.ctrlKey || event.metaKey;
      const key = event.key.toLowerCase();
      if (key === "escape") {
        setMenu(null);
        setTooltip(null);
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
        event.preventDefault();
        store.paste();
        return;
      }
      if (key === "delete" || key === "backspace") {
        if (store.selection.nodes.length > 0 || store.selection.connections.length > 0) {
          event.preventDefault();
          store.deleteSelection();
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
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  // --------------------------------------------------------------- connect
  const descriptorFor = useCallback(
    (nodeId: string | null | undefined, handleId: string | null | undefined) =>
      doc === null || index === null || nodeId === null || nodeId === undefined
        ? null
        : descriptorForPort(doc.diagram.nodes, index, nodeId, handleId ?? null),
    [doc, index],
  );

  const onConnect: OnConnect = useCallback(
    (connection: Connection) => {
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
    [descriptorFor, showTooltip],
  );

  const onConnectStart: OnConnectStart = useCallback(
    (_event, params) => {
      setMenu(null);
      setDragOrigin(descriptorFor(params.nodeId, params.handleId));
    },
    [descriptorFor],
  );

  const onConnectEnd: OnConnectEnd = useCallback(
    (event, state: FinalConnectionState) => {
      const origin = dragOrigin;
      setDragOrigin(null);
      if (origin === null) {
        return;
      }
      // A completed connection is already in the document; re-checking it would
      // call it a duplicate. Only an interaction that did not validate shows a
      // refusal.
      if (state.isValid !== false) {
        return;
      }
      const nodeId = state.toHandle?.nodeId ?? state.toNode?.id ?? null;
      const portId = state.toHandle?.id ?? null;
      const target = descriptorFor(nodeId, portId);
      const current = useDocumentStore.getState().doc;
      if (target === null || current === null) {
        return;
      }
      const result = checkConnection(current, origin, target);
      if (!result.ok) {
        showTooltip(eventPoint(event), result.reason);
      }
    },
    [descriptorFor, dragOrigin, showTooltip],
  );

  const isValidConnection = useCallback(
    (connection: Connection | Edge) => {
      if (doc === null) {
        return false;
      }
      const from = descriptorFor(connection.source, connection.sourceHandle ?? null);
      const to = descriptorFor(connection.target, connection.targetHandle ?? null);
      if (from === null || to === null) {
        return false;
      }
      return checkConnection(doc, from, to).ok;
    },
    [descriptorFor, doc],
  );

  // ------------------------------------------------------------------- drop
  const onDrop = useCallback(
    (event: React.DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      const payload = readDragPayload(event.dataTransfer);
      if (payload === null || index === null) {
        return;
      }
      const position = screenToFlowPosition({ x: event.clientX, y: event.clientY });
      const store = useDocumentStore.getState();
      if (payload.kind === "junction") {
        store.addJunction(payload.junction, position);
        return;
      }
      const block = index.blocksByRef.get(payload.ref);
      if (block !== undefined) {
        store.addBlock(block, position);
      }
    },
    [index, screenToFlowPosition],
  );

  const onDragOver = useCallback((event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
  }, []);

  // --------------------------------------------------------------- xyflow
  const onSelectionChange: OnSelectionChangeFunc = useCallback(
    ({ nodes, edges }: { nodes: Node[]; edges: Edge[] }) => {
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
   * React Flow's `onSelectionChange` is driven by an effect and can trail the
   * pointer by one interaction with controlled nodes. Clicking is therefore
   * mirrored into the store directly; `onSelectionChange` still covers box
   * selection.
   */
  const onNodeClick = useCallback((event: React.MouseEvent, node: Node) => {
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
  }, []);

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

  const onEdgeContextMenu = useCallback((event: React.MouseEvent, edge: Edge) => {
    event.preventDefault();
    useDocumentStore.getState().setSelection([], [edge.id]);
    setMenu({ x: event.clientX, y: event.clientY, kind: "edge", id: edge.id });
  }, []);

  const onNodeContextMenu = useCallback((event: React.MouseEvent, node: Node) => {
    event.preventDefault();
    const store = useDocumentStore.getState();
    if (!store.selection.nodes.includes(node.id)) {
      store.setSelection([node.id], []);
    }
    setMenu({ x: event.clientX, y: event.clientY, kind: "node", id: node.id });
  }, []);

  const menuConnection = useMemo(
    () =>
      menu?.kind === "edge"
        ? doc?.diagram.connections.find((connection) => connection.id === menu.id) ?? null
        : null,
    [doc, menu],
  );

  const runMenuAction = (action: () => void): void => {
    action();
    setMenu(null);
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
          className="icon-button"
          data-testid="save-now"
          onClick={() => void saveCurrentModel()}
          aria-label="Save now"
          title="Save now"
        >
          ⌘
        </button>
      </div>

      <div
        className="editor__canvas"
        data-testid="canvas-surface"
        onDrop={onDrop}
        onDragOver={onDragOver}
      >
        <ReactFlow
          nodes={flow.nodes}
          edges={flow.edges}
          nodeTypes={NODE_TYPES}
          edgeTypes={EDGE_TYPES}
          connectionMode={ConnectionMode.Loose}
          connectionLineType={ConnectionLineType.SmoothStep}
          connectionLineStyle={{ stroke: "var(--color-accent)", strokeWidth: 1.6 }}
          connectionRadius={20}
          defaultViewport={{ x: 0, y: 0, zoom: ZOOM }}
          minZoom={0.2}
          maxZoom={2}
          deleteKeyCode={null}
          selectionKeyCode="Shift"
          multiSelectionKeyCode={["Meta", "Control"]}
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
            for (const dragged of nodes) {
              positions[dragged.id] = { x: dragged.position.x, y: dragged.position.y };
            }
            useDocumentStore.getState().setNodePositions(positions, true);
          }}
          onNodeDragStop={() => useDocumentStore.getState().endGesture()}
          onSelectionChange={onSelectionChange}
          onNodeClick={onNodeClick}
          onEdgeClick={onEdgeClick}
          onEdgeContextMenu={onEdgeContextMenu}
          onNodeContextMenu={onNodeContextMenu}
          onPaneClick={() => {
            setMenu(null);
            setTooltip(null);
            useDocumentStore.getState().setSelection([], []);
          }}
          onPaneContextMenu={(event) => {
            event.preventDefault();
            setMenu(null);
          }}
          proOptions={{ hideAttribution: true }}
        >
          <Background variant={BackgroundVariant.Dots} gap={18} size={1} color="var(--color-border)" />
          <Panel position="bottom-left" className="editor-legend" data-testid="canvas-legend">
            <span className="editor-legend__title">Domains</span>
            {DOMAIN_LEGEND.map((entry) => (
              <span className="editor-legend__item" key={entry.domain}>
                <span
                  className={`editor-legend__swatch${entry.domain === "Generic" ? " is-generic" : ""}`}
                  style={{ background: domainColor(entry.domain) }}
                  aria-hidden="true"
                />
                {entry.label}
              </span>
            ))}
            <span className="editor-legend__separator" aria-hidden="true" />
            <span className="editor-legend__item">
              <span className="editor-legend__glyph editor-legend__glyph--power" aria-hidden="true" />
              power
            </span>
            <span className="editor-legend__item">
              <span className="editor-legend__glyph editor-legend__glyph--input" aria-hidden="true" />
              in
            </span>
            <span className="editor-legend__item">
              <span className="editor-legend__glyph editor-legend__glyph--output" aria-hidden="true" />
              out
            </span>
          </Panel>
        </ReactFlow>
        {flow.nodes.length === 0 ? (
          <div className="editor__empty" data-testid="canvas-empty">
            <p>Drag a block from the library onto the canvas.</p>
            <p className="editor__empty-hint">
              Power ports connect as bonds or wires; outputs connect to inputs as signals.
            </p>
          </div>
        ) : null}
      </div>

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
          {menu.kind === "node" ? (
            <>
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
                data-testid="delete-selection"
                onClick={() => runMenuAction(() => useDocumentStore.getState().deleteSelection())}
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
