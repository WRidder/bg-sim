/**
 * Renders the Plots panel into the detached browser window.
 *
 * Mounted once at the app root so switching dock tabs (or hiding the Plots
 * tab) never unmounts the charts that live in the popup.
 */

import { createPortal } from "react-dom";

import { useDetachStore } from "./detachStore";
import { PlotPanel } from "./PlotPanel";

export function DetachedPlotWindow() {
  const detached = useDetachStore((state) => state.detached);
  const popup = useDetachStore((state) => state.popup);
  if (!detached || popup === null || popup.closed) {
    return null;
  }
  const root = popup.document.getElementById("bgsim-detached-root");
  if (root === null) {
    return null;
  }
  return createPortal(<PlotPanel detached />, root);
}
