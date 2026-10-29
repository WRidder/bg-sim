import { create } from "zustand";

export interface HelpState {
  /** The block (or junction) ref whose help is open, or null. */
  blockRef: string | null;
  shortcutsOpen: boolean;
  openBlockHelp: (ref: string) => void;
  closeBlockHelp: () => void;
  setShortcutsOpen: (open: boolean) => void;
}

/** Which help surface is open: the block help dialog or the shortcuts overlay. */
export const useHelpStore = create<HelpState>()((set) => ({
  blockRef: null,
  shortcutsOpen: false,
  openBlockHelp: (ref) => set({ blockRef: ref, shortcutsOpen: false }),
  closeBlockHelp: () => set({ blockRef: null }),
  setShortcutsOpen: (open) =>
    set(open ? { shortcutsOpen: true, blockRef: null } : { shortcutsOpen: false }),
}));

export function resetHelpStore(): void {
  useHelpStore.setState({ blockRef: null, shortcutsOpen: false });
}
