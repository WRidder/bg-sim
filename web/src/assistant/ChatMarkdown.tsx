/**
 * A chat message as Markdown: the docs renderer with math (KaTeX) and ```mermaid fences. Its
 * links reach what the editor has open: a `signal:` link plots, a `block:` link shows the block.
 */

import { useMemo } from "react";

import { requestPlotsTab, requestCenterTab } from "../app/dockBus";
import { useAssistantLinks } from "./useAssistantLinks";
import { MarkdownView, type LinkActions } from "../docs/MarkdownView";
import { requestCenterNode } from "../editor/canvasFocus";
import { useRunStore } from "../plot/runStore";
import { useDocumentStore } from "../state/documentStore";
import { normalizeChatMath } from "./chatMath";

const ACTIONS: LinkActions = {
  openPage: () => requestCenterTab("docs"),
  showBlock: (target) => {
    if (useDocumentStore.getState().selectNodeAt(target.path, target.nodeId)) {
      requestCenterTab("diagram");
      requestCenterNode(target.nodeId);
    }
  },
  plotSignal: (id) => {
    useRunStore.getState().addSignal(id);
    requestPlotsTab();
  },
  notify: () => undefined,
};

export function ChatMarkdown({ text }: { text: string }) {
  const project = useDocumentStore((state) => state.project) ?? "";
  const modelName = useDocumentStore((state) => state.modelName);
  const links = useAssistantLinks();
  const source = useMemo(() => normalizeChatMath(text), [text]);
  return (
    <div className="assistant-markdown docs-preview">
      <MarkdownView text={source} project={project} model={modelName} links={links} actions={ACTIONS} variant="chat" />
    </div>
  );
}
