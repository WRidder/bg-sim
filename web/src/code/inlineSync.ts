/**
 * Keep every inline node's canvas interface in step with its source while the
 * Diagram tab is open (plan 7.7). The Code tab has its own linter doing the
 * same job for the node being edited; this hook covers the model as a whole,
 * including a model opened with inline nodes that were checked in an earlier
 * session (the interfaces are derived, not saved).
 */

import { useEffect, useMemo } from "react";

import { interfaceFromBlockCheck } from "../editor/nodeInterface";
import { useDocumentStore } from "../state/documentStore";
import { checkBlockSource } from "./blockCheck";
import {
  pruneInlineInterfaces,
  publishInlineInterface,
  useInlineInterfaceStore,
} from "./inlineInterfaces";
import { blockNameOf } from "./templates";

/** The plan's 300 ms block-check delay, shared with the linter. */
export const INLINE_CHECK_DELAY_MS = 300;

export function useInlineInterfaceSync(): void {
  const doc = useDocumentStore((state) => state.doc);

  const signature = useMemo(() => {
    if (doc === null) {
      return "";
    }
    return doc.diagram.nodes
      .filter((node) => "inline" in node.block)
      .map((node) => {
        const source = "inline" in node.block ? node.block.inline.source : "";
        return `${node.id}\u0000${node.name}\u0000${source}`;
      })
      .join("\u0001");
  }, [doc]);

  useEffect(() => {
    const current = useDocumentStore.getState().doc;
    if (current === null) {
      pruneInlineInterfaces(new Set());
      return;
    }
    const nodes = current.diagram.nodes.filter((node) => "inline" in node.block);
    pruneInlineInterfaces(new Set(nodes.map((node) => node.id)));

    const store = useInlineInterfaceStore.getState();
    const stale = nodes.filter((node) => {
      if (!("inline" in node.block)) {
        return false;
      }
      const entry = store.byNode[node.id];
      return entry === undefined || entry.source !== node.block.inline.source;
    });
    if (stale.length === 0) {
      return;
    }

    const abort = new AbortController();
    const timer = setTimeout(() => {
      for (const node of stale) {
        if (!("inline" in node.block)) {
          continue;
        }
        const source = node.block.inline.source;
        void checkBlockSource(source, `inline:${node.id}`, { signal: abort.signal }).then(
          (result) => {
            if (abort.signal.aborted) {
              return;
            }
            const iface =
              result.interface === null || result.interface === undefined
                ? null
                : interfaceFromBlockCheck(result.interface, blockNameOf(source) ?? node.name);
            publishInlineInterface(node.id, source, iface);
          },
          () => {
            // A failed check leaves the last good ports in place; the Code tab
            // shows the request error when the user opens the block.
          },
        );
      }
    }, INLINE_CHECK_DELAY_MS);

    return () => {
      clearTimeout(timer);
      abort.abort();
    };
  }, [signature]);
}
