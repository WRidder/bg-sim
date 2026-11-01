/**
 * The deformation exaggeration of the 3D View: a display factor on every deformation, beams and mode shapes (×1 is the
 * true scale). It is view state, not model data, so it never changes the model document (nor its hash
 * or the compile cache): like the breakpoints it is kept per model in `localStorage`, and the docked and
 * the detached view share it through this store. Every storage access is guarded; without storage the
 * factor simply does not survive a reload.
 *
 * A model may name a starting factor (`scene.exaggeration`, e.g. ×10 for a shaft whose twist is a few
 * mrad): the view opens with it while this browser has no stored choice for the model. A choice the user
 * makes is stored and wins; choosing the model's own default again clears the stored entry, so the model
 * keeps the say.
 */

import { create } from "zustand";

import { useDocumentStore } from "../state/documentStore";

/** The factors the view offers. */
export const EXAGGERATION_STEPS: readonly number[] = [1, 10, 100, 1000];

const STORAGE_PREFIX = "bgsim.viewer.exaggeration.";

/** `project/model` of the open model, or null. */
function modelKeyOf(project: string | null, modelName: string | null): string | null {
  return project !== null && modelName !== null ? `${project}/${modelName}` : null;
}

function isStep(value: unknown): value is number {
  return typeof value === "number" && EXAGGERATION_STEPS.includes(value);
}

/** The model's starting factor (`scene.exaggeration`) as a step; 1 when it names none or no step. */
export function modelDefaultExaggeration(value: unknown): number {
  return isStep(value) ? value : 1;
}

/** The stored factor of a model; `fallback` (the model's default, else 1) when nothing usable is stored. */
export function readExaggeration(modelKey: string, storage?: Pick<Storage, "getItem">, fallback = 1): number {
  try {
    const raw = (storage ?? localStorage).getItem(`${STORAGE_PREFIX}${modelKey}`);
    const value: unknown = raw === null ? null : JSON.parse(raw);
    return isStep(value) ? value : fallback;
  } catch {
    return fallback;
  }
}

function writeExaggeration(modelKey: string, factor: number, fallback: number): void {
  try {
    if (factor === fallback) localStorage.removeItem(`${STORAGE_PREFIX}${modelKey}`);
    else localStorage.setItem(`${STORAGE_PREFIX}${modelKey}`, JSON.stringify(factor));
  } catch {
    /* the factor simply will not be remembered */
  }
}

interface ExaggerationState {
  /** Factor per model key, read lazily. */
  readonly byModel: Readonly<Record<string, number>>;
  /** `fallback`: the model's own default factor (a choice equal to it is not stored). */
  set(modelKey: string, factor: number, fallback?: number): void;
}

export const useExaggerationStore = create<ExaggerationState>((set) => ({
  byModel: {},
  set: (modelKey, factor, fallback = 1) => {
    if (!isStep(factor)) return;
    writeExaggeration(modelKey, factor, fallback);
    set((s) => ({ byModel: { ...s.byModel, [modelKey]: factor } }));
  },
}));

/**
 * The exaggeration of the open model and its setter (a no-op without an open model): the choice made in
 * this browser, else the model's `scene.exaggeration`, else 1.
 */
export function useExaggeration(): readonly [number, (factor: number) => void] {
  const key = useDocumentStore((s) => modelKeyOf(s.project, s.modelName));
  const fallback = useDocumentStore((s) => modelDefaultExaggeration(s.doc?.scene?.exaggeration));
  const stored = useExaggerationStore((s) => (key === null ? undefined : s.byModel[key]));
  const setFor = useExaggerationStore((s) => s.set);
  const factor = stored ?? (key === null ? fallback : readExaggeration(key, undefined, fallback));
  const setFactor = (f: number): void => {
    if (key !== null) setFor(key, f, fallback);
  };
  return [factor, setFactor] as const;
}

/** "×100" */
export function formatFactor(factor: number): string {
  return `×${String(factor)}`;
}
