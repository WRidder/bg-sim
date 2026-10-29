/**
 * Detachable plot windows (W2.5).
 *
 * `window.open` is called from a user gesture and the same React tree renders
 * into the popup through a portal, so the detached panel shares the run store,
 * the cursor and the live tail with the dock. Closing the window (or "Dock")
 * returns the panel to the dock. Styles are cloned at open time; the popup
 * starts as `about:blank`, so the portal needs a root element created here.
 *
 * The factory is instantiated once for the manual Plots panel and once for the
 * automatic selection panel; each keeps its own window and popup lifecycle.
 */

import { create } from "zustand";

export interface DetachStoreState {
  detached: boolean;
  popup: Window | null;
  error: string | null;
  /** Open/focus the panel window; false when the browser blocked it. */
  detach: () => boolean;
  /** Close the window and put the panel back in the dock. */
  attach: () => void;
  clearError: () => void;
}

export interface DetachOptions {
  /** `window.open` name; reuse focuses the existing window. */
  windowName: string;
  /** Popup document title. */
  title: string;
  /** Human label used in the blocked-popup error. */
  label: string;
}

export function createDetachStore(options: DetachOptions) {
  let popupWindow: Window | null = null;
  let themeWatch: MutationObserver | null = null;

  const store = create<DetachStoreState>((set) => {
    const forget = (windowRef: Window): void => {
      if (popupWindow !== windowRef) {
        return;
      }
      popupWindow = null;
      themeWatch?.disconnect();
      themeWatch = null;
      if (store.getState().popup === windowRef) {
        store.setState({ detached: false, popup: null });
      }
    };

    return {
      detached: false,
      popup: null,
      error: null,

      detach: () => {
        if (popupWindow !== null && !popupWindow.closed) {
          popupWindow.focus();
          return true;
        }
        const windowRef = window.open(
          "",
          options.windowName,
          "popup=yes,width=1100,height=720",
        );
        if (windowRef === null) {
          set({
            error: `The browser blocked the ${options.label} window. Allow pop-ups for this site and try again.`,
          });
          return false;
        }

        popupWindow = windowRef;
        const doc = windowRef.document;
        doc.title = options.title;
        doc.documentElement.lang = document.documentElement.lang;
        doc.documentElement.dataset.theme =
          document.documentElement.dataset.theme ?? "";
        // a theme switch in the main window reaches the popup (the 3D view re-reads its token colours)
        themeWatch?.disconnect();
        themeWatch = new MutationObserver(() => {
          doc.documentElement.dataset.theme = document.documentElement.dataset.theme ?? "";
        });
        themeWatch.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
        // `about:blank` has no base URL, so relative asset URLs (fonts, images)
        // must resolve against the main document.
        const base = doc.createElement("base");
        base.href = document.baseURI;
        doc.head.appendChild(base);
        // Vite injects <style> tags in dev and links the bundle CSS in
        // production; both are cloned so the popup uses the same theme.
        for (const node of document.querySelectorAll<HTMLElement>(
          'link[rel="stylesheet"], style',
        )) {
          doc.head.appendChild(node.cloneNode(true));
        }
        doc.body.className = "bgsim-detached-body";
        doc.body.innerHTML = '<div id="bgsim-detached-root"></div>';
        windowRef.addEventListener("pagehide", () => forget(windowRef), {
          once: true,
        });
        windowRef.addEventListener("beforeunload", () => forget(windowRef), {
          once: true,
        });
        set({ detached: true, popup: windowRef, error: null });
        windowRef.focus();
        return true;
      },

      attach: () => {
        const windowRef = popupWindow;
        popupWindow = null;
        themeWatch?.disconnect();
        themeWatch = null;
        set({ detached: false, popup: null });
        if (windowRef !== null && !windowRef.closed) {
          windowRef.close();
        }
      },

      clearError: () => set({ error: null }),
    };
  });

  return store;
}

/** The manual Plots tab. */
export const useDetachStore = createDetachStore({
  windowName: "bgsim-plots",
  title: "bg-sim plots",
  label: "plot",
});

/** The automatic selection plot tab. */
export const useAutoDetachStore = createDetachStore({
  windowName: "bgsim-auto-plot",
  title: "bg-sim auto plot",
  label: "automatic plot",
});
