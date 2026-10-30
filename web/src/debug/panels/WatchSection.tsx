/**
 * Watch expressions (plan 7.9): expressions re-evaluated at every pause through
 * `debug.evaluate`. They read values; they do not stop the run (that is a watch
 * *breakpoint*, created with "Break when...").
 */

import { useState, type FormEvent } from "react";

import { useDebugStore } from "../debugStore";
import { useWatchExpressionStore, type WatchExpression } from "./watchExpressionStore";

function Row({ item }: { item: WatchExpression }) {
  const result = useWatchExpressionStore((state) => state.results[item.id]);
  const status = useDebugStore((state) => state.status);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(item.expr);

  const commit = (event: FormEvent): void => {
    event.preventDefault();
    if (draft.trim().length > 0) {
      useWatchExpressionStore.getState().edit(item.id, draft);
      setEditing(false);
    }
  };

  return (
    <li className="debug-watch" data-testid="watch-expression-row" data-expr={item.expr}>
      {editing ? (
        <form className="debug-watch__edit" onSubmit={commit}>
          <input
            type="text"
            value={draft}
            aria-label={`Edit the expression ${item.expr}`}
            data-testid="watch-expression-edit"
            spellCheck={false}
            autoFocus
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                event.stopPropagation();
                setDraft(item.expr);
                setEditing(false);
              }
            }}
          />
          <button type="submit" className="button">
            Save
          </button>
        </form>
      ) : (
        <>
          <code className="debug-watch__expr">{item.expr}</code>
          <span
            className={`debug-watch__result${result?.state === "error" ? " is-error" : ""}`}
            data-testid="watch-expression-value"
            role={result?.state === "error" ? "alert" : undefined}
          >
            {result === undefined
              ? status === "paused"
                ? "…"
                : "—"
              : result.state === "error"
                ? result.message
                : `${result.text}${result.unit ? ` ${result.unit}` : ""}`}
          </span>
          <button
            type="button"
            className="debug-row-button"
            aria-label={`Edit expression ${item.expr}`}
            title="Edit"
            onClick={() => {
              setDraft(item.expr);
              setEditing(true);
            }}
          >
            Edit
          </button>
          <button
            type="button"
            className="debug-row-button"
            aria-label={`Remove expression ${item.expr}`}
            title="Remove"
            data-testid="watch-expression-remove"
            onClick={() => useWatchExpressionStore.getState().remove(item.id)}
          >
            ✕
          </button>
        </>
      )}
    </li>
  );
}

export function WatchSection() {
  const items = useWatchExpressionStore((state) => state.items);
  const [text, setText] = useState("");

  const add = (event: FormEvent): void => {
    event.preventDefault();
    if (useWatchExpressionStore.getState().add(text) !== null) {
      setText("");
    }
  };

  return (
    <div data-testid="watch-expressions">
      <form className="debug-watch__add" onSubmit={add}>
        <input
          type="text"
          value={text}
          placeholder='s"Synthetic/sine" * 2   or   t'
          aria-label="New watch expression"
          data-testid="watch-expression-input"
          spellCheck={false}
          onChange={(event) => setText(event.target.value)}
        />
        <button type="submit" className="button" data-testid="watch-expression-add" disabled={text.trim().length === 0}>
          Add
        </button>
      </form>
      {items.length === 0 ? (
        <p className="debug-panel__hint" data-testid="watch-expressions-empty">
          Add an expression (a signal as s&quot;Motor1/i&quot;, the time t, arithmetic and comparisons) and it is
          evaluated at every pause.
        </p>
      ) : (
        <ul className="debug-watch-list">
          {items.map((item) => (
            <Row key={item.id} item={item} />
          ))}
        </ul>
      )}
    </div>
  );
}
