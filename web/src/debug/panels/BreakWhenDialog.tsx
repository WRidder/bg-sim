/**
 * The "Break when..." dialog (plan 7.9): a signal (preselected), a comparison and
 * a value with the signal's unit; the dialog writes the watch expression
 * `s"<id>" > 5` as a watch breakpoint. "Advanced" takes any watch expression
 * with completion of signal ids (`s"` opens the list).
 *
 * A watch the server refuses (the 17th) stays visible here with the server's
 * message, so the refusal is not lost when the dialog closes.
 */

import { useId, useMemo, useRef, useState, type KeyboardEvent } from "react";

import { useDialogFocus } from "../../app/useDialogFocus";
import type { BreakpointStatus } from "../../contracts/debug";
import { useRunStore } from "../../plot/runStore";
import { useBreakpointStore } from "../breakpointStore";
import { isDebugging, useDebugStore } from "../debugStore";
import {
  applyCompletion,
  COMPARISONS,
  completionFor,
  MAX_WATCH_SLOTS,
  parseWatchValue,
  watchExpression,
  watchSlotsUsed,
  type Comparison,
} from "./breakWhen";
import { useBreakWhenStore, type BreakWhenRequest } from "./breakWhenStore";

function Form({ request, onClose }: { request: BreakWhenRequest; onClose: () => void }) {
  const manifest = useRunStore((state) => state.manifest);
  const breakpoints = useBreakpointStore((state) => state.breakpoints);
  const titleId = useId();
  const [signalId, setSignalId] = useState(request.signalId);
  const [comparison, setComparison] = useState<Comparison>(">");
  const [valueText, setValueText] = useState("");
  const [advanced, setAdvanced] = useState("");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [caret, setCaret] = useState(0);
  const [active, setActive] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [refused, setRefused] = useState<BreakpointStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const advancedRef = useRef<HTMLInputElement>(null);

  const signals = useMemo(() => manifest?.signals ?? [], [manifest]);
  const ids = useMemo(() => {
    const all = new Set<string>(request.candidates);
    for (const signal of signals) {
      all.add(signal.id);
    }
    return [...all];
  }, [request, signals]);
  const unit = signals.find((signal) => signal.id === signalId.trim())?.unit ?? null;
  const used = watchSlotsUsed(breakpoints);
  const full = used >= MAX_WATCH_SLOTS;
  const completion = advancedOpen ? completionFor(advanced, caret, ids) : null;
  const activeOption = completion === null ? -1 : Math.min(active, completion.options.length - 1);

  const pick = (id: string): void => {
    if (completion === null) {
      return;
    }
    const next = applyCompletion(advanced, caret, completion, id);
    setAdvanced(next.text);
    setCaret(next.caret);
    setActive(0);
    window.requestAnimationFrame(() => {
      advancedRef.current?.focus();
      advancedRef.current?.setSelectionRange(next.caret, next.caret);
    });
  };

  const onAdvancedKey = (event: KeyboardEvent<HTMLInputElement>): void => {
    if (completion === null) {
      return;
    }
    const count = completion.options.length;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((activeOption + 1) % count);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((activeOption - 1 + count) % count);
    } else if (event.key === "Enter" || event.key === "Tab") {
      const chosen = completion.options[activeOption];
      if (chosen !== undefined) {
        event.preventDefault();
        event.stopPropagation();
        pick(chosen);
      }
    }
  };

  const submit = async (): Promise<void> => {
    let expr: string;
    if (advancedOpen && advanced.trim().length > 0) {
      expr = advanced.trim();
    } else {
      const id = signalId.trim();
      if (id.length === 0) {
        setError("Choose the signal to watch.");
        return;
      }
      if (parseWatchValue(valueText) === null) {
        setError("Enter the value as a number, for example 0.5 or 1e-3.");
        return;
      }
      expr = watchExpression(id, comparison, valueText);
    }
    setError(null);
    const id = useBreakpointStore.getState().add({
      enabled: true,
      kind: "watch",
      watch: { expr, context: null },
      hitCount: null,
    });
    if (!isDebugging(useDebugStore.getState())) {
      if (full) {
        setError(
          `All ${MAX_WATCH_SLOTS} watch slots are used. The debug run will refuse this watch; remove or disable another one in the Debug tab.`,
        );
        return;
      }
      onClose();
      return;
    }
    // A running debug run answers the full set; show the refusal, if any.
    setBusy(true);
    await useDebugStore.getState().syncBreakpoints();
    setBusy(false);
    const status = useDebugStore.getState().statuses[id];
    if (status !== undefined && !status.verified) {
      setRefused(status);
      return;
    }
    onClose();
  };

  return (
    <form
      className="break-when"
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <header className="open-dialog__header">
        <h2 className="open-dialog__title" id={titleId}>
          Break when…
        </h2>
        <button
          type="button"
          className="icon-button"
          aria-label="Close Break when"
          title="Close (Esc)"
          onClick={onClose}
        >
          <span aria-hidden="true">✕</span>
        </button>
      </header>
      <div className="break-when__body">
        <label className="break-when__field">
          <span>Signal</span>
          <input
            type="text"
            list={`${titleId}-signals`}
            value={signalId}
            data-testid="break-when-signal"
            spellCheck={false}
            onChange={(event) => setSignalId(event.target.value)}
          />
          <datalist id={`${titleId}-signals`}>
            {ids.map((id) => (
              <option key={id} value={id} />
            ))}
          </datalist>
        </label>
        <div className="break-when__row">
          <label className="break-when__field">
            <span>Comparison</span>
            <select
              value={comparison}
              data-testid="break-when-comparison"
              onChange={(event) => setComparison(event.target.value as Comparison)}
            >
              {COMPARISONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label} ({option.name})
                </option>
              ))}
            </select>
          </label>
          <label className="break-when__field">
            <span>Value{unit !== null && unit.length > 0 ? ` (${unit})` : ""}</span>
            <input
              type="text"
              inputMode="decimal"
              value={valueText}
              data-testid="break-when-value"
              placeholder="0.5"
              onChange={(event) => setValueText(event.target.value)}
            />
          </label>
        </div>
        <p className="break-when__preview" data-testid="break-when-preview">
          Pauses when{" "}
          <code>
            {parseWatchValue(valueText) === null
              ? `s"${signalId.trim()}" ${comparison} …`
              : watchExpression(signalId.trim(), comparison, valueText)}
          </code>
        </p>
        <details
          className="break-when__advanced"
          open={advancedOpen}
          onToggle={(event) => setAdvancedOpen(event.currentTarget.open)}
        >
          <summary>Advanced</summary>
          <label className="break-when__field">
            <span>Watch expression (type s&quot; to complete a signal id)</span>
            <input
              ref={advancedRef}
              type="text"
              value={advanced}
              data-testid="break-when-advanced"
              spellCheck={false}
              autoComplete="off"
              role="combobox"
              aria-expanded={completion !== null}
              aria-controls={`${titleId}-completion`}
              aria-autocomplete="list"
              placeholder='s"Motor1/i" > 5 && t > 0.1'
              onChange={(event) => {
                setAdvanced(event.target.value);
                setCaret(event.target.selectionStart ?? event.target.value.length);
                setActive(0);
              }}
              onSelect={(event) => setCaret(event.currentTarget.selectionStart ?? 0)}
              onKeyDown={onAdvancedKey}
            />
          </label>
          {completion !== null ? (
            <ul
              className="break-when__completion"
              role="listbox"
              id={`${titleId}-completion`}
              aria-label="Signal ids"
              data-testid="break-when-completion"
            >
              {completion.options.map((id, index) => (
                <li
                  key={id}
                  role="option"
                  aria-selected={index === activeOption}
                  className={index === activeOption ? "is-active" : undefined}
                  onMouseDown={(event) => {
                    event.preventDefault();
                    pick(id);
                  }}
                >
                  {id}
                </li>
              ))}
            </ul>
          ) : null}
        </details>
        <p className="break-when__slots" data-testid="break-when-slots">
          {used} / {MAX_WATCH_SLOTS} watch slots in use
          {full ? ". The next watch will be refused by the debug run." : "."}
        </p>
        {error !== null ? (
          <p className="break-when__error" role="alert" data-testid="break-when-error">
            {error}
          </p>
        ) : null}
        {refused !== null ? (
          <div className="break-when__error" role="alert" data-testid="break-when-refused">
            <p>The debug run did not accept this watch.</p>
            <ul>
              {refused.diagnostics.map((diagnostic, index) => (
                <li key={index}>
                  {diagnostic.code}: {diagnostic.message}
                  {diagnostic.hint ? ` ${diagnostic.hint}` : ""}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
      <footer className="break-when__actions">
        <button type="button" className="button" onClick={onClose}>
          {refused !== null ? "Close" : "Cancel"}
        </button>
        {refused === null ? (
          <button
            type="submit"
            className="button button--primary"
            disabled={busy}
            data-testid="break-when-add"
          >
            Add watch breakpoint
          </button>
        ) : null}
      </footer>
    </form>
  );
}

/** Mounted once (in the bottom dock); shows the dialog while a request is open. */
export function BreakWhenDialog() {
  const request = useBreakWhenStore((state) => state.request);
  const close = useBreakWhenStore((state) => state.close);
  const dialog = useRef<HTMLDivElement>(null);
  useDialogFocus(request !== null, dialog, close);

  if (request === null) {
    return null;
  }
  return (
    <div
      className="dialog-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          close();
        }
      }}
    >
      <div
        className="open-dialog break-when-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="Break when"
        data-testid="break-when-dialog"
        ref={dialog}
        tabIndex={-1}
      >
        <Form request={request} onClose={close} />
      </div>
    </div>
  );
}
