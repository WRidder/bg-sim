/**
 * The open request of the "Break when..." dialog (plan 7.9). The signal browser,
 * the canvas menus and the tests call `openBreakWhen`; `BreakWhenDialog` shows it.
 */

import { create } from "zustand";

export interface BreakWhenRequest {
  /** The signals the dialog offers, most likely first. */
  candidates: readonly string[];
  /** The preselected signal. */
  signalId: string;
}

interface BreakWhenState {
  request: BreakWhenRequest | null;
  open: (request: BreakWhenRequest) => void;
  close: () => void;
}

export const useBreakWhenStore = create<BreakWhenState>()((set) => ({
  request: null,
  open: (request) => set({ request }),
  close: () => set({ request: null }),
}));

/** Open the dialog for a signal; `candidates` defaults to the signal alone. */
export function openBreakWhen(signalId: string, candidates: readonly string[] = [signalId]): void {
  const list = candidates.includes(signalId) ? candidates : [signalId, ...candidates];
  useBreakWhenStore.getState().open({ candidates: list, signalId });
}
