/**
 * The name dialog of "Save to project library" (an inline code node) and
 * "+ Library block" (a new block from a template), plan 7.7.
 *
 * The name is proposed from the source's `@block <Name>` (made free in the
 * project library) and validated as it is typed: a Julia identifier that no
 * project block uses yet, ignoring case because it is also the file name. A
 * library file must declare the block named like the file, so a different
 * name renames the `@block` header; the dialog says so. When other inline
 * nodes have the identical source, it offers to re-point them as well.
 */

import { useCallback, useEffect, useId, useMemo, useRef, useState, type FormEvent } from "react";

import { useDialogFocus } from "../app/useDialogFocus";
import { useCatalogStore } from "../library/catalogStore";
import {
  blockNameProblem,
  loadProjectLibraryInfo,
  type ProjectLibraryInfo,
  type PublishOutcome,
} from "../library/projectBlocks";
import { useDocumentStore } from "../state/documentStore";
import {
  createProjectLibraryBlock,
  findInlineNode,
  identicalInlineNodes,
  saveInlineToProjectLibrary,
  suggestedBlockName,
  templateFor,
  type NewBlockKind,
  type SaveInlineOutcome,
} from "./inlineToLibrary";
import { blockNameOf } from "./templates";
import "./projectBlockDialog.css";

export type ProjectBlockRequest =
  | { mode: "save-inline"; nodeId: string }
  | { mode: "new"; kind?: NewBlockKind };

export type ProjectBlockResult =
  | { mode: "save-inline"; outcome: SaveInlineOutcome; nodeName: string }
  | { mode: "new"; outcome: PublishOutcome; kind: NewBlockKind };

export interface ProjectBlockDialogProps {
  project: string;
  request: ProjectBlockRequest;
  onClose: () => void;
  onDone: (result: ProjectBlockResult) => void;
}

type InfoState =
  | { status: "loading" }
  | { status: "ready"; info: ProjectLibraryInfo }
  | { status: "error"; message: string };

