/**
 * Per-browser view preferences of the library panel: which categories are expanded, which are
 * hidden, and whether the blocks show as a list or a grid of tiles. All three persist in localStorage (a private-mode browser without storage keeps them
 * for the session only). The search-time overrides are transient: while a query is active the
 * matching categories show expanded, and a category the user collapses during that search is
 * remembered here until the query changes.
 */

import { create } from "zustand";

export const EXPANDED_KEY = "bgsim.library.expanded";
export const HIDDEN_KEY = "bgsim.library.hidden";
export const VIEW_KEY = "bgsim.library.view";

/** The list shows a summary line and expandable details; the grid shows an icon and a label only. */
export type LibraryView = "list" | "grid";

function readView(): LibraryView {
  try {
    return window.localStorage.getItem(VIEW_KEY) === "grid" ? "grid" : "list";
  } catch {
    return "list";
  }
}

function writeView(view: LibraryView): void {
  try {
    window.localStorage.setItem(VIEW_KEY, view);
  } catch {
    // A private-mode browser has no storage; the preference still holds for this session.
  }
}

function readNames(key: string): ReadonlySet<string> {
  try {
    const raw = window.localStorage.getItem(key);
    if (raw === null) {
      return new Set();
    }
    const parsed: unknown = JSON.parse(raw);
    return new Set(
      Array.isArray(parsed) ? parsed.filter((name): name is string => typeof name === "string") : [],
    );
  } catch {
    return new Set();
  }
}

function writeNames(key: string, names: ReadonlySet<string>): void {
  try {
    window.localStorage.setItem(key, JSON.stringify([...names]));
  } catch {
    // A private-mode browser has no storage; the preference still holds for this session.
  }
}

interface LibraryPrefsState {
  /** Categories expanded when no search is active (persisted). */
  expanded: ReadonlySet<string>;
  /** Categories not listed and not searched (persisted). */
  hidden: ReadonlySet<string>;
  /** Categories collapsed by hand during the current search (transient). */
  searchCollapsed: ReadonlySet<string>;
  /** List or grid of tiles (persisted). */
  view: LibraryView;
  setView: (view: LibraryView) => void;
  toggleExpanded: (name: string) => void;
  toggleSearchCollapsed: (name: string) => void;
  clearSearchOverrides: () => void;
  expandAll: (names: readonly string[]) => void;
  collapseAll: (names: readonly string[]) => void;
  setHidden: (name: string, hidden: boolean) => void;
  showAll: () => void;
}

function toggled(names: ReadonlySet<string>, name: string): ReadonlySet<string> {
  const next = new Set(names);
  if (next.has(name)) {
    next.delete(name);
  } else {
    next.add(name);
  }
  return next;
}

export const useLibraryPrefs = create<LibraryPrefsState>((set, get) => ({
  expanded: readNames(EXPANDED_KEY),
  hidden: readNames(HIDDEN_KEY),
  searchCollapsed: new Set(),
  view: readView(),
  setView: (view) => {
    writeView(view);
    set({ view });
  },
  toggleExpanded: (name) => {
    const expanded = toggled(get().expanded, name);
    writeNames(EXPANDED_KEY, expanded);
    set({ expanded });
  },
  toggleSearchCollapsed: (name) => set({ searchCollapsed: toggled(get().searchCollapsed, name) }),
  clearSearchOverrides: () => {
    if (get().searchCollapsed.size > 0) {
      set({ searchCollapsed: new Set() });
    }
  },
  expandAll: (names) => {
    const expanded = new Set([...get().expanded, ...names]);
    writeNames(EXPANDED_KEY, expanded);
    set({ expanded, searchCollapsed: new Set() });
  },
  collapseAll: (names) => {
    const expanded = new Set(get().expanded);
    for (const name of names) {
      expanded.delete(name);
    }
    writeNames(EXPANDED_KEY, expanded);
    set({ expanded, searchCollapsed: new Set(names) });
  },
  setHidden: (name, hidden) => {
    const next = new Set(get().hidden);
    if (hidden) {
      next.add(name);
    } else {
      next.delete(name);
    }
    writeNames(HIDDEN_KEY, next);
    set({ hidden: next });
  },
  showAll: () => {
    writeNames(HIDDEN_KEY, new Set());
    set({ hidden: new Set() });
  },
}));

/** Re-read the persisted preferences (tests, and a storage reset). */
export function resetLibraryPrefs(): void {
  useLibraryPrefs.setState({
    expanded: readNames(EXPANDED_KEY),
    hidden: readNames(HIDDEN_KEY),
    searchCollapsed: new Set(),
    view: readView(),
  });
}
