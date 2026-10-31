/**
 * Name completion for expression fields: while the caret ends an identifier,
 * the global parameter names that start with it are offered below the input.
 * ArrowUp/ArrowDown move, Tab or Enter take the highlighted name, Escape
 * closes the list (a second Escape reverts the field as before).
 */

import { useState, type KeyboardEvent, type ReactNode, type RefObject } from "react";

/** The identifier that ends at `caret`, or null (inside a number or after a dot). */
export function identifierBeforeCaret(text: string, caret: number): { start: number; prefix: string } | null {
  const before = text.slice(0, caret);
  const match = /[A-Za-z_][A-Za-z0-9_]*$/.exec(before);
  if (match === null) {
    return null;
  }
  const start = caret - match[0].length;
  const previous = before[start - 1] ?? "";
  if (/[0-9.]/.test(previous)) {
    return null;
  }
  return { start, prefix: match[0] };
}

/** The names to offer for `prefix`: prefix matches first, then other substring matches. */
export function completionMatches(names: readonly string[], prefix: string): string[] {
  const lower = prefix.toLowerCase();
  const starts = names.filter((name) => name.toLowerCase().startsWith(lower) && name !== prefix);
  const contains = names.filter(
    (name) => !starts.includes(name) && name !== prefix && name.toLowerCase().includes(lower),
  );
  return [...starts, ...contains].slice(0, 8);
}

export interface ExpressionCompletion {
  /** Call from the input's onKeyDown first; true means the key was used. */
  onKeyDown: (event: KeyboardEvent<HTMLInputElement>) => boolean;
  /** Call after every change and caret move. */
  refresh: (text: string, caret: number | null) => void;
  close: () => void;
  /** Props for the input (combobox semantics while names are offered). */
  inputProps: Record<string, string | boolean | undefined>;
  list: ReactNode;
}

export function useExpressionCompletion({
  id,
  names,
  inputRef,
  setText,
  describe,
}: {
  id: string;
  names: readonly string[] | undefined;
  inputRef: RefObject<HTMLInputElement | null>;
  setText: (text: string) => void;
  /** A short hint per name, such as its value. */
  describe?: (name: string) => string | null;
}): ExpressionCompletion {
  const [state, setState] = useState<{ start: number; prefix: string; items: string[]; active: number } | null>(null);
  const listId = `${id}-completions`;

  const refresh = (text: string, caret: number | null): void => {
    if (names === undefined || names.length === 0 || caret === null) {
      setState(null);
      return;
    }
    const at = identifierBeforeCaret(text, caret);
    if (at === null) {
      setState(null);
      return;
    }
    const items = completionMatches(names, at.prefix);
    setState(items.length === 0 ? null : { ...at, items, active: 0 });
  };

  const accept = (name: string): void => {
    const input = inputRef.current;
    if (input === null || state === null) {
      return;
    }
    const text = input.value;
    const end = state.start + state.prefix.length;
    const next = text.slice(0, state.start) + name + text.slice(end);
    setText(next);
    setState(null);
    const caret = state.start + name.length;
    requestAnimationFrame(() => {
      input.setSelectionRange(caret, caret);
    });
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>): boolean => {
    if (state === null) {
      return false;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      setState({ ...state, active: (state.active + step + state.items.length) % state.items.length });
      return true;
    }
    if (event.key === "Enter" || event.key === "Tab") {
      const name = state.items[state.active];
      if (name !== undefined) {
        event.preventDefault();
        accept(name);
        return true;
      }
    }
    if (event.key === "Escape") {
      event.preventDefault();
      setState(null);
      return true;
    }
    return false;
  };

  const open = state !== null;
  const inputProps = {
    role: "combobox",
    "aria-autocomplete": "list",
    "aria-expanded": open,
    "aria-controls": open ? listId : undefined,
    "aria-activedescendant": open ? `${listId}-${state.active}` : undefined,
  };

  const list = open ? (
    <ul className="expression-completions" id={listId} role="listbox" data-testid={`${id}-completions`}>
      {state.items.map((name, index) => {
        const hint = describe?.(name) ?? null;
        return (
          <li
            key={name}
            id={`${listId}-${index}`}
            role="option"
            aria-selected={index === state.active}
            className={
              index === state.active
                ? "expression-completions__item expression-completions__item--active"
                : "expression-completions__item"
            }
            onMouseDown={(event) => {
              event.preventDefault();
              accept(name);
            }}
          >
            <code>{name}</code>
            {hint !== null ? <span className="expression-completions__hint">{hint}</span> : null}
          </li>
        );
      })}
    </ul>
  ) : null;

  return { onKeyDown, refresh, close: () => setState(null), inputProps, list };
}
