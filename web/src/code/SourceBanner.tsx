/**
 * The banner above the editor (plan 7.7): standard-library source is
 * read-only and offers "Copy to project library"; a project-library source is
 * editable and says where it is saved.
 */

import type { LibrarySourceKind } from "./sources";

export type CopyState = "idle" | "working" | "done" | "error";

export interface SourceBannerProps {
  sourceKind: LibrarySourceKind;
  name: string;
  path: string | null;
  project: string | null;
  copyState: CopyState;
  copyMessage: string | null;
  onCopy: () => void;
}

export function SourceBanner({
  sourceKind,
  name,
  path,
  project,
  copyState,
  copyMessage,
  onCopy,
}: SourceBannerProps) {
  if (sourceKind === "project") {
    return (
      <div className="code-banner code-banner--project" data-testid="code-project-banner">
        <span className="code-banner__title">Project library source</span>
        <span className="code-banner__text">
          {name}
          {path === null ? null : <code> · {path}</code>}
        </span>
      </div>
    );
  }

  const disabled = project === null || copyState === "working" || copyState === "done";
  return (
    <div className="code-banner code-banner--readonly" data-testid="code-readonly-banner">
      <span className="code-banner__title">Read-only standard library source</span>
      <span className="code-banner__text">
        {project === null
          ? "Open a project to copy this block."
          : "Copy the block into the project library to change its equations."}
      </span>
      <button
        type="button"
        className="button code-banner__button"
        data-testid="code-copy-to-library"
        onClick={onCopy}
        disabled={disabled}
        title={
          project === null
            ? "Open a project first"
            : copyState === "done"
              ? "This block has been copied"
              : "Fork the block into library/<Name>.jl"
        }
      >
        {copyState === "working" ? "Copying…" : copyState === "done" ? "Copied" : "Copy to project library"}
      </button>
      {copyMessage !== null ? (
        <span
          className={`code-banner__message code-banner__message--${copyState}`}
          role="status"
          data-testid="code-copy-message"
        >
          {copyMessage}
        </span>
      ) : null}
    </div>
  );
}
