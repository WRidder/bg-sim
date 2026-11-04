/**
 * The Docs tab (W5.6): a Markdown wiki for the open model. Left: the page tree, in two sections
 * when the project has project docs: **Project** (collapsible, on top; `<project>/docs/`, shared
 * by every model) and **This model** (`models/<model>.docs/`, travels with the model file).
 * Right: the selected page of either wiki in View, Edit or Split mode.
 */

import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { Group, Panel, Separator } from "react-resizable-panels";

import { EmptyState } from "../app/EmptyState";
import { requestPlotsTab } from "../app/dockBus";
import { requestLeaveModel } from "../app/leaveProject";
import { modelDocsUrl, readScreenTab } from "../app/route";
import { useDialogFocus } from "../app/useDialogFocus";
import { usePersistedPanelSizes } from "../state/layout";
import { useRunStore } from "../plot/runStore";
import { useDocumentStore } from "../state/documentStore";
import { requestCenterNode } from "../editor/canvasFocus";
import { DocsTree } from "./DocsTree";
import { MarkdownEditor } from "./MarkdownEditor";
import { MarkdownView, type LinkActions } from "./MarkdownView";
import {
  dirtyPageIds,
  docsStoreOf,
  openModelPage,
  openProjectPage,
  useDocsIndexStore,
  useDocsStore,
  useDocsViewStore,
  useProjectDocsStore,
  type DocsMode,
} from "./docsStore";
import { isLeaveConfirmed } from "./leaveGuard";
import { allIds, findPage, pathTo } from "./pageTree";
import { modelPagesOf, parseDocsRef, type LinkContext } from "./docsLinks";
import { useSyncedScroll } from "./useSyncedScroll";
import { DOC_MODEL_ATTRIBUTE, DOC_PAGE_ATTRIBUTE } from "../assistant/selectionStore";
import "./docs.css";

export interface DocsTabProps {
  /** Switch the centre area to the Diagram tab (block links). */
  onShowDiagram: () => void;
}

type Wiki = "model" | "project";

const MODES: readonly { id: DocsMode; label: string }[] = [
  { id: "view", label: "View" },
  { id: "edit", label: "Edit" },
  { id: "split", label: "Split" },
];

// The `page=` of the URL (a deep link into the Docs tab) is applied once per page load.
let urlPageApplied = false;

/** Forget that the URL's `page=` was applied (tests). */
export function resetDocsUrlPage(): void {
  urlPageApplied = false;
}

function ConfirmDelete({
  title,
  childCount,
  wiki,
  onChoose,
}: {
  title: string;
  childCount: number;
  wiki: Wiki;
  onChoose: (choice: "subtree" | "promote" | "cancel") => void;
}) {
  const dialog = useRef<HTMLDivElement>(null);
  useDialogFocus(true, dialog, () => onChoose("cancel"));
  return (
    <div className="dialog-backdrop" data-testid="docs-delete-backdrop">
      <div
        className="docs-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="docs-delete-title"
        data-testid="docs-delete-dialog"
        ref={dialog}
        tabIndex={-1}
      >
        <h2 id="docs-delete-title" className="docs-dialog__title">
          Delete “{title}”?
        </h2>
        {childCount > 0 ? (
          <p className="docs-dialog__text">
            This page has {childCount} sub-page{childCount === 1 ? "" : "s"}. Delete them too, or keep
            them and move them up one level.
          </p>
        ) : (
          <p className="docs-dialog__text">
            The page text is removed from {wiki === "project" ? "the project docs" : "the model's docs"}.
          </p>
        )}
        <div className="docs-dialog__actions">
          <button type="button" className="button" onClick={() => onChoose("cancel")}>
            Cancel
          </button>
          {childCount > 0 ? (
            <button type="button" className="button" data-testid="docs-delete-promote" onClick={() => onChoose("promote")}>
              Delete page, keep sub-pages
            </button>
          ) : null}
          <button type="button" className="button button--primary" data-testid="docs-delete-confirm" onClick={() => onChoose("subtree")}>
            {childCount > 0 ? "Delete page and sub-pages" : "Delete"}
          </button>
        </div>
      </div>
    </div>
  );
}

