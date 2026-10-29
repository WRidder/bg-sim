import { useEffect } from "react";

import { activeModel } from "../editor/subsystemPath";
import { useDocumentStore } from "../state/documentStore";
import { nodeRef } from "../state/modelFactory";
import { useHelpStore } from "./helpStore";
import { isTypingTarget } from "./shortcuts";

/** The ref of the single selected block (or `junction:0` / `junction:1`), or null. */
export function selectedBlockRef(): string | null {
  const state = useDocumentStore.getState();
  if (state.doc === null || state.selection.nodes.length !== 1) {
    return null;
  }
  const model = activeModel(state.doc, state.activePath);
  const node = model?.diagram.nodes.find((entry) => entry.id === state.selection.nodes[0]);
  if (node === undefined) {
    return null;
  }
  return "junction" in node.block ? `junction:${node.block.junction}` : nodeRef(node);
}

/**
 * App-wide single-key shortcuts: `?` toggles the shortcuts overlay, `/` focuses
 * the library search, F1 opens the help of the selected block. Ctrl+O lives in
 * the TopBar and Ctrl+Enter in the RunBar, next to the controls they drive.
 */
export function useAppShortcuts(): void {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey) {
        return;
      }
      const help = useHelpStore.getState();
      if (event.key === "F1") {
        event.preventDefault();
        const ref = selectedBlockRef();
        if (ref !== null) {
          help.openBlockHelp(ref);
        } else {
          help.setShortcutsOpen(true);
        }
        return;
      }
      if (isTypingTarget(event.target)) {
        return;
      }
      if (event.key === "?") {
        event.preventDefault();
        help.setShortcutsOpen(!help.shortcutsOpen);
        return;
      }
      if (event.key === "/") {
        if (document.querySelector('[role="dialog"][aria-modal="true"]') !== null) {
          return;
        }
        const search = document.querySelector<HTMLInputElement>('[data-testid="library-search"]');
        if (search !== null) {
          event.preventDefault();
          search.focus();
          search.select();
        }
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);
}
