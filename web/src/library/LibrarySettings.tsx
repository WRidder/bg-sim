/**
 * The quick settings of the library panel: a small cog at the top right of the panel title opens
 * a popover with a show/hide checkbox per category, "Show all", and "Expand all" / "Collapse
 * all". The choices persist through src/library/libraryPrefs.ts. The popover is non-modal: it
 * closes on Escape (focus returns to the cog), on a press outside it, and when focus leaves it.
 */

import { useCallback, useEffect, useLayoutEffect, useRef, useState, type FocusEvent } from "react";
import { createPortal } from "react-dom";

import { useCatalogStore } from "./catalogStore";
import { libraryCategories } from "./catalogIndex";
import { CogIcon } from "./icons";
import { useLibraryPrefs } from "./libraryPrefs";

const POPOVER_WIDTH = 256;
const MARGIN = 8;

interface Placement {
  top: number;
  left: number;
  maxHeight: number;
}

/**
 * Below the cog, opening to the right (over the canvas) so the library list stays in view while
 * categories are shown or hidden; clamped to the viewport.
 */
function placeBelow(button: HTMLElement): Placement {
  const rect = button.getBoundingClientRect();
  const top = rect.bottom + 4;
  const left = Math.max(MARGIN, Math.min(rect.left, window.innerWidth - POPOVER_WIDTH - MARGIN));
  return { top, left, maxHeight: Math.max(160, window.innerHeight - top - MARGIN) };
}

export function LibrarySettings() {
  const index = useCatalogStore((state) => state.index);
  const hidden = useLibraryPrefs((state) => state.hidden);
  const [open, setOpen] = useState(false);
  const [placement, setPlacement] = useState<Placement | null>(null);
  const button = useRef<HTMLButtonElement>(null);
  const popover = useRef<HTMLDivElement>(null);

  const categories = index === null ? [] : libraryCategories(index);
  const shown = categories.filter((name) => !hidden.has(name));

  const close = useCallback((refocus: boolean) => {
    setOpen(false);
    if (refocus) {
      button.current?.focus();
    }
  }, []);

  useLayoutEffect(() => {
    if (!open || button.current === null) {
      return;
    }
    const place = (): void => {
      if (button.current !== null) {
        setPlacement(placeBelow(button.current));
      }
    };
    place();
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
  }, [open]);

  useEffect(() => {
    if (!open) {
      return;
    }
    popover.current?.querySelector<HTMLElement>("input, button")?.focus();
    const onPointerDown = (event: PointerEvent): void => {
      const target = event.target as Node;
      if (popover.current?.contains(target) || button.current?.contains(target)) {
        return;
      }
      close(false);
    };
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        close(true);
      }
    };
    window.addEventListener("pointerdown", onPointerDown, true);
    window.addEventListener("keydown", onKeyDown, true);
    return () => {
      window.removeEventListener("pointerdown", onPointerDown, true);
      window.removeEventListener("keydown", onKeyDown, true);
    };
  }, [close, open]);

  const onBlur = (event: FocusEvent<HTMLDivElement>): void => {
    const next = event.relatedTarget;
    if (next instanceof Node && (popover.current?.contains(next) || button.current?.contains(next))) {
      return;
    }
    // Focus moved on by keyboard (Tab past the last control): the popover is done.
    if (next !== null) {
      close(false);
    }
  };

  const prefs = useLibraryPrefs.getState;

  return (
    <>
      <button
        ref={button}
        type="button"
        className={`icon-button library-settings__button${open ? " is-active" : ""}`}
        aria-label="Library settings"
        title="Library settings: show or hide categories, expand or collapse all"
        aria-haspopup="dialog"
        aria-expanded={open}
        data-testid="library-settings"
        disabled={index === null}
        onClick={() => setOpen((current) => !current)}
      >
        <CogIcon size={14} />
      </button>
      {open
        ? createPortal(
            <div
              ref={popover}
              className="library-settings"
              role="dialog"
              aria-label="Library settings"
              data-testid="library-settings-popover"
              style={
                placement === null
                  ? { visibility: "hidden" }
                  : { top: placement.top, left: placement.left, maxHeight: placement.maxHeight }
              }
              onBlur={onBlur}
            >
              <fieldset className="library-settings__categories">
                <legend className="library-settings__legend">Show categories</legend>
                {categories.map((name) => (
                  <label className="library-settings__option" key={name}>
                    <input
                      type="checkbox"
                      checked={!hidden.has(name)}
                      data-testid={`library-settings-show-${name}`}
                      onChange={(event) => prefs().setHidden(name, !event.target.checked)}
                    />
                    <span>{name}</span>
                  </label>
                ))}
              </fieldset>
              <div className="library-settings__actions">
                <button
                  type="button"
                  className="button"
                  data-testid="library-settings-show-all"
                  disabled={hidden.size === 0}
                  onClick={() => prefs().showAll()}
                >
                  Show all
                </button>
                <button
                  type="button"
                  className="button"
                  data-testid="library-settings-expand-all"
                  disabled={shown.length === 0}
                  onClick={() => prefs().expandAll(shown)}
                >
                  Expand all
                </button>
                <button
                  type="button"
                  className="button"
                  data-testid="library-settings-collapse-all"
                  disabled={shown.length === 0}
                  onClick={() => prefs().collapseAll(categories)}
                >
                  Collapse all
                </button>
              </div>
            </div>,
            document.body,
          )
        : null}
    </>
  );
}
