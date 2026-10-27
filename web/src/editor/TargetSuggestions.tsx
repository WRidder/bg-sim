/**
 * The drop-on-empty palette: a filterable list of elements that can be added
 * at the release point and connected to the port the drag started from.
 *
 * The list arrives already filtered by compatibility and ranked by
 * `suggestTargets`; this component only narrows it with the search box and
 * reports the choice. Arrow keys move, Enter picks, Escape closes.
 */

import { useEffect, useMemo, useRef, useState } from "react";

import { describePort, type PortDescriptor } from "./connectionRules";
import { BlockIcon, JunctionGlyph } from "./icons";
import {
  filterSuggestions,
  suggestionPortLabel,
  type TargetSuggestion,
} from "./suggestTargets";

export interface TargetSuggestionsProps {
  suggestions: readonly TargetSuggestion[];
  origin: PortDescriptor;
  /** Viewport position of the panel (fixed). */
  x: number;
  y: number;
  onPick: (suggestion: TargetSuggestion) => void;
  onClose: () => void;
}

export function TargetSuggestions({
  suggestions,
  origin,
  x,
  y,
  onPick,
  onClose,
}: TargetSuggestionsProps) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const optionRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const filtered = useMemo(
    () => filterSuggestions(suggestions, query),
    [suggestions, query],
  );
  const clampedActive =
    filtered.length === 0 ? -1 : Math.min(active, filtered.length - 1);

  useEffect(() => {
    if (clampedActive < 0) {
      return;
    }
    const option = optionRefs.current[clampedActive];
    if (typeof option?.scrollIntoView === "function") {
      option.scrollIntoView({ block: "nearest" });
    }
  }, [clampedActive]);

  const choose = (suggestion: TargetSuggestion | undefined): void => {
    if (suggestion !== undefined) {
      onPick(suggestion);
    }
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>): void => {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      onClose();
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (filtered.length > 0) {
        setActive((current) => (Math.min(current, filtered.length - 1) + 1) % filtered.length);
      }
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      if (filtered.length > 0) {
        setActive(
          (current) =>
            (Math.min(current, filtered.length - 1) - 1 + filtered.length) % filtered.length,
        );
      }
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      event.stopPropagation();
      choose(filtered[clampedActive]);
    }
  };

  return (
    <div
      className="target-suggest"
      role="dialog"
      aria-label="Add a compatible element"
      data-testid="target-suggestions"
      style={{ left: x, top: y }}
      onKeyDown={onKeyDown}
      onPointerDown={(event) => event.stopPropagation()}
    >
      <div className="target-suggest__header">
        <span className="target-suggest__title">Add an element</span>
        <span className="target-suggest__origin" data-testid="target-suggestions-origin">
          connect from {describePort(origin)}
        </span>
        <button
          type="button"
          className="target-suggest__close"
          aria-label="Close suggestions"
          data-testid="target-suggestions-close"
          onClick={onClose}
        >
          ×
        </button>
      </div>

      <input
        type="search"
        className="target-suggest__filter"
        placeholder="Filter compatible elements…"
        aria-label="Filter suggested elements"
        data-testid="target-suggestions-filter"
        value={query}
        autoFocus
        onChange={(event) => {
          setQuery(event.target.value);
          setActive(0);
        }}
      />

      {filtered.length > 0 ? (
        <div
          className="target-suggest__list"
          role="listbox"
          aria-label="Compatible elements"
          data-testid="target-suggestions-list"
        >
          {filtered.map((suggestion, index) => (
            <button
              key={suggestion.key}
              ref={(element) => {
                optionRefs.current[index] = element;
              }}
              type="button"
              role="option"
              aria-selected={index === clampedActive}
              className="target-suggest__option"
              data-testid={`target-suggestion-${suggestion.key}`}
              data-ref={suggestion.kind === "block" ? suggestion.block.ref : suggestion.key}
              title={suggestion.description}
              onMouseEnter={() => setActive(index)}
              onClick={() => choose(suggestion)}
            >
              <span className="target-suggest__icon" aria-hidden="true">
                {suggestion.kind === "junction" ? (
                  <JunctionGlyph kind={suggestion.junction} size={26} />
                ) : (
                  <BlockIcon icon={suggestion.icon} name={suggestion.name} size={26} />
                )}
              </span>
              <span className="target-suggest__text">
                <span className="target-suggest__name">
                  {suggestion.name}
                  <span className="target-suggest__group">{suggestion.group}</span>
                </span>
                <span className="target-suggest__port">
                  {suggestionPortLabel(suggestion)}
                </span>
              </span>
            </button>
          ))}
        </div>
      ) : (
        <p className="target-suggest__empty" data-testid="target-suggestions-empty">
          {suggestions.length === 0
            ? "No library element can connect to this port."
            : `No compatible element matches “${query}”.`}
        </p>
      )}

      <div className="target-suggest__hint" aria-hidden="true">
        {filtered.length} compatible · ↑↓ choose · Enter add · Esc close
      </div>
    </div>
  );
}
