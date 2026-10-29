import { createPortal } from "react-dom";

import DockViewer, { type DockViewerProps } from "./DockViewer";
import { useViewerDetachStore } from "./detachStore";

/**
 * Renders the 3D View into the detached browser window. Mounted once at the app root; the dock
 * shows a placeholder while this is mounted, so there is never more than one engine.
 */
export function DetachedViewerWindow({ createEngine }: { createEngine?: DockViewerProps["createEngine"] } = {}) {
  const detached = useViewerDetachStore((state) => state.detached);
  const popup = useViewerDetachStore((state) => state.popup);
  if (!detached || popup === null || popup.closed) {
    return null;
  }
  const root = popup.document.getElementById("bgsim-detached-root");
  if (root === null) {
    return null;
  }
  return createPortal(<DockViewer active hostWindow={popup} createEngine={createEngine} />, root);
}
