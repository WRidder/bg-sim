/**
 * Gutter breakpoints and the pause line for the Code tab (plan 7.9, D26).
 *
 * The gutter shows one marker per line breakpoint of the open block, plus an
 * arrow on the line a statement pause stopped at:
 *
 *   - filled circle   verified by the server (or hit) and enabled;
 *   - hollow circle   not verified yet (no debug run), or `verified = false`
 *                     (hover shows the E401 or W401 message from the server);
 *   - dashed circle   disabled;
 *   - `?` / `#`       inside the circle: a condition / a hit count is set;
 *   - arrow           where the run is paused (the line also gets a highlight).
 *
 * The extension itself knows nothing about the stores: `CodeEditor` feeds it
 * `GutterEntry` lists through {@link attachBreakpointSync}, which computes them
 * with {@link gutterEntriesFor} from the breakpoint store and the debug store.
 * Click or F9 toggles, right-click asks the host to edit the condition.
 */

import { type Extension, RangeSet, StateEffect, StateField, type Text } from "@codemirror/state";
import { Decoration, type DecorationSet, EditorView, GutterMarker, gutter, keymap } from "@codemirror/view";

import type { Breakpoint, BreakpointStatus, LineBreakpoint, PausedInfo } from "../contracts/debug";
import { lineBreakpointsOf, useBreakpointStore } from "../debug/breakpointStore";
import { useDebugStore } from "../debug/debugStore";
import "./breakpoints.css";

export interface GutterEntry {
  /** 1-based line. */
  line: number;
  /** The breakpoint id, or null for a pause-only arrow. */
  id: string | null;
  enabled: boolean;
  /** True/false from the server, null before any debug run reported it. */
  verified: boolean | null;
  title: string;
  conditional: boolean;
  hitCount: boolean;
  paused: boolean;
}

export interface GutterHandlers {
  /** Click in the gutter or F9. */
  onToggle: (line: number) => void;
  /** Right-click on a marker: edit its condition and hit count. */
  onEdit: (id: string, point: { x: number; y: number }) => void;
  /** The text moved a breakpoint to another line. */
  onMoved: (id: string, line: number) => void;
}

// ------------------------------------------------------------------- entries

function describeBreakpoint(
  entry: LineBreakpoint,
  status: BreakpointStatus | undefined,
): { title: string; verified: boolean | null } {
  const details: string[] = [];
  if (entry.condition !== null && entry.condition !== undefined && entry.condition.length > 0) {
    details.push(`when ${entry.condition}`);
  }
  if (entry.hitCount !== null && entry.hitCount !== undefined) {
    details.push(`hit ${entry.hitCount}`);
  }
  const suffix = details.length > 0 ? ` (${details.join(", ")})` : "";
  const verified = status === undefined ? null : status.verified;
  if (!entry.enabled) {
    return { title: `Disabled breakpoint at line ${entry.line.line}${suffix}`, verified };
  }
  if (status === undefined) {
    return {
      title: `Breakpoint at line ${entry.line.line}${suffix}. It is checked when a debug run starts.`,
      verified,
    };
  }
  if (!status.verified) {
    const lines = status.diagnostics.map((diagnostic) => {
      const hint = diagnostic.hint === null || diagnostic.hint === undefined ? "" : ` ${diagnostic.hint}`;
      return `${diagnostic.code}: ${diagnostic.message}${hint}`;
    });
    const reason = lines.length > 0 ? lines.join("\n") : "The model has no statement at this line.";
    return { title: `Unverified breakpoint at line ${entry.line.line}${suffix}\n${reason}`, verified };
  }
  const where = status.resolved.paths.length > 0 ? `, ${status.resolved.paths.join(", ")}` : "";
  return { title: `Breakpoint at line ${entry.line.line}${suffix}${where}`, verified };
}

/** The gutter entries of one source: its line breakpoints plus the pause arrow. */
export function gutterEntriesFor(
  ref: string,
  breakpoints: readonly Breakpoint[],
  statuses: Readonly<Record<string, BreakpointStatus>>,
  paused: PausedInfo | null,
): GutterEntry[] {
  const byLine = new Map<number, GutterEntry>();
  for (const entry of lineBreakpointsOf(breakpoints, ref)) {
    if (byLine.has(entry.line.line)) {
      continue;
    }
    const { title, verified } = describeBreakpoint(entry, statuses[entry.id]);
    byLine.set(entry.line.line, {
      line: entry.line.line,
      id: entry.id,
      enabled: entry.enabled,
      verified,
      title,
      conditional: entry.condition !== null && entry.condition !== undefined && entry.condition.length > 0,
      hitCount: entry.hitCount !== null && entry.hitCount !== undefined,
      paused: false,
    });
  }
  const location = paused?.location;
  if (location !== null && location !== undefined && location.scope !== "watch" && location.ref === ref) {
    const line = location.range.line;
    const existing = byLine.get(line);
    if (existing !== undefined) {
      byLine.set(line, { ...existing, paused: true });
    } else {
      byLine.set(line, {
        line,
        id: null,
        enabled: true,
        verified: null,
        title: `Paused here (${location.path})`,
        conditional: false,
        hitCount: false,
        paused: true,
      });
    }
  }
  return [...byLine.values()].sort((a, b) => a.line - b.line);
}

