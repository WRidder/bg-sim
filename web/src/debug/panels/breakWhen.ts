/**
 * Watch breakpoint expressions for the "Break when..." dialog (plan 7.9, D22).
 *
 * Pure helpers: the comparison table, the expression the dialog writes, the
 * signal ids an expression mentions, the `s"` completion and the watch slot
 * count. The Debug panel, the dialog and the tests share them.
 */

import type { Breakpoint, WatchBreakpoint } from "../../contracts/debug";

/** The server's watch pool (plan 5.13). */
export const MAX_WATCH_SLOTS = 16;

export type Comparison = ">" | "<" | ">=" | "<=";

export interface ComparisonOption {
  value: Comparison;
  /** What the select shows. */
  label: string;
  /** Spoken name. */
  name: string;
}

export const COMPARISONS: readonly ComparisonOption[] = [
  { value: ">", label: ">", name: "is greater than" },
  { value: "<", label: "<", name: "is less than" },
  { value: ">=", label: "≥", name: "is at least" },
  { value: "<=", label: "≤", name: "is at most" },
];

/** A number as the user typed it, or null when it is not a finite number. */
export function parseWatchValue(text: string): number | null {
  const trimmed = text.trim();
  if (trimmed.length === 0 || !/^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/.test(trimmed)) {
    return null;
  }
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : null;
}

/** `s"Motor1/i" > 5`: the expression of a simple watch. */
export function watchExpression(signalId: string, comparison: Comparison, value: string): string {
  return `s"${signalId}" ${comparison} ${value.trim()}`;
}

/** Every `s"id"` an expression mentions, in order, without repeats. */
export function signalIdsOfExpression(expr: string): string[] {
  const ids: string[] = [];
  for (const match of expr.matchAll(/s"([^"]*)"/g)) {
    const id = match[1];
    if (id !== undefined && id.length > 0 && !ids.includes(id)) {
      ids.push(id);
    }
  }
  return ids;
}

export interface Completion {
  /** Index in the text where the id being typed starts (just after `s"`). */
  from: number;
  /** The signal ids that match what is typed so far. */
  options: string[];
}

/**
 * Signal-id completion: `s"` followed by a prefix opens the list of matching
 * ids. Null when the caret is not inside an `s"..."` literal.
 */
export function completionFor(
  text: string,
  caret: number,
  ids: readonly string[],
  limit = 8,
): Completion | null {
  const before = text.slice(0, caret);
  const open = before.lastIndexOf('s"');
  if (open < 0) {
    return null;
  }
  const typed = before.slice(open + 2);
  if (typed.includes('"')) {
    return null;
  }
  // `s"` must start a token: not the tail of another word such as `ts"`.
  const previous = open > 0 ? before.charAt(open - 1) : "";
  if (/[A-Za-z0-9_]/.test(previous)) {
    return null;
  }
  const needle = typed.toLowerCase();
  const starts = ids.filter((id) => id.toLowerCase().startsWith(needle));
  const contains = ids.filter(
    (id) => !id.toLowerCase().startsWith(needle) && id.toLowerCase().includes(needle),
  );
  const options = [...starts, ...contains].slice(0, limit);
  return options.length === 0 ? null : { from: open + 2, options };
}

/** Insert the chosen id and close the literal; returns the new text and caret. */
export function applyCompletion(
  text: string,
  caret: number,
  completion: Completion,
  id: string,
): { text: string; caret: number } {
  const tail = text.slice(caret);
  const closing = tail.startsWith('"') ? 1 : 0;
  const head = text.slice(0, completion.from);
  const next = `${head}${id}"${tail.slice(closing)}`;
  return { text: next, caret: head.length + id.length + 1 };
}

export function watchBreakpoints(breakpoints: readonly Breakpoint[]): WatchBreakpoint[] {
  return breakpoints.filter((entry): entry is WatchBreakpoint => entry.kind === "watch");
}

/** The slots in use: the server counts every watch breakpoint, enabled or not. */
export function watchSlotsUsed(breakpoints: readonly Breakpoint[]): number {
  return watchBreakpoints(breakpoints).length;
}

export function watchSlotsText(breakpoints: readonly Breakpoint[]): string {
  return `${watchSlotsUsed(breakpoints)} / ${MAX_WATCH_SLOTS} watch slots`;
}
