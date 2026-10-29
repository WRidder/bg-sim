/**
 * The Docs tab (W5.6): a Markdown wiki for the open model. Left: the page tree. Right: the
 * selected page in View, Edit or Split mode. The docs are stored next to the model file
 * (`models/<model>.docs/`) and travel with it.
 */

import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { Group, Panel, Separator } from "react-resizable-panels";

import { EmptyState } from "../app/EmptyState";
import { requestPlotsTab } from "../app/dockBus";
import { useDialogFocus } from "../app/useDialogFocus";
import { usePersistedPanelSizes } from "../state/layout";
import { useRunStore } from "../plot/runStore";
import { useDocumentStore } from "../state/documentStore";
import { DocsTree } from "./DocsTree";
import { MarkdownEditor } from "./MarkdownEditor";
import { MarkdownView, type LinkActions } from "./MarkdownView";
import { dirtyPageIds, useDocsStore, type DocsMode } from "./docsStore";
import { allIds, findPage, pathTo } from "./pageTree";
import type { LinkContext } from "./docsLinks";
import { useSyncedScroll } from "./useSyncedScroll";
import "./docs.css";

export interface DocsTabProps {
  /** Switch the centre area to the Diagram tab (block links). */
  onShowDiagram: () => void;
}

const MODES: readonly { id: DocsMode; label: string }[] = [
  { id: "view", label: "View" },
  { id: "edit", label: "Edit" },
  { id: "split", label: "Split" },
];

