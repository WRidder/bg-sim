/**
 * Splitter sizes (plan 7.2: "All splitters are resizable, and the layout
 * persists in localStorage (wrapped in try/catch)").
 *
 * A layout is a map of panel id to a percentage of the parent group, which is
 * exactly what `react-resizable-panels` accepts as `defaultLayout` and hands
 * back from `onLayoutChanged`.
 */

import { useCallback, useState } from "react";

export type PanelSizes = Record<string, number>;

const LAYOUT_KEY_PREFIX = "bgsim.layout.";

type ReadStorage = Pick<Storage, "getItem">;
type WriteStorage = Pick<Storage, "setItem">;

function layoutKey(key: string): string {
  return `${LAYOUT_KEY_PREFIX}${key}`;
}

function isSizes(value: unknown): value is PanelSizes {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return false;
  }
  const entries = Object.entries(value);
  return (
    entries.length > 0 &&
    entries.every(([id, size]) => id.length > 0 && typeof size === "number" && Number.isFinite(size) && size > 0)
  );
}

/**
 * Reads a stored layout. Returns null when there is nothing stored, when the
 * value is not a layout, or when storage is unavailable.
 */
export function readPanelSizes(key: string, storage?: ReadStorage): PanelSizes | null {
  try {
    const raw = (storage ?? localStorage).getItem(layoutKey(key));
    if (raw === null) {
      return null;
    }
    const parsed: unknown = JSON.parse(raw);
    return isSizes(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

/** Stores a layout; a storage failure is ignored (the default layout returns). */
export function writePanelSizes(key: string, sizes: PanelSizes, storage?: WriteStorage): void {
  try {
    (storage ?? localStorage).setItem(layoutKey(key), JSON.stringify(sizes));
  } catch {
    /* the layout simply will not be remembered */
  }
}

export interface PersistedLayout {
  /** Pass to `Group` as `defaultLayout`. */
  defaultLayout: PanelSizes;
  /** Pass to `Group` as `onLayoutChanged`. */
  onLayoutChanged: (sizes: PanelSizes) => void;
}

/**
 * A group layout that survives a reload. The stored sizes are read once, when
 * the group mounts, so a drag never fights with a re-read.
 */
export function usePersistedPanelSizes(key: string, fallback: PanelSizes): PersistedLayout {
  const [defaultLayout] = useState<PanelSizes>(() => readPanelSizes(key) ?? fallback);
  const onLayoutChanged = useCallback((sizes: PanelSizes) => writePanelSizes(key, sizes), [key]);
  return { defaultLayout, onLayoutChanged };
}