/** The line a pause stopped at in this source, or null. */
export function pausedLineIn(ref: string, paused: PausedInfo | null): number | null {
  const location = paused?.location;
  if (location === null || location === undefined || location.scope === "watch" || location.ref !== ref) {
    return null;
  }
  return location.range.line;
}

// ------------------------------------------------------------------- marker

function sameEntry(a: GutterEntry, b: GutterEntry): boolean {
  return (
    a.line === b.line &&
    a.id === b.id &&
    a.enabled === b.enabled &&
    a.verified === b.verified &&
    a.title === b.title &&
    a.conditional === b.conditional &&
    a.hitCount === b.hitCount &&
    a.paused === b.paused
  );
}

export function markerState(entry: GutterEntry): "verified" | "unverified" | "disabled" | "pause" {
  if (entry.id === null) {
    return "pause";
  }
  if (!entry.enabled) {
    return "disabled";
  }
  return entry.verified === true ? "verified" : "unverified";
}

class BreakpointMarker extends GutterMarker {
  constructor(readonly entry: GutterEntry) {
    super();
  }

  eq(other: GutterMarker): boolean {
    return other instanceof BreakpointMarker && sameEntry(this.entry, other.entry);
  }

  toDOM(): Node {
    const entry = this.entry;
    const state = markerState(entry);
    const dom = document.createElement("span");
    dom.className = `cm-bp-marker cm-bp-marker--${state}${entry.paused ? " cm-bp-marker--paused" : ""}`;
    dom.dataset.testid = "bp-marker";
    dom.setAttribute("data-testid", "bp-marker");
    dom.dataset.line = String(entry.line);
    dom.dataset.state = state;
    if (entry.id !== null) {
      dom.dataset.bpId = entry.id;
    }
    dom.title = entry.title;
    dom.setAttribute("role", "img");
    dom.setAttribute("aria-label", entry.title.split("\n")[0] ?? entry.title);
    if (state === "pause") {
      dom.textContent = "▶";
    } else if (entry.conditional) {
      dom.textContent = "?";
    } else if (entry.hitCount) {
      dom.textContent = "#";
    }
    return dom;
  }
}

class SpacerMarker extends GutterMarker {
  toDOM(): Node {
    const dom = document.createElement("span");
    dom.className = "cm-bp-marker cm-bp-marker--spacer";
    return dom;
  }
}

// -------------------------------------------------------------------- state

/** Replace the gutter entries (and with them the pause highlight). */
export const setGutterEntries = StateEffect.define<GutterEntry[]>();

interface GutterState {
  entries: GutterEntry[];
  markers: RangeSet<GutterMarker>;
  decorations: DecorationSet;
}

const pausedLine = Decoration.line({ class: "cm-paused-line", attributes: { "data-paused": "true" } });

function buildState(doc: Text, entries: readonly GutterEntry[]): GutterState {
  const markers: { from: number; value: GutterMarker }[] = [];
  const lines: number[] = [];
  const kept: GutterEntry[] = [];
  for (const entry of entries) {
    if (entry.line < 1 || entry.line > doc.lines) {
      continue;
    }
    const from = doc.line(entry.line).from;
    kept.push(entry);
    markers.push({ from, value: new BreakpointMarker(entry) });
    if (entry.paused) {
      lines.push(from);
    }
  }
  return {
    entries: kept,
    markers: RangeSet.of(
      markers.map((marker) => marker.value.range(marker.from)),
      true,
    ),
    decorations: Decoration.set(lines.map((from) => pausedLine.range(from)), true),
  };
}

const gutterState = StateField.define<GutterState>({
  create: (state) => buildState(state.doc, []),
  update(value, transaction) {
    for (const effect of transaction.effects) {
      if (effect.is(setGutterEntries)) {
        return buildState(transaction.state.doc, effect.value);
      }
    }
    if (transaction.docChanged) {
      return {
        entries: value.entries,
        markers: value.markers.map(transaction.changes),
        decorations: value.decorations.map(transaction.changes),
      };
    }
    return value;
  },
  provide: (field) => EditorView.decorations.from(field, (value) => value.decorations),
});

