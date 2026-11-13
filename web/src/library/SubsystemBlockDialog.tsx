/**
 * The dialog of "Save to project library" for a subsystem: the block name,
 * which parameters each instance can set, what else is written, and what is
 * not carried over. The plan is library/subsystemToBlock.ts; the save is
 * library/saveSubsystem.ts.
 */

import { useCallback, useEffect, useId, useMemo, useRef, useState, type FormEvent } from "react";

import { useDialogFocus } from "../app/useDialogFocus";
import type { ModelNode } from "../contracts/model";
import { useDocumentStore } from "../state/documentStore";
import { useCatalogStore } from "./catalogStore";
import { loadProjectLibraryInfo, type ProjectLibraryInfo } from "./projectBlocks";
import { saveSubsystemToProjectLibrary, type SaveSubsystemOutcome } from "./saveSubsystem";
import {
  planSubsystemBlock,
  subsystemBlockNameProblem,
  subsystemParameters,
  suggestedSubsystemBlockName,
} from "./subsystemToBlock";
import "../code/projectBlockDialog.css";

export interface SubsystemBlockDialogProps {
  project: string;
  node: ModelNode;
  /** Instance path of the node, e.g. `Arm/Joint1`. */
  path: string;
  onClose: () => void;
  onDone: (outcome: SaveSubsystemOutcome) => void;
}

type InfoState =
  | { status: "loading" }
  | { status: "ready"; info: ProjectLibraryInfo }
  | { status: "error"; message: string };

