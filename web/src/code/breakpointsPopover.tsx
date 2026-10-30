/**
 * The small popover of a gutter breakpoint (right-click, plan 7.9): the
 * condition, the hit count, enable/disable and remove. It edits the breakpoint
 * store directly, so a change during a debug run reaches the server through the
 * debug store's breakpoint sync.
 */

import { useEffect, useRef, useState, type KeyboardEvent } from "react";

import { useBreakpointStore } from "../debug/breakpointStore";

export interface BreakpointPopoverProps {
  id: string;
  /** Viewport position of the right-click. */
  point: { x: number; y: number };
  onClose: () => void;
}

/** Parse the hit-count field: blank clears it, otherwise a whole number of at least 1. */
export function parseHitCount(text: string): { ok: true; value: number | null } | { ok: false } {
  const trimmed = text.trim();
  if (trimmed.length === 0) {
    return { ok: true, value: null };
  }
  if (!/^\d+$/.test(trimmed) || Number(trimmed) < 1) {
    return { ok: false };
  }
  return { ok: true, value: Number(trimmed) };
}

export function BreakpointPopover({ id, point, onClose }: BreakpointPopoverProps) {
  const entry = useBreakpointStore((state) => state.breakpoints.find((item) => item.id === id));
  const line = entry?.kind === "line" ? entry : null;
  const [condition, setCondition] = useState(line?.condition ?? "");
  const [hitCount, setHitCount] = useState(
    line?.hitCount === null || line?.hitCount === undefined ? "" : String(line.hitCount),
  );
  const [invalid, setInvalid] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    root.current?.querySelector<HTMLInputElement>("input")?.focus();
    const onPointerDown = (event: MouseEvent): void => {
      if (root.current !== null && !root.current.contains(event.target as Node)) {
        onClose();
      }
    };
    window.addEventListener("mousedown", onPointerDown);
    return () => window.removeEventListener("mousedown", onPointerDown);
  }, [onClose]);

  if (line === null) {
    return null;
  }

  const apply = (): void => {
    const parsed = parseHitCount(hitCount);
    if (!parsed.ok) {
      setInvalid(true);
      return;
    }
    const store = useBreakpointStore.getState();
    store.setCondition(id, condition);
    store.setHitCount(id, parsed.value);
    onClose();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLElement>): void => {
    if (event.key === "Enter") {
      event.preventDefault();
      apply();
    } else if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      onClose();
    }
  };

  return (
    <div
      className="bp-popover"
      role="dialog"
      aria-label={`Breakpoint at line ${line.line.line}`}
      data-testid="bp-popover"
      ref={root}
      style={{ left: Math.max(8, point.x), top: Math.max(8, point.y) }}
      onKeyDown={onKeyDown}
    >
      <div className="bp-popover__title">Breakpoint · line {line.line.line}</div>
      <label className="bp-popover__field">
        <span>Condition</span>
        <input
          type="text"
          value={condition}
          placeholder="e.g. k == 5 (empty: always)"
          aria-label="Breakpoint condition"
          data-testid="bp-condition"
          spellCheck={false}
          onChange={(event) => setCondition(event.target.value)}
        />
      </label>
      <label className="bp-popover__field">
        <span>Hit count</span>
        <input
          type="text"
          inputMode="numeric"
          value={hitCount}
          placeholder="pause on the n-th hit (empty: every hit)"
          aria-label="Breakpoint hit count"
          aria-invalid={invalid}
          data-testid="bp-hit-count"
          onChange={(event) => {
            setHitCount(event.target.value);
            setInvalid(false);
          }}
        />
      </label>
      {invalid ? (
        <p className="bp-popover__error" role="alert">
          The hit count is a whole number of 1 or more, or empty.
        </p>
      ) : null}
      <div className="bp-popover__actions">
        <label className="bp-popover__check">
          <input
            type="checkbox"
            checked={line.enabled}
            data-testid="bp-enabled"
            onChange={(event) => useBreakpointStore.getState().setEnabled(id, event.target.checked)}
          />
          Enabled
        </label>
        <span className="bp-popover__spacer" />
        <button
          type="button"
          className="button"
          data-testid="bp-remove"
          onClick={() => {
            useBreakpointStore.getState().remove(id);
            onClose();
          }}
        >
          Remove
        </button>
        <button type="button" className="button button--primary" data-testid="bp-apply" onClick={apply}>
          Apply
        </button>
      </div>
    </div>
  );
}
