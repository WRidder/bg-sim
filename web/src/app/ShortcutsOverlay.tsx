import { useRef } from "react";

import { useHelpStore } from "./helpStore";
import { SHORTCUT_GROUPS } from "./shortcuts";
import { useDialogFocus } from "./useDialogFocus";

/** The `?` overlay: every keyboard shortcut, grouped by where it works. */
export function ShortcutsOverlay() {
  const open = useHelpStore((state) => state.shortcutsOpen);
  const setOpen = useHelpStore((state) => state.setShortcutsOpen);
  const dialog = useRef<HTMLDivElement>(null);
  const close = (): void => setOpen(false);
  useDialogFocus(open, dialog, close);

  if (!open) {
    return null;
  }
  return (
    <div
      className="dialog-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          close();
        }
      }}
    >
      <div
        className="help-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="shortcuts-title"
        data-testid="shortcuts-overlay"
        ref={dialog}
        tabIndex={-1}
      >
        <header className="open-dialog__header">
          <h2 className="open-dialog__title" id="shortcuts-title">
            Keyboard shortcuts
          </h2>
          <button
            type="button"
            className="icon-button"
            aria-label="Close the shortcuts"
            title="Close (Esc)"
            data-testid="shortcuts-close"
            onClick={close}
          >
            <span aria-hidden="true">✕</span>
          </button>
        </header>
        <div className="help-dialog__body help-dialog__body--columns">
          {SHORTCUT_GROUPS.map((group) => (
            <section key={group.title} aria-labelledby={`shortcut-group-${group.title}`}>
              <h3 className="open-dialog__heading" id={`shortcut-group-${group.title}`}>
                {group.title}
              </h3>
              <dl className="shortcut-list">
                {group.entries.map((entry) => (
                  <div className="shortcut-list__row" key={entry.description}>
                    <dt>
                      {entry.keys.map((combo, position) => (
                        <span key={combo.join("+")}>
                          {position > 0 ? <span className="shortcut-list__or"> or </span> : null}
                          {combo.map((cap, capPosition) => (
                            <span key={cap}>
                              {capPosition > 0 ? "+" : null}
                              <kbd>{cap}</kbd>
                            </span>
                          ))}
                        </span>
                      ))}
                    </dt>
                    <dd>{entry.description}</dd>
                  </div>
                ))}
              </dl>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