export function ProjectBlockDialog({ project, request, onClose, onDone }: ProjectBlockDialogProps) {
  const doc = useDocumentStore((state) => state.doc);
  const catalogIndex = useCatalogStore((state) => state.index);
  const dialog = useRef<HTMLFormElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const titleId = useId();
  const nameId = useId();
  const hintId = useId();

  const [info, setInfo] = useState<InfoState>({ status: "loading" });
  const [kind, setKind] = useState<NewBlockKind>(
    request.mode === "new" ? (request.kind ?? "equation") : "equation",
  );
  const [name, setName] = useState("");
  const [touched, setTouched] = useState(false);
  const [includeIdentical, setIncludeIdentical] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const close = useCallback(() => {
    if (!busy) {
      onClose();
    }
  }, [busy, onClose]);
  useDialogFocus(true, dialog, close);

  useEffect(() => {
    let alive = true;
    loadProjectLibraryInfo(project).then(
      (loaded) => {
        if (alive) {
          setInfo({ status: "ready", info: loaded });
        }
      },
      (cause: unknown) => {
        if (alive) {
          setInfo({
            status: "error",
            message: cause instanceof Error ? cause.message : String(cause),
          });
        }
      },
    );
    return () => {
      alive = false;
    };
  }, [project]);

  // The name field is disabled until the library is read; then it takes the focus.
  useEffect(() => {
    if (info.status === "ready") {
      input.current?.focus();
      input.current?.select();
    }
  }, [info.status]);

  const inline = request.mode === "save-inline" ? findInlineNode(doc, request.nodeId) : null;
  const inlineSource =
    inline !== null && "inline" in inline.node.block ? inline.node.block.inline.source : null;
  const source = request.mode === "save-inline" ? inlineSource : templateFor(kind);
  const declared = source === null ? null : blockNameOf(source);
  const identical = useMemo(
    () =>
      request.mode === "save-inline" && inlineSource !== null
        ? identicalInlineNodes(doc, request.nodeId, inlineSource)
        : [],
    [doc, inlineSource, request],
  );

  // Taken names: the files in library/ and, in case the project listing lags,
  // the project blocks the catalog already knows.
  const taken = useMemo(() => {
    const names = new Set<string>(info.status === "ready" ? info.info.libraryNames : []);
    for (const block of catalogIndex?.blocks ?? []) {
      if (block.ref.startsWith("project:")) {
        names.add(block.ref.slice("project:".length));
      }
    }
    return [...names];
  }, [catalogIndex, info]);

  // Propose a name once the library is known, and follow the template kind
  // until the user types a name of their own.
  const suggestion =
    source === null || info.status !== "ready" ? "" : suggestedBlockName(source, taken);
  const shownName = touched ? name : suggestion;
  const trimmed = shownName.trim();
  const problem = info.status === "ready" ? blockNameProblem(trimmed, taken) : null;
  const renames = declared !== null && problem === null && trimmed !== declared;

  const sourceProblem =
    request.mode === "save-inline"
      ? inline === null
        ? "This inline block is no longer in the model."
        : declared === null
          ? "The source has no @block <Name> declaration; add one before saving it to the library."
          : null
      : null;

  const canSubmit =
    !busy && info.status === "ready" && problem === null && sourceProblem === null && source !== null;

  async function submit(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (!canSubmit || info.status !== "ready" || source === null) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (request.mode === "save-inline") {
        const nodeIds = [
          request.nodeId,
          ...(includeIdentical ? identical.map((entry) => entry.id) : []),
        ];
        const outcome = await saveInlineToProjectLibrary(project, {
          name: trimmed,
          source,
          nodeIds,
          libraryDir: info.info.libraryDir,
        });
        onDone({ mode: "save-inline", outcome, nodeName: inline?.node.name ?? request.nodeId });
      } else {
        const outcome = await createProjectLibraryBlock(project, {
          name: trimmed,
          kind,
          libraryDir: info.info.libraryDir,
        });
        onDone({ mode: "new", outcome, kind });
      }
    } catch (cause) {
      setBusy(false);
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  }

  const libraryDir = info.status === "ready" ? info.info.libraryDir : "library";
  const title = request.mode === "save-inline" ? "Save to project library" : "New library block";

  return (
    <div className="dialog-backdrop" data-testid="project-block-backdrop">
      <form
        className="project-block-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        data-testid="project-block-dialog"
        data-mode={request.mode}
        ref={dialog}
        tabIndex={-1}
        onSubmit={(event) => void submit(event)}
      >
        <h2 id={titleId} className="project-block-dialog__title">
          {title}
        </h2>
        <p className="project-block-dialog__text">
          {request.mode === "save-inline"
            ? `The source of ${inline?.node.name ?? "this inline block"} becomes a reusable block in ${libraryDir}/. The block on the diagram then uses it, keeping its name, position and values.`
            : `A new block in ${libraryDir}/, started from a template. It appears in the library's Project category, ready to drag onto the diagram.`}
        </p>

        {request.mode === "new" ? (
          <fieldset className="project-block-dialog__kinds">
            <legend>Start from</legend>
            <label>
              <input
                type="radio"
                name="project-block-kind"
                value="equation"
                checked={kind === "equation"}
                data-testid="project-block-kind-equation"
                onChange={() => setKind("equation")}
              />
              Equation block <span className="project-block-dialog__muted">(continuous, @equations)</span>
            </label>
            <label>
              <input
                type="radio"
                name="project-block-kind"
                value="discrete"
                checked={kind === "discrete"}
                data-testid="project-block-kind-discrete"
                onChange={() => setKind("discrete")}
              />
              Discrete block <span className="project-block-dialog__muted">(sampled, @discrete)</span>
            </label>
          </fieldset>
        ) : null}

        <label className="project-block-dialog__field" htmlFor={nameId}>
          Block name
        </label>
        <input
          id={nameId}
          ref={input}
          type="text"
          className="project-block-dialog__input"
          data-testid="project-block-name"
          value={shownName}
          placeholder={info.status === "loading" ? "Reading the project library…" : "e.g. FirstOrderLag"}
          disabled={info.status !== "ready" || busy}
          spellCheck={false}
          autoComplete="off"
          aria-invalid={problem !== null}
          aria-describedby={hintId}
          onChange={(event) => {
            setTouched(true);
            setName(event.target.value);
            setError(null);
          }}
        />
        <p
          id={hintId}
          className={`project-block-dialog__hint${problem !== null ? " project-block-dialog__hint--error" : ""}`}
          data-testid="project-block-name-hint"
          role={problem !== null ? "alert" : undefined}
        >
          {info.status === "loading"
            ? "Reading the project library…"
            : info.status === "error"
              ? info.message
              : problem !== null
                ? problem
                : `Saved as ${libraryDir}/${trimmed}.jl, used as project:${trimmed}.`}
        </p>
        {renames ? (
          <p className="project-block-dialog__note" data-testid="project-block-rename-note">
            The header <code>@block {declared}</code> becomes <code>@block {trimmed}</code>: a
            library block is named like its file.
          </p>
        ) : null}

        {identical.length > 0 ? (
          <label className="project-block-dialog__check" data-testid="project-block-identical">
            <input
              type="checkbox"
              checked={includeIdentical}
              data-testid="project-block-identical-check"
              onChange={(event) => setIncludeIdentical(event.target.checked)}
              disabled={busy}
            />
            Also use it for {identical.length} other inline block
            {identical.length === 1 ? "" : "s"} with the same source (
            {identical.map((entry) => entry.path).join(", ")})
          </label>
        ) : null}

        {sourceProblem !== null ? (
          <p className="project-block-dialog__error" role="alert" data-testid="project-block-source-error">
            {sourceProblem}
          </p>
        ) : null}
        {error !== null ? (
          <p className="project-block-dialog__error" role="alert" data-testid="project-block-error">
            {error}
          </p>
        ) : null}

        <div className="project-block-dialog__actions">
          <button
            type="button"
            className="button"
            data-testid="project-block-cancel"
            disabled={busy}
            onClick={close}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="button button--primary"
            data-testid="project-block-submit"
            disabled={!canSubmit}
          >
            {busy
              ? request.mode === "save-inline"
                ? "Saving…"
                : "Creating…"
              : request.mode === "save-inline"
                ? "Save to library"
                : "Create block"}
          </button>
        </div>
      </form>
    </div>
  );
}
