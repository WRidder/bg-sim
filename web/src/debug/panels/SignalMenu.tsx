/**
 * A small context menu for one signal (plan 7.9): "Plot", "Break when..." and
 * "Explain signal". The signal browser and the inspector's port rows open it on
 * right-click (or the context-menu key); the canvas menus embed the two debug
 * items through `SignalMenuItems`.
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

/** A "Plot …" item at the top of the menu. */
export interface SignalPlotItem {
  signalId: string;
  label: string;
  title: string;
  /** Why it is disabled (a tooltip), or null when it works. */
  disabledReason?: string | null;
  run: () => void;
}

export interface SignalContextMenuProps {
  x: number;
  y: number;
  signalId: string;
  /** The signals "Break when..." offers (default: just `signalId`). */
  candidates?: readonly string[];
  /** Plot items listed first, like the + button of the signal browser. */
  plotItems?: readonly SignalPlotItem[];
  onClose: () => void;
}

/** A fixed-position menu at the pointer; Escape and a click elsewhere close it. */
export function SignalContextMenu({
  x,
  y,
  signalId,
  candidates,
  plotItems = [],
  onClose,
}: SignalContextMenuProps) {
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
      {plotItems.map((item) => (
        <button
          type="button"
          role="menuitem"
          key={item.signalId}
          data-testid="signal-menu-plot"
          data-signal-id={item.signalId}
          disabled={(item.disabledReason ?? null) !== null}
          title={item.disabledReason ?? item.title}
          onClick={() => {
            item.run();
            onClose();
          }}
        >
          {item.label}
        </button>
      ))}
      <SignalMenuItems signalId={signalId} candidates={candidates} onDone={onClose} />
    </div>
  );
}
