/**
 * The live interface of every inline code node (plan 7.7).
 *
 * An inline node's ports are not in the catalog: they come from `block.check`
 * as the user types. The editor publishes each answer here, and the canvas
 * reads it through `interfaceForNode`, so a port that appears in the source
 * appears on the node without a document reload.
 *
 * Kept outside the document deliberately: the port list is a derived fact,
 * not something the model file stores. A failed check keeps the last good
 * interface, so a transient syntax error does not make every connected bond
 * vanish while the user is halfway through a line.
 */

import { create } from "zustand";

import type { NodeInterface } from "../editor/nodeInterface";

export interface InlineInterfaceEntry {
  /** The source this answer belongs to (so an unchanged source is not rechecked). */
  source: string;
  /** The last good interface, or null before the first successful check. */
  iface: NodeInterface | null;
}

interface InlineInterfaceState {
  byNode: Record<string, InlineInterfaceEntry>;
  revision: number;
  publish: (nodeId: string, source: string, iface: NodeInterface | null) => void;
  remove: (nodeId: string) => void;
  clear: () => void;
}

export const useInlineInterfaceStore = create<InlineInterfaceState>()((set) => ({
  byNode: {},
  revision: 0,

  publish: (nodeId, source, iface) =>
    set((state) => {
      const previous = state.byNode[nodeId];
      const nextIface = iface ?? previous?.iface ?? null;
      if (previous !== undefined && previous.source === source && previous.iface === nextIface) {
        return state;
      }
      return {
        byNode: { ...state.byNode, [nodeId]: { source, iface: nextIface } },
        revision: state.revision + 1,
      };
    }),

  remove: (nodeId) =>
    set((state) => {
      if (state.byNode[nodeId] === undefined) {
        return state;
      }
      const byNode = { ...state.byNode };
      delete byNode[nodeId];
      return { byNode, revision: state.revision + 1 };
    }),

  clear: () => set({ byNode: {}, revision: 0 }),
}));

/** The interface the canvas draws for an inline node, or null if not checked. */
export function inlineInterfaceFor(nodeId: string): NodeInterface | null {
  return useInlineInterfaceStore.getState().byNode[nodeId]?.iface ?? null;
}

/** True once a `block.check` has produced at least one usable interface. */
export function hasInlineInterface(nodeId: string): boolean {
  return inlineInterfaceFor(nodeId) !== null;
}

/** The source the stored answer was computed from, or null. */
export function inlineInterfaceSource(nodeId: string): string | null {
  return useInlineInterfaceStore.getState().byNode[nodeId]?.source ?? null;
}

/** Publish one `block.check` answer (`iface` null means "the source has errors"). */
export function publishInlineInterface(
  nodeId: string,
  source: string,
  iface: NodeInterface | null,
): void {
  useInlineInterfaceStore.getState().publish(nodeId, source, iface);
}

/** Drop interfaces for inline nodes that no longer exist. */
export function pruneInlineInterfaces(liveNodeIds: ReadonlySet<string>): void {
  const state = useInlineInterfaceStore.getState();
  for (const nodeId of Object.keys(state.byNode)) {
    if (!liveNodeIds.has(nodeId)) {
      state.remove(nodeId);
    }
  }
}

/** Test hook: forget every published interface. */
export function resetInlineInterfaces(): void {
  useInlineInterfaceStore.getState().clear();
}
