import { create } from "zustand";

/** Ephemeral selection of one probe lead; the document owns the lead itself. */
interface ProbeUiState {
  activeLinkId: string | null;
  setActiveLink: (id: string | null) => void;
}

export const useProbeUi = create<ProbeUiState>()((set) => ({
  activeLinkId: null,
  setActiveLink: (activeLinkId) => set({ activeLinkId }),
}));
