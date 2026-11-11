/**
 * The Code tab of plan 7.2/7.7.
 *
 * A CodeMirror 6 editor with the Julia legacy mode, `block.check` squiggles,
 * block autocomplete, the read-only stdlib banner with "Copy to project
 * library", and the inline Equation/Discrete-code nodes whose ports follow
 * their source. An inline node can be saved to the project library (it then
 * becomes an instance of the reusable block), and "+ Library block" starts a
 * new project library block from a template (code/inlineToLibrary.ts). It listens for the `bgsim:open-source` event from the
 * inspector and the diagnostics panel, and double-clicking an inline node on
 * the canvas arrives through the same request store.
 */

import { useEffect, useMemo, useState } from "react";

import { EmptyState } from "../app/EmptyState";
import { registerUnsavedWork } from "../app/leaveProject";
import type { CatalogBlock } from "../contracts/catalog";
import type { BlockCheckResult } from "../contracts/worker-rpc";
import { copyBlockToProjectLibrary } from "../inspector/copyToLibrary";
import { useCatalogStore } from "../library/catalogStore";
import { fetchCatalog } from "../library/catalogClient";
import { activeDiagram } from "../editor/subsystemPath";
import { writeProjectLibrary } from "../library/projectBlocks";
import { inlineNodePosition, useDocumentStore } from "../state/documentStore";
import { BreakpointPopover } from "./breakpointsPopover";
import { CodeEditor } from "./CodeEditor";
import {
  openTarget,
  useCodeSessionStore,
  useOpenSourceEvents,
  useResolveSourceRequests,
} from "./codeSession";
import { interfaceFromBlockCheck } from "../editor/nodeInterface";
import { publishInlineInterface } from "./inlineInterfaces";
import { projectTarget, saveInlineMessage } from "./inlineToLibrary";
import {
  ProjectBlockDialog,
  type ProjectBlockRequest,
  type ProjectBlockResult,
} from "./ProjectBlockDialog";
import { blockNameOf, DISCRETE_TEMPLATE, EQUATION_TEMPLATE } from "./templates";
import { SourceBanner, type CopyState } from "./SourceBanner";
import type { CodeTarget } from "./sources";
import { publishCodeSelection } from "../assistant/selectionStore";
import type { MappedDiagnostic } from "./lintMapping";
import "./code.css";

/** Project-library saves are debounced like the model autosave. */
export const LIBRARY_SAVE_DELAY_MS = 800;

type SaveState = "idle" | "dirty" | "saving" | "saved" | "error";

function targetKeyOf(target: CodeTarget | null): string {
  if (target === null) {
    return "none";
  }
  return target.kind === "inline" ? `inline:${target.nodeId}` : `library:${target.blockRef}`;
}

function libraryTarget(block: CatalogBlock): CodeTarget {
  return {
    kind: "library",
    sourceKind: block.ref.startsWith("project:") ? "project" : "stdlib",
    blockRef: block.ref,
    name: block.name,
    path: block.path,
    line: 1,
    col: 1,
  };
}

