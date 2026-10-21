import { useRef, type KeyboardEvent } from "react";

export interface TabBadge {
  count: number;
  tone: "error" | "warning";
}

export interface TabDefinition<Id extends string> {
  id: Id;
  label: string;
  /** Count badges, e.g. diagnostics. Zero-count badges are not rendered. */
  badges?: readonly TabBadge[];
}

export interface TabStripProps<Id extends string> {
  tabs: readonly TabDefinition<Id>[];
  active: Id;
  onSelect: (id: Id) => void;
  ariaLabel: string;
  /** Prefix for the tab/tabpanel id wiring, e.g. "center" or "dock". */
  idPrefix: string;
}

/**
 * An accessible tab strip (role="tablist" with arrow-key navigation, WAI-ARIA
 * tabs pattern). The panel itself is rendered by the caller.
 */
export function TabStrip<Id extends string>({
  tabs,
  active,
  onSelect,
  ariaLabel,
  idPrefix,
}: TabStripProps<Id>) {
  const listRef = useRef<HTMLDivElement>(null);

  const selectByIndex = (index: number): void => {
    const wrapped = (index + tabs.length) % tabs.length;
    const tab = tabs[wrapped];
    if (tab === undefined) {
      return;
    }
    onSelect(tab.id);
    listRef.current?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[wrapped]?.focus();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>): void => {
    const current = tabs.findIndex((tab) => tab.id === active);
    switch (event.key) {
      case "ArrowRight":
      case "ArrowDown":
        event.preventDefault();
        selectByIndex(current + 1);
        break;
      case "ArrowLeft":
      case "ArrowUp":
        event.preventDefault();
        selectByIndex(current - 1);
        break;
      case "Home":
        event.preventDefault();
        selectByIndex(0);
        break;
      case "End":
        event.preventDefault();
        selectByIndex(tabs.length - 1);
        break;
      default:
        break;
    }
  };

  return (
    <div
      ref={listRef}
      className="tab-strip"
      role="tablist"
      aria-label={ariaLabel}
      onKeyDown={handleKeyDown}
    >
      {tabs.map((tab) => {
        const selected = tab.id === active;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            id={`${idPrefix}-tab-${tab.id}`}
            aria-selected={selected}
            aria-controls={`${idPrefix}-panel-${tab.id}`}
            tabIndex={selected ? 0 : -1}
            className="tab-strip__tab"
            onClick={() => onSelect(tab.id)}
          >
            {tab.label}
            {(tab.badges ?? [])
              .filter((badge) => badge.count > 0)
              .map((badge) => (
                <span
                  key={badge.tone}
                  className={`tab-strip__badge tab-strip__badge--${badge.tone}`}
                  aria-label={`${badge.count} ${badge.tone === "error" ? "errors" : "warnings"}`}
                >
                  {badge.count}
                </span>
              ))}
          </button>
        );
      })}
    </div>
  );
}
