/**
 * The detached 3D View (W5.5): the same popup lifecycle as the Plots (`createDetachStore`), with its
 * own window. Run, cursor, bindings and playback time live in shared stores, so the popup and the
 * main window stay in step; only one of the two mounts the viewer (and its engine) at a time.
 */

import { createDetachStore } from "../plot/detachStore";

export const useViewerDetachStore = createDetachStore({
  windowName: "bgsim-3d-view",
  title: "bg-sim 3D view",
  label: "3D view",
});
