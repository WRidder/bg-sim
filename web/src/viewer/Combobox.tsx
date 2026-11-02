import { useCallback, useId, useMemo, useRef, useState, type KeyboardEvent, type ReactElement } from "react";

/**
 * A searchable single-choice field for long lists (the thousands of signals of a large model, the
 * entities of a scene). Closed it is one text input showing the current value; the option list is
 * built only while it is open, filtered by what is typed, and windowed: only the rows in view exist
 * in the DOM. A binding table of hundreds of rows therefore costs one input per field instead of a
 * `<select>` with every signal as an `<option>`.
 *
 * Keyboard: typing filters and opens the list, Down/Up (Alt+Down opens) and PageDown/PageUp move,
 * Enter chooses, Escape closes and restores the value. Leaving the field keeps the value unless the
 * typed text is exactly one of the choices (or empty, for a field with a "none" choice).
 * ARIA: `role="combobox"` with `aria-expanded`, `aria-controls` and `aria-activedescendant` on a
 * `role="listbox"`; the options carry `aria-setsize` and `aria-posinset` since only a window of them
 * is rendered.
 */

/** The choices of a combobox, precomputed once per list (lowercase search text, value positions). */
export interface ComboChoices {
  readonly values: readonly string[];
  readonly labels: readonly string[];
  /** Lowercase labels, what typing is matched against. */
  readonly search: readonly string[];
  readonly position: ReadonlyMap<string, number>;
}

export function comboChoices(values: readonly string[], labels: readonly string[] = values): ComboChoices {
  const position = new Map<string, number>();
  values.forEach((v, k) => {
    if (!position.has(v)) position.set(v, k);
  });
  return { values, labels, search: labels.map((l) => l.toLowerCase()), position };
}

export const NO_CHOICES: ComboChoices = comboChoices([]);

/** Indices of the choices whose label holds every whitespace-separated term of `query` (any case), in list order. */
export function filterChoices(choices: ComboChoices, query: string): number[] {
  const terms = query.toLowerCase().split(/\s+/).filter((t) => t !== "");
  const out: number[] = [];
  const { search } = choices;
  for (let k = 0; k < search.length; k++) {
    const s = search[k] ?? "";
    if (terms.every((t) => s.includes(t))) out.push(k);
  }
  return out;
}

/** Height of one option row in px (fixed, so the list can be windowed); keep in step with `.combo__option`. */
export const OPTION_HEIGHT = 24;
/** Option rows in view while the list is open. */
const VISIBLE = 12;
/** Extra rows rendered above and below the view. */
const OVERSCAN = 6;

interface Item {
  readonly value: string;
  readonly label: string;
  readonly kind: "none" | "unknown" | "choice";
}

export interface ComboboxProps {
  readonly value: string;
  readonly choices: ComboChoices;
  /** The accessible name of the field. */
  readonly label: string;
  readonly testId?: string;
  /** Offers the empty value first with this label (an optional field: "none"). */
  readonly noneLabel?: string;
  /** Shown in the empty field when there is no "none" choice ("Choose a signal"). */
  readonly placeholder?: string;
  /** Suffix of a value that is not among the choices: `<value> (<unknownNote>)`. */
  readonly unknownNote: string;
  readonly className?: string;
  readonly onChange: (value: string) => void;
}

