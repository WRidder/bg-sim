/**
 * The list/grid switch of the library panel title: two icon buttons in a segmented group, the
 * pressed one being the current view. The choice persists through src/library/libraryPrefs.ts
 * (the cog's quick settings offer the same choice).
 */

import { GridViewIcon, ListViewIcon } from "./icons";
import { useLibraryPrefs, type LibraryView } from "./libraryPrefs";

const OPTIONS: { view: LibraryView; label: string; title: string }[] = [
  { view: "list", label: "List view", title: "List view: names with a summary and details" },
  { view: "grid", label: "Grid view", title: "Grid view: icons with their names" },
];

export function LibraryViewToggle() {
  const view = useLibraryPrefs((state) => state.view);
  return (
    <div className="library-view-toggle" role="group" aria-label="Library view">
      {OPTIONS.map((option) => (
        <button
          key={option.view}
          type="button"
          className={`library-view-toggle__button${view === option.view ? " is-active" : ""}`}
          aria-label={option.label}
          aria-pressed={view === option.view}
          title={option.title}
          data-testid={`library-view-${option.view}`}
          onClick={() => useLibraryPrefs.getState().setView(option.view)}
        >
          {option.view === "list" ? <ListViewIcon size={14} /> : <GridViewIcon size={14} />}
        </button>
      ))}
    </div>
  );
}
