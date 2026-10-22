/**
 * Edits to the simulation settings in the top bar (plan 7.2).
 *
 * The controls belong to the model document, so a change must go through the
 * document store: the auto-save hook then writes it and the next run sends it
 * to the backend. W1.1's store does not expose a settings command, and this
 * work package does not own that file, so the update is a direct immutable
 * `setState` with a bumped revision. That keeps saving and running correct;
 * the one limitation is that a settings change is not an undo step. It is
 * recorded in the work-package report.
 */

import type { ModelSettings } from "../contracts/model";
import { useDocumentStore } from "../state/documentStore";

/** Parse a finite number from the compact inputs (`1`, `1e-6`, `0.5`). */
export function parseFiniteNumber(text: string): number | null {
  const trimmed = text.trim();
  if (trimmed.length === 0) {
    return null;
  }
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : null;
}

/**
 * Apply a partial settings change to the open model. Returns false when no
 * model is open. The revision bump is what makes the existing auto-save pick
 * the change up; `saveState: "dirty"` mirrors every other document edit.
 */
export function updateModelSettings(patch: Partial<ModelSettings>): boolean {
  let applied = false;
  useDocumentStore.setState((state) => {
    const doc = state.doc;
    if (doc === null) {
      return {};
    }
    applied = true;
    return {
      doc: {
        ...doc,
        settings: { ...doc.settings, ...patch },
      },
      revision: state.revision + 1,
      saveState: "dirty",
      saveError: null,
    };
  });
  return applied;
}

/** True when `t_end` is a finite time after `t_start`. */
export function isValidEndTime(value: number, tStart: number): boolean {
  return Number.isFinite(value) && value > tStart;
}

/** True for a positive relative tolerance. */
export function isValidTolerance(value: number): boolean {
  return Number.isFinite(value) && value > 0;
}
