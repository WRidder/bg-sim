/**
 * Editable fields of the inspector.
 *
 * A field keeps a local draft while it has focus. Enter and blur commit the
 * draft through a document-store command; Escape reverts. Because the document
 * remains the only source of truth, undo, redo, autosave and the canvas all see
 * exactly one value. The local draft is dropped as soon as the document value
 * changes underneath it (an undo, a reset, or a command from another panel).
 */

import { useEffect, useRef, useState, type ReactNode } from "react";

export interface TextFieldProps {
  id: string;
  /** The input's test id; the wrapper appends `-field`, the error `-error`. */
  testId: string;
  label: string;
  value: string;
  /** Live validation; returns a message or null. */
  issue: (text: string) => string | null;
  /** Commit through the store; returns a refusal message or null. */
  onCommit: (text: string) => string | null;
  onReset?: () => void;
  resetLabel?: string;
  unit?: string | null;
  description?: string | null;
  meta?: ReactNode;
  badges?: ReactNode;
  placeholder?: string;
  inputMode?: "text" | "numeric" | "decimal";
  /** Render the value as an expression (mono, no spellcheck); always true here. */
  ariaLabel?: string;
}

export function TextField({
  id,
  testId,
  label,
  value,
  issue,
  onCommit,
  onReset,
  resetLabel,
  unit,
  description,
  meta,
  badges,
  placeholder,
  inputMode = "text",
  ariaLabel,
}: TextFieldProps) {
  const [draft, setDraft] = useState(value);
  const [error, setError] = useState<string | null>(null);
  const lastValue = useRef(value);
  const skipBlur = useRef(false);
  const errorId = `${id}-error`;
  const descriptionId = `${id}-description`;

  useEffect(() => {
    if (lastValue.current !== value) {
      lastValue.current = value;
      setDraft(value);
      setError(null);
    }
  }, [value]);

  const update = (text: string): void => {
    setDraft(text);
    setError(issue(text));
  };

  const commit = (): boolean => {
    const text = draft.trim();
    const currentIssue = issue(text);
    if (currentIssue !== null) {
      setError(currentIssue);
      return false;
    }
    if (text === value.trim()) {
      setError(null);
      return true;
    }
    const refusal = onCommit(text);
    if (refusal !== null) {
      setError(refusal);
      return false;
    }
    setError(null);
    return true;
  };

  const describedBy =
    [description !== null && description !== undefined ? descriptionId : null, error !== null ? errorId : null]
      .filter((entry): entry is string => entry !== null)
      .join(" ") || undefined;

  return (
    <div className="inspector-field" data-testid={`${testId}-field`}>
      <div className="inspector-field__head">
        <label className="inspector-field__label" htmlFor={id}>
          {label}
        </label>
        {badges}
        {unit !== undefined ? (
          <span
            className="inspector-field__unit"
            title={unit === null ? "Dimensionless" : `Unit: ${unit}`}
          >
            {unit ?? "—"}
          </span>
        ) : null}
      </div>
      <div className="inspector-field__row">
        <input
          id={id}
          className="inspector-input"
          data-testid={testId}
          type="text"
          inputMode={inputMode}
          value={draft}
          placeholder={placeholder}
          aria-label={ariaLabel}
          aria-invalid={error !== null}
          aria-describedby={describedBy}
          autoComplete="off"
          spellCheck={false}
          onChange={(event) => update(event.target.value)}
          onBlur={() => {
            if (skipBlur.current) {
              skipBlur.current = false;
              return;
            }
            commit();
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              if (commit()) {
                skipBlur.current = true;
                event.currentTarget.blur();
              }
            } else if (event.key === "Escape") {
              event.preventDefault();
              skipBlur.current = true;
              setDraft(value);
              setError(null);
              event.currentTarget.blur();
            }
          }}
        />
        {onReset !== undefined ? (
          <button
            type="button"
            className="inspector-reset"
            data-testid={`${testId}-reset`}
            aria-label={resetLabel ?? `Reset ${label} to its default`}
            title={resetLabel ?? "Reset to the default"}
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => {
              setError(null);
              onReset();
            }}
          >
            ↺
          </button>
        ) : null}
      </div>
      {description !== null && description !== undefined && description.length > 0 ? (
        <p className="inspector-field__description" id={descriptionId}>
          {description}
        </p>
      ) : null}
      {meta !== undefined ? <p className="inspector-field__meta">{meta}</p> : null}
      {error !== null ? (
        <p className="inspector-field__error" id={errorId} role="alert" data-testid={`${testId}-error`}>
          {error}
        </p>
      ) : null}
    </div>
  );
}

export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectFieldProps {
  id: string;
  testId: string;
  label: string;
  value: string;
  options: readonly SelectOption[];
  onChange: (value: string) => string | null;
  onReset?: () => void;
  resetLabel?: string;
  unit?: string | null;
  description?: string | null;
  meta?: ReactNode;
  badges?: ReactNode;
  /** Shown when the stored value is not one of the options. */
  invalidMessage?: string | null;
}

/** A drop-down field; used for Int enumerations (D11) and Bool constants. */
export function SelectField({
  id,
  testId,
  label,
  value,
  options,
  onChange,
  onReset,
  resetLabel,
  unit,
  description,
  meta,
  badges,
  invalidMessage,
}: SelectFieldProps) {
  const [error, setError] = useState<string | null>(null);
  const lastValue = useRef(value);

  useEffect(() => {
    if (lastValue.current !== value) {
      lastValue.current = value;
      setError(null);
    }
  }, [value]);

  const errorId = `${id}-error`;
  const descriptionId = `${id}-description`;
  const known = options.some((option) => option.value === value);
  const shownError = error ?? (known ? null : (invalidMessage ?? null));
  const describedBy =
    [
      description !== null && description !== undefined ? descriptionId : null,
      shownError !== null ? errorId : null,
    ]
      .filter((entry): entry is string => entry !== null)
      .join(" ") || undefined;

  return (
    <div className="inspector-field" data-testid={`${testId}-field`}>
      <div className="inspector-field__head">
        <label className="inspector-field__label" htmlFor={id}>
          {label}
        </label>
        {badges}
        {unit !== undefined ? (
          <span
            className="inspector-field__unit"
            title={unit === null ? "Dimensionless" : `Unit: ${unit}`}
          >
            {unit ?? "—"}
          </span>
        ) : null}
      </div>
      <div className="inspector-field__row">
        <select
          id={id}
          className="inspector-input inspector-select"
          data-testid={testId}
          value={known ? value : ""}
          aria-invalid={shownError !== null}
          aria-describedby={describedBy}
          onChange={(event) => {
            const refusal = onChange(event.target.value);
            setError(refusal);
          }}
        >
          {known ? null : (
            <option value="" disabled>
              Choose…
            </option>
          )}
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        {onReset !== undefined ? (
          <button
            type="button"
            className="inspector-reset"
            data-testid={`${testId}-reset`}
            aria-label={resetLabel ?? `Reset ${label} to its default`}
            title={resetLabel ?? "Reset to the default"}
            onClick={() => {
              setError(null);
              onReset();
            }}
          >
            ↺
          </button>
        ) : null}
      </div>
      {description !== null && description !== undefined && description.length > 0 ? (
        <p className="inspector-field__description" id={descriptionId}>
          {description}
        </p>
      ) : null}
      {meta !== undefined ? <p className="inspector-field__meta">{meta}</p> : null}
      {shownError !== null ? (
        <p className="inspector-field__error" id={errorId} role="alert" data-testid={`${testId}-error`}>
          {shownError}
        </p>
      ) : null}
    </div>
  );
}
