/**
 * Breakpoints (plan 7.9): every breakpoint with an enable toggle, a kind icon
 * (colour plus glyph), the verified state and the server's diagnostics, and a
 * delete button; the use of the 16 watch slots; and the "break on" switches.
 */

import { requestSource } from "../../code/codeSession";
import type { Breakpoint, BreakpointStatus } from "../../contracts/debug";
import { useDocumentStore } from "../../state/documentStore";
import { useBreakpointStore } from "../breakpointStore";
import { isDebugging, useDebugStore } from "../debugStore";
import { blockLabel, formatPauseTime } from "../format";
import { sourceKindOf } from "../pauseNavigation";
import { MAX_WATCH_SLOTS, watchSlotsText, watchSlotsUsed } from "./breakWhen";
import {
  enabledExceptionCodes,
  eventBreakOn,
  EXCEPTION_CODES,
  EXCEPTION_TEXT,
  setEventBreak,
  setExceptionBreak,
} from "./breakOn";

const KIND_GLYPH: Record<Breakpoint["kind"], string> = {
  line: "●",
  watch: "◆",
  time: "◷",
  event: "▲",
  exception: "✱",
};

const KIND_NAME: Record<Breakpoint["kind"], string> = {
  line: "Line breakpoint",
  watch: "Watch breakpoint",
  time: "Time breakpoint",
  event: "Event breakpoint",
  exception: "Exception breakpoint",
};

/** What a breakpoint row says. */
export function describeBreakpoint(entry: Breakpoint, doc = useDocumentStore.getState().doc): string {
  switch (entry.kind) {
    case "line": {
      const where = `${blockLabel(entry.line.ref, doc)} line ${entry.line.line}`;
      const path = entry.line.path !== null ? ` (${entry.line.path})` : "";
      const condition =
        entry.condition !== undefined && entry.condition !== null ? ` when ${entry.condition}` : "";
      const hits = entry.hitCount !== undefined && entry.hitCount !== null ? `, hit ${entry.hitCount}` : "";
      return `${where}${path}${condition}${hits}`;
    }
    case "watch": {
      const hits = entry.hitCount !== undefined && entry.hitCount !== null ? `, hit ${entry.hitCount}` : "";
      return `${entry.watch.expr}${hits}`;
    }
    case "time":
      return `t = ${formatPauseTime(entry.time.t)}`;
    case "event":
      return entry.event.path === null
        ? "after every @events firing"
        : `after @events of ${entry.event.path}`;
    case "exception":
      return `on ${entry.exception.on.join(", ")}`;
  }
}

function StatusText({ status, debugging }: { status: BreakpointStatus | undefined; debugging: boolean }) {
  if (status === undefined) {
    return (
      <span className="debug-bp__state" data-state="pending">
        {debugging ? "checking…" : "not checked until a debug run"}
      </span>
    );
  }
  return (
    <span className="debug-bp__state" data-state={status.verified ? "verified" : "unverified"}>
      {status.verified ? "verified" : "not verified"}
      {status.verified && status.resolved.hooks > 0 ? ` (${status.resolved.hooks})` : ""}
    </span>
  );
}

function Row({ entry }: { entry: Breakpoint }) {
  const status = useDebugStore((state) => state.statuses[entry.id]);
  const debugging = useDebugStore(isDebugging);
  const text = describeBreakpoint(entry);
  const line = entry.kind === "line" ? entry.line : null;
  return (
    <li
      className={`debug-bp${entry.enabled ? "" : " is-disabled"}`}
      data-testid="breakpoint-row"
      data-kind={entry.kind}
      data-bp-id={entry.id}
      data-verified={status === undefined ? "unknown" : String(status.verified)}
    >
      <input
        type="checkbox"
        checked={entry.enabled}
        aria-label={`Enable ${KIND_NAME[entry.kind].toLowerCase()} ${text}`}
        data-testid="breakpoint-enable"
        onChange={(event) => useBreakpointStore.getState().setEnabled(entry.id, event.target.checked)}
      />
      <span
        className={`debug-bp__icon debug-bp__icon--${entry.kind}`}
        role="img"
        aria-label={KIND_NAME[entry.kind]}
        title={KIND_NAME[entry.kind]}
      >
        {KIND_GLYPH[entry.kind]}
      </span>
      {line !== null ? (
        <button
          type="button"
          className="debug-bp__text debug-bp__text--link"
          title="Open this line in the Code tab"
          data-testid="breakpoint-open"
          onClick={() =>
            requestSource(
              { kind: sourceKindOf(line.ref), ref: line.ref, line: line.line, col: 1 },
              { reveal: true },
            )
          }
        >
          {text}
        </button>
      ) : (
        <code className="debug-bp__text" data-testid="breakpoint-text">
          {text}
        </code>
      )}
      <StatusText status={status} debugging={debugging} />
      <button
        type="button"
        className="debug-row-button"
        aria-label={`Delete ${KIND_NAME[entry.kind].toLowerCase()} ${text}`}
        title="Delete"
        data-testid="breakpoint-delete"
        onClick={() => useBreakpointStore.getState().remove(entry.id)}
      >
        ✕
      </button>
      {status !== undefined && status.diagnostics.length > 0 ? (
        <ul className="debug-bp__diagnostics" data-testid="breakpoint-diagnostics">
          {status.diagnostics.map((diagnostic, index) => (
            <li key={`${diagnostic.code}-${index}`} data-severity={diagnostic.severity}>
              <strong>{diagnostic.code}</strong> {diagnostic.message}
              {diagnostic.hint ? ` ${diagnostic.hint}` : ""}
            </li>
          ))}
        </ul>
      ) : null}
    </li>
  );
}

export function BreakpointsSection() {
  const breakpoints = useBreakpointStore((state) => state.breakpoints);
  const events = eventBreakOn(breakpoints);
  const codes = enabledExceptionCodes(breakpoints);
  const slots = watchSlotsUsed(breakpoints);
  return (
    <div data-testid="breakpoints-section">
      <p
        className={`debug-panel__slots${slots >= MAX_WATCH_SLOTS ? " is-full" : ""}`}
        data-testid="watch-slots"
        aria-live="polite"
      >
        {watchSlotsText(breakpoints)}
      </p>
      <fieldset className="debug-breakon">
        <legend>Break on</legend>
        <label title="Pause after every @events firing of any instance">
          <input
            type="checkbox"
            checked={events}
            data-testid="break-on-events"
            onChange={(event) => setEventBreak(event.target.checked)}
          />
          Events
        </label>
        {EXCEPTION_CODES.map((code) => (
          <label key={code} title={EXCEPTION_TEXT[code].hint}>
            <input
              type="checkbox"
              checked={codes.includes(code)}
              data-testid={`break-on-${code}`}
              onChange={(event) => setExceptionBreak(code, event.target.checked)}
            />
            {EXCEPTION_TEXT[code].label}
          </label>
        ))}
      </fieldset>
      {breakpoints.length === 0 ? (
        <p className="debug-panel__hint" data-testid="breakpoints-empty">
          No breakpoints. Click the gutter of a source line, or use &quot;Break when…&quot; on a signal, to
          add one.
        </p>
      ) : (
        <ul className="debug-bp-list" aria-label="Breakpoints">
          {breakpoints.map((entry) => (
            <Row key={entry.id} entry={entry} />
          ))}
        </ul>
      )}
    </div>
  );
}
