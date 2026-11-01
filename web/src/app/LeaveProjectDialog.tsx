import { useCallback, useRef } from "react";

import {
  leaveWithoutSaving,
  saveAndLeave,
  useLeaveProjectStore,
  type LeaveDestination,
} from "./leaveProject";
import { useDialogFocus } from "./useDialogFocus";

const TITLES: Record<LeaveDestination, string> = {
  library: "Back to the library?",
  project: "Back to the project's models?",
  model: "Open another model?",
};

/** The prompt before leaving the open model with unsaved work (leaveProject.ts). */
export function LeaveProjectDialog() {
  const pending = useLeaveProjectStore((state) => state.pending);
  const destination = useLeaveProjectStore((state) => state.destination);
  const error = useLeaveProjectStore((state) => state.error);
  const busy = useLeaveProjectStore((state) => state.busy);
  const close = useLeaveProjectStore((state) => state.close);
  const dialog = useRef<HTMLDivElement>(null);
  const cancel = useCallback(() => {
    if (!useLeaveProjectStore.getState().busy) {
      close();
    }
  }, [close]);
  useDialogFocus(pending !== null, dialog, cancel);
  if (pending === null) {
    return null;
  }
  return (
    <div className="dialog-backdrop" data-testid="leave-project-backdrop">
      <div
        className="leave-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="leave-project-title"
        aria-describedby="leave-project-text"
        data-testid="leave-project-dialog"
        ref={dialog}
        tabIndex={-1}
      >
        <h2 id="leave-project-title" className="leave-dialog__title">
          {TITLES[destination]}
        </h2>
        <div id="leave-project-text">
          <p className="leave-dialog__text">Some changes are not saved yet:</p>
          <ul className="leave-dialog__list">
            {pending.map((label) => (
              <li key={label}>{label}</li>
            ))}
          </ul>
        </div>
        {error !== null ? (
          <p className="leave-dialog__error" role="alert" data-testid="leave-project-error">
            {error}
          </p>
        ) : null}
        <div className="leave-dialog__actions">
          <button
            type="button"
            className="button"
            data-testid="leave-project-cancel"
            disabled={busy}
            onClick={cancel}
          >
            Cancel
          </button>
          <button
            type="button"
            className="button"
            data-testid="leave-project-discard"
            disabled={busy}
            onClick={leaveWithoutSaving}
          >
            Leave without saving
          </button>
          <button
            type="button"
            className="button button--primary"
            data-testid="leave-project-save"
            disabled={busy}
            onClick={() => void saveAndLeave()}
          >
            {busy ? "Saving…" : "Save and leave"}
          </button>
        </div>
      </div>
    </div>
  );
}
