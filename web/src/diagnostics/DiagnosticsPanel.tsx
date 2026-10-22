import { EmptyState } from "../app/EmptyState";

/**
 * The diagnostics panel of plan 7.2/7.3/7.4, mounted in the bottom dock.
 *
 * This file is owned by W1.3. The placeholder renders the empty state; the real
 * panel lists the `model.check` diagnostics, filters them, groups them by path,
 * navigates on click and feeds the badge counts to `BottomDock`.
 */
export function DiagnosticsPanel() {
  return (
    <EmptyState
      title="No diagnostics"
      hint="Checks report errors and warnings here. Click one to jump to the element or the line that caused it."
    />
  );
}
