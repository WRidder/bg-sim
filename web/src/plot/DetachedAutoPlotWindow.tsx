/**
 * Renders the automatic selection plot into its detached browser window.
 *
 * Mounted once at the app root so switching dock tabs or detaching the manual
 * Plots panel never unmounts the automatic charts.
 */

import { createPortal } from "react-dom";

import { AutoPlotPanel } from "./AutoPlotPanel";
import { useAutoDetachStore } from "./detachStore";

export function DetachedAutoPlotWindow() {
  const detached = useAutoDetachStore((state) => state.detached);
  const popup = useAutoDetachStore((state) => state.popup);
  if (!detached || popup === null || popup.closed) {
    return null;
  }
  const root = popup.document.getElementById("bgsim-detached-root");
  if (root === null) {
    return null;
  }
  return createPortal(<AutoPlotPanel detached />, root);
}
