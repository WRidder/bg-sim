import { create } from "zustand";

export interface HelpState {
  /** The block (or junction) ref whose help is open, or null. */
  blockRef: string | null;
  shortcutsOpen: boolean;
  /** The user manual (help icon in the top bar, F1 without a selected block). */
  manualOpen: boolean;
  openBlockHelp: (ref: string) => void;
  closeBlockHelp: () => void;
  setShortcutsOpen: (open: boolean) => void;
  setManualOpen: (open: boolean) => void;
}

/** Which help surface is open: the block help dialog, the shortcuts overlay or the user manual. */
export const useHelpStore = create<HelpState>()((set) => ({
  blockRef: null,
  shortcutsOpen: false,
  manualOpen: false,
  openBlockHelp: (ref) => set({ blockRef: ref, shortcutsOpen: false, manualOpen: false }),
  closeBlockHelp: () => set({ blockRef: null }),
  setShortcutsOpen: (open) =>
    set(open ? { shortcutsOpen: true, blockRef: null, manualOpen: false } : { shortcutsOpen: false }),
  setManualOpen: (open) =>
    set(open ? { manualOpen: true, blockRef: null, shortcutsOpen: false } : { manualOpen: false }),
}));

export function resetHelpStore(): void {
  useHelpStore.setState({ blockRef: null, shortcutsOpen: false, manualOpen: false });
}