/** The entries currently shown (test and debugging aid). */
export function gutterEntriesOf(view: EditorView): readonly GutterEntry[] {
  return view.state.field(gutterState).entries;
}

/** The 1-based paused line shown by the view, or null. */
export function pausedLineOf(view: EditorView): number | null {
  return view.state.field(gutterState).entries.find((entry) => entry.paused)?.line ?? null;
}

/** The gutter, its click handlers, F9, and the pause line. */
export function breakpointGutter(handlers: () => GutterHandlers): Extension {
  const lineOf = (view: EditorView, from: number): number => view.state.doc.lineAt(from).number;

  return [
    gutterState,
    gutter({
      class: "cm-bp-gutter",
      markers: (view) => view.state.field(gutterState).markers,
      initialSpacer: () => new SpacerMarker(),
      domEventHandlers: {
        mousedown(view, block, event) {
          if ((event as MouseEvent).button !== 0) {
            return false;
          }
          handlers().onToggle(lineOf(view, block.from));
          return true;
        },
        contextmenu(view, block, event) {
          const line = lineOf(view, block.from);
          const entry = view.state.field(gutterState).entries.find((item) => item.line === line);
          if (entry === undefined || entry.id === null) {
            return false;
          }
          event.preventDefault();
          const mouse = event as MouseEvent;
          handlers().onEdit(entry.id, { x: mouse.clientX, y: mouse.clientY });
          return true;
        },
      },
    }),
    keymap.of([
      {
        key: "F9",
        run: (view) => {
          handlers().onToggle(lineOf(view, view.state.selection.main.head));
          return true;
        },
      },
    ]),
    // Text edits move the markers with the lines; tell the store where they went.
    EditorView.updateListener.of((update) => {
      if (!update.docChanged) {
        return;
      }
      if (update.transactions.some((transaction) => transaction.effects.some((e) => e.is(setGutterEntries)))) {
        return;
      }
      const moved: { id: string; line: number }[] = [];
      const iterator = update.state.field(gutterState).markers.iter();
      while (iterator.value !== null) {
        const marker = iterator.value;
        if (marker instanceof BreakpointMarker && marker.entry.id !== null) {
          const line = lineOf(update.view, iterator.from);
          if (line !== marker.entry.line) {
            moved.push({ id: marker.entry.id, line });
          }
        }
        iterator.next();
      }
      if (moved.length > 0) {
        // Dispatching from an update listener is not allowed; hand over to the store.
        queueMicrotask(() => {
          for (const item of moved) {
            handlers().onMoved(item.id, item.line);
          }
        });
      }
    }),
  ];
}

// --------------------------------------------------------------------- sync

export interface BreakpointSyncOptions {
  /** `inline:<node-id>` or the library block ref the editor shows. */
  ref: string;
  onEdit: (id: string, point: { x: number; y: number }) => void;
}

/** The handlers `CodeEditor` hands to {@link breakpointGutter} for a source. */
export function storeHandlers(options: BreakpointSyncOptions): GutterHandlers {
  return {
    onToggle: (line) => {
      useBreakpointStore.getState().toggleLine(options.ref, line, null);
    },
    onEdit: options.onEdit,
    onMoved: (id, line) => useBreakpointStore.getState().moveLine(id, line),
  };
}

/**
 * Keep a view's gutter in step with the breakpoint store and the debug store.
 * Scrolls the paused line into view at every new pause. Returns the unsubscribe.
 */
export function attachBreakpointSync(view: EditorView, ref: string): () => void {
  let lastSignature = "";
  let lastPauseCount = -1;

  const apply = (): void => {
    const breakpoints = useBreakpointStore.getState().breakpoints;
    const debug = useDebugStore.getState();
    const entries = gutterEntriesFor(ref, breakpoints, debug.statuses, debug.pausedInfo);
    const signature = JSON.stringify(entries);
    const newPause = debug.pauseCount !== lastPauseCount;
    lastPauseCount = debug.pauseCount;
    if (signature === lastSignature) {
      return;
    }
    lastSignature = signature;
    const effects: StateEffect<unknown>[] = [setGutterEntries.of(entries)];
    const paused = entries.find((entry) => entry.paused);
    if (paused !== undefined && newPause && paused.line <= view.state.doc.lines) {
      effects.push(EditorView.scrollIntoView(view.state.doc.line(paused.line).from, { y: "center" }));
    }
    view.dispatch({ effects });
  };

  apply();
  const offBreakpoints = useBreakpointStore.subscribe(apply);
  const offDebug = useDebugStore.subscribe(apply);
  return () => {
    offBreakpoints();
    offDebug();
  };
}
