import { EmptyState } from "../app/EmptyState";

/**
 * The signal browser of plan 7.5, mounted in the bottom dock's Signals tab.
 *
 * This file is owned by W1.4. The placeholder renders the empty state; the real
 * browser is a tree by instance path with search, kind icons and units, and
 * double-click adds a signal to the active plot.
 */
export function SignalBrowser() {
  return (
    <EmptyState
      title="No signals"
      hint="After a run, browse every recorded signal here and add it to a plot panel."
    />
  );
}
