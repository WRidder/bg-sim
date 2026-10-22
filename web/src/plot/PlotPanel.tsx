import { EmptyState } from "../app/EmptyState";

/**
 * The plot area of plan 7.5, mounted in the bottom dock's Plots tab.
 *
 * This file is owned by W1.4. The placeholder renders the empty state; the real
 * panel stacks uPlot instances, links their cursors and re-requests `/data` on a
 * zoom with the new `t0`/`t1`/`px`.
 */
export function PlotPanel() {
  return (
    <EmptyState
      title="No run data"
      hint="Run a model to plot its signals here. Every signal is recorded by default."
    />
  );
}