export function CodeTab() {
  const doc = useDocumentStore((state) => state.doc);
  const project = useDocumentStore((state) => state.project);
  const index = useCatalogStore((state) => state.index);
  const target = useCodeSessionStore((state) => state.target);
  const sessionError = useCodeSessionStore((state) => state.error);

  useResolveSourceRequests(doc, index);
  useOpenSourceEvents();

  const inlineNodes = useMemo(
    () =>
      doc === null
        ? []
        : doc.diagram.nodes.filter((node) => "inline" in node.block),
    [doc],
  );
  const blocks = useMemo(() => index?.blocks ?? [], [index]);
  const stdlibBlocks = useMemo(
    () => blocks.filter((block) => !block.ref.startsWith("project:")),
    [blocks],
  );
  const projectBlocks = useMemo(
    () => blocks.filter((block) => block.ref.startsWith("project:")),
    [blocks],
  );

  const targetKey = targetKeyOf(target);
  const inlineNode =
    target?.kind === "inline"
      ? (doc?.diagram.nodes.find((node) => node.id === target.nodeId) ?? null)
      : null;
  const libraryBlock =
    target?.kind === "library" ? (index?.blocksByRef.get(target.blockRef) ?? null) : null;

  const source =
    target?.kind === "inline"
      ? inlineNode !== null && "inline" in inlineNode.block
        ? inlineNode.block.inline.source
        : null
      : (libraryBlock?.source ?? target?.seed ?? null);

  const [draft, setDraft] = useState<{ key: string; source: string } | null>(null);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [copyState, setCopyState] = useState<CopyState>("idle");
  const [copyMessage, setCopyMessage] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  /** A new library block the notice offers to place on the diagram. */
  const [placeRef, setPlaceRef] = useState<string | null>(null);
  const [blockDialog, setBlockDialog] = useState<ProjectBlockRequest | null>(null);
  const [diagnostics, setDiagnostics] = useState<MappedDiagnostic[]>([]);
  const [checkError, setCheckError] = useState<string | null>(null);
  const [checked, setChecked] = useState(false);
  const [breakpointEdit, setBreakpointEdit] = useState<{
    id: string;
    point: { x: number; y: number };
  } | null>(null);

  // A different source starts clean: no diagnostics, draft or save status
  // from the previous block may leak into it.
  useEffect(() => {
    setDraft(null);
    setSaveState("idle");
    setSaveMessage(null);
    setCopyState("idle");
    setCopyMessage(null);
    setDiagnostics([]);
    setCheckError(null);
    setChecked(false);
    setBreakpointEdit(null);
  }, [targetKey]);

  const draftSource = draft?.key === targetKey ? draft.source : null;
  const effectiveSource = draftSource ?? source;
  const currentValue =
    target === null
      ? ""
      : target.kind === "inline"
        ? `inline:${target.nodeId}`
        : target.blockRef;

  // Save an edited project-library block, debounced like the model autosave.
  useEffect(() => {
    if (
      target === null ||
      target.kind !== "library" ||
      target.sourceKind !== "project" ||
      project === null ||
      draft === null ||
      draft.key !== targetKey
    ) {
      return;
    }
    const name = target.name;
    const text = draft.source;
    const timer = setTimeout(() => {
      setSaveState("saving");
      setSaveMessage(null);
      void writeProjectLibrary(project, name, text).then(
        async () => {
          setSaveState("saved");
          try {
            const catalog = await fetchCatalog(project);
            useCatalogStore.getState().setCatalog(catalog);
          } catch {
            // The file is written; the next catalog load picks up the interface.
            setSaveMessage("Saved; the library catalog could not be refreshed.");
          }
        },
        (error: unknown) => {
          setSaveState("error");
          setSaveMessage(error instanceof Error ? error.message : String(error));
        },
      );
    }, LIBRARY_SAVE_DELAY_MS);
    return () => clearTimeout(timer);
  }, [draft, project, target, targetKey]);

  // An edited library block that is not on disk yet asks before leaving the project.
  useEffect(() => {
    if (
      target === null ||
      target.kind !== "library" ||
      target.sourceKind !== "project" ||
      project === null ||
      draft === null ||
      draft.key !== targetKey ||
      saveState === "saved"
    ) {
      return;
    }
    const name = target.name;
    const text = draft.source;
    return registerUnsavedWork("code-tab", () => ({
      label: `the library block “${name}”`,
      save: () =>
        writeProjectLibrary(project, name, text).then(
          () => true,
          () => false,
        ),
    }));
  }, [draft, project, saveState, target, targetKey]);

  function chooseSource(value: string): void {
    if (value.startsWith("inline:")) {
      const nodeId = value.slice("inline:".length);
      openTarget({ kind: "inline", nodeId, ref: value, line: 1, col: 1 });
      return;
    }
    const block = blocks.find((entry) => entry.ref === value);
    if (block !== undefined) {
      openTarget(libraryTarget(block));
    }
  }

  function createInline(kind: "equation" | "discrete"): void {
    const id = useDocumentStore
      .getState()
      .addInlineBlock(kind, kind === "equation" ? EQUATION_TEMPLATE : DISCRETE_TEMPLATE);
    if (id === null) {
      showNotice("Open a model before adding a code block.");
      return;
    }
    openTarget({ kind: "inline", nodeId: id, ref: `inline:${id}`, line: 1, col: 1 });
  }

  function showNotice(text: string | null, place: string | null = null): void {
    setNotice(text);
    setPlaceRef(place);
  }

  function handleBlockDone(result: ProjectBlockResult): void {
    setBlockDialog(null);
    if (result.mode === "save-inline") {
      // A re-pointed node already switched this tab to the library block
      // (saveInlineToProjectLibrary); otherwise the inline node stays open.
      showNotice(saveInlineMessage(result.outcome, result.nodeName));
      return;
    }
    const { outcome } = result;
    openTarget(projectTarget(outcome));
    if (outcome.ref !== null) {
      showNotice(
        `Created ${outcome.file}. ${outcome.name} is in the library's Project category: drag it onto the diagram.`,
        useDocumentStore.getState().doc === null ? null : outcome.ref,
      );
    } else if (outcome.catalogError !== null) {
      showNotice(
        `Created ${outcome.file}, but the catalog could not be refreshed (${outcome.catalogError}). Reopen the project to see ${outcome.name} in the library.`,
      );
    } else {
      showNotice(
        `Created ${outcome.file}. The catalog does not list project:${outcome.name} yet; the file is editable here and appears in the library's Project category once the worker publishes it.`,
      );
    }
  }

  /** "Place on diagram": add the new library block in the next free slot of the open diagram. */
  function placeOnDiagram(ref: string): void {
    const block = index?.blocksByRef.get(ref);
    const store = useDocumentStore.getState();
    const diagram = store.doc === null ? null : activeDiagram(store.doc, store.activePath);
    if (block === undefined || diagram === null) {
      showNotice("Open a model to place the block.");
      return;
    }
    const id = store.addBlock(block, inlineNodePosition(diagram.nodes));
    if (id === null) {
      showNotice("The block could not be placed on the diagram.");
      return;
    }
    const placed = useDocumentStore.getState().doc;
    const name =
      placed === null
        ? block.name
        : (activeDiagram(placed, store.activePath)?.nodes.find((node) => node.id === id)?.name ??
          block.name);
    showNotice(`Placed ${name} (${ref}) on the diagram.`);
  }

  function handleChange(next: string): void {
    if (target === null) {
      return;
    }
    setChecked(false);
    if (target.kind === "inline") {
      const result = useDocumentStore
        .getState()
        .setInlineSource(target.nodeId, next, { coalesce: true });
      if (!result.ok && result.error !== undefined) {
        setCheckError(result.error);
      }
      return;
    }
    if (target.sourceKind === "project") {
      setDraft({ key: targetKey, source: next });
      setSaveState("dirty");
    }
  }

  function handleCheck(text: string, result: BlockCheckResult): void {
    if (target === null) {
      return;
    }
    setChecked(true);
    if (target.kind !== "inline") {
      return;
    }
    const iface =
      result.interface === null || result.interface === undefined
        ? null
        : interfaceFromBlockCheck(
            result.interface,
            blockNameOf(text) ?? inlineNode?.name ?? "Inline block",
            text,
          );
    publishInlineInterface(target.nodeId, text, iface);
  }

  async function handleCopy(): Promise<void> {
    if (project === null || target?.kind !== "library" || target.sourceKind !== "stdlib") {
      return;
    }
    if (libraryBlock === null) {
      setCopyState("error");
      setCopyMessage("This block is no longer in the catalog; reload the library.");
      return;
    }
    setCopyState("working");
    setCopyMessage(null);
    try {
      const outcome = await copyBlockToProjectLibrary(project, libraryBlock);
      if (outcome.catalog !== null) {
        useCatalogStore.getState().setCatalog(outcome.catalog);
      }
      setCopyState("done");
      setCopyMessage(
        outcome.ref === null
          ? `Copied to ${outcome.file}; the worker has not published it yet.`
          : `Copied to ${outcome.file}.`,
      );
      showNotice(
        outcome.ref === null
          ? `Copied to ${outcome.file}. The worker has not published project:${outcome.name} yet; the file is editable here.`
          : `Copied to ${outcome.file} and re-pointed.`,
      );
      openTarget({
        kind: "library",
        sourceKind: "project",
        blockRef: outcome.ref ?? `project:${outcome.name}`,
        name: outcome.name,
        path: outcome.file,
        line: 1,
        col: 1,
        seed: outcome.source,
      });
    } catch (error) {
      setCopyState("error");
      setCopyMessage(error instanceof Error ? error.message : String(error));
    }
  }

  const readOnly = target?.kind === "library" && target.sourceKind === "stdlib";
  return (
    <div
      className="code-tab"
      data-testid="code-tab"
      data-node-id={target?.kind === "inline" ? target.nodeId : ""}
    >
      <div className="code-toolbar">
        <span className="code-toolbar__label">Source</span>
        <select
          className="code-toolbar__select"
          data-testid="code-source-select"
          value={currentValue}
          onChange={(event) => chooseSource(event.target.value)}
          aria-label="Open a block source"
        >
          <option value="">Choose a source…</option>
          {inlineNodes.length > 0 ? (
            <optgroup label="Inline blocks">
              {inlineNodes.map((node) => (
                <option key={node.id} value={`inline:${node.id}`}>
                  {node.name} (inline)
                </option>
              ))}
            </optgroup>
          ) : null}
          {projectBlocks.length > 0 ? (
            <optgroup label="Project library">
              {projectBlocks.map((block) => (
                <option key={block.ref} value={block.ref}>
                  {block.name}
                </option>
              ))}
            </optgroup>
          ) : null}
          {target?.kind === "library" &&
          target.sourceKind === "project" &&
          !projectBlocks.some((block) => block.ref === target.blockRef) ? (
            <optgroup label="Project library">
              <option value={target.blockRef}>{target.name}</option>
            </optgroup>
          ) : null}
          <optgroup label="Standard library">
            {stdlibBlocks.map((block) => (
              <option key={block.ref} value={block.ref}>
                {block.group} / {block.name}
              </option>
            ))}
          </optgroup>
        </select>
        <span className="code-toolbar__spacer" />
        <button
          type="button"
          className="button code-toolbar__button"
          data-testid="code-new-equation"
          onClick={() => createInline("equation")}
          disabled={doc === null}
          title="Add an Equation code node to the diagram"
        >
          + Equation
        </button>
        <button
          type="button"
          className="button code-toolbar__button"
          data-testid="code-new-discrete"
          onClick={() => createInline("discrete")}
          disabled={doc === null}
          title="Add a Discrete code node to the diagram"
        >
          + Discrete
        </button>
        <button
          type="button"
          className="button code-toolbar__button"
          data-testid="code-new-library-block"
          onClick={() => setBlockDialog({ mode: "new" })}
          disabled={project === null}
          title={
            project === null
              ? "Open a project first"
              : "Create a reusable equation or discrete block in the project library (library/<Name>.jl)"
          }
        >
          + Library block
        </button>
      </div>

      {notice !== null ? (
        <p className="code-notice" role="status" data-testid="code-notice">
          {notice}
          {placeRef !== null ? (
            <button
              type="button"
              className="button code-notice__action"
              data-testid="code-place-on-diagram"
              onClick={() => placeOnDiagram(placeRef)}
            >
              Place on diagram
            </button>
          ) : null}
        </p>
      ) : null}

      {blockDialog !== null && project !== null ? (
        <ProjectBlockDialog
          project={project}
          request={blockDialog}
          onClose={() => setBlockDialog(null)}
          onDone={handleBlockDone}
        />
      ) : null}

      {sessionError !== null ? (
        <div className="code-state" role="alert" data-testid="code-error">
          <p className="code-state__title">The source could not be opened</p>
          <p className="code-state__text">{sessionError}</p>
          <button
            type="button"
            className="button"
            data-testid="code-close"
            onClick={() => useCodeSessionStore.getState().close()}
          >
            Close
          </button>
        </div>
      ) : target === null ? (
        <div className="code-empty" data-testid="code-empty">
          <EmptyState
            title="No source open"
            hint="Select a block and choose “Open source” to read and edit its code here, create an inline Equation or Discrete code node, or start a reusable block in the project library."
          />
          <div className="code-empty__actions">
            <button
              type="button"
              className="button"
              data-testid="code-empty-new-equation"
              onClick={() => createInline("equation")}
              disabled={doc === null}
            >
              New equation block
            </button>
            <button
              type="button"
              className="button"
              data-testid="code-empty-new-discrete"
              onClick={() => createInline("discrete")}
              disabled={doc === null}
            >
              New discrete code block
            </button>
            <button
              type="button"
              className="button"
              data-testid="code-empty-new-library-block"
              onClick={() => setBlockDialog({ mode: "new" })}
              disabled={project === null}
            >
              New library block
            </button>
          </div>
        </div>
      ) : effectiveSource === null ? (
        <div className="code-state" role="alert" data-testid="code-missing-source">
          <p className="code-state__title">This source is no longer available</p>
          <p className="code-state__text">
            The block may have been deleted, or it is not in the open project library.
          </p>
          <button
            type="button"
            className="button"
            data-testid="code-close"
            onClick={() => useCodeSessionStore.getState().close()}
          >
            Close
          </button>
        </div>
      ) : (
        <>
          <div className="code-source-head" data-testid="code-open-source">
            <span className="code-source-head__name">
              {target.kind === "inline" ? (inlineNode?.name ?? target.ref) : target.name}
            </span>
            <code className="code-source-head__ref">
              {target.kind === "inline" ? target.ref : target.blockRef}
            </code>
            {target.kind === "inline" ? (
              <span className="code-source-head__hint">inline · saved with the model</span>
            ) : (
              <span className="code-source-head__hint">
                {target.sourceKind === "stdlib" ? "read-only" : "project library"}
              </span>
            )}
            <span className="code-toolbar__spacer" />
            {target.kind === "inline" ? (
              <button
                type="button"
                className="button code-toolbar__button"
                data-testid="code-save-to-library"
                disabled={project === null || inlineNode === null}
                onClick={() => setBlockDialog({ mode: "save-inline", nodeId: target.nodeId })}
                title={
                  project === null
                    ? "Open a project first"
                    : "Make this code a reusable block in library/<Name>.jl; this node then uses it"
                }
              >
                Save to project library
              </button>
            ) : null}
            {target.kind === "library" && target.sourceKind === "project" ? (
              <span
                className="code-save"
                data-testid="code-save-status"
                data-state={saveState === "error" ? "error" : saveState}
                title={saveMessage ?? "Saved to the project library"}
              >
                {saveState === "saving"
                  ? "Saving…"
                  : saveState === "dirty"
                    ? "Unsaved changes"
                    : saveState === "error"
                      ? "Save failed"
                      : "Saved"}
              </span>
            ) : null}
            <button
              type="button"
              className="icon-button"
              data-testid="code-close"
              onClick={() => useCodeSessionStore.getState().close()}
              aria-label="Close the source"
              title="Close the source"
            >
              ×
            </button>
          </div>

          {target.kind === "library" ? (
            <SourceBanner
              sourceKind={target.sourceKind}
              name={target.name}
              path={target.path}
              project={project}
              copyState={copyState}
              copyMessage={copyMessage}
              onCopy={() => void handleCopy()}
            />
          ) : null}

          {saveMessage !== null ? (
            <p
              className="code-notice code-notice--error"
              role={saveState === "error" ? "alert" : "status"}
              data-testid="code-save-message"
            >
              {saveMessage}
            </p>
          ) : null}

          <div className="code-editor-wrap">
            <CodeEditor
              targetKey={targetKey}
              source={effectiveSource}
              readOnly={readOnly}
              checkRef={target.kind === "inline" ? `inline:${target.nodeId}` : target.blockRef}
              line={target.line}
              col={target.col}
              onChange={handleChange}
              onSelection={(text, fromLine, toLine) =>
                publishCodeSelection(
                  target.kind === "inline" ? (inlineNode?.name ?? target.nodeId) : target.blockRef,
                  text,
                  fromLine,
                  toLine,
                )
              }
              onCheck={handleCheck}
              onDiagnostics={(items, error) => {
                setDiagnostics(items);
                setCheckError(error);
                setChecked(true);
              }}
              onUndo={
                target.kind === "inline"
                  ? () => useDocumentStore.getState().undo()
                  : undefined
              }
              onRedo={
                target.kind === "inline"
                  ? () => useDocumentStore.getState().redo()
                  : undefined
              }
              onFocus={
                target.kind === "inline"
                  ? () =>
                      useDocumentStore
                        .getState()
                        .beginGesture(`inline-source:${target.nodeId}`)
                  : undefined
              }
              onBlur={() => useDocumentStore.getState().endGesture()}
              onEditBreakpoint={(id, point) => setBreakpointEdit({ id, point })}
            />
            {breakpointEdit !== null ? (
              <BreakpointPopover
                id={breakpointEdit.id}
                point={breakpointEdit.point}
                onClose={() => setBreakpointEdit(null)}
              />
            ) : null}
          </div>

          <div
            className="code-diagnostics"
            data-testid="code-diagnostics"
            data-count={diagnostics.length}
            aria-live="polite"
          >
            {checkError !== null ? (
              <p className="code-diagnostic code-diagnostic--request" role="alert" data-testid="code-check-error">
                {checkError}
              </p>
            ) : diagnostics.length === 0 ? (
              <p className="code-diagnostic code-diagnostic--ok" data-testid="code-no-diagnostics">
                {checked ? "No problems." : "Checking…"}
              </p>
            ) : (
              diagnostics.map((entry, index) => (
                <div
                  key={`${entry.code}:${entry.from}:${index}`}
                  className={`code-diagnostic code-diagnostic--${entry.severity}`}
                  data-testid={`code-diagnostic-${index}`}
                  data-code={entry.code}
                  data-severity={entry.severity}
                >
                  <span className="code-diagnostic__code">{entry.code}</span>
                  <span className="code-diagnostic__message">{entry.detail}</span>
                  {entry.hint !== null ? (
                    <span className="code-diagnostic__hint">{entry.hint}</span>
                  ) : null}
                  <span className="code-diagnostic__where">
                    {entry.contract.source?.range.line ?? 1}:
                    {entry.contract.source?.range.col ?? 1}
                  </span>
                </div>
              ))
            )}
          </div>
        </>
      )}
    </div>
  );
}