function ConfirmDelete({
  title,
  childCount,
  onChoose,
}: {
  title: string;
  childCount: number;
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
          <p className="docs-dialog__text">The page text is removed from the model&apos;s docs.</p>
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

  const status = useDocsStore((state) => state.status);
  const error = useDocsStore((state) => state.error);
  const docs = useDocsStore((state) => state.docs);
  const selected = useDocsStore((state) => state.selected);
  const mode = useDocsStore((state) => state.mode);
  const saved = useDocsStore((state) => state.saved);
  const drafts = useDocsStore((state) => state.drafts);
  const saving = useDocsStore((state) => state.saving);
  const problem = useDocsStore((state) => state.problem);
  const assets = useDocsStore((state) => state.assets);
  const unusedImages = useDocsStore((state) => state.unusedImages);

  const layout = usePersistedPanelSizes("docs", { tree: 26, page: 74 });
  const [notice, setNotice] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const pageArea = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (project !== null && modelName !== null) {
      void useDocsStore.getState().load(project, modelName);
    }
  }, [project, modelName]);

  // Leaving the page (reload, close) with unsaved edits asks first.
  const dirty = useMemo(() => new Set(dirtyPageIds({ saved, drafts })), [saved, drafts]);
  useEffect(() => {
    if (dirty.size === 0) {
      return;
    }
    const warn = (event: BeforeUnloadEvent): void => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty.size]);

  const setMode = useDocsStore((state) => state.setMode);
  const focusAfterToggle = useRef(false);
  const toggleMode = useCallback(() => {
    focusAfterToggle.current = true;
    setMode(useDocsStore.getState().mode === "view" ? "edit" : "view");
  }, [setMode]);
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
    const id = useDocsStore.getState().selected;
    if (id !== null) {
      const ok = await useDocsStore.getState().save(id);
      setNotice(ok ? "Saved." : null);
    }
  }, []);

  const links = useMemo<LinkContext>(
    () => ({
      pageIds: allIds(docs.pages),
      model,
      signalIds: manifest === null ? null : new Set(manifest.signals.map((signal) => signal.id)),
    }),
    [docs, model, manifest],
  );

  const actions = useMemo<LinkActions>(
    () => ({
      openPage: (id) => void useDocsStore.getState().select(id),
      showBlock: (target) => {
        void useDocsStore
          .getState()
          .saveAll()
          .then(() => {
            if (useDocumentStore.getState().selectNodeAt(target.path, target.nodeId)) {
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
    [onShowDiagram],
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

  useSyncedScroll(mode === "split", pageArea, `${selected ?? ""}:${mode}:${status}`);

  if (project === null || modelName === null) {
    return <EmptyState title="No model open" hint="Open a model to read and write its docs." />;
  }
  if (status === "error") {
    return (
      <div className="docs-state" role="alert" data-testid="docs-error">
        <p className="docs-state__title">The docs could not be loaded</p>
        <p>{error}</p>
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

  const store = useDocsStore.getState;
  const page = selected === null ? null : findPage(docs.pages, selected);
  const text = selected === null ? undefined : (drafts[selected] ?? saved[selected]);
  const isDirty = selected !== null && dirty.has(selected);
  const deletingPage = deleting === null ? null : findPage(docs.pages, deleting);
  const crumbs = selected === null ? [] : (pathTo(docs.pages, selected) ?? []);

  const requestRemove = (id: string): void => setDeleting(id);

  return (
    <div className="docs-tab" data-testid="docs-tab" data-status={status} onKeyDown={onKeyDown}>
      <Group
        id="bgsim-docs"
        orientation="horizontal"
        defaultLayout={layout.defaultLayout}
        onLayoutChanged={layout.onLayoutChanged}
      >
        <Panel id="tree" defaultSize="26" minSize={160} maxSize="50" className="docs-panel" style={{ overflow: "hidden" }}>
          {docs.pages.length === 0 ? (
            <div className="docs-empty" data-testid="docs-empty">
              <EmptyState
                title={status === "loading" ? "Loading the docs" : "No documentation yet"}
                hint={`Write notes, equations and pictures for ${modelName}. They are saved with the model.`}
              />
              <button
                type="button"
                className="button button--primary"
                data-testid="docs-create-first"
                disabled={status !== "ready"}
                onClick={() => void store().createFirstPage()}
              >
                Create first page
              </button>
            </div>
          ) : (
            <DocsTree
              docs={docs}
              selected={selected}
              dirty={dirty}
              onSelect={(id) => void store().select(id)}
              onNewSibling={(after) => void store().newSibling(after)}
              onNewChild={(parent) => void store().newChild(parent)}
              onRename={(id, title) => void store().rename(id, title)}
              onRemove={requestRemove}
              onMove={(id, target, position) => void store().move(id, target, position)}
              onMoveKey={(id, key) => store().moveByKey(id, key)}
            />
          )}
        </Panel>

        <Separator className="splitter" />

        <Panel id="page" defaultSize="74" minSize="30" className="docs-panel" style={{ overflow: "hidden" }}>
          <div className="docs-page" ref={pageArea}>
            <div className="docs-toolbar">
              <nav className="docs-crumbs" aria-label="Page path" data-testid="docs-crumbs">
                {crumbs.map((id, index) => (
                  <span key={id}>
                    {index > 0 ? <span aria-hidden="true"> / </span> : null}
                    {findPage(docs.pages, id)?.title}
                  </span>
                ))}
              </nav>
              <span className="docs-toolbar__spacer" />
              {unusedImages > 0 ? (
                <span className="docs-unused" data-testid="docs-unused">
                  <span data-testid="docs-unused-count">{unusedImages} unused image{unusedImages === 1 ? "" : "s"}</span>
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
                data-state={saving ? "saving" : isDirty ? "dirty" : "saved"}
              >
                {saving ? "Saving…" : isDirty ? "● Unsaved changes" : page === null ? "" : "Saved"}
              </span>
              <button
                type="button"
                className="button docs-toolbar__button"
                data-testid="docs-save"
                disabled={!isDirty || saving}
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
                    onClick={() => store().setMode(entry.id)}
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
                <button type="button" className="docs-banner__close" onClick={() => store().setProblem(null)}>
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
                      pageKey={`${project}/${modelName}/${page.id}`}
                      value={text}
                      project={project}
                      model={modelName}
                      knownAssets={assets}
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
                      <MarkdownView text={text} project={project} model={modelName} links={links} actions={actions} />
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
          onChoose={(choice) => {
            setDeleting(null);
            if (choice !== "cancel") {
              void store().remove(deletingPage.id, choice);
            }
          }}
        />
      ) : null}
    </div>
  );
}
