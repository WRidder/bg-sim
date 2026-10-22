import { EmptyState } from "../app/EmptyState";

/**
 * The Inspector of plan 7.2 and 7.4, mounted by `InspectorPanel`.
 *
 * This file is owned by W1.2. The placeholder renders the empty state; the real
 * inspector reads the selected node from the document store and edits it through
 * the store's commands so undo/redo keeps working.
 */
export function Inspector() {
  return (
    <EmptyState
      title="Nothing selected"
      hint="Select a block on the diagram to edit its name, parameters, ports and start values here."
    />
  );
}
