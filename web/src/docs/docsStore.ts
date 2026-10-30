/**
 * State of the Docs tab (W5.6): the page tree of the open model, the page texts (saved and
 * draft), the selected page and the view mode. Tree edits are saved at once; page texts are
 * saved with Ctrl+S, when the tab is left, or when another model is opened.
 */

import { create } from "zustand";

import {
  deleteUnusedAssets,
  deletePage,
  fetchManifest,
  fetchPage,
  listAssets,
  saveManifest,
  savePage,
} from "./docsApi";
import { registerLeaveGuard } from "./leaveGuard";
import {
  EMPTY_DOCS,
  addChild,
  addSibling,
  dropPage,
  findPage,
  firstPageId,
  keyboardMove,
  renamePage,
  type DeleteMode,
  type Docs,
  type DropPosition,
} from "./pageTree";

export type DocsMode = "view" | "edit" | "split";

const MODE_KEY = "bgsim.docs.mode";

function storedMode(): DocsMode {
  try {
    const value = localStorage.getItem(MODE_KEY);
    return value === "edit" || value === "split" || value === "view" ? value : "view";
  } catch {
    return "view";
  }
}

export interface DocsState {
  project: string | null;
  model: string | null;
  status: "idle" | "loading" | "ready" | "error";
  error: string | null;
  docs: Docs;
  selected: string | null;
  mode: DocsMode;
  /** Page texts as stored. */
  saved: Record<string, string>;
  /** Unsaved edits; a page is dirty when its draft differs from `saved`. */
  drafts: Record<string, string>;
  saving: boolean;
  /** The last failure of a save or tree edit. */
  problem: string | null;
  /** Asset names that exist in the model's docs folder. */
  assets: ReadonlySet<string>;
  unusedImages: number;

  load: (project: string, model: string) => Promise<void>;
  select: (id: string | null) => Promise<void>;
  setMode: (mode: DocsMode) => void;
  setDraft: (id: string, text: string) => void;
  save: (id: string) => Promise<boolean>;
  saveAll: () => Promise<boolean>;
  createFirstPage: () => Promise<void>;
  newSibling: (afterId: string | null) => Promise<void>;
  newChild: (parentId: string) => Promise<void>;
  rename: (id: string, title: string) => Promise<void>;
  remove: (id: string, mode: DeleteMode | null) => Promise<void>;
  move: (id: string, targetId: string, position: DropPosition) => Promise<void>;
  moveByKey: (id: string, key: string) => Promise<boolean>;
  noteAsset: (name: string) => void;
  refreshAssets: () => Promise<void>;
  cleanUpImages: () => Promise<string[]>;
  setProblem: (message: string | null) => void;
}

const INITIAL = {
  project: null,
  model: null,
  status: "idle" as const,
  error: null,
  docs: EMPTY_DOCS,
  selected: null,
  saved: {},
  drafts: {},
  saving: false,
  problem: null,
  assets: new Set<string>() as ReadonlySet<string>,
  unusedImages: 0,
};

let loadToken = 0;

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/** Ids of the pages with unsaved edits. */
export function dirtyPageIds(state: Pick<DocsState, "saved" | "drafts">): string[] {
  return Object.keys(state.drafts).filter((id) => state.drafts[id] !== state.saved[id]);
}

