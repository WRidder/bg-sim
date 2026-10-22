/**
 * The signal browser of plan 7.5, mounted in the bottom dock's Signals tab.
 *
 * A tree by instance path with a search over id/path/unit/kind, a glyph per
 * signal kind (state, algebraic, observed, port e/f/P, discrete, input/output),
 * the unit, and two ways to plot a signal: double-click (or Enter) adds it to
 * the active panel, drag-and-drop targets a specific panel.
 *
 * The list is the manifest's `signals` table (plan 3.5), so it always matches
 * the columns the run actually recorded.
 */

import { useMemo, useState, type DragEvent, type KeyboardEvent } from "react";

import { EmptyState } from "../app/EmptyState";
import type { RunSignal, RunSignalKind } from "../contracts/run-manifest";
import { useRunStore, plottedSignalIds } from "./runStore";
import { writeSignalDrag } from "./signalDnd";
import {
  buildSignalTree,
  countNodeSignals,
  filterSignals,
  signalLeafName,
  type SignalPathNode,
} from "./signalTree";
import "./plot.css";

const KIND_TITLE: Record<RunSignalKind, string> = {
  state: "state variable",
  algebraic: "algebraic variable",
  observed: "observed variable",
  port: "power-port variable",
  power: "port power",
  discrete: "discrete signal",
  input: "input signal",
  output: "output signal",
};

/** A distinct short glyph per kind; the port glyph is the variable letter. */
function kindGlyph(signal: RunSignal): string {
  switch (signal.kind) {
    case "state":
      return "◉";
    case "algebraic":
      return "ƒ";
    case "observed":
      return "◎";
    case "port": {
      const suffix = signal.id.split(".").pop();
      return suffix === "e" || suffix === "f" ? suffix : "p";
    }
    case "power":
      return "P";
    case "discrete":
      return "▮";
    case "input":
      return "in";
    case "output":
      return "out";
    default:
      return "?";
  }
}

export function SignalBrowser() {
  const manifest = useRunStore((state) => state.manifest);
  const status = useRunStore((state) => state.status);
  const panels = useRunStore((state) => state.panels);
  const activePanelId = useRunStore((state) => state.activePanelId);
  const notice = useRunStore((state) => state.notice);
  const addSignal = useRunStore((state) => state.addSignal);
  const [query, setQuery] = useState("");
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(new Set());

  const allSignals = manifest?.signals ?? [];
  const filtered = useMemo(
    () => filterSignals(allSignals, query),
    [allSignals, query],
  );
  const tree = useMemo(() => buildSignalTree(filtered), [filtered]);
  const plotted = useMemo(() => new Set(plottedSignalIds(panels)), [panels]);
  const activeIndex = panels.findIndex((panel) => panel.id === activePanelId);
  const activeNumber = activeIndex >= 0 ? activeIndex + 1 : 1;
  const searching = query.trim().length > 0;

  const toggle = (key: string): void => {
    setCollapsed((current) => {
      const next = new Set(current);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const add = (signal: RunSignal): void => {
    addSignal(signal.id);
  };

  const onDragStart = (
    event: DragEvent<HTMLLIElement>,
    signal: RunSignal,
  ): void => {
    writeSignalDrag(event.dataTransfer, signal.id);
  };

  const onRowKeyDown = (
    event: KeyboardEvent<HTMLLIElement>,
    signal: RunSignal,
  ): void => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      add(signal);
    }
  };

  const renderSignal = (signal: RunSignal) => (
    <li
      className={`signal-row${plotted.has(signal.id) ? " is-plotted" : ""}`}
      key={signal.id}
      role="treeitem"
      tabIndex={0}
      draggable
      data-testid="signal-item"
      data-signal-id={signal.id}
      data-kind={signal.kind}
      aria-label={`${signal.id} (${KIND_TITLE[signal.kind]}${
        signal.unit ? `, ${signal.unit}` : ""
      }); double-click or press Enter to add it to Panel ${activeNumber}`}
      title={`${signal.id} — ${KIND_TITLE[signal.kind]}${
        signal.unit ? ` · ${signal.unit}` : ""
      } · ${signal.type}`}
      onDragStart={(event) => onDragStart(event, signal)}
      onDoubleClick={() => add(signal)}
      onKeyDown={(event) => onRowKeyDown(event, signal)}
    >
      <span
        className={`signal-kind signal-kind--${signal.kind}`}
        data-kind={signal.kind}
        title={KIND_TITLE[signal.kind]}
        aria-label={KIND_TITLE[signal.kind]}
      >
        {kindGlyph(signal)}
      </span>
      <span className="signal-row__name">{signalLeafName(signal)}</span>
      <span className="signal-row__unit">{signal.unit ?? "—"}</span>
      <span className="signal-row__type">{signal.type}</span>
      <button
        type="button"
        className="signal-row__add"
        aria-label={`Add ${signal.id} to Panel ${activeNumber}`}
        title={`Add ${signal.id} to Panel ${activeNumber}`}
        onClick={(event) => {
          event.stopPropagation();
          add(signal);
        }}
      >
        +
      </button>
    </li>
  );

  const renderNode = (node: SignalPathNode, depth: number) => {
    const open = searching || !collapsed.has(node.key);
    return (
      <li
        className="signal-tree__node"
        key={node.key}
        role="treeitem"
        aria-expanded={open}
      >
        <button
          type="button"
          className="signal-tree__group"
          onClick={() => toggle(node.key)}
          style={{ paddingLeft: 6 + depth * 12 }}
          aria-label={`${node.path || "model"}: ${countNodeSignals(node)} signals`}
        >
          <span className="signal-tree__arrow" aria-hidden="true">
            {open ? "▾" : "▸"}
          </span>
          <span className="signal-tree__segment">{node.segment}</span>
          <span className="signal-tree__count">{countNodeSignals(node)}</span>
        </button>
        {open ? (
          <ul className="signal-tree__children" role="group">
            {node.children.map((child) => renderNode(child, depth + 1))}
            {node.signals.map(renderSignal)}
          </ul>
        ) : null}
      </li>
    );
  };

  if (manifest === null) {
    return (
      <EmptyState
        title="No signals"
        hint={
          status === "starting"
            ? "The run is starting; its recorded signals appear here as soon as the worker reports them."
            : "After a run, browse every recorded signal here and add it to a plot panel."
        }
      />
    );
  }

  return (
    <div className="signal-browser" data-testid="signal-browser">
      <div className="signal-browser__search">
        <input
          type="search"
          className="signal-browser__input"
          placeholder="Search signals, paths, units…"
          aria-label="Search signals"
          data-testid="signal-search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <span className="signal-browser__count" data-testid="signal-count">
          {filtered.length}/{allSignals.length}
        </span>
      </div>

      {notice !== null ? (
        <p className="signal-browser__notice" role="status" data-testid="signal-notice">
          {notice}
        </p>
      ) : null}

      <div className="signal-browser__scroll">
        {tree.length === 0 ? (
          <p className="signal-browser__no-match" data-testid="signal-no-match">
            {searching
              ? `No signal matches “${query}”.`
              : status === "starting" || status === "running"
                ? "The run has not published its signal list yet; it appears when the worker writes the manifest."
                : "This run recorded no signals."}
          </p>
        ) : (
          <ul className="signal-tree" role="tree" aria-label="Recorded signals">
            {tree.map((node) => renderNode(node, 0))}
          </ul>
        )}
      </div>

      <p className="signal-browser__footer" data-testid="signal-target">
        Double-click a signal to add it to{" "}
        <strong>Panel {activeNumber}</strong>. Drag it onto a panel to choose the
        target.
      </p>
    </div>
  );
}
