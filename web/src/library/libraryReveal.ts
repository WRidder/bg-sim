/**
 * Show a block in the library browser after it was added to the project
 * library ("Save to project library", "+ Library block"): the browser expands
 * the block's category (categories start collapsed), un-hides it, clears a
 * search that would filter it out, scrolls to the entry and highlights it
 * briefly. The request waits until the refreshed catalog lists the block.
 */

import { create } from "zustand";

/** How long the new entry stays highlighted. */
export const REVEAL_HIGHLIGHT_MS = 4000;

interface LibraryRevealState {
  /** The catalog ref to show, until the library browser has shown it. */
  pending: string | null;
  reveal: (ref: string) => void;
  consume: () => void;
}

export const useLibraryReveal = create<LibraryRevealState>()((set) => ({
  pending: null,
  reveal: (ref) => set({ pending: ref }),
  consume: () => set({ pending: null }),
}));

/** Ask the library browser to show `ref` (a `project:<Name>` block). */
export function revealLibraryBlock(ref: string): void {
  useLibraryReveal.getState().reveal(ref);
}
