/**
 * Whether the assistant panel is open, and how wide. Kept apart from the chat's store: the top
 * bar needs this much on every page, the chat code loads only when the panel first opens.
 */

import { create } from "zustand";

const OPEN_KEY = "bgsim.assistant.open";
const WIDTH_KEY = "bgsim.assistant.width";

export const MIN_PANEL_WIDTH = 320;
export const MAX_PANEL_WIDTH = 900;
const DEFAULT_PANEL_WIDTH = 420;

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // a browser without storage only forgets the panel between visits
  }
}

export function clampPanelWidth(width: number): number {
  return Math.min(MAX_PANEL_WIDTH, Math.max(MIN_PANEL_WIDTH, Math.round(width)));
}

function initialWidth(): number {
  const stored = Number(read(WIDTH_KEY));
  return Number.isFinite(stored) && stored > 0 ? clampPanelWidth(stored) : DEFAULT_PANEL_WIDTH;
}

export interface AssistantPanelState {
  open: boolean;
  width: number;
  toggle: () => void;
  setOpen: (open: boolean) => void;
  setWidth: (width: number) => void;
}

export const useAssistantPanelStore = create<AssistantPanelState>()((set, get) => ({
  open: read(OPEN_KEY) === "1",
  width: initialWidth(),
  toggle: () => get().setOpen(!get().open),
  setOpen: (open) => {
    write(OPEN_KEY, open ? "1" : "0");
    set({ open });
  },
  setWidth: (width) => {
    const next = clampPanelWidth(width);
    write(WIDTH_KEY, String(next));
    set({ width: next });
  },
}));
