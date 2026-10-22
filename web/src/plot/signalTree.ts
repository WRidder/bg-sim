/**
 * The signal-tree model behind the Signals tab (plan 7.5: "a tree by instance
 * path, with search"). Pure functions keep the grouping and the search
 * testable without rendering the browser.
 */

import type { RunSignal } from "../contracts/run-manifest";

/** One path segment; `signals` belong to exactly this path. */
export interface SignalPathNode {
  /** Stable key; the full instance path ("" for the model root). */
  key: string;
  /** The last path segment, shown in the tree. */
  segment: string;
  /** The full instance path. */
  path: string;
  children: SignalPathNode[];
  signals: RunSignal[];
}

/**
 * Build the tree, creating intermediate nodes when a signal's path has a
 * segment that owns no signal itself (subsystem paths). Children and signals
 * are sorted by name so the tree is stable across runs.
 */
export function buildSignalTree(
  signals: readonly RunSignal[],
): SignalPathNode[] {
  const roots: SignalPathNode[] = [];
  const nodes = new Map<string, SignalPathNode>();

  const ensure = (path: string): SignalPathNode => {
    const existing = nodes.get(path);
    if (existing !== undefined) {
      return existing;
    }
    const segments = path.split("/").filter((segment) => segment.length > 0);
    const segment = segments[segments.length - 1] ?? "(model)";
    const parentPath = segments.slice(0, -1).join("/");
    const node: SignalPathNode = {
      key: path,
      segment,
      path,
      children: [],
      signals: [],
    };
    nodes.set(path, node);
    if (parentPath.length === 0) {
      roots.push(node);
    } else {
      ensure(parentPath).children.push(node);
    }
    return node;
  };

  for (const signal of signals) {
    ensure(signal.path.trim()).signals.push(signal);
  }

  const sortNode = (node: SignalPathNode): void => {
    node.children.sort((a, b) => a.segment.localeCompare(b.segment));
    node.signals.sort((a, b) => a.id.localeCompare(b.id));
    for (const child of node.children) {
      sortNode(child);
    }
  };
  roots.sort((a, b) => a.segment.localeCompare(b.segment));
  for (const root of roots) {
    sortNode(root);
  }
  return roots;
}

/** The number of signals at or below a node. */
export function countNodeSignals(node: SignalPathNode): number {
  return (
    node.signals.length +
    node.children.reduce((total, child) => total + countNodeSignals(child), 0)
  );
}

/**
 * Filter by signal id, path, unit or kind. The match is case-insensitive and
 * the query is split on whitespace, so "motor rad/s" finds the speed signals
 * of the motor.
 */
export function filterSignals(
  signals: readonly RunSignal[],
  query: string,
): RunSignal[] {
  const terms = query
    .trim()
    .toLowerCase()
    .split(/\s+/)
    .filter((term) => term.length > 0);
  if (terms.length === 0) {
    return [...signals];
  }
  return signals.filter((signal) => {
    const haystack = [
      signal.id,
      signal.path,
      signal.unit ?? "",
      signal.kind,
      signal.type,
    ]
      .join(" ")
      .toLowerCase();
    return terms.every((term) => haystack.includes(term));
  });
}

/** The leaf label of a signal inside its path node. */
export function signalLeafName(signal: RunSignal): string {
  const prefix = signal.path.trim();
  if (prefix.length > 0 && signal.id.startsWith(`${prefix}/`)) {
    return signal.id.slice(prefix.length + 1);
  }
  return signal.id;
}
