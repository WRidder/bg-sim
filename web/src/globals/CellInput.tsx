/**
 * An editable table cell of the Equations manager: a local draft while
 * focused, Enter/blur commits through a store command, Escape reverts. A
 * refused commit keeps the draft and shows the reason under the cell.
 */

import { useEffect, useRef, useState } from "react";

import { useExpressionCompletion } from "../inspector/expressionCompletion";

export interface CellInputProps {
  id: string;
  testId: string;
  label: string;
  value: string;
  onCommit: (text: string) => string | null;
  /** Live check while typing (syntax); null when fine. */
  issue?: (text: string) => string | null;
  placeholder?: string;
  mono?: boolean;
  completions?: readonly string[];
  describeCompletion?: (name: string) => string | null;
  title?: string;
}

export function CellInput({
  id,
  testId,
  label,
  value,
  onCommit,
  issue,
  placeholder,
  mono = false,
  completions,
  describeCompletion,
  title,
}: CellInputProps) {
  const [draft, setDraft] = useState(value);
  const [error, setError] = useState<string | null>(null);
  const last = useRef(value);
  const skipBlur = useRef(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (last.current !== value) {
      last.current = value;
      setDraft(value);
      setError(null);
    }
  }, [value]);

  const update = (text: string): void => {
    setDraft(text);
    setError(issue?.(text) ?? null);
  };
  const completion = useExpressionCompletion({
    id,
    names: completions,
    inputRef,
    setText: update,
    describe: describeCompletion,
  });

  const commit = (): boolean => {
    if (draft === value) {
      setError(null);
      return true;
    }
    const local = issue?.(draft) ?? null;
    if (local !== null) {
      setError(local);
      return false;
    }
    const refusal = onCommit(draft);
    setError(refusal);
    return refusal === null;
  };

  const errorId = `${id}-error`;
  return (
    <div className="equations-cell">
      <input
        ref={inputRef}
        id={id}
        className={mono ? "equations-input equations-input--mono" : "equations-input"}
        data-testid={testId}
        type="text"
        value={draft}
        placeholder={placeholder}
        title={title}
        aria-label={label}
        aria-invalid={error !== null}
        aria-describedby={error !== null ? errorId : undefined}
        autoComplete="off"
        spellCheck={false}
        {...(completions !== undefined ? completion.inputProps : {})}
        onChange={(event) => {
          update(event.target.value);
          completion.refresh(event.target.value, event.target.selectionStart);
        }}
        onBlur={() => {
          completion.close();
          if (skipBlur.current) {
            skipBlur.current = false;
            return;
          }
          commit();
        }}
        onKeyDown={(event) => {
          if (completion.onKeyDown(event)) {
            return;
          }
          if (event.key === "Enter") {
            event.preventDefault();
            if (commit()) {
              skipBlur.current = true;
              event.currentTarget.blur();
            }
          } else if (event.key === "Escape") {
            event.preventDefault();
            event.stopPropagation();
            skipBlur.current = true;
            setDraft(value);
            setError(null);
            event.currentTarget.blur();
          }
        }}
      />
      {completion.list}
      {error !== null ? (
        <p className="equations-cell__error" id={errorId} role="alert" data-testid={`${testId}-error`}>
          {error}
        </p>
      ) : null}
    </div>
  );
}
