/**
 * The user manual: a full-screen modal with the page list on the left and the rendered page
 * on the right. The pages are Markdown files in `pages/` rendered by the Docs tab's
 * `MarkdownView`, so math, code and tables look the same. `page:<id>` links open another
 * manual page inside the dialog; https links open in a new tab.
 *
 * Loaded lazily from the top bar, so the Markdown stack stays out of the main chunk.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useHelpStore } from "../app/helpStore";
import { useDialogFocus } from "../app/useDialogFocus";
import type { LinkContext } from "../docs/docsLinks";
import { MarkdownView, type LinkActions } from "../docs/MarkdownView";
import "../docs/docs.css";
import { filterPages, loadLastPage, MANUAL_PAGE_IDS, MANUAL_PAGES, saveLastPage } from "./manualPages";
import "./manual.css";

const LINKS: LinkContext = { pageIds: MANUAL_PAGE_IDS, model: null, signalIds: null };

export default function UserManualDialog() {
  const setManualOpen = useHelpStore((state) => state.setManualOpen);
  const setShortcutsOpen = useHelpStore((state) => state.setShortcutsOpen);
  const dialog = useRef<HTMLDivElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const [pageId, setPageId] = useState<string>(() => loadLastPage() ?? MANUAL_PAGES[0]?.id ?? "");
  const [query, setQuery] = useState("");
  // Set when a link inside the page moved to another page: the new page then takes the focus.
  const focusContent = useRef(false);

  // Stable, or the focus hook would re-run (and refocus the dialog) on every keystroke.
  const close = useCallback(() => setManualOpen(false), [setManualOpen]);
  useDialogFocus(true, dialog, close);

  const open = useCallback((id: string) => {
    setPageId(id);
    saveLastPage(id);
  }, []);

  const actions = useMemo<LinkActions>(
    () => ({
      openPage: (id) => {
        focusContent.current = true;
        open(id);
      },
      showBlock: () => undefined,
      plotSignal: () => undefined,
      notify: () => undefined,
    }),
    [open],
  );

  useEffect(() => {
    const area = content.current;
    if (area === null) {
      return;
    }
    area.scrollTop = 0;
    if (focusContent.current) {
      focusContent.current = false;
      area.focus();
    }
  }, [pageId]);

  const page = MANUAL_PAGES.find((entry) => entry.id === pageId) ?? MANUAL_PAGES[0];
  const visible = filterPages(MANUAL_PAGES, query);

  return (
    <div
      className="dialog-backdrop manual-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          close();
        }
      }}
    >
      <div
        className="manual-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="manual-title"
        data-testid="user-manual"
        ref={dialog}
        tabIndex={-1}
      >
        <header className="open-dialog__header">
          <h2 className="open-dialog__title" id="manual-title">
            User manual
          </h2>
          <button
            type="button"
            className="button"
            data-testid="manual-shortcuts"
            title="Show every keyboard shortcut (?)"
            onClick={() => setShortcutsOpen(true)}
          >
            Keyboard shortcuts
          </button>
          <button
            type="button"
            className="icon-button"
            aria-label="Close the user manual"
            title="Close (Esc)"
            data-testid="manual-close"
            onClick={close}
          >
            <span aria-hidden="true">✕</span>
          </button>
        </header>
        <div className="manual-dialog__body">
          <nav className="manual-nav" aria-label="Manual pages">
            <input
              type="search"
              className="open-dialog__input manual-nav__search"
              placeholder="Search the manual"
              aria-label="Search the manual"
              data-testid="manual-search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            {visible.length === 0 ? (
              <p className="manual-nav__empty" data-testid="manual-no-match">
                No page mentions “{query.trim()}”.
              </p>
            ) : (
              <ol className="manual-nav__list">
                {visible.map((entry) => (
                  <li key={entry.id}>
                    <button
                      type="button"
                      className={`manual-nav__item${entry.id === page?.id ? " is-current" : ""}`}
                      aria-current={entry.id === page?.id ? "page" : undefined}
                      data-testid={`manual-nav-${entry.id}`}
                      onClick={() => open(entry.id)}
                    >
                      {entry.title}
                    </button>
                  </li>
                ))}
              </ol>
            )}
          </nav>
          {page === undefined ? null : (
            <div
              className="docs-preview manual-page"
              role="region"
              aria-label={page.title}
              tabIndex={0}
              ref={content}
              data-testid="manual-page"
              data-page={page.id}
            >
              <MarkdownView text={page.text} project="" model="" links={LINKS} actions={actions} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
