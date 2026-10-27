/**
 * The detached Plots window (W2.5).
 *
 * `window.open` is called from a user gesture and the same React tree renders
 * into the popup through a portal, so the detached plots share the run store,
 * the cursor and the live tail with the dock. Closing the window (or "Dock")
 * returns the plots to the dock. Styles are cloned at open time; the popup
 * starts as `about:blank`, so the portal needs a root element created here.
 */

import { create } from "zustand";

export interface DetachStoreState {
  detached: boolean;
  popup: Window | null;
  error: string | null;
  /** Open/focus the plot window; false when the browser blocked it. */
  detach: () => boolean;
  /** Close the window and put the plots back in the dock. */
  attach: () => void;
  clearError: () => void;
}

let popupWindow: Window | null = null;

function forget(window: Window): void {
  if (popupWindow !== window) {
    return;
  }
  popupWindow = null;
  if (useDetachStore.getState().popup === window) {
    useDetachStore.setState({ detached: false, popup: null });
  }
}

export const useDetachStore = create<DetachStoreState>((set) => ({
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
      "bgsim-plots",
      "popup=yes,width=1100,height=720",
    );
    if (windowRef === null) {
      set({
        error:
          "The browser blocked the plot window. Allow pop-ups for this site and try again.",
      });
      return false;
    }

    popupWindow = windowRef;
    const doc = windowRef.document;
    doc.title = "bg-sim plots";
    doc.documentElement.lang = document.documentElement.lang;
    doc.documentElement.dataset.theme =
      document.documentElement.dataset.theme ?? "";
    // `about:blank` has no base URL, so relative asset URLs (fonts, images)
    // must resolve against the main document.
    const base = doc.createElement("base");
    base.href = document.baseURI;
    doc.head.appendChild(base);
    // Vite injects <style> tags in dev and links the bundle CSS in production;
    // both are cloned so the popup uses the same theme and plot styles.
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
    set({ detached: false, popup: null });
    if (windowRef !== null && !windowRef.closed) {
      windowRef.close();
    }
  },

  clearError: () => set({ error: null }),
}));
