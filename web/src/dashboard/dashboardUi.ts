/**
 * View state of the Dashboard tab that is not part of the model: edit mode (Home Assistant
 * style: arrange and configure cards) versus use mode, and the card whose settings are open.
 */

import { create } from "zustand";

export interface DashboardUiState {
  editMode: boolean;
  /** The card whose settings popover is open. */
  settingsCardId: string | null;
  setEditMode: (on: boolean) => void;
  openSettings: (cardId: string | null) => void;
}

export const useDashboardUi = create<DashboardUiState>()((set) => ({
  editMode: false,
  settingsCardId: null,
  setEditMode: (on) => set({ editMode: on, settingsCardId: null }),
  openSettings: (cardId) => set({ settingsCardId: cardId }),
}));

export function resetDashboardUi(): void {
  useDashboardUi.setState({ editMode: false, settingsCardId: null });
}
