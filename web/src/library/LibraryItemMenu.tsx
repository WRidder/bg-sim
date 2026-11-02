/**
 * The right-click menu of a library entry (list row or grid tile): **Show source** opens
 * the block in the Code tab, **Info** opens the block help. Junctions have no source, so
 * they get Info only. Keyboard: the first item takes focus, arrows move, Esc closes.
 */

import { useEffect, useRef } from "react";

import { useHelpStore } from "../app/helpStore";
import { requestSource } from "../code/codeSession";

export interface LibraryMenuState {
  x: number;
  y: number;
  /** The block ref (`stdlib:…`, `project:…`) or the junction key the help knows. */
  ref: string;
  label: string;
  /** False for a junction: there is no source to show. */
  hasSource: boolean;
}

export function LibraryItemMenu({ menu, onClose }: { menu: LibraryMenuState; onClose: () => void }) {
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

  const run = (action: () => void) => {
    onClose();
    action();
  };

  return (
    <div
      ref={root}
      className="editor-menu library-menu"
      role="menu"
      aria-label={`Actions for ${menu.label}`}
      data-testid="library-menu"
      style={{ position: "fixed", left: menu.x, top: menu.y, zIndex: 70 }}
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
      {menu.hasSource ? (
        <button
          type="button"
          role="menuitem"
          data-testid="library-menu-source"
          title="Open the block source in the Code tab"
          onClick={() =>
            run(() =>
              requestSource(
                { kind: menu.ref.startsWith("stdlib:") ? "stdlib" : "project", ref: menu.ref, line: 1, col: 1 },
                { reveal: true },
              ),
            )
          }
        >
          Show source
        </button>
      ) : null}
      <button
        type="button"
        role="menuitem"
        data-testid="library-menu-info"
        title="Open the block help"
        onClick={() => run(() => useHelpStore.getState().openBlockHelp(menu.ref))}
      >
        Info
      </button>
    </div>
  );
}
