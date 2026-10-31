/**
 * The conflict dialog of a paste and the notice that follows it.
 *
 * One small dialog lists every conflict (a library block, global or data file that the
 * target already has with different content) with a choice per row. The defaults keep
 * the target's own definitions, so a paste never silently changes them.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { useDialogFocus } from "../app/useDialogFocus";
import { usePasteUiStore } from "./pasteUi";
import { defaultChoices, type Conflict, type ConflictChoice } from "./resolve";
import "./clipboard.css";

const KIND_LABEL: Record<Conflict["kind"], string> = {
  library: "Library block",
  global: "Global parameter",
  dataFile: "Data file",
};

function choiceLabel(conflict: Conflict, choice: ConflictChoice): string {
  if (choice === "existing") {
    return conflict.kind === "global"
      ? `Use this model's ${conflict.existing}`
      : `Use this project's ${conflict.existing}`;
  }
  if (choice === "rename") {
    return `Import as ${conflict.renameTo}`;
  }
  return "Convert the pasted blocks to inline";
}

export function PasteConflictDialog() {
  const request = usePasteUiStore((state) => state.dialog);
  const answer = usePasteUiStore((state) => state.answer);
  const dialog = useRef<HTMLDivElement>(null);
  const [choices, setChoices] = useState<Record<string, ConflictChoice>>({});
  const cancel = useCallback(() => answer(null), [answer]);
  useDialogFocus(request !== null, dialog, cancel);

  useEffect(() => {
    setChoices(request === null ? {} : defaultChoices(request.conflicts));
  }, [request]);

  if (request === null) {
    return null;
  }
  return (
    <div className="dialog-backdrop" data-testid="paste-conflict-backdrop">
      <div
        className="paste-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="paste-dialog-title"
        aria-describedby="paste-dialog-text"
        data-testid="paste-conflict-dialog"
        ref={dialog}
        tabIndex={-1}
      >
        <h2 id="paste-dialog-title" className="paste-dialog__title">
          Paste: {request.conflicts.length === 1 ? "one name is" : `${request.conflicts.length} names are`} already
          used
        </h2>
        <p id="paste-dialog-text" className="paste-dialog__text">
          The copied elements bring definitions that {request.project.length > 0 ? request.project : "the target"}{" "}
          already has with different content. Choose per item; the default keeps what is here.
        </p>
        <ul className="paste-dialog__list">
          {request.conflicts.map((conflict) => {
            const id = `paste-choice-${conflict.kind}-${conflict.name}`;
            return (
              <li key={conflict.key} className="paste-dialog__row" data-testid={`paste-conflict-${conflict.kind}-${conflict.name}`}>
                <label htmlFor={id} className="paste-dialog__label">
                  <span className="paste-dialog__kind">{KIND_LABEL[conflict.kind]}</span>{" "}
                  <code>{conflict.name}</code>
                </label>
                <span className="paste-dialog__detail">{conflict.detail}</span>
                <select
                  id={id}
                  className="paste-dialog__select"
                  data-testid={id}
                  value={choices[conflict.key] ?? "existing"}
                  onChange={(event) =>
                    setChoices((current) => ({ ...current, [conflict.key]: event.target.value as ConflictChoice }))
                  }
                >
                  {conflict.choices.map((choice) => (
                    <option key={choice} value={choice}>
                      {choiceLabel(conflict, choice)}
                    </option>
                  ))}
                </select>
              </li>
            );
          })}
        </ul>
        {request.writesFiles ? (
          <p className="paste-dialog__note">
            New library blocks and data files are written to the project when you paste. Undo removes the pasted
            elements, but not those files.
          </p>
        ) : null}
        <div className="paste-dialog__actions">
          <button type="button" className="button" data-testid="paste-conflict-cancel" onClick={cancel}>
            Cancel
          </button>
          <button
            type="button"
            className="button button--primary"
            data-testid="paste-conflict-confirm"
            onClick={() => answer(choices)}
          >
            Paste
          </button>
        </div>
      </div>
    </div>
  );
}

/** What the last paste imported and left behind; stays until closed or replaced. */
export function PasteNoticePanel() {
  const notice = usePasteUiStore((state) => state.notice);
  const dismiss = usePasteUiStore((state) => state.dismissNotice);
  const busy = usePasteUiStore((state) => state.busy);
  if (notice === null) {
    return busy ? (
      <div className="paste-notice paste-notice--busy" role="status" data-testid="paste-busy">
        Pasting…
      </div>
    ) : null;
  }
  return (
    <div
      className={`paste-notice${notice.tone === "error" ? " paste-notice--error" : ""}`}
      role={notice.tone === "error" ? "alert" : "status"}
      data-testid="paste-notice"
      data-tone={notice.tone}
      key={notice.id}
    >
      <div className="paste-notice__header">
        <strong className="paste-notice__title">{notice.title}</strong>
        <button
          type="button"
          className="paste-notice__close"
          aria-label="Close the paste notice"
          data-testid="paste-notice-close"
          onClick={dismiss}
        >
          ×
        </button>
      </div>
      {notice.lines.length > 0 ? (
        <ul className="paste-notice__lines">
          {notice.lines.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