export const useDocsStore = create<DocsState>()((set, get) => {
  /** The open model, or a thrown message when no model is open. */
  const target = (): { project: string; model: string } => {
    const { project, model } = get();
    if (project === null || model === null) {
      throw new Error("Open a model before editing its docs.");
    }
    return { project, model };
  };

  const commitTree = async (next: Docs, selected?: string | null): Promise<boolean> => {
    const previous = get().docs;
    const { project, model } = target();
    set({ docs: next, ...(selected === undefined ? {} : { selected }), problem: null });
    try {
      await saveManifest(project, model, next);
      return true;
    } catch (error) {
      set({ docs: previous, problem: message(error) });
      return false;
    }
  };

  const loadPage = async (id: string): Promise<void> => {
    const { project, model, saved } = get();
    if (project === null || model === null || saved[id] !== undefined) {
      return;
    }
    try {
      const text = await fetchPage(project, model, id);
      if (get().project === project && get().model === model) {
        set((state) => ({ saved: { ...state.saved, [id]: text } }));
      }
    } catch (error) {
      set({ problem: message(error) });
    }
  };

  return {
    ...INITIAL,
    mode: storedMode(),

    load: async (project, model) => {
      const state = get();
      if (state.project === project && state.model === model && state.status !== "error") {
        return;
      }
      if (dirtyPageIds(state).length > 0) {
        await get().saveAll();
      }
      loadToken += 1;
      const token = loadToken;
      set({ ...INITIAL, project, model, status: "loading" });
      try {
        const [docs, listing] = await Promise.all([
          fetchManifest(project, model),
          listAssets(project, model).catch(() => ({ assets: [], unused: 0 })),
        ]);
        if (token !== loadToken) {
          return;
        }
        set({
          docs,
          status: "ready",
          assets: new Set(listing.assets.map((asset) => asset.file)),
          unusedImages: listing.unused,
        });
        const first = firstPageId(docs);
        if (first !== null) {
          await get().select(first);
        }
      } catch (error) {
        if (token === loadToken) {
          set({ status: "error", error: message(error) });
        }
      }
    },

    select: async (id) => {
      set({ selected: id });
      if (id !== null) {
        await loadPage(id);
      }
    },

    setMode: (mode) => {
      set({ mode });
      try {
        localStorage.setItem(MODE_KEY, mode);
      } catch {
        // The mode is only a convenience; ignore blocked storage.
      }
    },

    setDraft: (id, text) => {
      set((state) => ({ drafts: { ...state.drafts, [id]: text } }));
    },

    save: async (id) => {
      const state = get();
      const text = state.drafts[id];
      if (text === undefined || text === state.saved[id]) {
        return true;
      }
      const { project, model } = target();
      set({ saving: true, problem: null });
      try {
        await savePage(project, model, id, text);
      } catch (error) {
        set({ saving: false, problem: message(error) });
        return false;
      }
      set((current) => {
        const drafts = { ...current.drafts };
        // Keep a newer draft typed while the request was in flight.
        if (drafts[id] === text) {
          delete drafts[id];
        }
        return { saved: { ...current.saved, [id]: text }, drafts, saving: false };
      });
      // The page may have gained or lost image references.
      void get().refreshAssets();
      return true;
    },

    saveAll: async () => {
      let ok = true;
      for (const id of dirtyPageIds(get())) {
        ok = (await get().save(id)) && ok;
      }
      return ok;
    },

    createFirstPage: async () => {
      const added = addSibling(get().docs, null, "Overview");
      if (added !== null && (await commitTree(added.docs, added.id))) {
        await loadPage(added.id);
      }
    },

    newSibling: async (afterId) => {
      const added = addSibling(get().docs, afterId);
      if (added !== null && (await commitTree(added.docs, added.id))) {
        await loadPage(added.id);
      }
    },

    newChild: async (parentId) => {
      const added = addChild(get().docs, parentId);
      if (added !== null && (await commitTree(added.docs, added.id))) {
        await loadPage(added.id);
      }
    },

    rename: async (id, title) => {
      const next = renamePage(get().docs, id, title);
      if (next !== null) {
        await commitTree(next);
      }
    },

    remove: async (id, mode) => {
      const { project, model, docs } = get();
      if (project === null || model === null) {
        return;
      }
      const page = findPage(docs.pages, id);
      if (page === null) {
        return;
      }
      try {
        const pages = await deletePage(
          project,
          model,
          id,
          page.children.length === 0 ? null : (mode === "promote" ? "promote" : "delete"),
        );
        const next: Docs = { ...docs, pages };
        set((state) => {
          const saved = { ...state.saved };
          const drafts = { ...state.drafts };
          const alive = new Set<string>();
          const collect = (list: Docs["pages"]): void => {
            for (const entry of list) {
              alive.add(entry.id);
              collect(entry.children);
            }
          };
          collect(pages);
          for (const key of Object.keys(saved)) {
            if (!alive.has(key)) {
              delete saved[key];
            }
          }
          for (const key of Object.keys(drafts)) {
            if (!alive.has(key)) {
              delete drafts[key];
            }
          }
          const selected =
            state.selected !== null && alive.has(state.selected) ? state.selected : firstPageId(next);
          return { docs: next, saved, drafts, selected, problem: null };
        });
        const selected = get().selected;
        if (selected !== null) {
          await loadPage(selected);
        }
        await get().refreshAssets();
      } catch (error) {
        set({ problem: message(error) });
      }
    },

    move: async (id, targetId, position) => {
      const next = dropPage(get().docs, id, targetId, position);
      if (next !== null) {
        await commitTree(next);
      }
    },

    moveByKey: async (id, key) => {
      const next = keyboardMove(get().docs, id, key);
      if (next === null) {
        return false;
      }
      return commitTree(next);
    },

    noteAsset: (name) => {
      set((state) => ({ assets: new Set(state.assets).add(name) }));
    },

    refreshAssets: async () => {
      const { project, model } = get();
      if (project === null || model === null) {
        return;
      }
      try {
        const listing = await listAssets(project, model);
        if (get().project === project && get().model === model) {
          set({
            assets: new Set(listing.assets.map((asset) => asset.file)),
            unusedImages: listing.unused,
          });
        }
      } catch (error) {
        set({ problem: message(error) });
      }
    },

    cleanUpImages: async () => {
      const { project, model } = get();
      if (project === null || model === null) {
        return [];
      }
      // References are read from the saved pages, so save the edits first.
      if (!(await get().saveAll())) {
        return [];
      }
      try {
        const deleted = await deleteUnusedAssets(project, model);
        await get().refreshAssets();
        return deleted;
      } catch (error) {
        set({ problem: message(error) });
        return [];
      }
    },

    setProblem: (problem) => set({ problem }),
  };
});

registerLeaveGuard({
  hasUnsaved: () => dirtyPageIds(useDocsStore.getState()).length > 0,
  saveAll: () => useDocsStore.getState().saveAll(),
});

/** Reset to the empty state (tests). */
export function resetDocsStore(): void {
  loadToken += 1;
  useDocsStore.setState({ ...INITIAL, mode: "view" });
}
