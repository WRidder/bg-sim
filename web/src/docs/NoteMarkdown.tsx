/**
 * The rendered text of a sticky note on the canvas: the Docs renderer
 * (`MarkdownView`) in its restricted `note` variant. It is loaded lazily with
 * the rest of the Markdown stack, so the canvas chunk stays small.
 *
 * Links work as on a docs page: `page:<id>` opens the page in the Docs tab,
 * `project:<id>` a page of the project docs, `model:<name>/<id>` a page of
 * another model's docs, `block:<Name>` selects the block, `signal:<id>` plots
 * the signal.
 */

import { memo, useEffect, useMemo } from "react";

import { requestCenterTab, requestPlotsTab } from "../app/dockBus";
import { requestLeaveModel } from "../app/leaveProject";
import { modelDocsUrl } from "../app/route";
import { useRunStore } from "../plot/runStore";
import { useDocumentStore } from "../state/documentStore";
import { requestCenterNode } from "../editor/canvasFocus";
import { modelPagesOf, type LinkContext } from "./docsLinks";
import {
  openModelPage,
  openProjectPage,
  useDocsIndexStore,
  useDocsStore,
  useProjectDocsStore,
} from "./docsStore";
import { MarkdownView, type LinkActions } from "./MarkdownView";
import { allIds } from "./pageTree";

const NOTE_ACTIONS: LinkActions = {
  openPage: (id) => {
    void openModelPage(id);
    requestCenterTab("docs");
  },
  openProjectPage: (id) => {
    void openProjectPage(id);
    requestCenterTab("docs");
  },
  openModelPage: (name, id) => {
    const { project, modelName } = useDocumentStore.getState();
    if (name === modelName) {
      void openModelPage(id);
      requestCenterTab("docs");
    } else if (project !== null) {
      void requestLeaveModel(modelDocsUrl(project, name, id), "model");
    }
  },
  showBlock: (target) => {
    if (useDocumentStore.getState().selectNodeAt(target.path, target.nodeId)) {
      requestCenterNode(target.nodeId);
    }
  },
  plotSignal: (id) => {
    useRunStore.getState().addSignal(id);
    requestPlotsTab();
  },
  notify: () => undefined,
};

export interface NoteMarkdownProps {
  text: string;
}

function NoteMarkdown({ text }: NoteMarkdownProps) {
  const project = useDocumentStore((state) => state.project);
  const modelName = useDocumentStore((state) => state.modelName);
  // Only a note with a block: link follows the document; the others do not
  // re-render (and re-parse) on every edit or drag.
  const linksBlocks = /\]\(\s*block:/i.test(text);
  const doc = useDocumentStore((state) => (linksBlocks ? state.doc : null));
  const pages = useDocsStore((state) => state.docs.pages);
  const docsProject = useDocsStore((state) => state.project);
  const docsModel = useDocsStore((state) => state.model);
  const projectPages = useProjectDocsStore((state) => state.docs.pages);
  const projectDocsProject = useProjectDocsStore((state) => state.project);
  const index = useDocsIndexStore((state) => state.index);
  const manifest = useRunStore((state) => state.manifest);
  const linksPages = /\]\(\s*page:/i.test(text);
  const linksProject = /\]\(\s*project:/i.test(text);
  const linksModels = /\]\(\s*model:/i.test(text);

  // A page: link needs the model's page list; load it once, like the Docs tab does.
  useEffect(() => {
    if (!(linksPages || linksModels) || project === null || modelName === null) {
      return;
    }
    if (docsProject !== project || docsModel !== modelName) {
      void useDocsStore.getState().load(project, modelName);
    }
  }, [linksPages, linksModels, project, modelName, docsProject, docsModel]);

  // Likewise the project docs for project: links and every page tree for model: links.
  useEffect(() => {
    if (project === null) {
      return;
    }
    if (linksProject && projectDocsProject !== project) {
      void useProjectDocsStore.getState().load(project, null);
    }
    if (linksModels) {
      void useDocsIndexStore.getState().load(project);
    }
  }, [linksProject, linksModels, project, projectDocsProject]);

  const links = useMemo<LinkContext>(
    () => ({
      pageIds: allIds(pages),
      model: doc,
      signalIds: manifest === null ? null : new Set(manifest.signals.map((signal) => signal.id)),
      projectPageIds: allIds(projectPages),
      modelPages: modelPagesOf(index?.models ?? [], modelName === null ? {} : { [modelName]: pages }),
    }),
    [pages, doc, manifest, projectPages, index, modelName],
  );

  return (
    <MarkdownView
      text={text}
      project={project ?? ""}
      model={modelName ?? ""}
      links={links}
      actions={NOTE_ACTIONS}
      variant="note"
    />
  );
}

/** Re-renders only when the text changes (or a link target list it uses). */
export default memo(NoteMarkdown);
