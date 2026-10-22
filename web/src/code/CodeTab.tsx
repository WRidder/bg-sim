import { EmptyState } from "../app/EmptyState";

/**
 * The Code tab of plan 7.2 and 7.7, mounted by `CenterTabs`.
 *
 * This file is owned by W2.1. The placeholder renders the empty state; the real
 * editor is CodeMirror 6 with the Julia legacy mode, the scope-macro
 * highlighter, `block.check` linting and autocomplete, and it listens for the
 * `bgsim:open-source` event that the inspector and the diagnostics panel emit.
 */
export function CodeTab() {
  return (
    <EmptyState
      title="No source open"
      hint="Select a block and choose “Open source” to read and edit its code here."
    />
  );
}
