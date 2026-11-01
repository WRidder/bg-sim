/**
 * Modal coordinates of flexible bodies among the model's signals, for the mode-shapes binding: a
 * ModalBody3D block records them as `<Block>/eta[1]` .. `<Block>/eta[n]`, and the binding table fills
 * a binding's signal list from such a block in one step.
 */

import type { SignalUnits } from "./bindingsValidate";

/** A block that records modal coordinates `<Block>/eta[i]`, with how many run from eta[1] without a gap. */
export interface ModalBlock {
  readonly block: string;
  readonly count: number;
}

const ETA = /^(.+)\/eta\[(\d+)\]$/;

/** The blocks among the signals with modal coordinates `<Block>/eta[1..n]`, in first-signal order. */
export function modalBlocks(signals: SignalUnits | null): ModalBlock[] {
  if (signals === null) return [];
  const indices = new Map<string, Set<number>>();
  for (const id of signals.keys()) {
    const m = ETA.exec(id);
    if (m === null) continue;
    const block = m[1] ?? "";
    const set = indices.get(block) ?? new Set<number>();
    set.add(Number(m[2]));
    indices.set(block, set);
  }
  const out: ModalBlock[] = [];
  for (const [block, set] of indices) {
    let count = 0;
    while (set.has(count + 1)) count++;
    if (count > 0) out.push({ block, count });
  }
  return out;
}

/** `<block>/eta[1]` .. `<block>/eta[n]`. */
export function modalSignals(block: string, n: number): string[] {
  return Array.from({ length: n }, (_, k) => `${block}/eta[${String(k + 1)}]`);
}
