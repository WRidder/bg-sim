/**
 * The Explain popover's state (plan 7.9, 5.13): which signal is explained, the
 * `model.explain` result and its progress. Explain needs no run: it compiles
 * the model document. The signal browser, the canvas menus, the inspector and
 * the tests call `openExplain`; `ExplainPopover` shows it.
 */

import { create } from "zustand";

import type { ExplainResult } from "../../contracts/debug";
import { useDocumentStore } from "../../state/documentStore";
import { postExplain } from "../panels/panelsApi";

export interface ExplainState {
  /** The explained signal, or null when the popover is closed. */
  signalId: string | null;
  status: "idle" | "loading" | "ready" | "error";
  result: ExplainResult | null;
  error: string | null;
  open: (signalId: string) => Promise<void>;
  close: () => void;
}

/** Only the newest request may publish its result. */
let sequence = 0;

export const useExplainStore = create<ExplainState>()((set) => ({
  signalId: null,
  status: "idle",
  result: null,
  error: null,

  open: async (signalId) => {
    sequence += 1;
    const mine = sequence;
    const { project, doc } = useDocumentStore.getState();
    if (doc === null) {
      set({ signalId, status: "error", result: null, error: "Open a model before explaining a signal." });
      return;
    }
    set({ signalId, status: "loading", result: null, error: null });
    try {
      const result = await postExplain(project, doc, signalId);
      if (mine === sequence) {
        set({ status: "ready", result, error: null });
      }
    } catch (error) {
      if (mine === sequence) {
        set({
          status: "error",
          result: null,
          error: error instanceof Error ? error.message : String(error),
        });
      }
    }
  },

  close: () => {
    sequence += 1;
    set({ signalId: null, status: "idle", result: null, error: null });
  },
}));

/** Open the Explain popover for a signal id. */
export function openExplain(signalId: string): void {
  void useExplainStore.getState().open(signalId);
}