export function DocsTab({ onShowDiagram }: DocsTabProps) {
  const project = useDocumentStore((state) => state.project);
  const modelName = useDocumentStore((state) => state.modelName);
  const model = useDocumentStore((state) => state.doc);
  const manifest = useRunStore((state) => state.manifest);

  const modelDocs = useDocsStore();
  const projectDocs = useProjectDocsStore();
  const wiki = useDocsViewStore((state) => state.wiki);
  const projectOpen = useDocsViewStore((state) => state.projectOpen);
  const index = useDocsIndexStore((state) => state.index);
  const mode = modelDocs.mode;

  const layout = usePersistedPanelSizes("docs", { tree: 26, page: 74 });
  const [notice, setNotice] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<{ wiki: Wiki; id: string } | null>(null);
  const pageArea = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (project !== null && modelName !== null) {
      void useDocsStore.getState().load(project, modelName);
      void useProjectDocsStore.getState().load(project, null);
      void useDocsIndexStore.getState().load(project);
    }
  }, [project, modelName]);

  const hasProjectDocs = projectDocs.docs.pages.length > 0;
  // The Project section exists once the project has docs; until then the model's docs are all.
  const shown: Wiki = wiki === "project" && hasProjectDocs ? "project" : "model";
  const current = shown === "project" ? projectDocs : modelDocs;
  const store = docsStoreOf(shown).getState;

  // A model without docs of its own starts on the project docs; a deep link (`page=`) wins.
  const bothReady = modelDocs.status === "ready" && projectDocs.status === "ready";
  useEffect(() => {
    if (!bothReady || urlPageApplied) {
      return;
    }
    urlPageApplied = true;
    const { tab, page } = readScreenTab();
    const ref = tab === "docs" ? parseDocsRef(page) : null;
    if (ref?.wiki === "project" && findPage(useProjectDocsStore.getState().docs.pages, ref.id) !== null) {
      void openProjectPage(ref.id);
    } else if (
      ref?.wiki === "model" &&
      ref.id !== null &&
      (ref.model === null || ref.model === modelName) &&
      findPage(useDocsStore.getState().docs.pages, ref.id) !== null
    ) {
      void openModelPage(ref.id);
    } else if (useDocsStore.getState().docs.pages.length === 0 && useProjectDocsStore.getState().docs.pages.length > 0) {
      useDocsViewStore.getState().setWiki("project");
    } else {
      useDocsViewStore.getState().setWiki("model");
    }
  }, [bothReady, modelName]);

  // Leaving the page (reload, close) with unsaved edits asks first.
  const dirtyModel = useMemo(() => new Set(dirtyPageIds(modelDocs)), [modelDocs]);
  const dirtyProject = useMemo(() => new Set(dirtyPageIds(projectDocs)), [projectDocs]);
  const anyDirty = dirtyModel.size + dirtyProject.size;
  useEffect(() => {
    if (anyDirty === 0) {
      return;
    }
    const warn = (event: BeforeUnloadEvent): void => {
      if (isLeaveConfirmed()) {
        return;
      }
      event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [anyDirty]);

  const focusAfterToggle = useRef(false);
  const toggleMode = useCallback(() => {
    focusAfterToggle.current = true;
    const docs = useDocsStore.getState();
    docs.setMode(docs.mode === "view" ? "edit" : "view");
  }, []);
  // Ctrl+E moves the focus with the mode, so the shortcut keeps working from the keyboard.
  useEffect(() => {
    if (!focusAfterToggle.current) {
      return;
    }
    focusAfterToggle.current = false;
    const target = pageArea.current?.querySelector<HTMLElement>(mode === "view" ? ".docs-preview" : ".cm-content");
    target?.focus();
  }, [mode]);

  const saveSelected = useCallback(async () => {
    const state = docsStoreOf(shown).getState();
    if (state.selected !== null) {
      const ok = await state.save(state.selected);
      setNotice(ok ? "Saved." : null);
    }
  }, [shown]);

  const links = useMemo<LinkContext>(
    () => ({
      pageIds: allIds(current.docs.pages),
      wiki: shown,
      model,
      signalIds: manifest === null ? null : new Set(manifest.signals.map((signal) => signal.id)),
      projectPageIds: allIds(projectDocs.docs.pages),
      modelPages: modelPagesOf(index?.models ?? [], modelName === null ? {} : { [modelName]: modelDocs.docs.pages }),
    }),
    [current.docs, shown, model, manifest, projectDocs.docs, index, modelName, modelDocs.docs],
  );

  const actions = useMemo<LinkActions>(
    () => ({
      openPage: (id) => void (shown === "project" ? openProjectPage(id) : openModelPage(id)),
      openProjectPage: (id) => void openProjectPage(id),
      openModelPage: (name, id) => {
        if (name === useDocumentStore.getState().modelName) {
          void openModelPage(id);
          return;
        }
        const target = useDocumentStore.getState().project;
        if (target !== null) {
          void requestLeaveModel(modelDocsUrl(target, name, id), "model");
        }
      },
      showBlock: (target) => {
        void useDocsStore
          .getState()
          .saveAll()
          .then(() => {
            if (useDocumentStore.getState().selectNodeAt(target.path, target.nodeId)) {
              requestCenterNode(target.nodeId);
              onShowDiagram();
            } else {
              setNotice(`The block "${target.name}" is no longer in the model.`);
            }
          });
      },
      plotSignal: (id) => {
        useRunStore.getState().addSignal(id);
        requestPlotsTab();
        setNotice(`Plotting ${id}.`);
      },
      notify: setNotice,
    }),
    [onShowDiagram, shown],
  );

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>): void => {
    if (!(event.ctrlKey || event.metaKey) || event.altKey) {
      return;
    }
    const key = event.key.toLowerCase();
    if (key === "s") {
      event.preventDefault();
      void saveSelected();
    } else if (key === "e") {
      event.preventDefault();
      toggleMode();
    }
  };

  useSyncedScroll(mode === "split", pageArea, `${shown}:${current.selected ?? ""}:${mode}:${current.status}`);

  if (project === null || modelName === null) {
    return <EmptyState title="No model open" hint="Open a model to read and write its docs." />;
  }
  if (modelDocs.status === "error") {
    return (
      <div className="docs-state" role="alert" data-testid="docs-error">
        <p className="docs-state__title">The docs could not be loaded</p>
        <p>{modelDocs.error}</p>
        <button
          type="button"
          className="button"
          onClick={() => {
            useDocsStore.setState({ status: "idle" });
            void useDocsStore.getState().load(project, modelName);
          }}
        >
          Try again
        </button>
      </div>
    );
  }

  const selected = current.selected;
  const docs = current.docs;
  const page = selected === null ? null : findPage(docs.pages, selected);
  const text = selected === null ? undefined : (current.drafts[selected] ?? current.saved[selected]);
  const dirty = shown === "project" ? dirtyProject : dirtyModel;
  const isDirty = selected !== null && dirty.has(selected);
  const deletingStore = deleting === null ? null : docsStoreOf(deleting.wiki).getState();
  const deletingPage = deleting === null || deletingStore === null ? null : findPage(deletingStore.docs.pages, deleting.id);
  const crumbs = selected === null ? [] : (pathTo(docs.pages, selected) ?? []);
  const problem = current.problem ?? (shown === "model" ? projectDocs.problem : null);

  const treeHandlers = (target: Wiki) => {
    const of = docsStoreOf(target).getState;
    return {
      onSelect: (id: string) => void (target === "project" ? openProjectPage(id) : openModelPage(id)),
      onNewSibling: (after: string | null) => {
        useDocsViewStore.getState().setWiki(target);
        void of().newSibling(after);
      },
      onNewChild: (parent: string) => {
        useDocsViewStore.getState().setWiki(target);
        void of().newChild(parent);
      },
      onRename: (id: string, title: string) => void of().rename(id, title),
      onRemove: (id: string) => setDeleting({ wiki: target, id }),
      onMove: (id: string, to: string, position: "before" | "after" | "inside") => void of().move(id, to, position),
      onMoveKey: (id: string, key: string) => of().moveByKey(id, key),
    };
  };

  const addProjectDocs = (): void => {
    void useProjectDocsStore
      .getState()
      .createFirstPage()
      .then(() => {
        if (useProjectDocsStore.getState().docs.pages.length > 0) {
          useDocsViewStore.getState().setWiki("project");
        }
      });
  };

  const modelSection =
    modelDocs.docs.pages.length === 0 ? (
      <div className="docs-empty" data-testid="docs-empty">
        <EmptyState
          title={modelDocs.status === "loading" ? "Loading the docs" : "No documentation yet"}
          hint={`Write notes, equations and pictures for ${modelName}. They are saved with the model.`}
        />
        <button
          type="button"
          className="button button--primary"
          data-testid="docs-create-first"
          disabled={modelDocs.status !== "ready"}
          onClick={() => {
            useDocsViewStore.getState().setWiki("model");
            void useDocsStore.getState().createFirstPage();
          }}
        >
          Create first page
        </button>
      </div>
    ) : (
      <DocsTree
        docs={modelDocs.docs}
        selected={shown === "model" ? modelDocs.selected : null}
        dirty={dirtyModel}
        ariaLabel={hasProjectDocs ? "Pages of this model" : "Pages"}
        {...treeHandlers("model")}
      />
    );

  return (
    <div className="docs-tab" data-testid="docs-tab" data-status={modelDocs.status} data-wiki={shown} onKeyDown={onKeyDown}>
      <Group
        id="bgsim-docs"
        orientation="horizontal"
        defaultLayout={layout.defaultLayout}
        onLayoutChanged={layout.onLayoutChanged}
      >
        <Panel id="tree" defaultSize="26" minSize={160} maxSize="50" className="docs-panel" style={{ overflow: "hidden" }}>
          {hasProjectDocs ? (
            <div className="docs-sections">
              <section
                className="docs-section docs-section--project"
                data-testid="docs-section-project"
                data-open={projectOpen ? "true" : "false"}
                aria-label="Project docs"
              >
                <button
                  type="button"
                  className="docs-section__header"
                  aria-expanded={projectOpen}
                  data-testid="docs-section-project-toggle"
                  onClick={() => useDocsViewStore.getState().setProjectOpen(!projectOpen)}
                  title="The project docs: shared by every model of the project"
                >
                  <span aria-hidden="true">{projectOpen ? "▾" : "▸"}</span> Project
                  {dirtyProject.size > 0 ? <span className="docs-tree__dirty" aria-label="Unsaved changes"> ●</span> : null}
                </button>
                {projectOpen ? (
                  <div className="docs-section__body">
                    <DocsTree
                      docs={projectDocs.docs}
                      selected={shown === "project" ? projectDocs.selected : null}
                      dirty={dirtyProject}
                      testIdPrefix="project-docs"
                      ariaLabel="Project pages"
                      hint={false}
                      {...treeHandlers("project")}
                    />
                  </div>
                ) : null}
              </section>
              <section className="docs-section docs-section--model" data-testid="docs-section-model" aria-label="Docs of this model">
                <div className="docs-section__header docs-section__header--static">This model</div>
                <div className="docs-section__body docs-section__body--grow">{modelSection}</div>
              </section>
            </div>
          ) : (
            <div className="docs-sections">
              <div className="docs-section__body docs-section__body--grow">{modelSection}</div>
              {projectDocs.status === "ready" ? (
                <button
                  type="button"
                  className="docs-add-project"
                  data-testid="docs-add-project"
                  onClick={addProjectDocs}
                  title="Start the project docs: pages shared by every model of the project, stored in the project's docs/ folder"
                >
                  + Add project docs
                </button>
              ) : null}
            </div>
          )}
        </Panel>

        <Separator className="splitter" />

        <Panel id="page" defaultSize="74" minSize="30" className="docs-panel" style={{ overflow: "hidden" }}>
          <div className="docs-page" ref={pageArea}>
            <div className="docs-toolbar">
              <nav className="docs-crumbs" aria-label="Page path" data-testid="docs-crumbs">
                {hasProjectDocs ? (
                  <>
                    <button
                      type="button"
                      className="docs-crumbs__link"
                      data-testid="docs-crumbs-project"
                      onClick={() => {
                        const first = useProjectDocsStore.getState().docs.pages[0];
                        if (first !== undefined) {
                          void openProjectPage(first.id);
                        }
                      }}
                      title="Open the first page of the project docs"
                    >
                      Project docs
                    </button>
                    {shown === "model" ? (
                      <span>
                        <span aria-hidden="true"> / </span>
                        {modelName}
                      </span>
                    ) : null}
                    {crumbs.length > 0 ? <span aria-hidden="true"> / </span> : null}
                  </>
                ) : null}
                {crumbs.map((id, position) => (
                  <span key={id}>
                    {position > 0 ? <span aria-hidden="true"> / </span> : null}
                    {findPage(docs.pages, id)?.title}
                  </span>
                ))}
              </nav>
              <span className="docs-toolbar__spacer" />
              {current.unusedImages > 0 ? (
                <span className="docs-unused" data-testid="docs-unused">
                  <span data-testid="docs-unused-count">
                    {current.unusedImages} unused image{current.unusedImages === 1 ? "" : "s"}
                  </span>
                  <button
                    type="button"
                    className="button docs-toolbar__button"
                    data-testid="docs-cleanup"
                    onClick={() =>
                      void store()
                        .cleanUpImages()
                        .then((deleted) => setNotice(`Removed ${deleted.length} unused image${deleted.length === 1 ? "" : "s"}.`))
                    }
                    title="Delete the images that no page refers to"
                  >
                    Clean up
                  </button>
                </span>
              ) : null}
              <span
                className="docs-save"
                data-testid="docs-save-status"
                data-state={current.saving ? "saving" : isDirty ? "dirty" : "saved"}
              >
                {current.saving ? "Saving…" : isDirty ? "● Unsaved changes" : page === null ? "" : "Saved"}
              </span>
              <button
                type="button"
                className="button docs-toolbar__button"
                data-testid="docs-save"
                disabled={!isDirty || current.saving}
                onClick={() => void saveSelected()}
                title="Save the page (Ctrl+S)"
              >
                Save
              </button>
              <div className="docs-modes" role="group" aria-label="Page mode">
                {MODES.map((entry) => (
                  <button
                    key={entry.id}
                    type="button"
                    className="button docs-toolbar__button"
                    data-testid={`docs-mode-${entry.id}`}
                    aria-pressed={mode === entry.id}
                    disabled={page === null}
                    onClick={() => useDocsStore.getState().setMode(entry.id)}
                    title={entry.id === "split" ? "Editor and preview side by side" : `${entry.label} (Ctrl+E toggles View and Edit)`}
                  >
                    {entry.label}
                  </button>
                ))}
              </div>
            </div>

            {problem !== null ? (
              <p className="docs-banner docs-banner--error" role="alert" data-testid="docs-problem">
                {problem}{" "}
                <button
                  type="button"
                  className="docs-banner__close"
                  onClick={() => {
                    useDocsStore.getState().setProblem(null);
                    useProjectDocsStore.getState().setProblem(null);
                  }}
                >
                  Dismiss
                </button>
              </p>
            ) : null}
            {notice !== null ? (
              <p className="docs-banner" role="status" data-testid="docs-notice">
                {notice}{" "}
                <button type="button" className="docs-banner__close" onClick={() => setNotice(null)}>
                  Dismiss
                </button>
              </p>
            ) : null}

            {page === null ? (
              <div className="docs-body docs-body--empty">
                <EmptyState
                  title="No page selected"
                  hint={docs.pages.length === 0 ? "Create the first page to start." : "Select a page in the tree."}
                />
              </div>
            ) : text === undefined ? (
              <div className="docs-body docs-body--empty">
                <EmptyState title="Loading the page" hint="One moment." />
              </div>
            ) : (
              <div className="docs-body" data-mode={mode} data-testid="docs-body">
                {mode !== "view" ? (
                  <div className="docs-pane docs-pane--editor">
                    <MarkdownEditor
                      pageKey={`${project}/${shown === "project" ? ":project" : modelName}/${page.id}`}
                      value={text}
                      project={project}
                      model={shown === "project" ? null : modelName}
                      knownAssets={current.assets}
                      ariaLabel={`Markdown of ${page.title}`}
                      onChange={(next) => store().setDraft(page.id, next)}
                      onSave={() => void saveSelected()}
                      onToggleMode={toggleMode}
                      onAssetAdded={(name) => {
                        store().noteAsset(name);
                        void store().refreshAssets();
                      }}
                      onProblem={(message) => store().setProblem(message)}
                    />
                  </div>
                ) : null}
                {mode !== "edit" ? (
                  <div
                    className="docs-pane docs-preview"
                    data-testid="docs-preview"
                    role="region"
                    aria-label={`Preview of ${page.title}`}
                    tabIndex={0}
                  >
                    {text.trim() === "" ? (
                      <p className="docs-preview__empty">This page is empty. Switch to Edit to write it.</p>
                    ) : (
                      <div
                        {...{
                          [DOC_PAGE_ATTRIBUTE]: selected ?? "",
                          ...(shown === "project" ? {} : { [DOC_MODEL_ATTRIBUTE]: modelName }),
                        }}
                      >
                        <MarkdownView
                          text={text}
                          project={project}
                          model={shown === "project" ? null : modelName}
                          links={links}
                          actions={actions}
                        />
                      </div>
                    )}
                  </div>
                ) : null}
              </div>
            )}
          </div>
        </Panel>
      </Group>

      {deleting !== null && deletingPage !== null ? (
        <ConfirmDelete
          title={deletingPage.title}
          childCount={deletingPage.children.length}
          wiki={deleting.wiki}
          onChoose={(choice) => {
            const target = deleting;
            setDeleting(null);
            if (choice !== "cancel") {
              void docsStoreOf(target.wiki).getState().remove(deletingPage.id, choice);
            }
          }}
        />
      ) : null}
    </div>
  );
}
