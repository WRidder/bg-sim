/** What a link in a chat message can reach: the open model and the signals of its last run. */

import { useMemo } from "react";

import type { LinkContext } from "../docs/docsLinks";
import { useRunStore } from "../plot/runStore";
import { useDocumentStore } from "../state/documentStore";

const NO_PAGES: ReadonlySet<string> = new Set();

export function useAssistantLinks(): LinkContext {
  const model = useDocumentStore((state) => state.doc);
  const manifest = useRunStore((state) => state.manifest);
  return useMemo(
    () => ({
      pageIds: NO_PAGES,
      model,
      signalIds: manifest === null ? null : new Set(manifest.signals.map((signal) => signal.id)),
    }),
    [model, manifest],
  );
}
