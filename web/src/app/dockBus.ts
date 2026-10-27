/**
 * Small app-level bus for dock navigation.
 *
 * The canvas and the signal browser are deep in the tree, while the active
 * dock tab lives in `App`. Plotting from the canvas used to leave the dock on
 * whatever tab was open, so the new series were invisible; the plot actions
 * now ask for the Plots tab through this event.
 */

export const SHOW_PLOTS_EVENT = "bgsim:show-plots";

/** Ask the app shell to select the Plots tab (safe outside a browser). */
export function requestPlotsTab(): void {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(SHOW_PLOTS_EVENT));
  }
}
