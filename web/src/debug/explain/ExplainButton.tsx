/** A small "Explain" button for a signal id, mounted next to read-only signal ids (inspector, plan 7.9). */

import { openExplain } from "./explainStore";

export function ExplainButton({ signalId, testId }: { signalId: string; testId?: string }) {
  return (
    <button
      type="button"
      className="explain-button"
      aria-label={`Explain signal ${signalId}`}
      title={`Explain ${signalId}: kind, unit, defining expression and source equations`}
      data-testid={testId ?? "explain-signal-button"}
      data-signal-id={signalId}
      onClick={() => openExplain(signalId)}
    >
      Explain
    </button>
  );
}
