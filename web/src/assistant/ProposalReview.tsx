/**
 * What the assistant changed so far, against the saved project. Nothing is written until Apply.
 * An invalid draft cannot be applied; one that has not passed a check can, with a warning.
 */

import type { AssistantFileChange, AssistantProposal } from "../contracts/assistant";
import { canApply } from "./assistantStore";

const CHANGE_LABEL = { added: "new", changed: "changed", removed: "removed" } as const;

function FileRows({ file }: { file: AssistantFileChange }) {
  return (
    <details className="assistant-proposal__file">
      <summary>
        <span className={`assistant-proposal__change assistant-proposal__change--${file.change}`}>
          {CHANGE_LABEL[file.change]}
        </span>
        {file.kind} {file.name}
      </summary>
      {file.rows.length === 0 ? null : (
        <ul>
          {file.rows.map((row, index) => (
            <li key={index}>
              <span className={`assistant-proposal__op assistant-proposal__op--${row.op}`}>{row.op}</span> {row.what}
              {row.before === undefined && row.after === undefined ? null : (
                <span className="assistant-proposal__values">
                  {row.before ?? ""}
                  {row.before != null && row.after != null ? " → " : ""}
                  {row.after ?? ""}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </details>
  );
}

export interface ProposalReviewProps {
  proposal: AssistantProposal;
  running: boolean;
  applying: boolean;
  autoApply: boolean;
  onApply: () => void;
  onDiscard: () => void;
  onAutoApply: (on: boolean) => void;
}

export function ProposalReview({ proposal, running, applying, autoApply, onApply, onDiscard, onAutoApply }: ProposalReviewProps) {
  return (
    <section className="assistant-proposal" aria-label="Proposed changes" data-testid="assistant-proposal">
      <h3>Proposed changes</h3>
      {proposal.files.map((file) => (
        <FileRows key={`${file.kind}:${file.name}`} file={file} />
      ))}
      {proposal.issues.length === 0 ? null : (
        <ul className="assistant-proposal__issues">
          {proposal.issues.map((issue, index) => (
            <li key={index} data-severity={issue.severity}>
              {issue.file.replace(/^[a-z]+:/, "")}: {issue.code === null || issue.code === undefined ? "" : `${issue.code} `}
              {issue.message}
            </li>
          ))}
        </ul>
      )}
      {proposal.valid && !proposal.checked ? (
        <p className="assistant-proposal__note">Not checked since the last edit.</p>
      ) : null}
      <div className="assistant-proposal__actions">
        <button
          type="button"
          className="assistant-button assistant-button--primary"
          data-testid="assistant-apply"
          disabled={!canApply(proposal) || running || applying}
          onClick={onApply}
        >
          Apply
        </button>
        <button
          type="button"
          className="assistant-button"
          data-testid="assistant-discard"
          disabled={running || applying}
          onClick={onDiscard}
        >
          Discard
        </button>
        <label className="assistant-proposal__auto" title="Apply when a run ends with a checked draft">
          <input
            type="checkbox"
            data-testid="assistant-auto-apply"
            checked={autoApply}
            onChange={(event) => onAutoApply(event.target.checked)}
          />
          Apply automatically
        </label>
      </div>
    </section>
  );
}
