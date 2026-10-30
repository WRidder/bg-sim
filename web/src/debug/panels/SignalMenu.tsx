/**
 * A small context menu for one signal (plan 7.9): "Break when..." and "Explain
 * signal". The signal browser opens it on right-click (or the context-menu key);
 * the canvas menus embed the same two items through `SignalMenuItems`.
 */

import { useEffect, useRef } from "react";

import { openExplain } from "../explain/explainStore";
import { openBreakWhen } from "./breakWhenStore";

export interface SignalMenuItemsProps {
  /** The signal that is preselected / explained. */
  signalId: string;
  /** The signals "Break when..." offers. */
  candidates?: readonly string[];
  /** Called after an item ran (close the surrounding menu). */
  onDone: () => void;
  /** Why the items are disabled (a tooltip), or null when they work. */
  disabledReason?: string | null;
}

export function SignalMenuItems({ signalId, candidates, onDone, disabledReason = null }: SignalMenuItemsProps) {
  return (
    <>
      <button
        type="button"
        role="menuitem"
        data-testid="break-when"
        data-signal-id={signalId}
        disabled={disabledReason !== null}
        title={disabledReason ?? `Pause the debug run when ${signalId} crosses a value`}
        onClick={() => {
          openBreakWhen(signalId, candidates);
          onDone();
        }}
      >
        Break when…
      </button>
      <button
        type="button"
        role="menuitem"
        data-testid="explain-signal"
        data-signal-id={signalId}
        disabled={disabledReason !== null}
        title={disabledReason ?? `Explain ${signalId}: kind, unit, expression and source equations`}
        onClick={() => {
          openExplain(signalId);
          onDone();
        }}
      >
        Explain signal
      </button>
    </>
  );
}

export interface SignalContextMenuProps {
  x: number;
  y: number;
  signalId: string;
  onClose: () => void;
}

/** A fixed-position menu at the pointer; Escape and a click elsewhere close it. */
export function SignalContextMenu({ x, y, signalId, onClose }: SignalContextMenuProps) {
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    root.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
    const onPointer = (event: PointerEvent): void => {
      if (!(event.target instanceof Node) || !root.current?.contains(event.target)) {
        onClose();
      }
    };
    window.addEventListener("pointerdown", onPointer, true);
    return () => window.removeEventListener("pointerdown", onPointer, true);
  }, [onClose]);

  return (
    <div
      ref={root}
      className="editor-menu signal-menu"
      role="menu"
      aria-label={`Actions for ${signalId}`}
      data-testid="signal-menu"
      style={{ position: "fixed", left: x, top: y, zIndex: 70 }}
      onKeyDown={(event) => {
        const items = [...(root.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [])];
        const index = items.findIndex((item) => item === document.activeElement);
        if (event.key === "Escape") {
          event.preventDefault();
          event.stopPropagation();
          onClose();
        } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
          event.preventDefault();
          const step = event.key === "ArrowDown" ? 1 : -1;
          items[(index + step + items.length) % items.length]?.focus();
        }
      }}
    >
      <SignalMenuItems signalId={signalId} onDone={onClose} />
    </div>
  );
}