export function SubsystemBlockDialog({ project, node, path, onClose, onDone }: SubsystemBlockDialogProps) {
  const doc = useDocumentStore((state) => state.doc);
  const index = useCatalogStore((state) => state.index);
  const dialog = useRef<HTMLFormElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const titleId = useId();
  const nameId = useId();
  const hintId = useId();

  const [info, setInfo] = useState<InfoState>({ status: "loading" });
  const [name, setName] = useState("");
  const [touched, setTouched] = useState(false);
  const [chosen, setChosen] = useState<ReadonlySet<string>>(new Set());
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
          setInfo({ status: "error", message: cause instanceof Error ? cause.message : String(cause) });
        }
      },
    );
    return () => {
      alive = false;
    };
  }, [project]);

  useEffect(() => {
    if (info.status === "ready") {
      input.current?.focus();
      input.current?.select();
    }
  }, [info.status]);

  const taken = useMemo(() => {
    const names = new Set<string>(info.status === "ready" ? info.info.libraryNames : []);
    for (const block of index?.blocks ?? []) {
      if (block.ref.startsWith("project:")) {
        names.add(block.ref.slice("project:".length));
      }
    }
    // A library subsystem made in this session may not be in the library or the catalog yet.
    for (const name of Object.keys(doc?.definitions ?? {})) {
      names.add(name);
    }
    return [...names];
  }, [doc, index, info]);

  const parameters = useMemo(
    () => (doc === null || index === null ? [] : subsystemParameters(doc, node, index)),
    [doc, index, node],
  );

  const suggestion =
    info.status !== "ready" || index === null ? "" : suggestedSubsystemBlockName(node, taken, index);
  const shownName = touched ? name : suggestion;
  const trimmed = shownName.trim();
  const nameProblem =
    info.status === "ready" && index !== null ? subsystemBlockNameProblem(trimmed, taken, index) : null;

  const plan = useMemo(() => {
    if (doc === null || index === null || info.status !== "ready" || nameProblem !== null) {
      return null;
    }
    return planSubsystemBlock({ doc, node, path, name: trimmed, index, taken, expose: chosen });
  }, [chosen, doc, index, info.status, nameProblem, node, path, taken, trimmed]);

  const canSubmit = !busy && plan !== null && plan.problems.length === 0;

  async function submit(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (!canSubmit || plan === null || info.status !== "ready") {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onDone(
        await saveSubsystemToProjectLibrary(project, {
          nodeId: node.id,
          path,
          name: trimmed,
          plan,
          libraryDir: info.info.libraryDir,
        }),
      );
    } catch (cause) {
      setBusy(false);
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  }

  const toggle = (key: string, on: boolean): void => {
    const next = new Set(chosen);
    if (on) {
      next.add(key);
    } else {
      next.delete(key);
    }
    setChosen(next);
    setError(null);
  };

  const libraryDir = info.status === "ready" ? info.info.libraryDir : "library";
  const exposedNames = new Map((plan?.exposed ?? []).map((entry) => [entry.key, entry.name]));
  const others = (plan?.blocks ?? []).slice(0, -1);
  const selectable = parameters.filter((entry) => !entry.forced && entry.blocked === null);

  return (
    <div className="dialog-backdrop" data-testid="subsystem-block-backdrop">
      <form
        className="project-block-dialog project-block-dialog--wide"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        data-testid="subsystem-block-dialog"
        ref={dialog}
        tabIndex={-1}
        onSubmit={(event) => void submit(event)}
      >
        <h2 id={titleId} className="project-block-dialog__title">
          Save subsystem to project library
        </h2>
        <p className="project-block-dialog__text">
          {node.name} becomes a reusable block in {libraryDir}/. The block on the diagram then is
          an instance of it, keeping its name, position and connections; drag more instances
          from the library&apos;s Project category.
        </p>

        <label className="project-block-dialog__field" htmlFor={nameId}>
          Block name
        </label>
        <input
          id={nameId}
          ref={input}
          type="text"
          className="project-block-dialog__input"
          data-testid="subsystem-block-name"
          value={shownName}
          placeholder={info.status === "loading" ? "Reading the project library…" : "e.g. Actuator"}
          disabled={info.status !== "ready" || busy}
          spellCheck={false}
          autoComplete="off"
          aria-invalid={nameProblem !== null}
          aria-describedby={hintId}
          onChange={(event) => {
            setTouched(true);
            setName(event.target.value);
            setError(null);
          }}
        />
        <p
          id={hintId}
          className={`project-block-dialog__hint${nameProblem !== null ? " project-block-dialog__hint--error" : ""}`}
          data-testid="subsystem-block-name-hint"
          role={nameProblem !== null ? "alert" : undefined}
        >
          {info.status === "loading"
            ? "Reading the project library…"
            : info.status === "error"
              ? info.message
              : nameProblem !== null
                ? nameProblem
                : `Saved as ${libraryDir}/${trimmed}.jl, used as project:${trimmed}.`}
        </p>

        {parameters.length > 0 ? (
          <fieldset className="project-block-dialog__kinds" data-testid="subsystem-block-parameters">
            <legend>Parameters each instance can set</legend>
            <p className="project-block-dialog__muted">
              A ticked parameter becomes a parameter of the block, with the value shown as its
              default. The others keep their value in every instance.
              {selectable.length > 1 ? (
                <>
                  {" "}
                  <button
                    type="button"
                    className="project-block-dialog__link"
                    data-testid="subsystem-block-all"
                    disabled={busy}
                    onClick={() => {
                      setChosen(
                        chosen.size === selectable.length
                          ? new Set()
                          : new Set(selectable.map((entry) => entry.key)),
                      );
                    }}
                  >
                    {chosen.size === selectable.length ? "Untick all" : "Tick all"}
                  </button>
                </>
              ) : null}
            </p>
            <div className="project-block-dialog__list">
              {parameters.map((entry) => {
                const exposedAs = exposedNames.get(entry.key);
                return (
                  <label
                    key={entry.key}
                    className="project-block-dialog__check"
                    title={entry.blocked !== null && !entry.forced ? `Cannot be exposed: ${entry.blocked}.` : entry.description}
                  >
                    <input
                      type="checkbox"
                      data-testid={`subsystem-block-expose-${entry.key}`}
                      checked={entry.forced || chosen.has(entry.key)}
                      disabled={busy || entry.forced || entry.blocked !== null}
                      onChange={(event) => toggle(entry.key, event.target.checked)}
                    />
                    <span>
                      <code>{entry.key}</code> = {entry.value ?? entry.default}
                      {entry.unit !== null && entry.unit.length > 0 ? ` ${entry.unit}` : ""}
                      {exposedAs !== undefined ? (
                        <span className="project-block-dialog__muted"> → {exposedAs}</span>
                      ) : null}
                      {entry.forced ? (
                        <span className="project-block-dialog__muted">
                          {" "}
                          (uses a global parameter, so it is set on the instance)
                        </span>
                      ) : null}
                    </span>
                  </label>
                );
              })}
            </div>
          </fieldset>
        ) : null}

        {others.length > 0 ? (
          <p className="project-block-dialog__note" data-testid="subsystem-block-others">
            Also saved, because a library block is built from library blocks:{" "}
            {others
              .map((block) => `${block.name} (${block.origin === "inline" ? "inline block" : "subsystem"} ${block.path})`)
              .join(", ")}
            .
          </p>
        ) : null}

        {plan !== null && plan.problems.length === 0
          ? plan.notes.map((note) => (
              <p key={note} className="project-block-dialog__note" data-testid="subsystem-block-note">
                {note}
              </p>
            ))
          : null}

        {plan !== null && plan.problems.length > 0 ? (
          <div className="project-block-dialog__error" role="alert" data-testid="subsystem-block-problems">
            <p>This subsystem cannot be saved as a library block yet:</p>
            <ul>
              {plan.problems.map((problem) => (
                <li key={problem}>{problem}</li>
              ))}
            </ul>
          </div>
        ) : null}
        {error !== null ? (
          <p className="project-block-dialog__error" role="alert" data-testid="subsystem-block-error">
            {error}
          </p>
        ) : null}

        <div className="project-block-dialog__actions">
          <button
            type="button"
            className="button"
            data-testid="subsystem-block-cancel"
            disabled={busy}
            onClick={close}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="button button--primary"
            data-testid="subsystem-block-submit"
            disabled={!canSubmit}
          >
            {busy ? "Checking and saving…" : "Save to library"}
          </button>
        </div>
      </form>
    </div>
  );
}
