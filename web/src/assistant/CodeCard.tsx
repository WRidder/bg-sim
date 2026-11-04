/** A code cell the assistant ran: its source, what it printed, and the error if it failed. */

import type { AssistantCodeEvent } from "../contracts/assistant";

export function CodeCard({ cell }: { cell: AssistantCodeEvent }) {
  return (
    <section className="assistant-code" data-testid="code-card" data-ok={cell.ok}>
      <details open={!cell.ok}>
        <summary>
          <span className="assistant-code__title">{cell.title}</span>
          {cell.runId === null || cell.runId === undefined ? null : (
            <span className="assistant-code__run">run {cell.runId}</span>
          )}
        </summary>
        <pre>
          <code>{cell.code}</code>
        </pre>
      </details>
      {cell.output.length === 0 ? null : <pre className="assistant-code__output">{cell.output.join("\n")}</pre>}
      {cell.error === null || cell.error === undefined ? null : (
        <p className="assistant-code__error" role="alert">
          {cell.error}
        </p>
      )}
    </section>
  );
}