export function Combobox({ value, choices, label, testId, noneLabel, placeholder, unknownNote, className, onChange }: ComboboxProps): ReactElement {
  const listId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  /** The typed text; null while the field shows the value. */
  const [query, setQuery] = useState<string | null>(null);
  const [active, setActive] = useState(0);
  const [scroll, setScroll] = useState(0);

  const pos = choices.position.get(value);
  const known = pos !== undefined;
  const display = value === "" ? (noneLabel ?? "") : pos !== undefined ? (choices.labels[pos] ?? value) : `${value} (${unknownNote})`;

  // the option list exists only while open
  const items = useMemo((): Item[] => {
    if (!open) return [];
    const out: Item[] = [];
    if (query === null) {
      if (noneLabel !== undefined) out.push({ value: "", label: noneLabel, kind: "none" });
      if (value !== "" && !known) out.push({ value, label: `${value} (${unknownNote})`, kind: "unknown" });
      choices.values.forEach((v, k) => out.push({ value: v, label: choices.labels[k] ?? v, kind: "choice" }));
      return out;
    }
    if (noneLabel !== undefined && query.trim() === "") out.push({ value: "", label: noneLabel, kind: "none" });
    for (const k of filterChoices(choices, query)) out.push({ value: choices.values[k] ?? "", label: choices.labels[k] ?? "", kind: "choice" });
    return out;
  }, [open, query, choices, noneLabel, value, known, unknownNote]);

  /** The list's scroll offset to apply when it mounts. */
  const pendingScroll = useRef(0);
  const attachList = useCallback((el: HTMLDivElement | null): void => {
    listRef.current = el;
    if (el !== null) el.scrollTop = pendingScroll.current;
  }, []);
  const scrollTo = (top: number): void => {
    pendingScroll.current = top;
    setScroll(top);
    if (listRef.current !== null) listRef.current.scrollTop = top;
  };
  /** Scrolls the list so that row `k` is in view. */
  const reveal = (k: number): void => {
    const now = listRef.current?.scrollTop ?? scroll;
    const top = k * OPTION_HEIGHT;
    if (top < now) scrollTo(top);
    else if (top + OPTION_HEIGHT > now + VISIBLE * OPTION_HEIGHT) scrollTo(top + OPTION_HEIGHT - VISIBLE * OPTION_HEIGHT);
  };

  const openList = (): void => {
    if (open) return;
    // start on the current value, like a native select: after the "none" and "unknown" rows
    const lead = (noneLabel !== undefined ? 1 : 0) + (value !== "" && !known ? 1 : 0);
    const start = value === "" ? 0 : pos !== undefined ? lead + pos : lead - 1;
    setActive(start);
    scrollTo(Math.max(0, (start - Math.floor(VISIBLE / 2)) * OPTION_HEIGHT));
    setOpen(true);
  };
  const close = (): void => {
    setOpen(false);
    setQuery(null);
  };
  const choose = (v: string): void => {
    close();
    if (v !== value) onChange(v);
  };
  /** The value the typed text names exactly (an id or a label), or null. */
  const exact = (text: string): string | null => {
    const t = text.trim();
    if (t === "") return noneLabel !== undefined ? "" : null;
    if (choices.position.has(t)) return t;
    const k = choices.labels.indexOf(t);
    return k >= 0 ? (choices.values[k] ?? null) : null;
  };

  const move = (to: number): void => {
    if (items.length === 0) return;
    const k = Math.max(0, Math.min(items.length - 1, to));
    setActive(k);
    reveal(k);
  };
  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>): void => {
    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        if (!open) openList();
        else if (!e.altKey) move(active + 1);
        return;
      case "ArrowUp":
        e.preventDefault();
        if (open) move(active - 1);
        return;
      case "PageDown":
        if (!open) return;
        e.preventDefault();
        move(active + VISIBLE);
        return;
      case "PageUp":
        if (!open) return;
        e.preventDefault();
        move(active - VISIBLE);
        return;
      case "Enter": {
        // never submits the add form: Enter chooses, or opens the list
        e.preventDefault();
        if (!open) {
          openList();
          return;
        }
        const item = items[active];
        const typed = query !== null ? exact(query) : null;
        if (typed !== null) choose(typed);
        else if (item !== undefined) choose(item.value);
        return;
      }
      case "Escape":
        if (!open) return;
        e.preventDefault();
        e.stopPropagation();
        close();
        return;
      default:
    }
  };

  const first = Math.max(0, Math.floor(scroll / OPTION_HEIGHT) - OVERSCAN);
  const last = Math.min(items.length, first + VISIBLE + 2 * OVERSCAN);
  const shown = items.slice(first, last);
  const activeItem = open && active < items.length ? `${listId}-${String(active)}` : undefined;

  return (
    <div className={`combo${className !== undefined ? ` ${className}` : ""}`}>
      <input
        ref={inputRef}
        type="text"
        role="combobox"
        className="combo__input"
        aria-label={label}
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        aria-autocomplete="list"
        aria-activedescendant={activeItem}
        aria-invalid={value !== "" && !known ? true : undefined}
        data-testid={testId}
        data-value={value}
        title={display !== "" ? display : undefined}
        placeholder={placeholder}
        spellCheck={false}
        autoComplete="off"
        value={query ?? display}
        onChange={(e) => {
          const text = e.target.value;
          if (!open) setOpen(true);
          setQuery(text);
          // the exact match, else the first match, is what Enter takes
          const t = text.trim();
          const hit = t === "" ? -1 : filterChoices(choices, text).findIndex((k) => choices.values[k] === t || choices.labels[k] === t);
          const none = noneLabel !== undefined && t === "" ? 1 : 0;
          const k = hit >= 0 ? hit + none : 0;
          setActive(k);
          scrollTo(Math.max(0, (k - Math.floor(VISIBLE / 2)) * OPTION_HEIGHT));
        }}
        onClick={() => {
          if (open) {
            if (query === null) close();
            return;
          }
          openList();
          inputRef.current?.select();
        }}
        onFocus={(e) => {
          e.target.select();
        }}
        onBlur={() => {
          const typed = query !== null ? exact(query) : null;
          close();
          if (typed !== null && typed !== value) onChange(typed);
        }}
        onKeyDown={onKeyDown}
      />
      {open ? (
        <div
          ref={attachList}
          id={listId}
          role="listbox"
          aria-label={label}
          className="combo__list"
          style={{ maxHeight: VISIBLE * OPTION_HEIGHT }}
          data-testid={testId !== undefined ? `${testId}-list` : undefined}
          onMouseDown={(e) => {
            // keep the focus (and the typed text) in the input
            e.preventDefault();
          }}
          onClick={(e) => {
            // inside a <label>, a click would also be passed on to the input and open the list again
            e.preventDefault();
          }}
          onScroll={(e) => {
            pendingScroll.current = e.currentTarget.scrollTop;
            setScroll(e.currentTarget.scrollTop);
          }}
        >
          {items.length === 0 ? (
            <div className="combo__empty">No match</div>
          ) : (
            <div style={{ height: items.length * OPTION_HEIGHT, position: "relative" }}>
              {shown.map((item, j) => {
                const k = first + j;
                return (
                  <div
                    key={`${item.kind}:${item.value}`}
                    id={`${listId}-${String(k)}`}
                    role="option"
                    aria-selected={k === active}
                    aria-setsize={items.length}
                    aria-posinset={k + 1}
                    data-value={item.value}
                    data-current={item.value === value ? "true" : undefined}
                    className={`combo__option${item.kind !== "choice" ? " combo__option--note" : ""}`}
                    style={{ top: k * OPTION_HEIGHT }}
                    title={item.label}
                    onMouseEnter={() => {
                      setActive(k);
                    }}
                    onClick={() => {
                      choose(item.value);
                    }}
                  >
                    {item.label}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}
